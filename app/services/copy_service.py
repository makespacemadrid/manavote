"""Create fresh items from reusable source content in a single transaction."""
from datetime import date, datetime, timezone
import logging
from pathlib import Path
import secrets
import shutil
import hashlib
import json
import re

from app.db.transactions import write_transaction
from app.repositories.copy_repo import CopyRepository
from app.repositories.group_purchase_repo import GroupPurchaseRepository
from app.services import group_purchase_service
from app.services.platform_notification_service import queue_copy, deliver_pending


class CopyNotFound(ValueError):
    pass


class CopyConflict(ValueError):
    pass


def copy_preview(conn, *, kind, source_id):
    if kind not in CopyRepository.TABLES:
        raise CopyNotFound('Source item not found')
    source = CopyRepository(conn).source(kind, source_id)
    if source is None:
        raise CopyNotFound('Source item not found')
    return {'title': source['question' if kind == 'poll' else 'title'],
            'status': source['status']}


def copy_item(conn, *, kind, source_id, created_by, upload_folder, label=None, deadline=None, idempotency_key=None):
    if kind not in CopyRepository.TABLES:
        raise ValueError('Unknown copy kind')
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in (source_id, created_by)):
        raise ValueError('source_id and created_by must be positive integers')
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise ValueError('The new title/question must be a non-empty string')
    if deadline is not None and not isinstance(deadline, str):
        raise ValueError('Invalid deadline')
    if idempotency_key is not None and (not isinstance(idempotency_key, str) or re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', idempotency_key) is None):
        raise ValueError('idempotency_key must be 1..128 letters, digits, dots, underscores, colons or hyphens')
    fingerprint = hashlib.sha256(json.dumps([kind, source_id, created_by, label.strip() if label else None, deadline], ensure_ascii=False).encode()).hexdigest()
    request_key = 'explicit:' + hashlib.sha256(idempotency_key.encode()).hexdigest() if idempotency_key else 'auto:' + fingerprint
    new_image = None
    committed = False
    warnings = []
    repo = CopyRepository(conn)
    try:
        with write_transaction(conn):
            previous = repo.prior_request(created_by, request_key)
            if previous is not None:
                if previous['fingerprint'] != fingerprint:
                    raise CopyConflict('This request key was already used with different copy arguments')
                result = json.loads(previous['result_json'])
                if repo.source(kind, result[kind + '_id']) is None:
                    raise CopyConflict('The original copy was deleted; use a new request key')
                result['replayed'] = True
                return result
            if deadline is not None:
                if not isinstance(deadline, str):
                    raise ValueError('Invalid deadline')
                try:
                    if kind in {'poll', 'proposal'}:
                        parsed = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
                        if parsed.tzinfo is None:
                            raise ValueError('Voting deadline must include a timezone')
                        if parsed <= datetime.now(timezone.utc):
                            raise ValueError('Voting deadline must be in the future')
                        # Existing poll scheduling compares UTC-naive ISO timestamps.
                        deadline = parsed.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
                    elif date.fromisoformat(deadline) < date.today():
                        raise ValueError('Order deadline must not be in the past')
                except (TypeError, ValueError) as exc:
                    raise ValueError('Supply a future timezone-qualified voting deadline or current/future order date') from exc
            if not repo.member_exists(created_by):
                raise CopyNotFound('Creator member not found')
            source = repo.source(kind, source_id)
            if source is None:
                raise CopyNotFound('Source item not found')
            title = label.strip() if label is not None else source['question' if kind == 'poll' else 'title']
            if kind == 'poll' and not 5 <= len(title) <= 200:
                raise ValueError('Poll question must be 5..200 characters')
            if kind == 'group_purchase' and not 1 <= len(title) <= 150:
                raise ValueError('Group-purchase title must be 1..150 characters')
            if kind != 'poll' and source['image_filename']:
                original = Path(upload_folder) / source['image_filename']
                root = Path(upload_folder).resolve()
                if original.resolve().parent != root or original.suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
                    raise ValueError('Source image is not a supported local upload')
                if original.is_file():
                    new_image = secrets.token_hex(16) + original.suffix.lower()
                    shutil.copyfile(original, root / new_image)
                else:
                    warnings.append('Source image was unavailable; copied without an image.')
            if kind == 'proposal':
                new_id = repo.proposal(source, created_by, title, new_image, deadline)
            elif kind == 'poll':
                new_id = repo.poll(source, created_by, title, deadline)
            else:
                groups = GroupPurchaseRepository(conn)
                components = [(row['name'], row['unit_price']) for row in groups.components(source_id)]
                costs = [(row['label'], row['amount']) for row in groups.shared_costs(source_id)]
                # Reuse creation validation, but keep this use case's transaction owner.
                error = group_purchase_service.validate_creation(title=title, components=components,
                    deadline=deadline, product_url=source['url'], payment_method=source['payment_method'] or '',
                    component_error=None, shared_cost_error=None)
                if error:
                    raise ValueError(error)
                new_id = groups.create(title, source['description'], deadline, source['url'], new_image, source['payment_method'], created_by)
                groups.set_join_limit(new_id, source['join_member_limit'])
                groups.set_amount_cap(new_id, source['cap_at_125'])
                groups.insert_components(new_id, components)
                groups.insert_shared_costs(new_id, costs)
                group_purchase_service.enforce_purchase_limits(groups, new_id)
            result = {'success': True, 'source_id': source_id, kind + '_id': new_id, 'warnings': warnings, 'replayed': False}
            repo.save_request(created_by, request_key, fingerprint, json.dumps(result, ensure_ascii=False))
            queue_copy(conn, kind, new_id)
        committed = True
    finally:
        if new_image and not committed:
            (Path(upload_folder) / new_image).unlink(missing_ok=True)
    logging.getLogger(__name__).info('event=item_copied kind=%s source_id=%s new_id=%s actor_id=%s', kind, source_id, new_id, created_by)
    try:
        deliver_pending(conn,event_key=f'copy:{kind}:{new_id}')
    except Exception:
        logging.getLogger(__name__).warning('event=copy_notification_deferred kind=%s new_id=%s', kind, new_id)
    return result
