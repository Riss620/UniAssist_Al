import hashlib, hmac, secrets, os
from datetime import datetime, timedelta, timezone
from fastapi import Header, HTTPException
from .db import connect

SECRET = os.getenv('SECRET_KEY', 'dev-only-change-this-secret')

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 240000)
    return salt.hex() + '$' + digest.hex()

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split('$', 1)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt_hex), 240000)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False

def issue_session(user_id: int) -> str:
    token = secrets.token_urlsafe(36)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    with connect() as c:
        c.execute('INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)', (token_hash,user_id,expires))
    return token

def current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Please sign in')
    token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with connect() as c:
        row = c.execute('''SELECT u.id,u.name,u.email,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?''', (token_hash, datetime.now(timezone.utc).isoformat())).fetchone()
    if not row: raise HTTPException(401, 'Session expired. Please sign in again.')
    return dict(row)

def revoke_session(authorization: str | None):
    if authorization and authorization.startswith('Bearer '):
        token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
        with connect() as c: c.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash,))
