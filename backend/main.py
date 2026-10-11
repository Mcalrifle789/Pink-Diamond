"""Pink Diamond backend API.

Python (FastAPI) service that owns everything the browser must not be trusted
with: accounts and the Terms acceptance, subscriptions and the Uncensored
Mode entitlement, payments (payments.py, on the C/C++/Zig core), each user's
OpenRouter key, and the chat proxy.

Run:  uvicorn main:app --reload --port 4400
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

import database as db
import openrouter_keys as ork
import payments
import payments_core as core
from auth import current_user, hash_password, optional_user, password_matches, sign
from config import PLAN_CREDITS, PLAN_PRICES_CENTS, TERMS_VERSION, UNCENSORED_PRICE_CENTS, env
from entitlement import current_subscription, pink_active, subscribed

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
app.include_router(payments.router)


def _resolve_model(requested: str | None, is_subscribed: bool, unfiltered: bool) -> str:
    """Pick the model a chat request may use. Raises when the plan forbids it."""
    if not is_subscribed:
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
    accept_terms: bool = False
    terms_version: str | None = None


@app.post("/api/register")
def register(body: RegisterBody):
    # Spec §5: the Terms & Agreement (privacy policy + creation guidelines)
    # must be read and accepted before an account exists.
    if not body.accept_terms or body.terms_version != TERMS_VERSION:
        raise HTTPException(428, "Accept the current Terms & Agreement to create an account")
    if len(body.password) < 8:
        raise HTTPException(400, "Use at least 8 characters for your password")
    api_key = secrets.token_urlsafe(32)
    try:
        user_id = db.insert(
            "INSERT INTO users (username, email, password_hash, api_key_hash, terms_version, terms_accepted_at)"
            " VALUES (?,?,?,?,?,?)",
            (
                body.username.strip(),
                body.email.strip().lower(),
                hash_password(body.password),
                hashlib.sha256(api_key.encode()).hexdigest(),
                TERMS_VERSION,
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
    except Exception:
        raise HTTPException(409, "Username or email already registered")
    db.run("INSERT INTO credit_timeline (user_id, delta, reason) VALUES (?, 0, 'account created')", (user_id,))
    # api_key is never returned or stored in plaintext.
    return {"token": sign(user_id), "note": "Your API key was generated and stored securely."}


class LoginBody(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: LoginBody):
    user = db.one("SELECT * FROM users WHERE username=? OR email=?", (body.username, body.username.lower()))
    if user is None or not password_matches(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    return {"token": sign(user["id"]), "terms_current": user["terms_version"] == TERMS_VERSION}


class TermsBody(BaseModel):
    terms_version: str


@app.post("/api/terms/accept")
def accept_terms(body: TermsBody, user: dict = Depends(current_user)):
    """Re-acceptance after the Terms change (required before the next purchase)."""
    if body.terms_version != TERMS_VERSION:
        raise HTTPException(409, "Those are not the current Terms")
    db.run("UPDATE users SET terms_version=?, terms_accepted_at=? WHERE id=?",
           (TERMS_VERSION, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), user["id"]))
    return {"terms_version": TERMS_VERSION}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    created = datetime.fromisoformat(user["created_at"])
    if created.tzinfo is None:                  # stored as naive UTC
        created = created.replace(tzinfo=timezone.utc)
    sub = current_subscription(user["id"])
    funded = int(user["funded_cents"] or 0)
    return {
        "username": user["username"],
        "email": user["email"],
        "created_at": user["created_at"],
        "account_longevity_days": (datetime.now(timezone.utc) - created).days,
        "plan": sub["tier"] if sub else "free",
        "subscribed": sub is not None,
        "interval": sub["billing_interval"] if sub else None,
        "renews_at": sub["period_end"] if sub else None,
        "subscription_status": sub["status"] if sub else None,
        "pink_mode": bool(sub and sub["uncensored"]),
        "funded_credits": core.cents_to_credits(funded),
        "terms_current": user["terms_version"] == TERMS_VERSION,
        "theme": user["theme"],
    }


# ------------------------------------------------- demo billing (staging) ---

def require_demo_billing() -> None:
    """Staging-only shortcuts that grant plans without payment. Real money goes
    through payments.py (Stripe); these stay closed unless PD_DEMO_BILLING=1 and
    are never available once real payments are live."""
    if env("PD_DEMO_BILLING") != "1" or payments.live():
        raise HTTPException(501, "Demo billing is disabled")


class SubscribeBody(BaseModel):
    plan: str                # go | plus | pro | max
    interval: str = "month"
    uncensored: bool = False


@app.post("/api/subscribe")
def subscribe(body: SubscribeBody, user: dict = Depends(current_user), _: None = Depends(require_demo_billing)):
    if body.plan not in PLAN_CREDITS or body.interval not in ("month", "year"):
        raise HTTPException(400, "Unknown plan")
    price = core.plan_price_cents(PLAN_PRICES_CENTS[body.plan], body.interval)
    if body.uncensored:
        price += core.plan_price_cents(UNCENSORED_PRICE_CENTS, body.interval)
    period = (365 if body.interval == "year" else 30) * 86400
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO subscriptions (user_id, kind, tier, billing_interval, uncensored, amount_cents,"
            " status, period_end) VALUES (?, 'plan', ?, ?, ?, ?, 'active', ?)",
            (user["id"], body.plan, body.interval, int(body.uncensored), price, int(time.time()) + period),
        )
        conn.execute("UPDATE users SET plan=? WHERE id=?", (body.plan, user["id"]))
        payments.credit_payment(conn, user_id=user["id"], kind="subscription", amount_cents=price,
                                funded_cents=core.split_customer_cents(price),
                                stripe_ref=f"demo:{user['id']}:{secrets.token_hex(6)}", payment_intent=None)
    return {"plan": body.plan, "interval": body.interval,
            "funded_credits": core.cents_to_credits(core.split_customer_cents(price)), "share": "50%"}


class TopUpBody(BaseModel):
    amount_cents: int


@app.post("/api/topup")
def topup(body: TopUpBody, user: dict = Depends(current_user), _: None = Depends(require_demo_billing)):
    if not core.topup_valid(body.amount_cents):
        raise HTTPException(400, "Top-ups are between $5 and $1,000")
    with db.transaction() as conn:
        payments.credit_payment(conn, user_id=user["id"], kind="topup", amount_cents=body.amount_cents,
                                funded_cents=body.amount_cents,
                                stripe_ref=f"demo:{user['id']}:{secrets.token_hex(6)}", payment_intent=None)
    return {"credits_added": core.cents_to_credits(body.amount_cents)}


# ------------------------------------------------------------------ theme ---

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


@app.post("/api/pink-mode")
def toggle_pink_mode(body: dict, user: dict = Depends(current_user)):
    """The toggle. Off is always allowed; on requires the paid entitlement."""
    if body.get("enabled") and not pink_active(user["id"]):
        raise HTTPException(402, "Uncensored Mode add-on required")
    return {"pink_mode": bool(body.get("enabled")) and pink_active(user["id"])}


# -------------------------------------------------------------------- chat ---

@app.get("/api/models")
def list_models(user: dict | None = Depends(optional_user)):
    """The chat model picker. Locked entries are visible but not selectable."""
    is_subscribed = bool(user) and subscribed(user)
    models = [{"id": HOUSE_MODEL, "label": "Pink Diamond Lite", "provider": "house", "locked": False}]
    models += [
        {"id": mid, "label": label, "provider": "openrouter", "locked": not is_subscribed}
        for mid, label in OPENROUTER_MODELS.items()
    ]
    return {"subscribed": is_subscribed, "default": DEFAULT_MODEL if is_subscribed else HOUSE_MODEL,
            "models": models}


_or_status_cache: dict = {}


def _key_info(api_key: str) -> dict:
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError:
        return {"ok": False, "detail": "OpenRouter unreachable"}
    if resp.status_code != 200:
        return {"ok": False, "detail": f"Key rejected ({resp.status_code})"}
    data = resp.json().get("data", {})
    return {"ok": True, "management": bool(data.get("is_management_key") or data.get("is_provisioning_key")),
            "label": data.get("label")}


@app.get("/api/openrouter/status")
def openrouter_status():
    """Is OpenRouter connected? Never returns a key.

    Pink Diamond needs the *management* key (OPENROUTER_MANAGEMENT_KEY) to mint
    each paying user's own inference key; OPENROUTER_API_KEY is an optional
    shared inference key for staging.
    """
    cached = _or_status_cache.get("value")
    if cached and time.time() - _or_status_cache.get("at", 0) < 300:
        return cached
    result = {"management_key": {"configured": False}, "shared_key": {"configured": False},
              "per_user_keys": False}
    mgmt = env("OPENROUTER_MANAGEMENT_KEY")
    if mgmt:
        info = _key_info(mgmt)
        result["management_key"] = {"configured": True, "valid": info["ok"] and info.get("management", False),
                                    "label": info.get("label"), "detail": info.get("detail")
                                    or ("ok" if info.get("management") else "not a management key")}
        result["per_user_keys"] = result["management_key"]["valid"] and ork.configured()
    shared = env("OPENROUTER_API_KEY")
    if shared:
        info = _key_info(shared)
        result["shared_key"] = {"configured": True, "inference_ready": info["ok"] and not info.get("management"),
                                "label": info.get("label")}
    # Kept for older clients and native/go/orcheck.
    result["configured"] = bool(mgmt or shared)
    result["inference_ready"] = bool(result["per_user_keys"] or result["shared_key"].get("inference_ready"))
    result["detail"] = ("Connected" if result["inference_ready"] else
                        "Set OPENROUTER_MANAGEMENT_KEY and PD_KEY_ENCRYPTION_SECRET" if not result["configured"]
                        else "Configured, but no usable route yet")
    _or_status_cache.update(value=result, at=time.time())
    return result


class ChatBody(BaseModel):
    message: str
    model: str | None = None


@app.post("/api/chat")
def chat(body: ChatBody, user: dict = Depends(current_user)):
    unfiltered = pink_active(user["id"])          # server decides, not the browser
    model = _resolve_model(body.model, subscribed(user), unfiltered)

    # Spend comes out of the user's own OpenRouter key, whose limit is their
    # balance — OpenRouter itself refuses once it is used up.
    api_key = ork.user_key(user) or env("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(503, "Model access isn't funded yet — top up to start")

    system = (
        "You are Pink Diamond, a web-hosted AI agent."
        + (
            " Uncensored Mode is active for this account: blunt tone, adult creative work between"
            " consenting adults and dark fiction are allowed."
            " Hard limits that no payment removes: no sexual content involving minors,"
            " no sexual content involving real people, no genuine weapons/drug-synthesis/malware"
            " instructions, no targeted harassment of real people. State these limits plainly if asked."
        )
        if unfiltered
        else " Follow the Pink Diamond creation guidelines: no sexual or graphic content. Keep responses"
             " helpful and coherent."
    )
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
                "usage": {"include": True},
            },
        )
    if resp.status_code == 402:
        raise HTTPException(402, "Out of Pink Credits — top up to keep going")
    if resp.status_code != 200:
        raise HTTPException(502, "Model provider error")

    data = resp.json()
    reply = data["choices"][0]["message"]["content"]
    spent_credits = round(float((data.get("usage") or {}).get("cost") or 0) * 100, 2)
    with db.transaction() as conn:
        conn.execute("UPDATE users SET credits_used=credits_used+? WHERE id=?", (spent_credits, user["id"]))
        conn.execute("INSERT INTO credit_timeline (user_id, delta, reason) VALUES (?,?,?)",
                     (user["id"], -spent_credits, f"chat · {model}"))
        conn.execute("INSERT INTO chat_messages (user_id, role, content, unfiltered) VALUES (?,?,?,?)",
                     (user["id"], "user", body.message, int(unfiltered)))
        conn.execute("INSERT INTO chat_messages (user_id, role, content, unfiltered) VALUES (?,?,?,?)",
                     (user["id"], "agent", reply, int(unfiltered)))
    notice = None
    if user.get("or_key_hash"):
        bal = ork.balance({**user, "funded_cents": user["funded_cents"]})
        if bal["remaining_cents"] <= 0:
            notice = "You're out of Pink Credits — generation pauses until you top up."
        elif bal["low"]:
            notice = f"Low balance: {bal['credits']:,} Pink Credits left."
    return {"reply": reply, "unfiltered": unfiltered, "model": model,
            "credits_spent": spent_credits, "notice": notice}


if os.environ.get("PD_INIT_DB") == "1":
    db.init_db()
