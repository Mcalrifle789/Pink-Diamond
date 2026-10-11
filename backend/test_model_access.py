"""Model switching + OpenRouter gating (update spec).

Run from backend/:  python -m pytest -q test_model_access.py
"""

import os
import tempfile

os.environ["PD_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["PD_DEMO_BILLING"] = "1"
os.environ.pop("OPENROUTER_API_KEY", None)

import database as db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

db.init_db()
client = TestClient(main.app)


def _account(name: str) -> dict:
    token = client.post("/api/register", json={"username": name, "email": f"{name}@pd.test", "password": "pw123456"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_tokens_verify():
    headers = _account("tok")
    assert client.get("/api/me", headers=headers).status_code == 200


def test_free_account_never_reaches_openrouter():
    headers = _account("free")
    models = client.get("/api/models", headers=headers).json()
    assert models["subscribed"] is False
    assert models["default"] == main.HOUSE_MODEL
    assert all(m["locked"] for m in models["models"] if m["provider"] == "openrouter")
    for model in (None, main.HOUSE_MODEL, "openai/gpt-5.5"):
        resp = client.post("/api/chat", headers=headers, json={"message": "hi", "model": model})
        assert resp.status_code == 402


def test_guest_sees_locked_catalog():
    models = client.get("/api/models").json()
    assert models["subscribed"] is False
    assert any(m["provider"] == "openrouter" and m["locked"] for m in models["models"])


def test_subscriber_can_switch_models():
    headers = _account("paid")
    assert client.post("/api/subscribe", headers=headers, json={"plan": "plus"}).status_code == 200
    models = client.get("/api/models", headers=headers).json()
    assert models["subscribed"] is True
    assert not any(m["locked"] for m in models["models"])
    assert main._resolve_model("openai/gpt-5.5", True, False) == "openai/gpt-5.5"
    assert main._resolve_model(None, True, False) == main.DEFAULT_MODEL
    # Gate passes; with no key configured the proxy reports 503, not 402.
    resp = client.post("/api/chat", headers=headers, json={"message": "hi", "model": "x-ai/grok-4.7"})
    assert resp.status_code == 503


def test_unknown_model_rejected_for_subscriber():
    headers = _account("paid2")
    client.post("/api/subscribe", headers=headers, json={"plan": "go"})
    resp = client.post("/api/chat", headers=headers, json={"message": "hi", "model": "made/up"})
    assert resp.status_code == 400


def test_billing_closed_without_demo_flag():
    headers = _account("closed")
    os.environ.pop("PD_DEMO_BILLING")
    try:
        assert client.post("/api/subscribe", headers=headers, json={"plan": "max"}).status_code == 501
        assert client.post("/api/topup", headers=headers, json={"dollars": 5}).status_code == 501
    finally:
        os.environ["PD_DEMO_BILLING"] = "1"


def test_openrouter_status_without_key():
    status = client.get("/api/openrouter/status").json()
    assert status == {"configured": False, "inference_ready": False,
                      "detail": "OPENROUTER_API_KEY is not set in this environment"}
