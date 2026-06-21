"""SourceRegistry を調停して勝者を選び、mapper→discord_rpc へ送る。"""
from __future__ import annotations

import time
from typing import Any, Callable

from core.discord_rpc import DiscordRPC
from core.mapper import to_activity
from core.sources import Source, SourceRegistry


def select_active(sources: list[Source], now: float | None = None) -> Source | None:
    """有効・データあり・未失効の候補から勝者を1つ選ぶ。pin優先、次に(priority, updated_at)。"""
    candidates = [s for s in sources if s.is_candidate(now)]
    if not candidates:
        return None
    pinned = [s for s in candidates if s.pinned]
    pool = pinned if pinned else candidates
    return max(pool, key=lambda s: (s.priority, s.updated_at or 0.0))


class PresenceManager:
    def __init__(
        self,
        registry: SourceRegistry,
        discord_rpc: DiscordRPC,
        config: dict[str, Any],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._registry = registry
        self._discord_rpc = discord_rpc
        self._config = config
        self._clock = clock
        self._last_sent_activity: dict[str, Any] | None = None
        self._last_sent_at: float = 0.0
        self._active_source_id: str | None = None

    @property
    def active_source_id(self) -> str | None:
        return self._active_source_id

    async def reevaluate(self) -> bool:
        """調停し、必要なら Discord へ送信する。送信/clearを行ったら True を返す。"""
        now = self._clock()
        winner = select_active(self._registry.all(), now)

        if winner is None:
            self._active_source_id = None
            return await self._clear_if_needed()

        activity = to_activity(winner.kind, winner.data or {}, self._config)
        self._active_source_id = winner.source_id

        if activity is None:
            return await self._clear_if_needed()

        if activity == self._last_sent_activity:
            return False

        min_interval = self._config.get("min_update_interval", 15)
        if self._last_sent_activity is not None and now - self._last_sent_at < min_interval:
            return False

        sent = await self._discord_rpc.set_activity(activity)
        if sent:
            self._last_sent_activity = activity
            self._last_sent_at = now
        return sent

    async def _clear_if_needed(self) -> bool:
        if self._last_sent_activity is None:
            return False
        self._last_sent_activity = None
        return await self._discord_rpc.clear()
