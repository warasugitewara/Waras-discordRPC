"""GUI ウィジェットのオフスクリーン スモークテスト。

Qt ランタイム(PySide6 + システムライブラリ)が無い環境では skip する。
レンダリングや実トレイ常駐、qasync+aiohttp+pypresence 同居は Windows 11 実機での
検証が必要(AGENTS.md「既知のリスク」)。ここでは構築とデータ反映のみ検証する。
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")
try:  # システムライブラリ(libEGL 等)欠如時は QApplication 生成で失敗する
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover
    pytest.skip("PySide6 runtime unavailable", allow_module_level=True)


@pytest.fixture(scope="module")
def qapp():
    try:
        app = QApplication.instance() or QApplication([])
    except Exception:  # pragma: no cover
        pytest.skip("Qt platform unavailable")
    yield app


class FakeEngine:
    """snapshot/config と GUI 操作メソッドだけを持つ engine スタブ。"""

    def __init__(self):
        self.calls = []
        self._config = {"manual": {"activity_type": "playing", "details": "hi"}}
        self._listeners = []

    @property
    def config(self):
        return self._config

    def add_listener(self, cb):
        self._listeners.append(cb)

    def snapshot(self):
        return {
            "discord_connected": True,
            "active_source_id": "phone-music",
            "sources": [
                {
                    "source_id": "phone-music",
                    "name": "Phone Music",
                    "kind": "music",
                    "enabled": True,
                    "priority": 5,
                    "pinned": False,
                    "has_data": True,
                    "stale": False,
                    "is_active": True,
                }
            ],
            "preview": {
                "activity_type": "listening",
                "details": "Strobe",
                "state": "deadmau5",
                "large_image": "https://x/art.jpg",
                "buttons": [{"label": "Open", "url": "https://x"}],
                "start": 1,
                "end": 2,
            },
        }

    async def set_source_enabled(self, sid, enabled):
        self.calls.append(("enabled", sid, enabled))

    async def set_source_priority(self, sid, priority):
        self.calls.append(("priority", sid, priority))

    async def set_source_pinned(self, sid, pinned):
        self.calls.append(("pinned", sid, pinned))

    async def forget_source(self, sid):
        self.calls.append(("forget", sid))

    async def apply_manual(self, data):
        self.calls.append(("manual", data))

    async def clear_manual(self):
        self.calls.append(("clear_manual",))


def make_scheduler(engine):
    scheduled = []

    def schedule(coro):
        scheduled.append(coro)
        # FakeEngine のメソッドは呼ばれた時点で calls に積まれるよう、即実行する。
        try:
            coro.send(None)
        except StopIteration:
            pass
        return None

    return schedule, scheduled


def test_preview_widget_refresh(qapp):
    from gui.preview import PreviewWidget

    w = PreviewWidget()
    w.refresh(FakeEngine().snapshot())

    assert w._details.text() == "Strobe"
    assert w._state.text() == "deadmau5"
    assert "buttons" in w._meta.text()


def test_config_window_builds_source_rows(qapp):
    from gui.config_window import ConfigWindow

    engine = FakeEngine()
    schedule, _ = make_scheduler(engine)
    window = ConfigWindow(engine, schedule)

    assert window._table.rowCount() == 1
    assert window._table.item(0, 0).text().endswith("Phone Music")


def test_config_window_manual_form_validation_blocks_empty(qapp):
    from gui.config_window import ConfigWindow

    engine = FakeEngine()
    schedule, _ = make_scheduler(engine)
    window = ConfigWindow(engine, schedule)

    # details/state を空にすると検証エラーで apply_manual は呼ばれない
    window._m_fields["details"].setText("")
    window._m_fields["state"].setText("")
    window._on_apply_manual()

    assert all(c[0] != "manual" for c in engine.calls)
    assert window._m_error.text() != ""


def test_config_window_manual_apply_schedules_engine_call(qapp):
    from gui.config_window import ConfigWindow

    engine = FakeEngine()
    schedule, _ = make_scheduler(engine)
    window = ConfigWindow(engine, schedule)

    window._m_fields["details"].setText("Working")
    window._m_fields["state"].setText("Focus")
    window._on_apply_manual()

    manual_calls = [c for c in engine.calls if c[0] == "manual"]
    assert len(manual_calls) == 1
    assert manual_calls[0][1]["details"] == "Working"
