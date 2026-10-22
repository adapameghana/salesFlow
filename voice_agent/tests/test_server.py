"""HTTP/WS endpoints with models, Asterisk and the backend stubbed out."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from voice_agent import server
from voice_agent.config import Settings
from voice_agent.result_client import make_token


@pytest.fixture
def client(monkeypatch, tmp_path):
    placed = []

    async def fake_run_phone_call(svc, req):
        placed.append(req)

    monkeypatch.setattr(server, "run_phone_call", fake_run_phone_call)
    settings = Settings(voice_agent_secret="topsecret", preload_models=False, audiosocket_port=0,
                        audiosocket_host="127.0.0.1", cache_dir=tmp_path, vad_backend="energy",
                        ari_url="http://127.0.0.1:9", ollama_url="http://127.0.0.1:9")
    with TestClient(server.create_app(settings)) as c:
        c.placed = placed
        yield c


BODY = {"call_id": 42, "phone": "9876543210",
        "context": {"order_number": "ORD-2026-0007", "language": "te", "balance": 4250.0}}


def test_calls_requires_secret(client):
    assert client.post("/calls", json=BODY).status_code == 401
    assert client.post("/calls", json=BODY, headers={"X-Agent-Secret": "wrong"}).status_code == 401


def test_calls_accepted(client):
    r = client.post("/calls", json=BODY, headers={"X-Agent-Secret": "topsecret"})
    assert r.status_code == 202 and r.json() == {"accepted": True}


def test_calls_rejects_bad_phone(client):
    bad = dict(BODY, phone="+919876543210")
    assert client.post("/calls", json=bad, headers={"X-Agent-Secret": "topsecret"}).status_code == 422


def test_health(client):
    h = client.get("/health").json()
    assert h["asterisk"] is False and h["ollama"] is False
    assert h["models"]["stt"] is False and h["audiosocket"] is True


def test_ws_rejects_bad_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/test?call_id=42&token=nope") as ws:
            ws.receive_text()


def test_ws_reports_missing_context(client):
    token = make_token("topsecret", 42)
    with client.websocket_connect(f"/test?call_id=42&token={token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "end" and msg["intent"] is None
