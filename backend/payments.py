"""Pink Diamond payments — Stripe Checkout, Billing and webhooks.

Compliance shape (why it is built this way):
- Card data never touches Pink Diamond. Checkout's embedded page collects it
  inside Stripe's iframe (PCI-DSS SAQ A); "saved cards autofill" is Stripe's
  saved-payment-method feature, shown with the customer's consent checkbox.
- Subscriptions auto-renew through Stripe Billing. Before paying, the browser
  shows price, interval, renewal and how to cancel, and the API refuses a
  checkout unless the customer ticked the auto-renewal consent; cancelling is
  one click away in the Stripe customer portal (ROSCA / FTC / California ARL).
- Nothing is credited from the browser: only signed Stripe webhooks move money
  into an account, each processed exactly once, and the money arithmetic and
  subscription rules run in the native C/C++/Zig core (payments_core).
- Payments refuse to go live without a persistent database (see live()).
"""

from __future__ import annotations

import hashlib
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import database as db
import openrouter_keys as ork
import payments_core as core
from auth import current_user, optional_user
from config import (PLAN_NAMES, PLAN_PRICES_CENTS, TERMS_VERSION, TOPUP_PRESETS_CENTS,
                    UNCENSORED_PRICE_CENTS, SESSION_SECRET_DEFAULT, env)
from entitlement import current_subscription

router = APIRouter()
STRIPE_JS = "https://js.stripe.com/dahlia/stripe.js"
WEBHOOK_TOLERANCE_SECONDS = 300
WEBHOOK_EVENTS = ["checkout.session.completed", "invoice.paid", "invoice.payment_failed",
                  "customer.subscription.updated", "customer.subscription.deleted", "charge.refunded"]


def _stripe():
    import stripe

    stripe.api_key = env("STRIPE_SECRET_KEY")
    return stripe


def stripe_mode() -> str | None:
    key = env("STRIPE_SECRET_KEY")
    if not key:
        return None
    return "live" if key.startswith(("sk_live_", "rk_live_")) else "test"


def _setting_name(name: str) -> str:
    """Stripe objects belong to one account and mode, so their ids are stored
    per secret key: switching test -> live keys starts fresh."""
    digest = hashlib.sha256(env("STRIPE_SECRET_KEY").encode()).hexdigest()[:12]
    return f"{name}:{digest}"


def webhook_secret() -> str:
    """STRIPE_WEBHOOK_SECRET, or the one stored when ensure_webhook() created the endpoint."""
    explicit = env("STRIPE_WEBHOOK_SECRET")
    if explicit or not (env("STRIPE_SECRET_KEY") and env("PD_KEY_ENCRYPTION_SECRET")):
        return explicit
    row = db.one("SELECT value FROM settings WHERE key=?", (_setting_name("stripe_webhook_secret"),))
    return ork.decrypt(row["value"]) if row else ""


def ensure_webhook() -> None:
    """Register this site's webhook endpoint with Stripe once, keeping the
    signing secret encrypted in the database. Only the server ever sees the
    Stripe secret key, so this is how the endpoint gets wired without anyone
    copying secrets around. Needs PD_PUBLIC_URL so it never registers a
    one-off deployment URL."""
    origin = env("PD_PUBLIC_URL").rstrip("/")
    if (env("STRIPE_WEBHOOK_SECRET") or not origin or not env("STRIPE_SECRET_KEY")
            or not env("PD_KEY_ENCRYPTION_SECRET") or not db.persistent()):
        return
    name = _setting_name("stripe_webhook_secret")
    with db.transaction() as conn:
        db.lock(conn, "stripe_webhook")          # one creator across instances
        if conn.execute("SELECT 1 FROM settings WHERE key=?", (name,)).fetchone():
            return
        endpoint = _stripe().WebhookEndpoint.create(
            url=origin + "/api/payments/webhook",
            enabled_events=WEBHOOK_EVENTS,
            description="Pink Diamond payments (created by the site)",
        )
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (name, ork.encrypt(endpoint.secret)))


