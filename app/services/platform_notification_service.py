"""Copy announcements and once-per-deadline 24-hour Telegram warnings."""
from datetime import date, datetime, time, timedelta, timezone
import json
import logging
import os
import sqlite3
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.db.transactions import write_transaction
from app.integrations.telegram_client import TelegramClient
from app.repositories.platform_notification_repo import PlatformNotificationRepository
from app.services.poll_service import build_poll_announcement_message

logger = logging.getLogger(__name__)


def normalize_voting_deadline(value, *, local_zone=None, now=None):
    if value is None or value == '':
        return None
    if not isinstance(value,str):
        raise ValueError('Deadline must be a future ISO datetime with timezone')
    parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        if local_zone is None:
            raise ValueError('Deadline must include a timezone')
        naive = parsed
        parsed = parsed.replace(tzinfo=local_zone)
        if parsed.astimezone(timezone.utc).astimezone(local_zone).replace(tzinfo=None) != naive:
            raise ValueError('Invalid local deadline')
    parsed = parsed.astimezone(timezone.utc)
    if parsed <= (now or datetime.now(timezone.utc)):
        raise ValueError('Deadline must be in the future')
    return parsed.replace(tzinfo=None).isoformat()


def app_timezone(settings):
    try:
        return ZoneInfo(settings.get('timezone') or 'Europe/Madrid')
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('Europe/Madrid')


def deadline_instant(kind, value, settings):
    if kind == 'group_purchase':
        # A date remains open throughout that local calendar day, including DST days.
        return datetime.combine(date.fromisoformat(value) + timedelta(days=1), time.min, app_timezone(settings)).astimezone(timezone.utc)
    parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def queue_copy(conn, kind, item_id):
    PlatformNotificationRepository(conn).queue(f'copy:{kind}:{item_id}', kind, item_id)


def _link(settings, kind, item_id):
    path = {'proposal': f'/proposal/{item_id}', 'poll': f'/polls#poll-{item_id}', 'group_purchase': f'/group-purchases#purchase-{item_id}'}[kind]
    return (settings.get('url') or '').rstrip('/') + path


def _announcement(repo, kind, item, settings):
    title = item['question' if kind == 'poll' else 'title']
    link = _link(settings,kind,item['id'])
    if kind == 'poll':
        return build_poll_announcement_message(title,json.loads(item['options_json']),item['closes_at'],item['allow_multiple']) + '\n' + link
    if kind == 'proposal':
        description = item['description'] or ''
        excerpt = description[:200] + ('…' if len(description)>200 else '')
        deadline = f"\n⏰ Vote by: {item['voting_deadline']} UTC" if item['voting_deadline'] else ''
        return f"*{title}*\n\n🆕 New proposal\nBy: {repo.creator(item['created_by'])}\nAmount: €{item['amount']:.2f}{deadline}\n\n{excerpt}\n\n{item['url'] or ''}\n🔗 {link}"
    lines = [f'🛒 New group purchase: {title}',f"By: {repo.creator(item['created_by'])}", '']
    lines += [f"• {row['name']}: €{row['unit_price']:.2f}" for row in repo.components(item['id'])]
    if item['deadline']: lines.append(f"📅 Deadline: {item['deadline']}")
    if item['payment_method']: lines.append(f"💳 Payment: {item['payment_method']}")
    costs = repo.costs(item['id'])
    if costs: lines.append('➕ Shared costs: ' + ', '.join(f"{row['label']}: €{row['amount']:.2f}" for row in costs))
    if item['url']: lines.append(f"🔗 Product: {item['url']}")
    lines.append('👉 ' + link)
    return '\n'.join(lines)


def deliver_pending(conn, *, now=None, event_key=None):
    token, chat = os.getenv('TELEGRAM_BOT_TOKEN',''), os.getenv('TELEGRAM_CHAT_ID','')
    if not token or not chat:
        return
    now = now or datetime.now(timezone.utc)
    repo = PlatformNotificationRepository(conn)
    for event in repo.pending(event_key):
        with write_transaction(conn):
            if not repo.claim(event['event_key']): continue
        # Claim before networking: concurrent workers and retries cannot resend.
        # An ambiguous transport failure is recorded, never automatically replayed.
        try:
            settings = repo.settings()
            item = repo.item(event['kind'], event['item_id'])
            status = 'skipped'
            if item is not None:
                kind = event['kind']
                warning = event['deadline'] is not None
                valid = True
                if warning:
                    field = {'proposal':'voting_deadline','poll':'closes_at','group_purchase':'deadline'}[kind]
                    valid = item['status'] == ('active' if kind == 'proposal' else 'open') and item[field] == event['deadline']
                    valid = valid and now < deadline_instant(kind,event['deadline'],settings) <= now + timedelta(hours=24)
                if valid:
                    client = TelegramClient(token,chat,os.getenv('TELEGRAM_THREAD_ID',''))
                    if warning:
                        closes = deadline_instant(kind,event['deadline'],settings).astimezone(app_timezone(settings)).strftime('%Y-%m-%d %H:%M %Z')
                        title = item['question' if kind == 'poll' else 'title']
                        period = 'Joining' if kind == 'group_purchase' else 'Voting'
                        message = f"⚠️ {period} deadline within 24 hours\n{title[:500]}\n⏰ {closes}\n{_link(settings,kind,item['id'])}"
                        sent = client.send_message(message)
                    else:
                        message = _announcement(repo,kind,item,settings)
                        if len(message)>3800:
                            message = message[:3500] + '\n…\n' + _link(settings,kind,item['id'])
                        if kind == 'poll' and settings.get('poll_vote_mode','both') != 'web_only':
                            sent = client.send_poll_message(message,item['id'],json.loads(item['options_json']))
                        elif kind == 'proposal' and settings.get('proposal_vote_mode','both') != 'web_only':
                            sent = client.send_proposal_vote_message(message,item['id'])
                        else:
                            sent = client.send_message(message)
                    status = 'sent' if sent else 'failed'
        except Exception:
            # Notification failure must never roll back or misreport a committed copy.
            status = 'failed'
        with write_transaction(conn): repo.finish(event['event_key'],status)
        logger.log(logging.WARNING if status == 'failed' else logging.INFO,
                   'event=platform_notification key=%s status=%s',event['event_key'],status)


def run_notifications(db_path, *, now=None):
    now = now or datetime.now(timezone.utc)
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        repo = PlatformNotificationRepository(conn)
        settings = repo.settings()
        with write_transaction(conn):
            for row in repo.deadlines():
                try:
                    deadline = deadline_instant(row['kind'],row['deadline'],settings)
                except (ValueError, TypeError, OverflowError):
                    continue
                if now < deadline <= now + timedelta(hours=24):
                    key = f"deadline:{row['kind']}:{row['id']}:{deadline.isoformat()}"
                    repo.queue(key,row['kind'],row['id'],row['deadline'])
        deliver_pending(conn,now=now)
