"""pypresence AioPresence のラッパ。

connect/再接続(指数バックオフ)・set_activity・clear・接続状態(connected/disconnected)
通知を提供する。Discord未起動時は接続できないため、バックグラウンドの監視タスクが
定期的に再接続を試みる。
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Literal, Protocol

from pypresence import AioPresence
from pypresence.exceptions import PyPresenceException

logger = logging.getLogger(__name__)

ConnectionState = Literal["connected", "disconnected"]

# pypresence.types.ActivityType の数値と PROTOCOL.md の activity_type 文字列の対応。
ACTIVITY_TYPE_MAP: dict[str, int] = {
    "playing": 0,
    "listening": 2,
    "watching": 3,
    "competing": 5,
}

RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 30.0
SUPERVISOR_POLL_INTERVAL = 1.0

_CONNECTION_ERRORS = (PyPresenceException, OSError)


class PresenceClient(Protocol):
    async def connect(self) -> None: ...
    async def update(self, **kwargs: Any) -> Any: ...
    async def clear(self) -> Any: ...


class DiscordRPC:
    def __init__(
        self,
        client_id: str,
        on_state_change: Any = None,
        presence_client: PresenceClient | None = None,
    ) -> None:
        self._client_id = client_id
        self._on_state_change = on_state_change
        self._presence: PresenceClient = presence_client or AioPresence(client_id)
        self._connected = False
        self._closing = False
        self._supervisor_task: asyncio.Task[None] | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        """接続監視タスクを起動する(未接続なら接続、切断時は再接続)。"""
        self._closing = False
        if self._supervisor_task is None or self._supervisor_task.done():
            self._supervisor_task = asyncio.create_task(self._supervisor())

    async def stop(self) -> None:
        self._closing = True
        if self._supervisor_task is not None:
            self._supervisor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._supervisor_task
            self._supervisor_task = None
        if self._connected:
            with contextlib.suppress(*_CONNECTION_ERRORS):
                await self._presence.clear()
        self._set_connected(False)

    async def set_activity(self, activity: dict[str, Any]) -> bool:
        """activity dict を Discord へ送信する。失敗時は disconnected を通知し False を返す。"""
        if not self._connected:
            # 未接続のまま update() を叩くと pypresence が捕捉対象外の例外
            # (writer 未初期化など)を投げうるため、接続前は送らない。
            return False
        payload = dict(activity)
        if "activity_type" in payload and isinstance(payload["activity_type"], str):
            payload["activity_type"] = ACTIVITY_TYPE_MAP[payload["activity_type"]]
        try:
            await self._presence.update(**payload)
            return True
        except _CONNECTION_ERRORS as exc:
            logger.warning("activity送信失敗: %s", exc)
            self._set_connected(False)
            return False

    async def clear(self) -> bool:
        if not self._connected:
            return False
        try:
            await self._presence.clear()
            return True
        except _CONNECTION_ERRORS as exc:
            logger.warning("clear失敗: %s", exc)
            self._set_connected(False)
            return False

    async def _supervisor(self) -> None:
        delay = RECONNECT_BASE_DELAY
        while not self._closing:
            if not self._connected:
                try:
                    await self._presence.connect()
                    self._set_connected(True)
                    delay = RECONNECT_BASE_DELAY
                except _CONNECTION_ERRORS as exc:
                    logger.warning("Discord接続失敗、%.1f秒後に再試行: %s", delay, exc)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, RECONNECT_MAX_DELAY)
                    continue
            await asyncio.sleep(SUPERVISOR_POLL_INTERVAL)

    def _set_connected(self, value: bool) -> None:
        if value != self._connected:
            self._connected = value
            if self._on_state_change is not None:
                self._on_state_change("connected" if value else "disconnected")
