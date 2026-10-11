"""Payment system tests.

    python -m pytest -q test_payments.py                      # SQLite
    DATABASE_URL=postgresql://... python -m pytest -q test_payments.py   # Postgres

Stripe and the OpenRouter management API are faked; everything else — the
native C/C++/Zig core, signature checks, webhooks, ledger — runs for real.
"""

import hashlib
import hmac
import json
import os
import tempfile
import time
from types import SimpleNamespace

if not os.environ.get("DATABASE_URL"):
    os.environ["PD_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "pay.db")
os.environ.update({
    "STRIPE_SECRET_KEY": "sk_test_fake", "STRIPE_PUBLISHABLE_KEY": "pk_test_fake",
    "STRIPE_WEBHOOK_SECRET": "whsec_test_secret", "OPENROUTER_MANAGEMENT_KEY": "sk-or-mgmt-fake",
    "PD_KEY_ENCRYPTION_SECRET": "test-encryption-secret", "PD_SESSION_SECRET": "test-session-secret",
    "PD_TEST_PAYMENTS_FUND_OPENROUTER": "1",   # the fakes stand in for live mode
})
os.environ.pop("PD_DEMO_BILLING", None)
os.environ.pop("OPENROUTER_API_KEY", None)

import pytest  # noqa: E402
import stripe  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
import database as db  # noqa: E402
import main  # noqa: E402
import openrouter_keys as ork  # noqa: E402
import payments  # noqa: E402
import payments_core as core  # noqa: E402

db.init_db()
client = TestClient(main.app)
SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]


# ------------------------------------------------------------- fakes ---

class FakeOpenRouter:
    def __init__(self):
        self.keys = {}          # hash -> {"limit": float, "usage": float}
        self.calls = []

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("json")))
        if method == "POST" and path == "/keys":
            h = f"hash{len(self.keys) + 1}"
            self.keys[h] = {"limit": kwargs["json"]["limit"], "usage": 0.0}
            return {"key": f"sk-or-v1-user-{h}", "data": {"hash": h, **self.keys[h]}}
        h = path.rsplit("/", 1)[-1]
        if method == "PATCH":
            self.keys[h]["limit"] = kwargs["json"]["limit"]
        k = self.keys[h]
        return {"data": {"hash": h, "limit": k["limit"], "usage": k["usage"],
                         "limit_remaining": k["limit"] - k["usage"]}}


class FakeStripe:
    """Just enough of the stripe module for payments.py."""

    def __init__(self):
        self.sessions, self.subscriptions = [], {}
        fake = self

        class Customer:
            @staticmethod
            def create(**kw):
                return SimpleNamespace(id=f"cus_{kw['metadata']['pd_user_id']}")

        class Session:
            @staticmethod
            def create(**kw):
                fake.sessions.append(kw)
                return SimpleNamespace(id=f"cs_{len(fake.sessions)}", client_secret=f"cs_secret_{len(fake.sessions)}")

        class Subscription:
            @staticmethod
            def retrieve(sid):
                return fake.subscriptions[sid]

        class Product:
            @staticmethod
            def create(**kw):
                return SimpleNamespace(id="prod_uncensored")

        class WebhookEndpoint:
            @staticmethod
            def create(**kw):
                fake.webhooks.append(kw)
                return SimpleNamespace(id=f"we_{len(fake.webhooks)}", secret=f"whsec_auto_{len(fake.webhooks)}")

        self.webhooks = []
        self.Customer, self.Subscription, self.Product = Customer, Subscription, Product
        self.WebhookEndpoint = WebhookEndpoint
        self.checkout = SimpleNamespace(Session=Session)


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    orf, stf = FakeOpenRouter(), FakeStripe()
    monkeypatch.setattr(ork, "_mgmt", orf)
    monkeypatch.setattr(payments, "_stripe", lambda: stf)
    monkeypatch.setattr(db, "persistent", lambda: True)
    return SimpleNamespace(openrouter=orf, stripe=stf)


def account(name: str, accept=True) -> tuple[dict, int]:
    resp = client.post("/api/register", json={
        "username": name, "email": f"{name}@pd.test", "password": "pw123456!",
        "accept_terms": accept, "terms_version": config.TERMS_VERSION})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}, int(token.split(".")[0])


def signed(event: dict, secret=SECRET, ts=None) -> tuple[bytes, str]:
    payload = json.dumps(event).encode()
    ts = ts or int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return payload, f"t={ts},v1={sig}"


