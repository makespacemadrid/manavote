import hashlib
import secrets
from datetime import datetime
from werkzeug.security import check_password_hash, generate_password_hash

from app.repositories.member_repo import MemberRepository


def verify_and_migrate_password(stored_hash, password):
    if stored_hash.startswith("pbkdf2:sha256:") or stored_hash.startswith("scrypt:"):
        return check_password_hash(stored_hash, password), None
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()
    if stored_hash == legacy_hash:
        return True, generate_password_hash(password)
    return False, None


def authenticate(connection, username, password):
    repo = MemberRepository(connection)
    member = repo.find_login(username)
    if member is None:
        return None
    valid, migrated_hash = verify_and_migrate_password(member["password_hash"], password)
    if migrated_hash:
        repo.set_password_hash(member["id"], migrated_hash)
        connection.commit()
    return member if valid else None


def register_member(connection, username, password, is_admin=False):
    repo = MemberRepository(connection)
    if repo.get_by_username(username):
        return None
    member_id = repo.create(username, generate_password_hash(password), int(bool(is_admin)))
    connection.commit()
    return member_id


def change_password(connection, member_id, new_password, confirm_password):
    if not new_password or not confirm_password:
        return "All fields are required"
    if new_password != confirm_password:
        return "New passwords do not match"
    if len(new_password) < 4:
        return "Password must be at least 4 characters"
    MemberRepository(connection).set_password_hash(member_id, generate_password_hash(new_password))
    connection.commit()
    return None


def add_member_email(connection, member_id, email):
    repo = MemberRepository(connection)
    member = repo.get_by_id(member_id)
    if member and (member["email"] or "").strip():
        return "Your email address cannot be changed once it has been added."
    email = email.strip().lower()
    if not email or "@" not in email:
        return "Enter a valid email address."
    if repo.email_in_use(email, member_id):
        return "That email address is already in use."
    repo.add_email(member_id, email)
    connection.commit()
    return None


def upsert_oidc_member(connection, claims):
    subject = str(claims["sub"])
    preferred = (claims.get("preferred_username") or claims.get("email") or f"oidc-{subject[:12]}").strip()
    email = (claims.get("email") or "").strip() or None
    display_name = (claims.get("name") or "").strip() or None
    telegram_username = (claims.get("telegram_handle") or "").strip().lstrip("@") or None
    telegram_user_id = claims.get("telegram_id") or None
    groups = claims.get("groups") if isinstance(claims.get("groups"), list) else []
    is_admin = int("admins" in groups)
    repo = MemberRepository(connection)
    member = repo.find_oidc_identity(subject, email)
    if member:
        linked_at = (datetime.now().isoformat()
                     if telegram_user_id is not None and telegram_user_id != member["telegram_user_id"] else None)
        repo.update_oidc_identity(member["id"], subject, email, display_name, is_admin,
                                  telegram_username, telegram_user_id, linked_at)
        member_id = member["id"]
    else:
        username, suffix = preferred, 1
        while repo.get_by_username(username):
            suffix += 1
            username = f"{preferred}-{suffix}"
        member_id = repo.create_oidc_identity(
            username, generate_password_hash(secrets.token_urlsafe(32)), is_admin,
            telegram_username, telegram_user_id,
            datetime.now().isoformat() if telegram_user_id is not None else None,
            subject, email, display_name,
        )
    connection.commit()
    return repo.get_by_id(member_id)