def blockers() -> list[str]:
    """Everything that must be true before Pink Diamond may take real money."""
    missing = []
    for name in ("STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY", "PD_KEY_ENCRYPTION_SECRET"):
        if not env(name):
            missing.append(f"{name} is not set")
    if env("STRIPE_SECRET_KEY") and not webhook_secret():
        missing.append("Stripe webhook not registered (set PD_PUBLIC_URL, or STRIPE_WEBHOOK_SECRET)")
    if not ork.management_key():
        missing.append("no OpenRouter management key (OPENROUTER_MANAGEMENT_KEY, or one in OPENROUTER_API_KEY)")
    if env("PD_SESSION_SECRET") in ("", SESSION_SECRET_DEFAULT):
        missing.append("PD_SESSION_SECRET is not set")
    if not db.persistent():
        missing.append("no persistent database (set DATABASE_URL to Postgres)")
    return missing


def live() -> bool:
    return not blockers()


def require_live() -> None:
    if not live():
        raise HTTPException(503, "Payments are not live yet")


def _require_terms(user: dict) -> None:
    if user.get("terms_version") != TERMS_VERSION:
        raise HTTPException(428, "Accept the current Terms & Agreement first")


def _origin(request: Request) -> str:
    configured = env("PD_PUBLIC_URL")
    if configured:
        return configured.rstrip("/")
    return f"{request.url.scheme}://{request.url.netloc}"


def _customer_id(user: dict) -> str:
    if user.get("stripe_customer_id"):
        return user["stripe_customer_id"]
    customer = _stripe().Customer.create(
        email=user["email"],
        metadata={"pd_user_id": str(user["id"])},
        idempotency_key=f"pd-customer-{user['id']}",
    )
    db.run("UPDATE users SET stripe_customer_id=? WHERE id=?", (customer.id, user["id"]))
    return customer.id


# ------------------------------------------------------------- config ---

@router.get("/api/payments/config")
def payments_config(user: dict | None = Depends(optional_user)):
    try:
        if not webhook_secret():
            ensure_webhook()
    except Exception as exc:                     # reported through blockers()
        print(f"stripe webhook setup failed: {exc.__class__.__name__}: {exc}")
    plans = {
        key: {"name": PLAN_NAMES[key], "month_cents": cents,
              "year_cents": core.plan_price_cents(cents, "year")}
        for key, cents in PLAN_PRICES_CENTS.items()
    }
    return {
        "live": live(),
        "blockers": blockers(),
        "engine": core.engine(),
        "database": "postgres" if db.IS_POSTGRES else "sqlite",
        "stripe_mode": stripe_mode(),
        "publishable_key": env("STRIPE_PUBLISHABLE_KEY") if live() else None,
        "stripe_js": STRIPE_JS,
        "terms_version": TERMS_VERSION,
        "plans": plans,
        "uncensored": {"month_cents": UNCENSORED_PRICE_CENTS,
                       "year_cents": core.plan_price_cents(UNCENSORED_PRICE_CENTS, "year")},
        "topup": {"presets_cents": TOPUP_PRESETS_CENTS, "min_cents": core.TOPUP_MIN_CENTS,
                  "max_cents": core.TOPUP_MAX_CENTS, "credits_per_dollar": core.CREDITS_PER_DOLLAR},
        "split": "50% of every subscription payment funds your Pink Credits balance",
        "terms_accepted": bool(user and user.get("terms_version") == TERMS_VERSION),
    }


# ----------------------------------------------------------- checkout ---

class SubscriptionCheckout(BaseModel):
    plan: str
    interval: str = "month"            # month | year
    uncensored: bool = False
    accept_auto_renewal: bool = False  # the explicit renewal consent checkbox
    adult_confirmed: bool = False      # required for the Uncensored Mode add-on