def deliver(event: dict, **kw):
    payload, header = signed(event, **kw)
    return client.post("/api/payments/webhook", content=payload, headers={"stripe-signature": header})


_n = [0]


def evt(etype: str, obj: dict, **extra) -> dict:
    _n[0] += 1
    return {"id": f"evt_{_n[0]}", "type": etype, "data": {"object": obj, **extra}}


# ---------------------------------------------------- native == mirror ---

def test_native_core_is_loaded_and_matches_mirror():
    assert core.NATIVE, "build with: python native/payments/build.py"
    for cents in (0, 1, 2, 499, 500, 1199, 2299, 3399, 12199, 99_999, 100_000, 100_001, -7):
        assert core.split_customer_cents(cents) == core.split_customer_cents(cents, native=False)
        assert core.split_platform_cents(cents) == core.split_platform_cents(cents, native=False)
        assert core.cents_to_credits(cents) == core.cents_to_credits(cents, native=False)
        assert core.topup_valid(cents) == core.topup_valid(cents, native=False)
        for interval in ("month", "year"):
            assert core.plan_price_cents(cents, interval) == core.plan_price_cents(cents, interval, native=False)
    for state in range(5):
        for event in range(7):
            assert core.sub_transition(state, event) == core.sub_transition(state, event, native=False)
            for end in (0, 10, 20):
                assert core.sub_entitled(state, end, 10) == core.sub_entitled(state, end, 10, native=False)


def test_money_rules():
    assert core.split_customer_cents(2299) == 1150 and core.split_platform_cents(2299) == 1149
    assert core.cents_to_credits(100) == 100          # $1 = 100 Pink Credits
    assert core.plan_price_cents(2299, "year") == 22070
    assert core.plan_price_cents(config.UNCENSORED_PRICE_CENTS, "month") == 1000


def test_sha256_vectors():
    assert core.sha256_hex(b"") == hashlib.sha256(b"").hexdigest()
    assert core.sha256_hex(b"abc" * 1000) == hashlib.sha256(b"abc" * 1000).hexdigest()


def test_signature_verification_matches_stripe_library():
    payload, header = signed({"id": "evt_x", "object": "event"})
    now = int(time.time())
    for native in (True, False):
        assert core.stripe_verify(payload, header, SECRET, now, native=native) == core.SIG_OK
        assert core.stripe_verify(payload + b" ", header, SECRET, now, native=native) == core.SIG_MISMATCH
        assert core.stripe_verify(payload, header, "whsec_other", now, native=native) == core.SIG_MISMATCH
        assert core.stripe_verify(payload, header, SECRET, now + 3600, native=native) == core.SIG_EXPIRED
        assert core.stripe_verify(payload, "garbage", SECRET, now, native=native) == core.SIG_MALFORMED
        assert core.stripe_verify(payload, f"t={now}", SECRET, now, native=native) == core.SIG_MALFORMED
        # Rolling secrets: any matching v1 is accepted.
        assert core.stripe_verify(payload, header.replace("v1=", "v1=" + "0" * 64 + ",v1="), SECRET, now,
                                  native=native) == core.SIG_OK
    # Stripe's own verifier agrees with ours.
    stripe.Webhook.construct_event(payload, header, SECRET)


# -------------------------------------------------------------- terms ---

def test_terms_required_to_register():
    resp = client.post("/api/register", json={"username": "noterms", "email": "n@pd.test", "password": "pw123456!"})
    assert resp.status_code == 428
    resp = client.post("/api/register", json={"username": "oldterms", "email": "o@pd.test", "password": "pw123456!",
                                              "accept_terms": True, "terms_version": "1999-01-01"})
    assert resp.status_code == 428


def test_checkout_requires_current_terms():
    headers, uid = account("staleterms")
    db.run("UPDATE users SET terms_version='1999-01-01' WHERE id=?", (uid,))
    resp = client.post("/api/payments/checkout/subscription", headers=headers,
                       json={"plan": "plus", "accept_auto_renewal": True})
    assert resp.status_code == 428
    client.post("/api/terms/accept", headers=headers, json={"terms_version": config.TERMS_VERSION})
    resp = client.post("/api/payments/checkout/subscription", headers=headers,
                       json={"plan": "plus", "accept_auto_renewal": True})
    assert resp.status_code == 200


# ------------------------------------------------------------ checkout ---

