"""Pink Diamond backend API.

Python (FastAPI) service that owns everything the browser must not be trusted
with: accounts, subscriptions, the Pink Mode entitlement, credit accounting,
and the OpenRouter proxy that holds the real API key.

Run:  uvicorn main:app --reload --port 4400
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

import database as db

PLAN_PRICES_CENTS = {"go": 1199, "plus": 2299, "pro": 3399, "max": 12199}
PLAN_CREDITS = {"go": 2000, "plus": 3500, "pro": 8300, "max": 16660}
PINK_MODE_PRICE_CENTS = 1800          # +$18/mo add-on (see unfiltered.js HEAT.price)
PINK_MODE_CREDIT_MULTIPLIER = 2       # 2 credits per message, per the site spec

# Uncensored routing only ever happens after the server-side entitlement check.
UNFILTERED_MODELS = [
    "cognitivecomputations/dolphin-mistral-24b-venice-edition",
    "sao10k/l3.3-euryale-70b",
]
DEFAULT_MODEL = "openai/gpt-oss-120b"

# Model switching (update spec): subscribers may pick any of these OpenRouter
# models; accounts without an active plan never reach OpenRouter at all and are
# answered by the built-in house model instead. Mirrors
# native/rust/pink-access (the executable spec) and the picker in app.js.
HOUSE_MODEL = "pink-diamond/lite"
OPENROUTER_MODELS = {
    "openai/gpt-oss-120b": "GPT-OSS 120B",
    "anthropic/claude-sonnet-5.5": "Claude Sonnet 5.5",
    "openai/gpt-5.5": "GPT-5.5",
    "google/gemini-3.5-flash": "Gemini 3.5 Flash",
    "x-ai/grok-4.7": "Grok 4.7",
    "deepseek/deepseek-v4-pro": "DeepSeek V4 Pro",
    "meta-llama/llama-4-maverick": "Llama 4 Maverick",
    "mistralai/mistral-large": "Mistral Large",
}

app = FastAPI(title="Pink Diamond API")
_secret = os.environ.get("PD_SESSION_SECRET", "dev-secret-change-me")


# ---------------------------------------------------------------- sessions ---

SESSION_WINDOW_SECONDS = 7 * 24 * 3600


def _sign(user_id: int) -> str:
    # Same weekly bucket as _verify — signing with the raw timestamp made every
    # token fail verification.
    msg = f"pd:{user_id}:{int(time.time()) // SESSION_WINDOW_SECONDS}".encode()
    return f"{user_id}.{hmac.new(_secret.encode(), msg, hashlib.sha256).hexdigest()}"


def _verify(token: str) -> int:
    try:
        user_id, sig = token.split(".", 1)
        msg = f"pd:{user_id}:{int(time.time()) // SESSION_WINDOW_SECONDS}".encode()
        expected = hmac.new(_secret.encode(), msg, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError
        return int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(401, "Invalid or expired session")


def current_user(authorization: str = Header("")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not signed in")
    user_id = _verify(authorization[7:])
    user = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if user is None:
        raise HTTPException(401, "Account not found")
    return dict(user)


def optional_user(authorization: str = Header("")) -> dict | None:
    try:
        return current_user(authorization)
    except HTTPException:
        return None


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"


def _pink_active(user_id: int) -> bool:
    """The entitlement check. Always called server-side before unfiltered chat."""
    row = db.one(
        "SELECT 1 FROM subscriptions WHERE user_id=? AND kind='pink_mode'"
        " AND active=1 AND (renews_at IS NULL OR renews_at > datetime('now'))",
        (user_id,),
    )
    return row is not None


def _subscribed(user: dict) -> bool:
    """An active paid plan — the gate for every OpenRouter model."""
    if user.get("plan", "free") == "free":
        return False
    rows = db.all(
        "SELECT renews_at FROM subscriptions WHERE user_id=? AND kind='plan' AND active=1",
        (user["id"],),
    )
    now = datetime.now(timezone.utc)
    for row in rows:
        renews = row["renews_at"]
        if renews is None:
            return True
        when = datetime.fromisoformat(renews)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when > now:
            return True
    return False


def _resolve_model(requested: str | None, subscribed: bool, unfiltered: bool) -> str:
    """Pick the model a chat request may use. Raises when the plan forbids it."""
    if not subscribed:
        if requested and requested != HOUSE_MODEL:
            raise HTTPException(402, "Switching models requires an active subscription")
        raise HTTPException(402, "OpenRouter models require an active subscription")
    if unfiltered:
        return UNFILTERED_MODELS[0]
    if not requested or requested == HOUSE_MODEL:
        return DEFAULT_MODEL
    if requested not in OPENROUTER_MODELS:
        raise HTTPException(400, "Unknown model")
    return requested


# ---------------------------------------------------------------- accounts ---

class RegisterBody(BaseModel):
    username: str
    email: str
    password: str


@app.post("/api/register")
def register(body: RegisterBody):
    api_key = secrets.token_urlsafe(32)
    try:
        user_id = db.run(
            "INSERT INTO users (username, email, password_hash, api_key_hash) VALUES (?,?,?,?)",
            (
                body.username.strip(),
                body.email.strip().lower(),
                _hash_password(body.password),
                hashlib.sha256(api_key.encode()).hexdigest(),
            ),
        )
    except Exception:
        raise HTTPException(409, "Username or email already registered")
    db.run(
        "INSERT INTO credit_timeline (user_id, delta, reason) VALUES (?, 0, 'account created')",
        (user_id,),
    )
    # api_key is never returned or stored in plaintext.
    return {"token": _sign(user_id), "note": "Your API key was generated and stored securely."}


class LoginBody(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: LoginBody):
    user = db.one("SELECT * FROM users WHERE username=? OR email=?", (body.username, body.username.lower()))
    if user is None or "$" not in user["password_hash"]:
        raise HTTPException(401, "Invalid credentials")
    salt_hex, digest_hex = user["password_hash"].split("$", 1)
    if not hmac.compare_digest(_hash_password(body.password, bytes.fromhex(salt_hex)), user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    return {"token": _sign(user["id"])}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    created = datetime.fromisoformat(user["created_at"])
    if created.tzinfo is None:                  # SQLite datetime('now') is naive UTC
        created = created.replace(tzinfo=timezone.utc)
    longevity = (datetime.now(timezone.utc) - created).days
    credits = user["credits"]
    balance = user["api_balance"]
    return {
        "username": user["username"],
        "created_at": user["created_at"],
        "account_longevity_days": longevity,
        "plan": user["plan"],
        "pink_mode": bool(_pink_active(user["id"])),
        "subscribed": _subscribed(user),
        "credits": credits,
        "credits_used": user["credits_used"],
        "api_balance": round(balance, 2),
        "low_balance": balance <= 0.5,          # spec: notice when low or zero
        "low_credits": credits <= 25,
        "theme": user["theme"],
    }


# ----------------------------------------------------------- subscriptions ---

def require_billing() -> None:
    """No real payment provider is wired yet, so nothing that grants a plan,
    credits, or Pink Mode may run in production — otherwise anyone could
    subscribe for free and spend the OpenRouter key. Set PD_DEMO_BILLING=1 for
    staging; replace this dependency with the Stripe webhook before launch."""
    if os.environ.get("PD_DEMO_BILLING") != "1":
        raise HTTPException(501, "Billing is not live yet")


class SubscribeBody(BaseModel):
    plan: str  # port | plus | pro | max


@app.post("/api/subscribe")
def subscribe(body: SubscribeBody, user: dict = Depends(current_user), _: None = Depends(require_billing)):
    if body.plan not in PLAN_CREDITS:
        raise HTTPException(400, "Unknown plan")
    price_cents = PLAN_PRICES_CENTS[body.plan]
    funded = price_cents / 200            # 50% of every payment funds the user's key
    grant = PLAN_CREDITS[body.plan]
    db.run(
        "UPDATE users SET plan=?, credits=credits+?, api_balance=api_balance+? WHERE id=?",
        (body.plan, grant, funded / 100, user["id"]),
    )
    db.run(
        "INSERT INTO subscriptions (user_id, kind, tier, amount_cents, renews_at) VALUES (?,?,?,?,?)",
        (user["id"], "plan", body.plan, price_cents, (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()),
    )
    db.run(
        "INSERT INTO credit_timeline (user_id, delta, reason) VALUES (?,?,?)",
        (user["id"], grant, f"plan payment — ${(funded / 100):.2f} funds the API key"),
    )
    return {
        "plan": body.plan,
        "monthly_credits": PLAN_CREDITS[body.plan],
        "api_key_funding": {"amount": round(funded / 100, 2), "share": "50%"},
    }


class TopUpBody(BaseModel):
    dollars: float  # pay-as-you-go top-up


@app.post("/api/topup")
def topup(body: TopUpBody, user: dict = Depends(current_user), _: None = Depends(require_billing)):
    if body.dollars <= 0:
        raise HTTPException(400, "Top-up must be positive")
    grant = body.dollars * 10
    db.run(
        "UPDATE users SET credits=credits+?, credits_used=credits_used+?, api_balance=api_balance+? WHERE id=?",
        (grant, grant, body.dollars / 2, user["id"]),
    )
    db.run(
        "INSERT INTO credit_timeline (user_id, delta, reason) VALUES (?,?,?)",
        (user["id"], grant, f"top-up ${body.dollars:.2f} (50% funds API key)"),
    )
    return {"credits_added": grant, "api_key_funding": round(body.dollars / 2, 2)}


@app.get("/api/theme")
def get_theme(user: dict = Depends(current_user)):
    return {"theme": user["theme"]}


class ThemeBody(BaseModel):
    theme: str


@app.put("/api/theme")
def set_theme(body: ThemeBody, user: dict = Depends(current_user)):
    valid = {"neon-rose", "porcelain", "candlelight", "coral-dusk", "dark", "obsidian",
             "amethyst", "emerald", "sapphire", "uviolet"}
    if body.theme not in valid:
        raise HTTPException(400, "Unknown theme")
    db.run("UPDATE users SET theme=? WHERE id=?", (body.theme, user["id"]))
    return {"theme": body.theme}  # restored by /api/me on every sign-in


@app.post("/api/subscribe/pink-mode")
def subscribe_pink_mode(user: dict = Depends(current_user), _: None = Depends(require_billing)):
    if user["plan"] == "free":
        raise HTTPException(402, "Pink Mode requires a paid plan")
    db.run(
        "INSERT INTO subscriptions (user_id, kind, amount_cents, renews_at) VALUES (?,?,?,?)",
        (user["id"], "pink_mode", PINK_MODE_PRICE_CENTS, (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()),
    )
    return {"pink_mode": True, "price_monthly_cents": PINK_MODE_PRICE_CENTS}


@app.post("/api/pink-mode")
def toggle_pink_mode(body: dict, user: dict = Depends(current_user)):
    """The toggle. Off is always allowed; on requires the paid entitlement."""
    if body.get("enabled") and not _pink_active(user["id"]):
        raise HTTPException(402, "Pink Mode subscription required")
    return {"pink_mode": body.get("enabled", False) and _pink_active(user["id"])}


# -------------------------------------------------------------------- chat ---

@app.get("/api/models")
def list_models(user: dict | None = Depends(optional_user)):
    """The chat model picker. Locked entries are visible but not selectable."""
    subscribed = bool(user) and _subscribed(user)
    models = [{"id": HOUSE_MODEL, "label": "Pink Diamond Lite", "provider": "house", "locked": False}]
    models += [
        {"id": mid, "label": label, "provider": "openrouter", "locked": not subscribed}
        for mid, label in OPENROUTER_MODELS.items()
    ]
    return {"subscribed": subscribed, "default": DEFAULT_MODEL if subscribed else HOUSE_MODEL, "models": models}


_or_status_cache: dict = {}


@app.get("/api/openrouter/status")
def openrouter_status():
    """Is the OpenRouter key connected, and can it actually serve chat?

    Never returns the key. A management (provisioning) key authenticates but is
    refused by the completions endpoint, so it is reported as not usable.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {"configured": False, "inference_ready": False,
                "detail": "OPENROUTER_API_KEY is not set in this environment"}
    cached = _or_status_cache.get("value")
    if cached and time.time() - _or_status_cache.get("at", 0) < 300:
        return cached
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError:
        return {"configured": True, "inference_ready": False, "detail": "OpenRouter unreachable"}
    if resp.status_code != 200:
        result = {"configured": True, "inference_ready": False, "detail": f"Key rejected ({resp.status_code})"}
    else:
        data = resp.json().get("data", {})
        management = bool(data.get("is_management_key") or data.get("is_provisioning_key"))
        result = {
            "configured": True,
            "inference_ready": not management,
            "key_type": "management" if management else "inference",
            "label": data.get("label"),
            "limit_remaining": data.get("limit_remaining"),
            "detail": "Management keys cannot call chat completions — set an inference key"
            if management else "Connected",
        }
    _or_status_cache.update(value=result, at=time.time())
    return result


