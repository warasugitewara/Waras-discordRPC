"""ソース(feed/manual)を source_id で管理する SourceRegistry。"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Literal

SourceKind = Literal["generic", "music", "manual"]

# 初出ソースに適用する永続設定を返す provider。未知なら None。
SettingsProvider = Callable[[str], "dict[str, Any] | None"]


@dataclass
class Source:
    source_id: str
    name: str
    kind: SourceKind
    enabled: bool = True
    priority: int = 0
    pinned: bool = False
    data: dict[str, Any] | None = None
    updated_at: float | None = None
    expires_at: float | None = None
    origin_conn: Any | None = None

    def is_expired(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now if now is not None else time.time()) >= self.expires_at

    def is_candidate(self, now: float | None = None) -> bool:
        return self.enabled and self.data is not None and not self.is_expired(now)


class SourceRegistry:
    """すべての既知ソース(feed + manual)を保持する。"""

    def __init__(self, settings_provider: SettingsProvider | None = None) -> None:
        self._sources: dict[str, Source] = {}
        self._settings_provider = settings_provider

    def upsert(
        self,
        source_id: str,
        kind: SourceKind,
        data: dict[str, Any],
        name: str | None = None,
        ttl_seconds: float | None = None,
        origin_conn: Any | None = None,
    ) -> Source:
        """feed受信ごとに呼ばれる。未知の source_id は自動登録する。"""
        now = time.time()
        source = self._sources.get(source_id)
        if source is None:
            # 初出時のみ表示名を決める(永続設定 > feedのsource_name > source_id)。
            # 以後は GUI でのリネームを保持するため feed の name で上書きしない。
            source = Source(source_id=source_id, name=name or source_id, kind=kind)
            self._apply_persisted_settings(source)
            self._sources[source_id] = source
        source.kind = kind
        source.data = data
        source.updated_at = now
        source.expires_at = now + ttl_seconds if ttl_seconds is not None else None
        source.origin_conn = origin_conn
        return source

    def _apply_persisted_settings(self, source: Source) -> None:
        if self._settings_provider is None:
            return
        settings = self._settings_provider(source.source_id)
        if not settings:
            return
        if settings.get("name"):
            source.name = settings["name"]
        source.enabled = settings.get("enabled", source.enabled)
        source.priority = settings.get("priority", source.priority)
        source.pinned = settings.get("pinned", source.pinned)

    def get(self, source_id: str) -> Source | None:
        return self._sources.get(source_id)

    def all(self) -> list[Source]:
        return list(self._sources.values())

    def set_enabled(self, source_id: str, enabled: bool) -> None:
        if source_id in self._sources:
            self._sources[source_id].enabled = enabled

    def set_priority(self, source_id: str, priority: int) -> None:
        if source_id in self._sources:
            self._sources[source_id].priority = priority

    def set_pinned(self, source_id: str, pinned: bool) -> None:
        if source_id in self._sources:
            self._sources[source_id].pinned = pinned

    def remove(self, source_id: str) -> None:
        """GUIの「忘れる」操作。"""
        self._sources.pop(source_id, None)

    def clear_source(self, source_id: str) -> None:
        """`/clear` で指定された source_id のdataを即時失効させる。"""
        source = self._sources.get(source_id)
        if source is not None:
            source.data = None
            source.expires_at = None

    def expire_for_conn(self, origin_conn: Any) -> None:
        """WS切断時、その接続が供給したソースを即時失効させる(`/clear` 省略=全と同義)。"""
        for source in self._sources.values():
            if source.origin_conn is origin_conn:
                source.data = None
                source.expires_at = None

    def candidates(self, now: float | None = None) -> list[Source]:
        return [s for s in self._sources.values() if s.is_candidate(now)]
