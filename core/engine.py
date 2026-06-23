"""GUI に依存しないオーケストレータ(Bridge 本体)。

受信サーバ(aiohttp)・調停(PresenceManager)・Discord 送信(DiscordRPC)を結線し、
周期 tick で TTL 失効の反映と、レート制御で保留された更新の「合体フラッシュ」
(最新状態を間隔経過後に送る)を行う。GUI(gui/・app.py)はこの薄いビューとして載る。

GUI からの操作はこのクラスのメソッドを単一の asyncio ループ上で呼ぶ前提
(qasync により Qt と asyncio は同一ループ・同一スレッド)。
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any, Callable

from aiohttp import web
from pydantic import ValidationError

from config.store import ConfigStore
from core.discord_rpc import DiscordRPC
from core.mapper import to_activity
from core.models import ManualData
from core.presence_manager import PresenceManager
from core.receiver import create_app
from core.sources import Source, SourceRegistry

logger = logging.getLogger(__name__)

MANUAL_SOURCE_ID = "manual"
DEFAULT_TICK_INTERVAL = 5.0


class _NotifyingPresenceManager:
    """receiver(HTTP/WS)経由の reevaluate でも GUI リスナーへ通知する PresenceManager ラッパー。

    PresenceManager.reevaluate() は registry/active_source の変化を返り値(送信有無)でしか
    伝えないため、receiver 経由の更新だと GUI(Engine の listener)が呼ばれず一覧が古いままになる。
    """

    def __init__(self, presence_manager: PresenceManager, notify: Callable[[], None]) -> None:
        self._pm = presence_manager
        self._notify = notify

    @property
    def active_source_id(self) -> str | None:
        return self._pm.active_source_id

    async def reevaluate(self) -> bool:
        result = await self._pm.reevaluate()
        self._notify()
        return result


class Engine:
    def __init__(
        self,
        config: dict[str, Any],
        secrets: Any,
        store: ConfigStore | None = None,
        *,
        discord_rpc: DiscordRPC | None = None,
        registry: SourceRegistry | None = None,
        clock: Callable[[], float] | None = None,
        tick_interval: float = DEFAULT_TICK_INTERVAL,
    ) -> None:
        self._config = config
        self._secrets = secrets
        self._store = store
        self._tick_interval = tick_interval
        self._clock = clock or time.time
        self._registry = registry or SourceRegistry(settings_provider=self._persisted_source_settings)
        self._discord_rpc = discord_rpc or DiscordRPC(
            getattr(secrets, "discord_client_id", ""),
            on_state_change=self._handle_discord_state,
        )
        self._pm = PresenceManager(self._registry, self._discord_rpc, config, clock=self._clock)
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._tick_task: asyncio.Task[None] | None = None
        self._listeners: list[Callable[[], None]] = []
        self._notifying_pm = _NotifyingPresenceManager(self._pm, self._notify)

    # ---- 公開プロパティ(GUI/テスト用) ----
    @property
    def config(self) -> dict[str, Any]:
        return self._config

    @property
    def registry(self) -> SourceRegistry:
        return self._registry

    @property
    def presence_manager(self) -> PresenceManager:
        return self._pm

    @property
    def discord_connected(self) -> bool:
        return self._discord_rpc.connected

    @property
    def active_source_id(self) -> str | None:
        return self._pm.active_source_id

    # ---- ライフサイクル ----
    async def start(self) -> None:
        self._load_manual_source()
        self._discord_rpc.start()
        app = create_app(
            bridge_token=getattr(self._secrets, "bridge_token", ""),
            registry=self._registry,
            presence_manager=self._notifying_pm,
            discord_rpc=self._discord_rpc,
            ttl_seconds=self._config.get("ttl_seconds", 30),
        )
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        bind = self._config.get("bind", "127.0.0.1")
        port = self._config.get("port", 13520)
        self._site = web.TCPSite(self._runner, bind, port)
        await self._site.start()
        logger.info("受信サーバ起動: http://%s:%s", bind, port)
        self._tick_task = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        if self._tick_task is not None:
            self._tick_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tick_task
            self._tick_task = None
        if self._site is not None:
            await self._site.stop()
            self._site = None
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        await self._discord_rpc.stop()

    async def _tick_loop(self) -> None:
        """TTL 失効の反映と、保留更新の合体フラッシュ(最小間隔経過後の送出)。"""
        while True:
            await asyncio.sleep(self._tick_interval)
            self._reconcile_new_sources()
            if await self._pm.reevaluate():
                self._notify()

    # ---- GUI 操作 ----
    async def set_source_enabled(self, source_id: str, enabled: bool) -> None:
        self._registry.set_enabled(source_id, enabled)
        self._persist_source(source_id)
        await self._reevaluate_and_notify()

    async def set_source_priority(self, source_id: str, priority: int) -> None:
        self._registry.set_priority(source_id, priority)
        self._persist_source(source_id)
        await self._reevaluate_and_notify()

    async def set_source_pinned(self, source_id: str, pinned: bool) -> None:
        self._registry.set_pinned(source_id, pinned)
        if pinned:
            # pin は排他なので、他ソースの pinned=False への変化も永続化する。
            for s in self._registry.all():
                self._persist_source(s.source_id)
        else:
            self._persist_source(source_id)
        await self._reevaluate_and_notify()

    async def forget_source(self, source_id: str) -> None:
        self._registry.remove(source_id)
        self._config.get("sources", {}).pop(source_id, None)
        self._save()
        await self._reevaluate_and_notify()

    async def apply_manual(self, manual: dict[str, Any]) -> None:
        """手動モードを反映する。検証エラーは ValidationError として呼び出し元へ返す。"""
        data = ManualData.model_validate(manual).model_dump()
        self._config["manual"] = data
        self._save()
        self._registry.upsert(MANUAL_SOURCE_ID, "manual", data, name=self._manual_name())
        await self._reevaluate_and_notify()

    async def clear_manual(self) -> None:
        self._registry.clear_source(MANUAL_SOURCE_ID)
        await self._reevaluate_and_notify()

    # ---- 状態通知(GUI) ----
    def add_listener(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def snapshot(self) -> dict[str, Any]:
        """GUI 描画用の現在状態。副作用なし。"""
        now = self._clock()
        sources: list[dict[str, Any]] = []
        active_id = self._pm.active_source_id
        for s in self._registry.all():
            sources.append(
                {
                    "source_id": s.source_id,
                    "name": s.name,
                    "kind": s.kind,
                    "enabled": s.enabled,
                    "priority": s.priority,
                    "pinned": s.pinned,
                    "has_data": s.data is not None,
                    "stale": s.data is None or s.is_expired(now),
                    "is_active": s.source_id == active_id,
                }
            )
        sources.sort(key=lambda d: (-d["priority"], d["name"]))

        preview = None
        active = self._registry.get(active_id) if active_id else None
        if active is not None and active.data is not None:
            preview = to_activity(active.kind, active.data, self._config)

        return {
            "discord_connected": self._discord_rpc.connected,
            "active_source_id": active_id,
            "sources": sources,
            "preview": preview,
        }

    # ---- 内部 ----
    def _persisted_source_settings(self, source_id: str) -> dict[str, Any] | None:
        return self._config.get("sources", {}).get(source_id)

    def _manual_name(self) -> str:
        settings = self._persisted_source_settings(MANUAL_SOURCE_ID) or {}
        return settings.get("name", "手動")

    def _load_manual_source(self) -> None:
        manual = self._config.get("manual")
        if not manual:
            return
        try:
            data = ManualData.model_validate(manual).model_dump()
        except ValidationError:
            logger.warning("config の manual データが不正なため読み込みをスキップします")
            return
        self._registry.upsert(MANUAL_SOURCE_ID, "manual", data, name=self._manual_name())

    @staticmethod
    def _source_settings_dict(s: Source) -> dict[str, Any]:
        return {
            "name": s.name,
            "enabled": s.enabled,
            "priority": s.priority,
            "pinned": s.pinned,
        }

    def _reconcile_new_sources(self) -> None:
        """feed で初出したソースを config に永続化する(GUI で管理できるように)。"""
        sources_cfg = self._config.setdefault("sources", {})
        dirty = False
        for s in self._registry.all():
            if s.kind == "manual":
                continue
            if s.source_id not in sources_cfg:
                sources_cfg[s.source_id] = self._source_settings_dict(s)
                dirty = True
        if dirty:
            self._save()

    def _persist_source(self, source_id: str) -> None:
        s = self._registry.get(source_id)
        if s is None or s.kind == "manual":
            return
        self._config.setdefault("sources", {})[source_id] = self._source_settings_dict(s)
        self._save()

    def _save(self) -> None:
        if self._store is not None:
            self._store.save(self._config)

    async def _reevaluate_and_notify(self) -> None:
        await self._pm.reevaluate()
        self._notify()

    def _notify(self) -> None:
        for cb in self._listeners:
            try:
                cb()
            except Exception:  # GUI 側の例外でループを止めない
                logger.exception("listener callback error")

    def _handle_discord_state(self, state: str) -> None:
        self._notify()