@router.post("/api/payments/checkout/subscription")
def checkout_subscription(body: SubscriptionCheckout, request: Request, user: dict = Depends(current_user)):
    require_live()
    _require_terms(user)
    if body.plan not in PLAN_PRICES_CENTS or body.interval not in ("month", "year"):
        raise HTTPException(400, "Unknown plan or billing interval")
    if not body.accept_auto_renewal:
        raise HTTPException(400, "Auto-renewal terms must be accepted")
    if body.uncensored and not body.adult_confirmed:
        raise HTTPException(400, "Uncensored Mode is for adults (18+) only")
    if current_subscription(user["id"]):
        raise HTTPException(409, "You already have a subscription — change or cancel it in Manage billing")

    plan_cents = core.plan_price_cents(PLAN_PRICES_CENTS[body.plan], body.interval)
    items = [{
        "quantity": 1,
        "price_data": {
            "currency": "usd",
            "unit_amount": plan_cents,
            "recurring": {"interval": body.interval},
            "product_data": {"name": f"Pink Diamond {PLAN_NAMES[body.plan]}"},
        },
    }]
    if body.uncensored:
        items.append({
            "quantity": 1,
            "price_data": {
                "currency": "usd",
                "unit_amount": core.plan_price_cents(UNCENSORED_PRICE_CENTS, body.interval),
                "recurring": {"interval": body.interval},
                "product": _uncensored_product(_stripe()),
            },
        })
    meta = {"pd_user_id": str(user["id"]), "plan": body.plan, "interval": body.interval,
            "uncensored": "1" if body.uncensored else "0", "terms_version": TERMS_VERSION}
    session = _stripe().checkout.Session.create(
        mode="subscription",
        ui_mode="embedded_page",
        customer=_customer_id(user),
        client_reference_id=str(user["id"]),
        line_items=items,
        metadata=meta,
        subscription_data={"metadata": meta},
        saved_payment_method_options={"payment_method_save": "enabled"},
        return_url=_origin(request) + "/?checkout={CHECKOUT_SESSION_ID}#plans",
    )
    return {"client_secret": session.client_secret, "session_id": session.id}


class TopupCheckout(BaseModel):
    amount_cents: int


@router.post("/api/payments/checkout/topup")
def checkout_topup(body: TopupCheckout, request: Request, user: dict = Depends(current_user)):
    require_live()
    _require_terms(user)
    if not core.topup_valid(body.amount_cents):
        raise HTTPException(400, "Top-ups are between $5 and $1,000")
    credits = core.cents_to_credits(body.amount_cents)
    meta = {"pd_user_id": str(user["id"]), "kind": "topup", "amount_cents": str(body.amount_cents)}
    session = _stripe().checkout.Session.create(
        mode="payment",
        ui_mode="embedded_page",
        customer=_customer_id(user),
        client_reference_id=str(user["id"]),
        line_items=[{
            "quantity": 1,
            "price_data": {
                "currency": "usd",
                "unit_amount": body.amount_cents,
                "product_data": {"name": f"{credits:,} Pink Credits"},
            },
        }],
        metadata=meta,
        payment_intent_data={"metadata": meta},
        saved_payment_method_options={"payment_method_save": "enabled"},
        return_url=_origin(request) + "/?checkout={CHECKOUT_SESSION_ID}#plans",
    )
    return {"client_secret": session.client_secret, "session_id": session.id}


@router.get("/api/payments/session/{session_id}")
def checkout_status(session_id: str, user: dict = Depends(current_user)):
    require_live()
    session = _stripe().checkout.Session.retrieve(session_id)
    if session.client_reference_id != str(user["id"]):
        raise HTTPException(404, "Unknown checkout")
    return {"status": session.status, "payment_status": session.payment_status, "mode": session.mode}


def _portal_configuration() -> str:
    """A customer-portal setup that lets people update cards, see invoices and
    cancel (at period end) — but not switch plans behind our metadata."""
    row = db.one("SELECT value FROM settings WHERE key=?", (_setting_name("stripe_portal_config"),))
    if row:
        return row["value"]
    conf = _stripe().billing_portal.Configuration.create(
        business_profile={"headline": "Pink Diamond — manage billing"},
        features={
            "payment_method_update": {"enabled": True},
            "invoice_history": {"enabled": True},
            "customer_update": {"enabled": True, "allowed_updates": ["email", "address"]},
            "subscription_cancel": {"enabled": True, "mode": "at_period_end",
                                    "cancellation_reason": {"enabled": True, "options": [
                                        "too_expensive", "missing_features", "unused", "other"]}},
        },
    )
    db.run("INSERT INTO settings (key, value) VALUES (?, ?)", (_setting_name("stripe_portal_config"), conf.id))
    return conf.id


