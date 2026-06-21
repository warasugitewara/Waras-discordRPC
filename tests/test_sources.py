import time

from core.sources import SourceRegistry


def test_upsert_auto_registers_new_source():
    registry = SourceRegistry()
    registry.upsert("phone-music", "music", {"title": "x"}, name="Phone")

    source = registry.get("phone-music")
    assert source is not None
    assert source.enabled is True
    assert source.priority == 0
    assert source.data == {"title": "x"}


def test_upsert_keeps_settings_on_repeat_update():
    registry = SourceRegistry()
    registry.upsert("phone-music", "music", {"title": "x"})
    registry.set_priority("phone-music", 5)
    registry.set_pinned("phone-music", True)

    registry.upsert("phone-music", "music", {"title": "y"})

    source = registry.get("phone-music")
    assert source.priority == 5
    assert source.pinned is True
    assert source.data == {"title": "y"}


def test_candidates_excludes_disabled():
    registry = SourceRegistry()
    registry.upsert("a", "generic", {"details": "x"})
    registry.set_enabled("a", False)

    assert registry.candidates() == []


def test_candidates_excludes_expired_by_ttl():
    registry = SourceRegistry()
    registry.upsert("a", "generic", {"details": "x"}, ttl_seconds=10)
    now = time.time()

    assert len(registry.candidates(now)) == 1
    assert registry.candidates(now + 11) == []


def test_clear_source_removes_data_but_keeps_settings():
    registry = SourceRegistry()
    registry.upsert("a", "generic", {"details": "x"})
    registry.set_priority("a", 3)

    registry.clear_source("a")

    source = registry.get("a")
    assert source.data is None
    assert source.priority == 3
    assert registry.candidates() == []


def test_expire_for_conn_clears_only_matching_sources():
    registry = SourceRegistry()
    conn_a = object()
    conn_b = object()
    registry.upsert("a", "generic", {"details": "x"}, origin_conn=conn_a)
    registry.upsert("b", "generic", {"details": "y"}, origin_conn=conn_b)

    registry.expire_for_conn(conn_a)

    assert registry.get("a").data is None
    assert registry.get("b").data == {"details": "y"}


def test_remove_deletes_source_entirely():
    registry = SourceRegistry()
    registry.upsert("a", "generic", {"details": "x"})

    registry.remove("a")

    assert registry.get("a") is None
