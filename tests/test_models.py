import pytest
from pydantic import ValidationError

from core.models import (
    ClearEnvelope,
    GenericData,
    ManualData,
    MusicData,
    PresenceEnvelope,
)


def test_generic_data_requires_details_or_state():
    with pytest.raises(ValidationError):
        GenericData()


def test_generic_data_accepts_state_only():
    data = GenericData(state="Focus mode")
    assert data.activity_type == "playing"
    assert data.details is None


def test_generic_data_rejects_text_over_limit():
    with pytest.raises(ValidationError):
        GenericData(details="a" * 129)


def test_generic_data_rejects_too_many_buttons():
    button = {"label": "Open", "url": "https://example.com"}
    with pytest.raises(ValidationError):
        GenericData(details="hi", buttons=[button, button, button])


def test_generic_data_rejects_non_http_button_url():
    with pytest.raises(ValidationError):
        GenericData(details="hi", buttons=[{"label": "Open", "url": "ftp://example.com"}])


def test_generic_data_rejects_button_label_over_limit():
    with pytest.raises(ValidationError):
        GenericData(details="hi", buttons=[{"label": "a" * 33, "url": "https://example.com"}])


def test_generic_data_rejects_invalid_activity_type():
    with pytest.raises(ValidationError):
        GenericData(details="hi", activity_type="idle")


def test_music_data_minimal():
    data = MusicData(title="Strobe", artist="deadmau5")
    assert data.kind == "music"
    assert data.paused is False


def test_manual_data_requires_details_or_state():
    with pytest.raises(ValidationError):
        ManualData()


def test_manual_data_custom_timestamp_requires_start_ms():
    with pytest.raises(ValidationError):
        ManualData(details="hi", timestamp_mode="custom")


def test_manual_data_custom_timestamp_ok_with_start_ms():
    data = ManualData(details="hi", timestamp_mode="custom", start_ms=1000)
    assert data.start_ms == 1000


def test_presence_envelope_parses_generic():
    envelope = PresenceEnvelope.model_validate(
        {
            "op": "presence",
            "kind": "generic",
            "source_id": "tasker-status",
            "data": {"details": "Working", "state": "Focus mode"},
        }
    )
    assert isinstance(envelope.data, GenericData)
    assert envelope.data.details == "Working"


def test_presence_envelope_parses_music():
    envelope = PresenceEnvelope.model_validate(
        {
            "op": "presence",
            "kind": "music",
            "source_id": "phone-music",
            "seq": 1,
            "data": {
                "title": "Strobe",
                "artist": "deadmau5",
                "duration_ms": 634000,
                "position_ms": 42000,
            },
        }
    )
    assert isinstance(envelope.data, MusicData)
    assert envelope.data.title == "Strobe"


def test_presence_envelope_requires_source_id():
    with pytest.raises(ValidationError):
        PresenceEnvelope.model_validate(
            {"op": "presence", "kind": "generic", "source_id": "", "data": {"state": "x"}}
        )


def test_clear_envelope_defaults_to_no_source_id():
    envelope = ClearEnvelope.model_validate({"op": "clear"})
    assert envelope.source_id is None
