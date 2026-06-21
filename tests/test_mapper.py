from core.mapper import to_activity


def test_generic_maps_basic_fields():
    activity = to_activity(
        "generic",
        {"details": "Working", "state": "Focus mode", "activity_type": "playing"},
        {},
    )
    assert activity == {
        "activity_type": "playing",
        "details": "Working",
        "state": "Focus mode",
    }


def test_generic_maps_timestamps_buttons_party():
    activity = to_activity(
        "generic",
        {
            "details": "Working",
            "start_ms": 1000,
            "end_ms": 2000,
            "buttons": [{"label": "Open", "url": "https://example.com"}],
            "party": {"size": 1, "max": 4},
        },
        {},
    )
    assert activity["start"] == 1000
    assert activity["end"] == 2000
    assert activity["buttons"] == [{"label": "Open", "url": "https://example.com"}]
    assert activity["party_size"] == [1, 4]


def test_generic_truncates_buttons_to_two():
    buttons = [{"label": f"b{i}", "url": "https://example.com"} for i in range(3)]
    activity = to_activity("generic", {"details": "x", "buttons": buttons}, {})
    assert len(activity["buttons"]) == 2


def test_music_maps_to_listening_with_progress_bar():
    activity = to_activity(
        "music",
        {
            "title": "Strobe",
            "artist": "deadmau5",
            "album": "For Lack of a Better Name",
            "artwork_url": "https://example.com/art.jpg",
            "duration_ms": 634000,
            "position_ms": 42000,
            "paused": False,
        },
        {},
    )
    assert activity["activity_type"] == "listening"
    assert activity["details"] == "Strobe"
    assert activity["state"] == "deadmau5"
    assert activity["large_text"] == "For Lack of a Better Name"
    assert activity["large_image"] == "https://example.com/art.jpg"
    assert activity["end"] - activity["start"] == 634000


def test_music_paused_drops_timestamps_and_uses_pause_icon():
    activity = to_activity(
        "music",
        {"title": "Strobe", "artist": "deadmau5", "paused": True},
        {"assets": {"pause": "pause_icon"}},
    )
    assert "start" not in activity
    assert "end" not in activity
    assert activity["small_image"] == "pause_icon"


def test_music_blacklisted_artist_is_suppressed():
    activity = to_activity(
        "music",
        {"title": "Strobe", "artist": "deadmau5"},
        {"blacklist": ["deadmau5"]},
    )
    assert activity is None


def test_manual_custom_timestamp_mode():
    activity = to_activity(
        "manual",
        {"details": "hi", "timestamp_mode": "custom", "start_ms": 1000, "end_ms": 2000},
        {},
    )
    assert activity["start"] == 1000
    assert activity["end"] == 2000


def test_manual_online_elapsed_uses_given_online_since():
    activity = to_activity(
        "manual",
        {"details": "hi", "timestamp_mode": "online_elapsed"},
        {},
        online_since_ms=5000,
    )
    assert activity["start"] == 5000


def test_manual_none_timestamp_mode_has_no_timestamps():
    activity = to_activity("manual", {"details": "hi", "timestamp_mode": "none"}, {})
    assert "start" not in activity
    assert "end" not in activity
