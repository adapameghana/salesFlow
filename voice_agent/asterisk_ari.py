"""Originate calls through the Asterisk REST Interface (ARI) and wait for the outcome.

The originated channel runs the dialplan context (Answer + AudioSocket) once the
customer picks up, so "answered" means the AudioSocket connection for our UUID
arrived. If the channel disappears first, the hangup cause tells busy from no
answer; that cause comes from the ARI event WebSocket (ChannelDestroyed), with
plain polling of the channel as a fallback.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

# Q.850 hangup causes.
BUSY_CAUSES = {17, 21}  # user busy, call rejected
NO_ANSWER_CAUSES = {16, 18, 19, 20, 31}  # normal clearing before answer, no response, no answer


@dataclass
class OriginateResult:
    status: str  # answered | no_answer | busy | failed
    connection: Any = None  # AudioSocketConnection when answered
    error: str | None = None


def status_for_cause(cause: int | None) -> str:
    if cause in BUSY_CAUSES:
        return "busy"
    if cause in NO_ANSWER_CAUSES or cause is None:
        return "no_answer"
    return "failed"


class AriClient:
    def __init__(self, url: str, user: str, password: str, app: str):
        self.url = url.rstrip("/")
        self.auth = (user, password)
        self.app = app

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=f"{self.url}/ari", auth=self.auth, timeout=10)

    async def reachable(self) -> bool:
        try:
            async with self._client() as client:
                r = await client.get("/asterisk/info")
                return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def hangup(self, channel_id: str) -> None:
        try:
            async with self._client() as client:
                await client.delete(f"/channels/{channel_id}")
        except httpx.HTTPError:
            pass

    async def originate_and_wait(
        self, *, endpoint: str, context: str, extension: str, call_uuid: str,
        answered: asyncio.Future, ring_timeout: int, caller_id: str = "",
    ) -> OriginateResult:
        """Place the call and wait until it is answered (AudioSocket connected) or ends."""
        params: dict[str, Any] = {
            "endpoint": endpoint, "context": context, "extension": extension, "priority": 1,
            "timeout": ring_timeout, "channelId": call_uuid,
        }
        if caller_id:
            params["callerId"] = caller_id
        body = {"variables": {"CALL_UUID": call_uuid}}

        events = _ChannelEvents(self, call_uuid)
        await events.start()  # subscribe before originating so no event is missed
        try:
            async with self._client() as client:
                try:
                    r = await client.post("/channels", params=params, json=body)
                except httpx.HTTPError as exc:
                    return OriginateResult("failed", error=f"ARI originate failed: {exc}")
                if r.status_code >= 300:
                    return OriginateResult("failed", error=f"ARI originate {r.status_code}: {r.text[:200]}")
                await events.subscribe()
                deadline = asyncio.get_running_loop().time() + ring_timeout + 15
                while True:
                    if answered.done():
                        return OriginateResult("answered", connection=answered.result())
                    if events.destroyed:
                        # Give a just-answered AudioSocket connection a moment to win the race.
                        await asyncio.sleep(0.3)
                        if answered.done():
                            return OriginateResult("answered", connection=answered.result())
                        return OriginateResult(status_for_cause(events.cause))
                    if asyncio.get_running_loop().time() > deadline:
                        await self.hangup(call_uuid)
                        return OriginateResult("no_answer")
                    if not events.connected:  # fallback: poll the channel
                        try:
                            pr = await client.get(f"/channels/{call_uuid}")
                            if pr.status_code == 404:
                                events.destroyed = True
                                continue
                        except httpx.HTTPError:
                            pass
                    try:
                        await asyncio.wait_for(asyncio.shield(answered), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass
        finally:
            await events.stop()


class _ChannelEvents:
    """Listens on the ARI event WebSocket for our channel's ChannelDestroyed (with cause)."""

    def __init__(self, ari: AriClient, channel_id: str):
        self.ari = ari
        self.channel_id = channel_id
        self.connected = False
        self.destroyed = False
        self.cause: int | None = None
        self._task: asyncio.Task | None = None
        self._ws: Any = None

    async def start(self) -> None:
        try:
            import websockets  # lazy: only needed with a real Asterisk
            ws_url = self.ari.url.replace("http", "ws", 1) + "/ari/events"
            user, password = self.ari.auth
            self._ws = await asyncio.wait_for(websockets.connect(
                f"{ws_url}?app={self.ari.app}&api_key={user}:{password}"), timeout=5)
            self.connected = True
            self._task = asyncio.create_task(self._listen())
        except Exception as exc:  # polling still works without events
            log.info("ARI events unavailable (%s); polling channel state instead", exc)

    async def subscribe(self) -> None:
        """Ask ARI to send this (dialplan, non-Stasis) channel's events to our app."""
        if not self.connected:
            return
        try:
            async with self.ari._client() as client:
                await client.post(f"/applications/{self.ari.app}/subscription",
                                  params={"eventSource": f"channel:{self.channel_id}"})
        except httpx.HTTPError as exc:
            log.info("ARI subscription failed: %s", exc)

    async def _listen(self) -> None:
        try:
            async for message in self._ws:
                event = json.loads(message)
                channel = event.get("channel") or {}
                if channel.get("id") != self.channel_id:
                    continue
                if event.get("type") in ("ChannelDestroyed", "ChannelHangupRequest"):
                    cause = event.get("cause")
                    self.cause = int(cause) if cause is not None else self.cause
                    if event["type"] == "ChannelDestroyed":
                        self.destroyed = True
                        return
        except Exception as exc:
            log.info("ARI event stream closed: %s", exc)
            self.connected = False

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
