"""SourceRegistry を調停して勝者を選び、mapper→discord_rpc へ送る。"""
from __future__ import annotations

import copy
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
        # 送信済みを「勝者の論理データ」で記録する。mapper は music の進捗計算に
        # 実時刻を使うため、マップ後 activity で比較すると同一曲でも毎回ズレて
        # 不要に再送される。送信判定は data の変化(=曲変更/再生停止/シーク)で行う。
        self._last_sent_source_id: str | None = None
        self._last_sent_data: dict[str, Any] | None = None
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

        self._active_source_id = winner.source_id
        activity = to_activity(winner.kind, winner.data or {}, self._config)

        if activity is None:
            return await self._clear_if_needed()

        unchanged = (
            winner.source_id == self._last_sent_source_id
            and winner.data == self._last_sent_data
        )
        if unchanged:
            return False

        min_interval = self._config.get("min_update_interval", 15)
        if self._last_sent_source_id is not None and now - self._last_sent_at < min_interval:
            return False

        sent = await self._discord_rpc.set_activity(activity)
        if sent:
            self._last_sent_source_id = winner.source_id
            self._last_sent_data = copy.deepcopy(winner.data)
            self._last_sent_at = now
        return sent

    async def _clear_if_needed(self) -> bool:
        if self._last_sent_source_id is None:
            return False
        self._last_sent_source_id = None
        self._last_sent_data = None
        return await self._discord_rpc.clear()