class ChatBody(BaseModel):
    message: str
    model: str | None = None


@app.post("/api/chat")
def chat(body: ChatBody, user: dict = Depends(current_user)):
    unfiltered = _pink_active(user["id"])          # server decides, not the browser
    model = _resolve_model(body.model, _subscribed(user), unfiltered)
    cost = PINK_MODE_CREDIT_MULTIPLIER if unfiltered else 1
    if user["credits"] < cost:
        raise HTTPException(402, "Out of credits")

    system = (
        "You are Pink Diamond, a web-hosted AI agent."
        + (
            " Pink Mode is active for this account: blunt tone, adult creative work between"
            " consenting adults and dark fiction are allowed."
            " Hard limits that no payment removes: no sexual content involving minors,"
            " no sexual content involving real people, no genuine weapons/drug-synthesis/malware"
            " instructions, no targeted harassment of real people. State these limits plainly if asked."
        )
        if unfiltered
        else "You are Pink Diamond, a web-hosted AI agent. Keep responses helpful and coherent."
    )
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(503, "OPENROUTER_API_KEY is not configured")

    with httpx.Client(timeout=60) as client:
        resp = client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": body.message},
                ],
            },
        )
    if resp.status_code != 200:
        raise HTTPException(502, "Model provider error")

    reply = resp.json()["choices"][0]["message"]["content"]
    db.run("UPDATE users SET credits=credits-?, credits_used=credits_used+? WHERE id=?", (cost, cost, user["id"]))
    db.run(
        "INSERT INTO credit_timeline (user_id, delta, reason) VALUES (?,?,?)",
        (user["id"], -cost, "chat (pink mode)" if unfiltered else "chat"),
    )
    db.run(
        "INSERT INTO chat_messages (user_id, role, content, unfiltered) VALUES (?,?,?,?)",
        (user["id"], "user", body.message, int(unfiltered)),
    )
    db.run(
        "INSERT INTO chat_messages (user_id, role, content, unfiltered) VALUES (?,?,?,?)",
        (user["id"], "agent", reply, int(unfiltered)),
    )
    # Low / zero balance notices are first-class product features (spec §4).
    updated = db.one("SELECT credits, api_balance FROM users WHERE id=?", (user["id"],))
    notice = None
    if updated["credits"] <= 0:
        notice = "You are out of credits — generation pauses until you top up or upgrade."
    elif updated["credits"] <= 25:
        notice = f"Low credits: {updated['credits']:.0f} remaining."
    if updated["api_balance"] <= 0.5 and notice is None:
        notice = "API key balance is low — half of every payment funds it; top up anytime."
    return {"reply": reply, "unfiltered": unfiltered, "credits_charged": cost, "model": model,
            "credits_left": updated["credits"], "api_balance": round(updated["api_balance"], 2), "notice": notice}
