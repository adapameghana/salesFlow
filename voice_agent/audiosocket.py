"""Asterisk AudioSocket protocol: a TCP server that carries call audio.

Each frame is: 1 byte type, 2 bytes big-endian payload length, payload.
  0x00 hangup (no payload), 0x01 UUID (16 bytes), 0x10 audio (8 kHz signed
  linear 16-bit mono, little endian), 0xff error.
The dialplan runs AudioSocket(${CALL_UUID},host:9092) once the call is answered;
the first frame is the UUID, which maps the connection back to our call.
"""
from __future__ import annotations

import asyncio
import logging
import struct
import uuid as uuidlib
from dataclasses import dataclass

log = logging.getLogger(__name__)

KIND_HANGUP = 0x00
KIND_UUID = 0x01
KIND_AUDIO = 0x10
KIND_ERROR = 0xFF

SAMPLE_RATE = 8000
FRAME_BYTES = 320  # 20 ms of 8 kHz 16-bit audio
MAX_PAYLOAD = 0xFFFF


@dataclass
class Frame:
    kind: int
    payload: bytes = b""


def encode_frame(kind: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("AudioSocket payload too large")
    return struct.pack(">BH", kind, len(payload)) + payload


def encode_uuid(call_uuid: str) -> bytes:
    return encode_frame(KIND_UUID, uuidlib.UUID(call_uuid).bytes)


def decode_frames(buffer: bytearray) -> list[Frame]:
    """Pop all complete frames from the front of buffer (incomplete data stays)."""
    frames = []
    while len(buffer) >= 3:
        kind, length = struct.unpack(">BH", buffer[:3])
        if len(buffer) < 3 + length:
            break
        frames.append(Frame(kind, bytes(buffer[3:3 + length])))
        del buffer[:3 + length]
    return frames


async def read_frame(reader: asyncio.StreamReader) -> Frame:
    header = await reader.readexactly(3)
    kind, length = struct.unpack(">BH", header)
    payload = await reader.readexactly(length) if length else b""
    return Frame(kind, payload)


class AudioSocketConnection:
    """One answered call. Implements the pipeline Transport interface."""

    sample_rate = SAMPLE_RATE
    chunk_ms = 20
    lead_ms = 60  # how far ahead of real time we may send audio

    def __init__(self, call_uuid: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.call_uuid = call_uuid
        self._reader = reader
        self._writer = writer
        self.closed = False

    async def read(self) -> bytes | None:
        """Next chunk of caller audio, or None once the call has ended."""
        while not self.closed:
            try:
                frame = await read_frame(self._reader)
            except (asyncio.IncompleteReadError, ConnectionError):
                self.closed = True
                return None
            if frame.kind == KIND_AUDIO:
                return frame.payload
            if frame.kind == KIND_HANGUP:
                self.closed = True
                return None
            if frame.kind == KIND_ERROR:
                log.warning("AudioSocket error frame on %s: %s", self.call_uuid, frame.payload.hex())
        return None

    async def write(self, pcm: bytes) -> None:
        if self.closed:
            return
        try:
            for i in range(0, len(pcm), FRAME_BYTES):
                self._writer.write(encode_frame(KIND_AUDIO, pcm[i:i + FRAME_BYTES]))
            await self._writer.drain()
        except ConnectionError:
            self.closed = True

    async def event(self, payload: dict) -> None:  # phone calls have no side channel
        return None

    async def hangup(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self._writer.write(encode_frame(KIND_HANGUP))
            await self._writer.drain()
        except ConnectionError:
            pass
        finally:
            self._writer.close()


class AudioSocketServer:
    """Accepts Asterisk connections and hands each to whoever is waiting for its UUID."""

    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self._waiting: dict[str, asyncio.Future[AudioSocketConnection]] = {}
        self._server: asyncio.base_events.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        log.info("AudioSocket listening on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    def expect(self, call_uuid: str) -> asyncio.Future[AudioSocketConnection]:
        fut: asyncio.Future[AudioSocketConnection] = asyncio.get_running_loop().create_future()
        self._waiting[str(uuidlib.UUID(call_uuid))] = fut
        return fut

    def forget(self, call_uuid: str) -> None:
        self._waiting.pop(str(uuidlib.UUID(call_uuid)), None)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            frame = await asyncio.wait_for(read_frame(reader), timeout=5)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError):
            writer.close()
            return
        if frame.kind != KIND_UUID or len(frame.payload) != 16:
            log.warning("AudioSocket connection did not start with a UUID frame")
            writer.close()
            return
        call_uuid = str(uuidlib.UUID(bytes=frame.payload))
        fut = self._waiting.pop(call_uuid, None)
        if fut is None or fut.done():
            log.warning("Unexpected AudioSocket call %s; hanging up", call_uuid)
            writer.write(encode_frame(KIND_HANGUP))
            writer.close()
            return
        conn = AudioSocketConnection(call_uuid, reader, writer)
        fut.set_result(conn)
        # Keep this handler alive until the session closes the connection.
        while not conn.closed and not writer.is_closing():
            await asyncio.sleep(0.5)