def test_config_reports_blockers(monkeypatch):
    assert client.get("/api/payments/config").json()["live"] is True
    monkeypatch.setattr(db, "persistent", lambda: False)
    cfg = client.get("/api/payments/config").json()
    assert cfg["live"] is False and any("persistent database" in b for b in cfg["blockers"])
    headers, _ = account("notlive")
    assert client.post("/api/payments/checkout/topup", headers=headers,
                       json={"amount_cents": 1000}).status_code == 503


def test_subscription_checkout_is_priced_server_side(fakes):
    headers, uid = account("buyer")
    assert client.post("/api/payments/checkout/subscription", headers=headers,
                       json={"plan": "plus"}).status_code == 400          # no renewal consent
    assert client.post("/api/payments/checkout/subscription", headers=headers,
                       json={"plan": "plus", "accept_auto_renewal": True, "uncensored": True}).status_code == 400
    resp = client.post("/api/payments/checkout/subscription", headers=headers, json={
        "plan": "plus", "interval": "year", "uncensored": True, "adult_confirmed": True,
        "accept_auto_renewal": True})
    assert resp.status_code == 200 and resp.json()["client_secret"].startswith("cs_secret_")
    s = fakes.stripe.sessions[-1]
    assert s["mode"] == "subscription" and s["ui_mode"] == "embedded_page"
    assert s["saved_payment_method_options"] == {"payment_method_save": "enabled"}
    amounts = [i["price_data"]["unit_amount"] for i in s["line_items"]]
    assert amounts == [22070, 9600]                                      # yearly plan + yearly add-on
    assert all(i["price_data"]["recurring"] == {"interval": "year"} for i in s["line_items"])
    assert s["subscription_data"]["metadata"]["pd_user_id"] == str(uid)


def test_topup_checkout_bounds(fakes):
    headers, _ = account("topper")
    for bad in (499, 100_001, -1000):
        assert client.post("/api/payments/checkout/topup", headers=headers,
                           json={"amount_cents": bad}).status_code == 400
    for preset in config.TOPUP_PRESETS_CENTS + [1234]:
        assert client.post("/api/payments/checkout/topup", headers=headers,
                           json={"amount_cents": preset}).status_code == 200
    s = fakes.stripe.sessions[-1]
    assert s["mode"] == "payment" and s["line_items"][0]["price_data"]["product_data"]["name"] == "1,234 Pink Credits"


# ------------------------------------------------------------ webhooks ---

def test_webhook_rejects_bad_signatures():
    event = evt("checkout.session.completed", {"mode": "payment"})
    assert deliver(event, secret="whsec_wrong").status_code == 400
    assert deliver(event, ts=int(time.time()) - 3600).status_code == 400
    assert client.post("/api/payments/webhook", content=b"{}", headers={}).status_code == 400


def _subscribe_via_webhook(fakes, uid, *, sub_id, plan="plus", interval="month", uncensored=False, paid=2299):
    fakes.stripe.subscriptions[sub_id] = {
        "id": sub_id, "status": "active", "cancel_at_period_end": False,
        "metadata": {"pd_user_id": str(uid), "plan": plan, "interval": interval,
                     "uncensored": "1" if uncensored else "0"},
        "items": {"data": [{"current_period_end": int(time.time()) + 30 * 86400}]},
    }
    invoice = {"id": f"in_{sub_id}_{_n[0]}", "customer": f"cus_{uid}", "amount_paid": paid,
               "parent": {"subscription_details": {"subscription": sub_id}},
               "payments": {"data": [{"payment": {"payment_intent": f"pi_{sub_id}_{_n[0]}"}}]}}
    return deliver(evt("invoice.paid", invoice)), invoice


def test_subscription_payment_splits_and_mints_key(fakes):
    headers, uid = account("subscriber")
    resp, invoice = _subscribe_via_webhook(fakes, uid, sub_id="sub_A")
    assert resp.json()["outcome"] == "subscription paid"
    me = client.get("/api/me", headers=headers).json()
    assert me["subscribed"] and me["plan"] == "plus" and me["funded_credits"] == 1150
    # Half of $22.99 became the limit of a freshly minted per-user OpenRouter key.
    assert fakes.openrouter.keys == {"hash1": {"limit": 11.5, "usage": 0.0}}
    row = db.one("SELECT or_key_enc, or_key_hash FROM users WHERE id=?", (uid,))
    assert row["or_key_hash"] == "hash1" and "sk-or" not in row["or_key_enc"]           # encrypted at rest
    assert ork.decrypt(row["or_key_enc"]) == "sk-or-v1-user-hash1"
    # Balance shown to the user = what OpenRouter will still let them spend.
    fakes.openrouter.keys["hash1"]["usage"] = 1.25
    bal = client.get("/api/balance", headers=headers).json()
    assert bal["credits"] == 1025 and bal["dollars"] == 10.25 and bal["source"] == "openrouter"
    # Replayed webhook (same event) and re-sent invoice (new event id) never double-credit.
    payload, header = signed({"id": "evt_replay", "type": "invoice.paid", "data": {"object": invoice}})
    for _ in range(2):
        client.post("/api/payments/webhook", content=payload, headers={"stripe-signature": header})
    deliver(evt("invoice.paid", invoice))
    assert client.get("/api/me", headers=headers).json()["funded_credits"] == 1150


