"""AudioSocket framing, HMAC tokens, result payload shape, LLM output validation."""
import asyncio
import base64
import hashlib
import hmac
import struct
import uuid
from datetime import date

import pytest

from voice_agent.asterisk_ari import status_for_cause
from voice_agent.audiosocket import (
    KIND_AUDIO, KIND_HANGUP, KIND_UUID, AudioSocketServer, decode_frames, encode_frame, encode_uuid,
)
from voice_agent.llm import OllamaClassifier, validate_llm_output
from voice_agent.models import TranscriptEntry
from voice_agent.result_client import build_result_payload, check_secret, make_token, verify_token

from .conftest import make_ctx


def test_frame_roundtrip():
    audio = bytes(range(256)) + bytes(64)
    data = bytearray(encode_frame(KIND_AUDIO, audio) + encode_frame(KIND_HANGUP))
    assert data[:3] == bytes([0x10]) + struct.pack(">H", 320)
    partial = bytearray(data[:100])
    assert decode_frames(partial) == [] and len(partial) == 100  # incomplete frame stays
    frames = decode_frames(data)
    assert [(f.kind, f.payload) for f in frames] == [(KIND_AUDIO, audio), (KIND_HANGUP, b"")]
    assert data == bytearray()


def test_uuid_frame():
    u = str(uuid.uuid4())
    frame = encode_uuid(u)
    assert frame[0] == KIND_UUID and struct.unpack(">H", frame[1:3])[0] == 16
    assert uuid.UUID(bytes=frame[3:]) == uuid.UUID(u)


def test_audiosocket_server_maps_uuid_to_call():
    async def scenario():
        server = AudioSocketServer("127.0.0.1", 0)
        await server.start()
        port = server._server.sockets[0].getsockname()[1]
        call_uuid = str(uuid.uuid4())
        fut = server.expect(call_uuid)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(encode_uuid(call_uuid) + encode_frame(KIND_AUDIO, b"\x01\x00" * 160))
        await writer.drain()
        conn = await asyncio.wait_for(fut, 2)
        assert await conn.read() == b"\x01\x00" * 160
        await conn.write(b"\x00" * 640)  # split into two 320-byte frames
        got = await reader.readexactly(2 * 323)
        assert [f.kind for f in decode_frames(bytearray(got))] == [KIND_AUDIO, KIND_AUDIO]
        writer.write(encode_frame(KIND_HANGUP))
        await writer.drain()
        assert await conn.read() is None
        writer.close()
        await server.stop()

    asyncio.run(scenario())


def test_hmac_token():
    secret = "s3cret"
    expected = hmac.new(b"s3cret", b"42", hashlib.sha256).hexdigest()
    assert make_token(secret, 42) == expected
    assert verify_token(secret, "42", expected)
    assert verify_token(secret, 42, expected.upper())
    assert not verify_token(secret, 43, expected)
    assert not verify_token("", 42, make_token("", 42))
    assert not verify_token(secret, 42, None)
    assert not verify_token(secret, 42, "ünïcode")
    assert check_secret("abc", "abc") and not check_secret("abc", "abd") and not check_secret("", "")


def test_result_payload_matches_contract():
    p = build_result_payload(
        status="answered", intent="will_pay", promised_date=date(2026, 10, 24),
        summary="Customer will pay.", duration_seconds=47.6, recording_wav=b"RIFF....",
        transcript=[TranscriptEntry("agent", "Hello", 0.0), TranscriptEntry("customer", "ok", 6.234)],
    )
    assert set(p) == {"status", "intent", "promised_date", "summary", "transcript",
                      "duration_seconds", "recording_wav_base64", "error"}
    assert p["promised_date"] == "2026-10-24" and p["duration_seconds"] == 48
    assert p["transcript"][1] == {"speaker": "customer", "text": "ok", "ts": 6.23}
    assert base64.b64decode(p["recording_wav_base64"]) == b"RIFF...."
    assert p["error"] is None
    q = build_result_payload(status="no_answer")
    assert q["intent"] is None and q["promised_date"] is None and "recording_wav_base64" not in q
    with pytest.raises(ValueError):
        build_result_payload(status="weird")
    with pytest.raises(ValueError):
        build_result_payload(status="answered", intent="maybe")


def test_hangup_causes():
    assert status_for_cause(17) == "busy"
    assert status_for_cause(19) == "no_answer"
    assert status_for_cause(None) == "no_answer"
    assert status_for_cause(1) == "failed"


def test_validate_llm_output():
    ctx = make_ctx("te")
    ok = validate_llm_output({"intent": "will_pay", "promised_date": "2026-10-23",
                              "paid_method": "upi", "note": "will pay tomorrow"}, "రేపు", ctx)
    assert ok.intent == "will_pay" and ok.promised_date == date(2026, 10, 23) and ok.paid_method == "UPI"
    past = validate_llm_output({"intent": "will_pay", "promised_date": "2026-01-01"}, "x", ctx)
    assert past.promised_date is None
    paid = validate_llm_output({"intent": "paid_claimed", "promised_date": "2026-10-23"}, "x", ctx)
    assert paid.promised_date is None
    assert validate_llm_output({"intent": "pay_soon"}, "x", ctx) is None
    assert validate_llm_output(["will_pay"], "x", ctx) is None


def test_classifier_falls_back_when_ollama_down():
    clf = OllamaClassifier("http://127.0.0.1:9", "none", timeout=0.5)
    c = clf("రేపు కడతాను", make_ctx("te"), "payment_answer")
    assert c.source == "heuristic" and c.intent == "will_pay" and c.promised_date == date(2026, 10, 23)