@router.post("/api/payments/portal")
def billing_portal(request: Request, user: dict = Depends(current_user)):
    require_live()
    if not user.get("stripe_customer_id"):
        raise HTTPException(404, "No billing account yet")
    portal = _stripe().billing_portal.Session.create(
        customer=user["stripe_customer_id"],
        configuration=_portal_configuration(),
        return_url=_origin(request) + "/#plans",
    )
    return {"url": portal.url}


class UncensoredBody(BaseModel):
    enabled: bool
    adult_confirmed: bool = False


@router.post("/api/payments/uncensored")
def set_uncensored(body: UncensoredBody, user: dict = Depends(current_user)):
    """Add or remove the +$10 add-on on an existing subscription (prorated)."""
    require_live()
    sub = current_subscription(user["id"])
    if not sub or not sub["stripe_subscription_id"]:
        raise HTTPException(402, "Uncensored Mode is an add-on to a paid plan")
    if body.enabled and not body.adult_confirmed:
        raise HTTPException(400, "Uncensored Mode is for adults (18+) only")
    stripe = _stripe()
    remote = stripe.Subscription.retrieve(sub["stripe_subscription_id"])
    product = _uncensored_product(stripe)
    addon = [i for i in remote["items"]["data"] if _get(i, "price", "product") == product]
    if body.enabled and not addon:
        stripe.SubscriptionItem.create(
            subscription=remote.id,
            quantity=1,
            price_data={
                "currency": "usd",
                "unit_amount": core.plan_price_cents(UNCENSORED_PRICE_CENTS, sub["billing_interval"]),
                "recurring": {"interval": sub["billing_interval"]},
                "product": product,
            },
            proration_behavior="always_invoice",      # charged now, funds the balance via invoice.paid
        )
    elif not body.enabled and addon:
        stripe.SubscriptionItem.delete(addon[0].id, proration_behavior="create_prorations")
    stripe.Subscription.modify(remote.id, metadata={**dict(remote.metadata or {}),
                                                    "uncensored": "1" if body.enabled else "0"})
    db.run("UPDATE subscriptions SET uncensored=? WHERE id=?", (int(body.enabled), sub["id"]))
    return {"uncensored": body.enabled}


def _uncensored_product(stripe) -> str:
    row = db.one("SELECT value FROM settings WHERE key=?", (_setting_name("stripe_uncensored_product"),))
    if row:
        return row["value"]
    product = stripe.Product.create(name="Pink Diamond Uncensored Mode (18+)")
    db.run("INSERT INTO settings (key, value) VALUES (?, ?)", (_setting_name("stripe_uncensored_product"), product.id))
    return product.id


# ------------------------------------------------------------ balance ---

@router.get("/api/balance")
def get_balance(user: dict = Depends(current_user)):
    """Pink Credits left before OpenRouter reports insufficient funds."""
    result = ork.balance(user)
    sub = current_subscription(user["id"])
    result["subscription"] = None if not sub else {
        "plan": sub["tier"], "interval": sub["billing_interval"], "status": sub["status"],
        "renews_at": sub["period_end"], "uncensored": bool(sub["uncensored"]),
    }
    return result


# ------------------------------------------------------------ ledger ---

def credit_payment(conn, *, user_id: int, kind: str, amount_cents: int, funded_cents: int,
                   stripe_ref: str, payment_intent: str | None) -> bool:
    """Record a settled payment and fund the user's balance, exactly once.
    Returns False when this payment was already credited."""
    if conn.execute("SELECT 1 FROM payments WHERE stripe_ref=?", (stripe_ref,)).fetchone():
        return False
    credits = core.cents_to_credits(funded_cents)
    conn.execute(
        "INSERT INTO payments (user_id, kind, amount_cents, funded_cents, platform_cents, credits,"
        " stripe_ref, payment_intent) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, kind, amount_cents, funded_cents, amount_cents - funded_cents, credits,
         stripe_ref, payment_intent),
    )
    conn.execute("UPDATE users SET funded_cents=funded_cents+? WHERE id=?", (funded_cents, user_id))
    conn.execute(
        "INSERT INTO credit_timeline (user_id, delta, reason) VALUES (?,?,?)",
        (user_id, credits, f"{kind} ${amount_cents / 100:.2f} — {credits:,} Pink Credits"),
    )
    return True


# ----------------------------------------------------------- webhooks ---