def test_renewal_funds_again_and_failure_pauses(fakes):
    headers, uid = account("renewer")
    _subscribe_via_webhook(fakes, uid, sub_id="sub_R")
    _subscribe_via_webhook(fakes, uid, sub_id="sub_R")                    # next period's invoice
    assert client.get("/api/me", headers=headers).json()["funded_credits"] == 2300
    assert fakes.openrouter.keys["hash1"]["limit"] == 23.0
    deliver(evt("invoice.payment_failed", {"id": "in_fail", "parent": {"subscription_details": {"subscription": "sub_R"}}}))
    assert client.get("/api/me", headers=headers).json()["subscribed"] is False
    resp = client.post("/api/chat", headers=headers, json={"message": "hi", "model": "openai/gpt-5.5"})
    assert resp.status_code == 402                                          # no OpenRouter while past due
    _subscribe_via_webhook(fakes, uid, sub_id="sub_R")                      # Stripe's retry succeeds
    assert client.get("/api/me", headers=headers).json()["subscribed"] is True


def test_cancel_runs_to_period_end_then_ends(fakes):
    headers, uid = account("canceler")
    _subscribe_via_webhook(fakes, uid, sub_id="sub_C")
    sub = dict(fakes.stripe.subscriptions["sub_C"], cancel_at_period_end=True)
    deliver(evt("customer.subscription.updated", sub, previous_attributes={"cancel_at_period_end": False}))
    me = client.get("/api/me", headers=headers).json()
    assert me["subscribed"] and me["subscription_status"] == "canceling"
    deliver(evt("customer.subscription.deleted", sub))
    me = client.get("/api/me", headers=headers).json()
    assert not me["subscribed"] and me["plan"] == "free"
    assert me["funded_credits"] == 1150                                     # paid balance stays theirs


def test_uncensored_entitlement_follows_payment(fakes):
    headers, uid = account("adult")
    _subscribe_via_webhook(fakes, uid, sub_id="sub_U", uncensored=True, paid=3299)
    me = client.get("/api/me", headers=headers).json()
    assert me["pink_mode"] is True and me["funded_credits"] == 1650
    assert client.post("/api/pink-mode", headers=headers, json={"enabled": True}).json()["pink_mode"] is True


def test_topup_webhook_and_refund_clawback(fakes):
    headers, uid = account("topupper")
    session = {"id": "cs_top", "mode": "payment", "payment_status": "paid", "customer": f"cus_{uid}",
               "amount_total": 5000, "payment_intent": "pi_top",
               "metadata": {"pd_user_id": str(uid), "kind": "topup", "amount_cents": "5000"}}
    assert deliver(evt("checkout.session.completed", session)).json()["outcome"] == "topup credited"
    assert client.get("/api/me", headers=headers).json()["funded_credits"] == 5000   # $50 = 5,000 credits
    key = db.one("SELECT or_key_hash FROM users WHERE id=?", (uid,))["or_key_hash"]
    assert fakes.openrouter.keys[key]["limit"] == 50.0
    deliver(evt("charge.refunded", {"id": "ch_1", "payment_intent": "pi_top", "amount_refunded": 2000}))
    assert client.get("/api/me", headers=headers).json()["funded_credits"] == 3000
    deliver(evt("charge.refunded", {"id": "ch_1", "payment_intent": "pi_top", "amount_refunded": 5000}))
    assert client.get("/api/me", headers=headers).json()["funded_credits"] == 0
    assert fakes.openrouter.keys[key]["limit"] == 0.0


def test_unpaid_checkout_session_credits_nothing(fakes):
    headers, uid = account("unpaid")
    session = {"id": "cs_unpaid", "mode": "payment", "payment_status": "unpaid", "amount_total": 5000,
               "metadata": {"pd_user_id": str(uid), "kind": "topup"}}
    assert deliver(evt("checkout.session.completed", session)).json()["outcome"] == "ignored"
    assert client.get("/api/me", headers=headers).json()["funded_credits"] == 0


