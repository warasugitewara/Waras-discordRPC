import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from config.store import ConfigStore
from core.engine import MANUAL_SOURCE_ID, Engine
from core.sources import SourceRegistry


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeSecrets:
    bridge_token = "tok"
    discord_client_id = "123"


def make_engine(config=None, *, clock=None, tick_interval=0.01, store=None):
    discord_rpc = AsyncMock()
    discord_rpc.set_activity.return_value = True
    discord_rpc.clear.return_value = True
    discord_rpc.connected = True
    discord_rpc.start = MagicMock()  # start() は同期メソッド
    registry = SourceRegistry()
    engine = Engine(
        config if config is not None else {},
        FakeSecrets(),
        store=store,
        discord_rpc=discord_rpc,
        registry=registry,
        clock=clock,
        tick_interval=tick_interval,
    )
    return engine, discord_rpc, registry


async def test_gui_enable_disable_changes_arbitration():
    engine, discord_rpc, registry = make_engine()
    registry.upsert("a", "generic", {"details": "a"})
    registry.upsert("b", "generic", {"details": "b"})
    registry.set_priority("b", 10)
    await engine._reevaluate_and_notify()
    assert engine.active_source_id == "b"

    await engine.set_source_enabled("b", False)

    assert engine.active_source_id == "a"


async def test_gui_pin_overrides_priority():
    engine, discord_rpc, registry = make_engine()
    registry.upsert("a", "generic", {"details": "a"})
    registry.upsert("b", "generic", {"details": "b"})
    registry.set_priority("b", 10)

    await engine.set_source_pinned("a", True)

    assert engine.active_source_id == "a"


async def test_gui_changes_are_persisted_to_store(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    config = store.load()
    engine, discord_rpc, registry = make_engine(config, store=store)
    registry.upsert("phone-music", "music", {"title": "x", "artist": "y"})

    await engine.set_source_priority("phone-music", 7)

    saved = store.load()
    assert saved["sources"]["phone-music"]["priority"] == 7


async def test_new_feed_source_gets_persisted_settings_applied():
    config = {"sources": {"phone-music": {"name": "My Phone", "enabled": False, "priority": 9, "pinned": False}}}
    # 永続設定を読む settings_provider 付きの既定 registry を使うため registry は注入しない
    engine = Engine(config, FakeSecrets(), discord_rpc=_connected_mock(), tick_interval=0.01)
    engine.registry.upsert("phone-music", "music", {"title": "x", "artist": "y"}, name="feed-name")

    source = engine.registry.get("phone-music")
    assert source.name == "My Phone"  # 永続名が feed 名を上書き
    assert source.enabled is False
    assert source.priority == 9


async def test_apply_manual_updates_registry_and_config():
    config: dict = {}
    engine, discord_rpc, registry = make_engine(config)

    await engine.apply_manual({"details": "Hello", "state": "World"})

    manual = registry.get(MANUAL_SOURCE_ID)
    assert manual is not None
    assert manual.kind == "manual"
    assert config["manual"]["details"] == "Hello"
    assert engine.active_source_id == MANUAL_SOURCE_ID


async def test_apply_manual_rejects_invalid():
    engine, discord_rpc, registry = make_engine({})
    with pytest.raises(Exception):
        await engine.apply_manual({})  # details/state 無しは検証エラー


async def test_snapshot_shape():
    engine, discord_rpc, registry = make_engine({})
    registry.upsert("a", "generic", {"details": "a"})
    await engine._reevaluate_and_notify()

    snap = engine.snapshot()

    assert snap["discord_connected"] is True
    assert snap["active_source_id"] == "a"
    assert snap["sources"][0]["source_id"] == "a"
    assert snap["sources"][0]["is_active"] is True
    assert snap["preview"]["details"] == "a"


async def test_listener_notified_on_gui_action():
    engine, discord_rpc, registry = make_engine({})
    registry.upsert("a", "generic", {"details": "a"})
    calls = []
    engine.add_listener(lambda: calls.append(1))

    await engine.set_source_priority("a", 3)

    assert len(calls) == 1


async def test_tick_loop_flushes_coalesced_update():
    # 指摘3の解消確認: レート間隔内で保留(破棄)された最新状態が、周期 tick により
    # 間隔経過後に送出されること(registry が最新を保持 + 周期再評価)。
    clk = FakeClock(1000.0)
    engine, discord_rpc, registry = make_engine(
        {"min_update_interval": 15}, clock=clk, tick_interval=0.01
    )
    registry.upsert("a", "generic", {"details": "a"})
    await engine._pm.reevaluate()  # "a" 送信(count=1)
    assert discord_rpc.set_activity.await_count == 1

    registry.upsert("a", "generic", {"details": "b"})
    clk.advance(5)
    await engine._pm.reevaluate()  # 間隔内 → 破棄(count=1)
    assert discord_rpc.set_activity.await_count == 1

    clk.advance(11)  # 前回送信から16s経過
    task = asyncio.create_task(engine._tick_loop())
    try:
        for _ in range(50):
            await asyncio.sleep(0.01)
            if discord_rpc.set_activity.await_count == 2:
                break
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert discord_rpc.set_activity.await_count == 2
    assert discord_rpc.set_activity.await_args.args[0]["details"] == "b"


async def test_ttl_expiry_via_tick_triggers_clear():
    # registry の TTL は実時刻基準のため、ここでは clock を注入せず極小 TTL で失効させる。
    engine, discord_rpc, registry = make_engine(
        {"min_update_interval": 0}, tick_interval=0.01
    )
    registry.upsert("a", "generic", {"details": "a"}, ttl_seconds=0.02)
    await engine._pm.reevaluate()
    assert engine.active_source_id == "a"

    task = asyncio.create_task(engine._tick_loop())
    try:
        for _ in range(50):
            await asyncio.sleep(0.01)
            if discord_rpc.clear.await_count >= 1:
                break
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    discord_rpc.clear.assert_awaited()
    assert engine.active_source_id is None


def _connected_mock():
    m = AsyncMock()
    m.set_activity.return_value = True
    m.clear.return_value = True
    m.connected = True
    m.start = MagicMock()  # start() は同期メソッド
    return m


async def test_start_and_stop_bind_real_port():
    import aiohttp

    config = {"bind": "127.0.0.1", "port": 13599, "ttl_seconds": 30}
    engine = Engine(config, FakeSecrets(), discord_rpc=_connected_mock(), tick_interval=0.01)
    await engine.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://127.0.0.1:13599/health",
                headers={"Authorization": "Bearer tok"},
            ) as resp:
                body = await resp.json()
                assert body["status"] == "ok"
    finally:
        await engine.stop()


async def test_listener_notified_on_receiver_presence():
    # receiver(HTTP/WS)経由の更新でも GUI リスナーが呼ばれることを確認する
    # (バグ修正: 以前は presence_manager.reevaluate() のみで Engine._notify() が呼ばれなかった)。
    import aiohttp

    config = {"bind": "127.0.0.1", "port": 13598, "ttl_seconds": 30, "min_update_interval": 0}
    engine = Engine(config, FakeSecrets(), discord_rpc=_connected_mock(), tick_interval=0.01)
    calls = []
    engine.add_listener(lambda: calls.append(1))
    await engine.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://127.0.0.1:13598/presence",
                headers={"Authorization": "Bearer tok"},
                json={
                    "op": "presence",
                    "kind": "generic",
                    "source_id": "a",
                    "data": {"kind": "generic", "details": "Working"},
                },
            ) as resp:
                assert resp.status == 200
    finally:
        await engine.stop()

    assert len(calls) >= 1
    assert engine.active_source_id == "a"
