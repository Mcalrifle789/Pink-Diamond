"""Sessions and passwords.

Tokens are `<user id>.<issued at>.<HMAC>`, valid for seven days from issue.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from fastapi import Header, HTTPException

import database as db
from config import SESSION_SECRET_DEFAULT, env

SESSION_TTL_SECONDS = 7 * 24 * 3600


def _secret() -> bytes:
    return (env("PD_SESSION_SECRET") or SESSION_SECRET_DEFAULT).encode()


def _mac(user_id: int, issued: int) -> str:
    return hmac.new(_secret(), f"pd:{user_id}:{issued}".encode(), hashlib.sha256).hexdigest()


def sign(user_id: int) -> str:
    issued = int(time.time())
    return f"{user_id}.{issued}.{_mac(user_id, issued)}"


def verify(token: str) -> int:
    try:
        uid_s, issued_s, sig = token.split(".", 2)
        user_id, issued = int(uid_s), int(issued_s)
    except (ValueError, TypeError):
        raise HTTPException(401, "Invalid or expired session")
    if not hmac.compare_digest(sig, _mac(user_id, issued)):
        raise HTTPException(401, "Invalid or expired session")
    if not 0 <= time.time() - issued <= SESSION_TTL_SECONDS:
        raise HTTPException(401, "Invalid or expired session")
    return user_id


def current_user(authorization: str = Header("")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not signed in")
    user = db.one("SELECT * FROM users WHERE id = ?", (verify(authorization[7:]),))
    if user is None:
        raise HTTPException(401, "Account not found")
    return dict(user)


def optional_user(authorization: str = Header("")) -> dict | None:
    try:
        return current_user(authorization)
    except HTTPException:
        return None


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"


def password_matches(password: str, stored: str) -> bool:
    if "$" not in stored:
        return False
    salt_hex, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt_hex)), stored)