def test_openrouter_outage_never_loses_money(fakes, monkeypatch):
    headers, uid = account("outage")

    def down(*a, **k):
        raise ork.KeyError_("OpenRouter unreachable")
    monkeypatch.setattr(ork, "_mgmt", down)
    resp, _ = _subscribe_via_webhook(fakes, uid, sub_id="sub_O")
    assert "deferred" in resp.json()["outcome"]
    assert client.get("/api/me", headers=headers).json()["funded_credits"] == 1150    # ledger kept it
    monkeypatch.setattr(ork, "_mgmt", fakes.openrouter)
    ork.sync_limit(uid)                                                       # healed later
    assert list(fakes.openrouter.keys.values())[-1]["limit"] == 11.5


def test_demo_billing_closed_when_live():
    headers, _ = account("demo")
    os.environ["PD_DEMO_BILLING"] = "1"
    try:
        assert client.post("/api/subscribe", headers=headers, json={"plan": "go"}).status_code == 501
    finally:
        os.environ.pop("PD_DEMO_BILLING")


def test_webhook_registers_itself_once(fakes, monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET")
    monkeypatch.setenv("PD_PUBLIC_URL", "https://pink.example/")
    cfg = client.get("/api/payments/config").json()
    assert cfg["live"] is True and cfg["stripe_mode"] == "test", cfg["blockers"]
    client.get("/api/payments/config")
    assert len(fakes.stripe.webhooks) == 1
    hook = fakes.stripe.webhooks[0]
    assert hook["url"] == "https://pink.example/api/payments/webhook"
    assert set(hook["enabled_events"]) == set(payments.WEBHOOK_EVENTS)
    # The stored secret verifies deliveries; the old one no longer does.
    event = evt("checkout.session.completed", {"mode": "payment", "payment_status": "unpaid"})
    assert deliver(event, secret="whsec_auto_1").status_code == 200
    assert deliver(evt("charge.refunded", {}), secret=SECRET).status_code == 400


def test_webhook_not_registered_without_public_url(fakes, monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_other_account")
    monkeypatch.delenv("PD_PUBLIC_URL", raising=False)
    cfg = client.get("/api/payments/config").json()
    assert cfg["live"] is False and any("webhook" in b for b in cfg["blockers"])
    assert fakes.stripe.webhooks == []


def test_management_key_accepted_in_openrouter_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MANAGEMENT_KEY")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-mgmt-in-api-slot")
    monkeypatch.setattr(ork, "_kind_cache", {})
    monkeypatch.setattr(ork, "key_info", lambda k: {"ok": True, "management": True, "label": "m"})
    assert ork.management_key() == "sk-or-v1-mgmt-in-api-slot"
    assert ork.shared_inference_key() == ""          # never used for chat
    assert ork.configured()
    monkeypatch.setattr(ork, "_kind_cache", {})
    monkeypatch.setattr(ork, "key_info", lambda k: {"ok": True, "management": False, "label": "i"})
    assert ork.management_key() == "" and ork.shared_inference_key() == "sk-or-v1-mgmt-in-api-slot"


def test_test_mode_payments_never_fund_openrouter(fakes, monkeypatch):
    monkeypatch.delenv("PD_TEST_PAYMENTS_FUND_OPENROUTER")
    headers, uid = account("testcard")
    resp, _ = _subscribe_via_webhook(fakes, uid, sub_id="sub_testcard")
    assert resp.status_code == 200
    assert not any(c[0] == "POST" for c in fakes.openrouter.calls if c[1] == "/keys")   # no real key minted
    bal = client.get("/api/balance", headers=headers).json()
    assert bal["funded_cents"] == core.split_customer_cents(2299) and "not funded" in bal["source"]
    # A key minted earlier is clamped back to zero.
    monkeypatch.setenv("PD_TEST_PAYMENTS_FUND_OPENROUTER", "1")
    ork.sync_limit(uid)
    h = db.one("SELECT or_key_hash FROM users WHERE id=?", (uid,))["or_key_hash"]
    assert fakes.openrouter.keys[h]["limit"] > 0
    monkeypatch.delenv("PD_TEST_PAYMENTS_FUND_OPENROUTER")
    client.get("/api/balance", headers=headers)
    assert fakes.openrouter.keys[h]["limit"] == 0
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_fake")
    assert ork.real_money() and ork.target_cents(1150) == 1150
