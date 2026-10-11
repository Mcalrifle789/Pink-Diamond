"""Per-user OpenRouter keys, minted with the OpenRouter management key.

Every paying user gets their own inference key. Its credit limit always equals
`users.funded_cents` (half of each subscription payment plus every top-up),
so OpenRouter itself stops spending at the user's balance and its
`limit_remaining` is exactly what the user has left — the number the site
shows as Pink Credits.

The ledger in our database is the source of truth; `sync_limit` pushes it to
OpenRouter idempotently (it sets the absolute limit, never increments), so a
failed or repeated call can't lose or double money. Raw keys are stored
encrypted (Fernet, PD_KEY_ENCRYPTION_SECRET) and never sent to the browser.
"""

from __future__ import annotations

import base64
import hashlib

import httpx

import database as db
import payments_core as core
from config import env

API = "https://openrouter.ai/api/v1"


class KeyError_(RuntimeError):
    pass


def configured() -> bool:
    return bool(env("OPENROUTER_MANAGEMENT_KEY") and env("PD_KEY_ENCRYPTION_SECRET"))


def _fernet():
    from cryptography.fernet import Fernet

    secret = env("PD_KEY_ENCRYPTION_SECRET")
    if not secret:
        raise KeyError_("PD_KEY_ENCRYPTION_SECRET is not set")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def encrypt(raw_key: str) -> str:
    return _fernet().encrypt(raw_key.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def _mgmt(method: str, path: str, **kwargs) -> dict:
    key = env("OPENROUTER_MANAGEMENT_KEY")
    if not key:
        raise KeyError_("OPENROUTER_MANAGEMENT_KEY is not set")
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.request(method, API + path, headers={"Authorization": f"Bearer {key}"}, **kwargs)
    except httpx.HTTPError as exc:
        raise KeyError_(f"OpenRouter unreachable: {exc.__class__.__name__}") from exc
    if resp.status_code >= 300:
        raise KeyError_(f"OpenRouter management API returned {resp.status_code}")
    return resp.json()


def sync_limit(user_id: int) -> None:
    """Make the user's OpenRouter key exist with limit == funded_cents."""
    with db.transaction() as conn:
        user = conn.execute(
            "SELECT id, or_key_hash, funded_cents FROM users WHERE id=? FOR UPDATE", (user_id,)
        ).fetchone()
        if user is None:
            raise KeyError_("unknown user")
        limit = round(int(user["funded_cents"]) / 100, 2)
        if user["or_key_hash"]:
            _mgmt("PATCH", f"/keys/{user['or_key_hash']}", json={"limit": limit})
            return
        if limit <= 0:
            return            # nothing paid yet, so no key yet
        created = _mgmt("POST", "/keys", json={"name": f"pink-diamond-user-{user_id}", "limit": limit})
        raw, key_hash = created.get("key"), (created.get("data") or {}).get("hash")
        if not raw or not key_hash:
            raise KeyError_("OpenRouter did not return a key")
        conn.execute("UPDATE users SET or_key_hash=?, or_key_enc=? WHERE id=?", (key_hash, encrypt(raw), user_id))


def user_key(user: dict) -> str | None:
    """The user's own inference key (decrypted), if they have one."""
    if not user.get("or_key_enc"):
        return None
    return decrypt(user["or_key_enc"])


def balance(user: dict) -> dict:
    """What the user can still spend, from OpenRouter when reachable."""
    funded = int(user.get("funded_cents") or 0)
    result = {
        "funded_cents": funded,
        "source": "ledger",
        "remaining_cents": funded,
        "used_cents": 0,
    }
    if user.get("or_key_hash") and configured():
        try:
            data = _mgmt("GET", f"/keys/{user['or_key_hash']}").get("data") or {}
            limit = data.get("limit")
            if limit is None or round(float(limit) * 100) != funded:
                sync_limit(user["id"])                        # heal a missed sync
            used = round(float(data.get("usage") or 0) * 100)
            result.update(source="openrouter", used_cents=used, remaining_cents=max(0, funded - used))
        except KeyError_:
            result["source"] = "ledger (OpenRouter unreachable)"
    result["credits"] = core.cents_to_credits(result["remaining_cents"])
    result["dollars"] = round(result["remaining_cents"] / 100, 2)
    result["low"] = result["remaining_cents"] <= 50
    return result
