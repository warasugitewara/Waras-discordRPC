from unittest.mock import AsyncMock

from core.presence_manager import PresenceManager, select_active
from core.sources import SourceRegistry


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_manager(config=None):
    registry = SourceRegistry()
    discord_rpc = AsyncMock()
    discord_rpc.set_activity.return_value = True
    discord_rpc.clear.return_value = True
    clock = FakeClock()
    manager = PresenceManager(registry, discord_rpc, config or {}, clock=clock)
    return registry, discord_rpc, clock, manager


async def test_no_candidates_does_nothing():
    registry, discord_rpc, clock, manager = make_manager()

    sent = await manager.reevaluate()

    assert sent is False
    discord_rpc.set_activity.assert_not_called()
    discord_rpc.clear.assert_not_called()


async def test_selects_highest_priority():
    registry, discord_rpc, clock, manager = make_manager()
    registry.upsert("low", "generic", {"details": "low"})
    registry.set_priority("low", 1)
    registry.upsert("high", "generic", {"details": "high"})
    registry.set_priority("high", 5)

    await manager.reevaluate()

    assert manager.active_source_id == "high"
    discord_rpc.set_activity.assert_awaited_once()
    assert discord_rpc.set_activity.await_args.args[0]["details"] == "high"


async def test_pinned_overrides_priority():
    registry, discord_rpc, clock, manager = make_manager()
    registry.upsert("low", "generic", {"details": "low"})
    registry.set_priority("low", 0)
    registry.set_pinned("low", True)
    registry.upsert("high", "generic", {"details": "high"})
    registry.set_priority("high", 5)

    await manager.reevaluate()

    assert manager.active_source_id == "low"


async def test_disabled_source_excluded():
    registry, discord_rpc, clock, manager = make_manager()
    registry.upsert("a", "generic", {"details": "a"})
    registry.set_enabled("a", False)

    await manager.reevaluate()

    assert manager.active_source_id is None
    discord_rpc.set_activity.assert_not_called()


async def test_same_activity_is_not_resent():
    registry, discord_rpc, clock, manager = make_manager()
    registry.upsert("a", "generic", {"details": "a"})

    await manager.reevaluate()
    clock.advance(20)  # min_update_interval(既定15s)を超えても内容同一なら送らない
    sent_again = await manager.reevaluate()

    assert sent_again is False
    discord_rpc.set_activity.assert_awaited_once()


async def test_rate_limited_within_min_interval():
    registry, discord_rpc, clock, manager = make_manager({"min_update_interval": 15})
    registry.upsert("a", "generic", {"details": "a"})
    await manager.reevaluate()

    registry.upsert("a", "generic", {"details": "b"})
    clock.advance(5)
    sent = await manager.reevaluate()

    assert sent is False
    discord_rpc.set_activity.assert_awaited_once()


async def test_update_sent_after_min_interval_elapses():
    registry, discord_rpc, clock, manager = make_manager({"min_update_interval": 15})
    registry.upsert("a", "generic", {"details": "a"})
    await manager.reevaluate()

    registry.upsert("a", "generic", {"details": "b"})
    clock.advance(16)
    sent = await manager.reevaluate()

    assert sent is True
    assert discord_rpc.set_activity.await_count == 2


async def test_music_same_data_not_resent_after_interval():
    # mapper は music の start/end を実時刻から計算するため、マップ後 activity で
    # 比較すると同一曲でも毎回ズレて再送されてしまう。データ不変なら間隔経過後も
    # 再送しないことを保証する(進捗バーは Discord 側が描画する)。
    registry, discord_rpc, clock, manager = make_manager()
    registry.upsert("phone-music", "music", {"title": "Strobe", "artist": "deadmau5"})
    await manager.reevaluate()

    clock.advance(60)
    registry.upsert("phone-music", "music", {"title": "Strobe", "artist": "deadmau5"})
    sent = await manager.reevaluate()

    assert sent is False
    discord_rpc.set_activity.assert_awaited_once()


async def test_music_song_change_is_resent():
    registry, discord_rpc, clock, manager = make_manager()
    registry.upsert("phone-music", "music", {"title": "Strobe", "artist": "deadmau5"})
    await manager.reevaluate()

    clock.advance(16)
    registry.upsert("phone-music", "music", {"title": "Ghosts n Stuff", "artist": "deadmau5"})
    sent = await manager.reevaluate()

    assert sent is True
    assert discord_rpc.set_activity.await_count == 2


async def test_winner_disappearing_triggers_clear():
    registry, discord_rpc, clock, manager = make_manager()
    registry.upsert("a", "generic", {"details": "a"})
    await manager.reevaluate()

    registry.clear_source("a")
    sent = await manager.reevaluate()

    assert sent is True
    discord_rpc.clear.assert_awaited_once()
    assert manager.active_source_id is None


async def test_blacklisted_music_triggers_clear_when_previously_sent():
    registry, discord_rpc, clock, manager = make_manager({"blacklist": ["deadmau5"]})
    registry.upsert("a", "music", {"title": "Strobe", "artist": "Other Artist"})
    await manager.reevaluate()

    registry.upsert("a", "music", {"title": "Strobe", "artist": "deadmau5"})
    sent = await manager.reevaluate()

    assert sent is True
    discord_rpc.clear.assert_awaited_once()


def test_select_active_prefers_recent_updated_at_when_priority_tied():
    registry = SourceRegistry()
    registry.upsert("old", "generic", {"details": "old"})
    registry.upsert("new", "generic", {"details": "new"})

    winner = select_active(registry.all())

    assert winner.source_id == "new"