def _get(obj, *path, default=None):
    for key in path:
        if obj is None:
            return default
        obj = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
    return default if obj is None else obj


def _invoice_subscription_id(invoice: dict) -> str | None:
    # 2025+ API versions moved it under parent.subscription_details.
    return (_get(invoice, "parent", "subscription_details", "subscription")
            or invoice.get("subscription"))


def _invoice_payment_intent(invoice: dict) -> str | None:
    pi = invoice.get("payment_intent")
    if pi:
        return pi if isinstance(pi, str) else pi.get("id")
    for p in _get(invoice, "payments", "data", default=[]) or []:
        pi = _get(p, "payment", "payment_intent")
        if pi:
            return pi if isinstance(pi, str) else pi.get("id")
    return None


def _period_end(subscription: dict) -> int:
    end = subscription.get("current_period_end")
    if not end:  # 2025+ API versions: per item
        ends = [i.get("current_period_end") or 0 for i in _get(subscription, "items", "data", default=[])]
        end = max(ends or [0])
    return int(end or 0)


def _user_for(conn, meta: dict | None, customer: str | None):
    uid = (meta or {}).get("pd_user_id")
    if uid:
        return conn.execute("SELECT * FROM users WHERE id=?", (int(uid),)).fetchone()
    if customer:
        return conn.execute("SELECT * FROM users WHERE stripe_customer_id=?", (customer,)).fetchone()
    return None


def _apply_lifecycle(conn, sub_id: str, event: int, *, user_id: int | None = None,
                     remote: dict | None = None) -> None:
    row = conn.execute(
        "SELECT * FROM subscriptions WHERE stripe_subscription_id=? FOR UPDATE", (sub_id,)
    ).fetchone()
    meta = dict((remote or {}).get("metadata") or {})
    if row is None:
        if user_id is None:
            return
        conn.execute(
            "INSERT INTO subscriptions (user_id, kind, tier, billing_interval, uncensored, status,"
            " period_end, stripe_subscription_id) VALUES (?, 'plan', ?, ?, ?, 'none', 0, ?)",
            (user_id, meta.get("plan"), meta.get("interval", "month"),
             int(meta.get("uncensored") == "1"), sub_id),
        )
        row = conn.execute("SELECT * FROM subscriptions WHERE stripe_subscription_id=?", (sub_id,)).fetchone()
    state = core.sub_transition(core.SUB_STATE_CODES.get(row["status"], core.SUB_NONE), event)
    updates = {"status": core.SUB_STATE_NAMES[state]}
    if remote:
        updates["period_end"] = _period_end(remote) or row["period_end"]
        if meta.get("plan"):
            updates["tier"] = meta["plan"]
        if "uncensored" in meta:
            updates["uncensored"] = int(meta["uncensored"] == "1")
    sets = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE subscriptions SET {sets} WHERE id=?", (*updates.values(), row["id"]))
    entitled = core.sub_entitled(state, int(updates.get("period_end", row["period_end"])), int(time.time()))
    tier = updates.get("tier", row["tier"]) if entitled else "free"
    conn.execute("UPDATE users SET plan=? WHERE id=?", (tier or "free", row["user_id"]))


