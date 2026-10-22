"""Talks to the backend: fetch call context, post call results (interface contract)."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
from typing import Any

import httpx

from .models import CALL_INTENTS, CALL_STATUSES, TranscriptEntry

log = logging.getLogger(__name__)


def make_token(secret: str, call_id: int | str) -> str:
    """Hex HMAC-SHA256 of str(call_id) keyed with VOICE_AGENT_SECRET."""
    return hmac.new(secret.encode(), str(call_id).encode(), hashlib.sha256).hexdigest()


def verify_token(secret: str, call_id: int | str, token: str | None) -> bool:
    if not secret or not token:
        return False
    return hmac.compare_digest(make_token(secret, call_id).encode(),
                               token.strip().lower().encode("utf-8"))


def check_secret(secret: str, header_value: str | None) -> bool:
    return bool(secret) and header_value is not None and hmac.compare_digest(
        secret.encode(), header_value.encode())


def build_result_payload(
    *, status: str, intent: str | None = None, promised_date: Any = None, summary: str = "",
    transcript: list[TranscriptEntry] | None = None, duration_seconds: float = 0,
    recording_wav: bytes | None = None, error: str | None = None,
) -> dict[str, Any]:
    if status not in CALL_STATUSES:
        raise ValueError(f"bad status {status!r}")
    if intent is not None and intent not in CALL_INTENTS:
        raise ValueError(f"bad intent {intent!r}")
    payload: dict[str, Any] = {
        "status": status,
        "intent": intent,
        "promised_date": promised_date.isoformat() if hasattr(promised_date, "isoformat") else promised_date,
        "summary": summary,
        "transcript": [t.as_dict() for t in (transcript or [])],
        "duration_seconds": int(round(duration_seconds)),
        "error": error,
    }
    if recording_wav:
        payload["recording_wav_base64"] = base64.b64encode(recording_wav).decode("ascii")
    return payload


class BackendClient:
    def __init__(self, base_url: str, secret: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-Agent-Secret": secret}

    async def get_context(self, call_id: int) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{self.base_url}/api/internal/reminders/{call_id}/context",
                                 headers=self.headers)
            r.raise_for_status()
            return r.json()

    async def post_result(self, call_id: int, payload: dict[str, Any], attempts: int = 4) -> bool:
        url = f"{self.base_url}/api/internal/reminders/{call_id}/result"
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post(url, json=payload, headers=self.headers)
                if r.status_code < 300:
                    return True
                log.warning("Result POST for call %s got %s: %s", call_id, r.status_code, r.text[:200])
                if 400 <= r.status_code < 500 and r.status_code not in (408, 429):
                    break  # the backend rejected it; retrying will not help
            except httpx.HTTPError as exc:
                log.warning("Result POST for call %s failed (attempt %d): %s", call_id, attempt, exc)
            if attempt < attempts:
                await asyncio.sleep(2 ** attempt)
        log.error("Giving up posting result for call %s: status=%s intent=%s summary=%s",
                  call_id, payload.get("status"), payload.get("intent"), payload.get("summary"))
        return False
