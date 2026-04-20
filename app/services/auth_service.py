import hashlib
from werkzeug.security import check_password_hash, generate_password_hash


def verify_and_migrate_password(stored_hash, password):
    if stored_hash.startswith("pbkdf2:sha256:") or stored_hash.startswith("scrypt:"):
        return check_password_hash(stored_hash, password), None
    legacy_hash = hashlib.sha256(password.encode()).hexdigest()
    if stored_hash == legacy_hash:
        return True, generate_password_hash(password)
    return False, None