def handle_event(event: dict) -> str:
    """Apply one verified Stripe event. Returns a short outcome for logs/tests."""
    etype, obj = event["type"], event["data"]["object"]
    fund_user = None
    remote: dict = {}
    if etype == "invoice.paid" and _invoice_subscription_id(obj) and env("STRIPE_SECRET_KEY"):
        # Network call before taking the database lock.
        remote = dict(_stripe().Subscription.retrieve(_invoice_subscription_id(obj)))
    with db.transaction() as conn:
        if conn.execute("SELECT 1 FROM stripe_events WHERE id=?", (event["id"],)).fetchone():
            return "duplicate"
        conn.execute("INSERT INTO stripe_events (id, type) VALUES (?, ?)", (event["id"], etype))

        if etype == "checkout.session.completed" and obj.get("mode") == "payment":
            if obj.get("payment_status") != "paid" or _get(obj, "metadata", "kind") != "topup":
                return "ignored"
            user = _user_for(conn, obj.get("metadata"), obj.get("customer"))
            if user is None:
                return "unknown user"
            amount = int(obj["amount_total"])
            pi = obj.get("payment_intent")
            if credit_payment(conn, user_id=user["id"], kind="topup", amount_cents=amount,
                              funded_cents=amount, stripe_ref=pi or obj["id"], payment_intent=pi):
                fund_user = user["id"]
            outcome = "topup credited"

        elif etype == "invoice.paid":
            sub_id = _invoice_subscription_id(obj)
            if not sub_id:
                return "ignored"
            meta = remote.get("metadata") or _get(obj, "parent", "subscription_details", "metadata") or {}
            remote["metadata"] = meta
            user = _user_for(conn, meta, obj.get("customer"))
            if user is None:
                return "unknown user"
            _apply_lifecycle(conn, sub_id, core.EV_INVOICE_PAID, user_id=user["id"], remote=remote)
            paid = int(obj.get("amount_paid") or 0)
            if paid > 0 and credit_payment(
                    conn, user_id=user["id"], kind="subscription", amount_cents=paid,
                    funded_cents=core.split_customer_cents(paid), stripe_ref=obj["id"],
                    payment_intent=_invoice_payment_intent(obj)):
                fund_user = user["id"]
            outcome = "subscription paid"

        elif etype == "invoice.payment_failed":
            sub_id = _invoice_subscription_id(obj)
            if sub_id:
                _apply_lifecycle(conn, sub_id, core.EV_PAYMENT_FAILED)
            outcome = "payment failed"

        elif etype == "customer.subscription.updated":
            prev = _get(event, "data", "previous_attributes", default={}) or {}
            ev = None
            if obj.get("cancel_at_period_end") and not prev.get("cancel_at_period_end", False):
                ev = core.EV_CANCEL_AT_PERIOD_END
            elif not obj.get("cancel_at_period_end") and prev.get("cancel_at_period_end"):
                ev = core.EV_RESUMED
            elif obj.get("status") in ("past_due", "unpaid"):
                ev = core.EV_PAYMENT_FAILED
            if ev is None:
                ev = 0          # period/metadata refresh only
            _apply_lifecycle(conn, obj["id"], ev, remote=obj)
            outcome = "subscription updated"

        elif etype == "customer.subscription.deleted":
            _apply_lifecycle(conn, obj["id"], core.EV_DELETED, remote=obj)
            outcome = "subscription ended"

        elif etype == "charge.refunded":
            pi = obj.get("payment_intent")
            row = conn.execute("SELECT * FROM payments WHERE payment_intent=? AND kind!='refund'", (pi,)).fetchone() if pi else None
            if row is None:
                return "refund for unknown payment"
            refunded = int(obj.get("amount_refunded") or 0)
            # Claw back the funded share in proportion to the refund.
            claw = -min(int(row["funded_cents"]), round(row["funded_cents"] * refunded / max(1, row["amount_cents"])))
            already = conn.execute(
                "SELECT COALESCE(SUM(funded_cents), 0) AS s FROM payments WHERE kind='refund' AND payment_intent=?",
                (pi,)).fetchone()["s"]
            delta = claw - int(already)
            if delta < 0 and credit_payment(conn, user_id=row["user_id"], kind="refund",
                                            amount_cents=-refunded, funded_cents=delta,
                                            stripe_ref=f"refund:{obj['id']}:{refunded}", payment_intent=pi):
                fund_user = row["user_id"]
            outcome = "refund applied"
        else:
            outcome = "ignored"

    if fund_user is not None and ork.configured():
        try:
            ork.sync_limit(fund_user)       # healed on the next balance read if this fails
        except ork.KeyError_:
            outcome += " (OpenRouter sync deferred)"
    return outcome


@router.post("/api/payments/webhook")
async def stripe_webhook(request: Request):
    secret = webhook_secret()
    if not secret:
        raise HTTPException(503, "Webhook secret not configured")
    payload = await request.body()
    header = request.headers.get("stripe-signature", "")
    verdict = core.stripe_verify(payload, header, secret, int(time.time()), WEBHOOK_TOLERANCE_SECONDS)
    if verdict != core.SIG_OK:
        raise HTTPException(400, "Invalid signature")
    event = json.loads(payload)
    return {"received": True, "outcome": handle_event(event)}
