"""aiohttp web.Application: GET /ws、POST /presence、POST /clear、GET /health。

受信した presence/clear を core.models で検証 → SourceRegistry へ反映 →
PresenceManager の再評価をトリガーする。契約の詳細は docs/PROTOCOL.md を参照。
"""
from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from aiohttp import web
from pydantic import ValidationError

from core.models import ClearEnvelope, PresenceEnvelope
from core.sources import SourceRegistry

logger = logging.getLogger(__name__)

RATE_LIMIT_MAX_MESSAGES = 10
RATE_LIMIT_WINDOW_SECONDS = 1.0


class DiscordStatusProvider(Protocol):
    @property
    def connected(self) -> bool: ...


class PresenceReevaluator(Protocol):
    @property
    def active_source_id(self) -> str | None: ...

    async def reevaluate(self) -> bool: ...


class RateLimiter:
    """簡易スライディングウィンドウのレート制限(接続/IP単位)。"""

    def __init__(
        self,
        max_messages: int = RATE_LIMIT_MAX_MESSAGES,
        window_seconds: float = RATE_LIMIT_WINDOW_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._max = max_messages
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[Any, deque[float]] = {}

    def allow(self, key: Any) -> bool:
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > self._window:
            hits.popleft()
        if len(hits) >= self._max:
            return False
        hits.append(now)
        return True


def _extract_token(request: web.Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[len("Bearer "):]
    return request.query.get("token")


def create_app(
    *,
    bridge_token: str,
    registry: SourceRegistry,
    presence_manager: PresenceReevaluator,
    discord_rpc: DiscordStatusProvider,
    ttl_seconds: float = 30.0,
    rate_limiter: RateLimiter | None = None,
) -> web.Application:
    app = web.Application()
    limiter = rate_limiter or RateLimiter()

    def _authorized(request: web.Request) -> bool:
        return _extract_token(request) == bridge_token

    async def _apply_presence(envelope: PresenceEnvelope, origin_conn: Any = None) -> None:
        registry.upsert(
            envelope.source_id,
            envelope.kind,
            envelope.data.model_dump(),
            name=envelope.source_name,
            ttl_seconds=ttl_seconds,
            origin_conn=origin_conn,
        )
        await presence_manager.reevaluate()

    async def _apply_clear(envelope: ClearEnvelope, origin_conn: Any = None) -> None:
        if envelope.source_id:
            registry.clear_source(envelope.source_id)
        elif origin_conn is not None:
            registry.expire_for_conn(origin_conn)
        else:
            for source in registry.all():
                registry.clear_source(source.source_id)
        await presence_manager.reevaluate()

    async def handle_ws(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)

        if not _authorized(request):
            await ws.close(code=4001, message=b"unauthorized")
            return ws

        await ws.send_json({"op": "ready"})

        async for msg in ws:
            if msg.type != web.WSMsgType.TEXT:
                continue
            if not limiter.allow(ws):
                await ws.send_json({"op": "error", "message": "rate limit exceeded"})
                continue

            try:
                payload = msg.json()
            except ValueError:
                await ws.send_json({"op": "error", "message": "invalid json"})
                continue

            op = payload.get("op")
            if op == "ping":
                await ws.send_json({"op": "pong"})
            elif op == "presence":
                try:
                    envelope = PresenceEnvelope.model_validate(payload)
                except ValidationError as exc:
                    await ws.send_json({"op": "error", "message": str(exc)})
                    continue
                await _apply_presence(envelope, origin_conn=ws)
                if envelope.seq is not None:
                    await ws.send_json({"op": "ack", "seq": envelope.seq})
            elif op == "clear":
                try:
                    envelope = ClearEnvelope.model_validate(payload)
                except ValidationError as exc:
                    await ws.send_json({"op": "error", "message": str(exc)})
                    continue
                await _apply_clear(envelope, origin_conn=ws)
            else:
                await ws.send_json({"op": "error", "message": f"unknown op: {op}"})

        registry.expire_for_conn(ws)
        await presence_manager.reevaluate()
        return ws

    async def handle_presence(request: web.Request) -> web.Response:
        if not _authorized(request):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        if not limiter.allow(request.remote):
            return web.json_response({"ok": False, "error": "rate limited"}, status=429)
        try:
            body = await request.json()
            envelope = PresenceEnvelope.model_validate(body)
        except (ValueError, ValidationError) as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

        await _apply_presence(envelope)
        return web.json_response({"ok": True})

    async def handle_clear(request: web.Request) -> web.Response:
        if not _authorized(request):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        body: dict[str, Any] = {}
        if request.body_exists:
            try:
                body = await request.json()
            except ValueError:
                body = {}
        try:
            envelope = ClearEnvelope.model_validate(body)
        except ValidationError as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

        await _apply_clear(envelope)
        return web.json_response({"ok": True})

    async def handle_health(request: web.Request) -> web.Response:
        if not _authorized(request):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        return web.json_response(
            {
                "status": "ok",
                "discord": "connected" if discord_rpc.connected else "disconnected",
                "active_source": presence_manager.active_source_id,
            }
        )

    app.router.add_get("/ws", handle_ws)
    app.router.add_post("/presence", handle_presence)
    app.router.add_post("/clear", handle_clear)
    app.router.add_get("/health", handle_health)
    return app
