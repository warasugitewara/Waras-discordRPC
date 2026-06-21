"""設定画面。タブ: ソース一覧 / 手動モード編集 / プレビュー。

engine のメソッドを呼んで状態を変更し、engine.snapshot() で表示を更新する。
engine のコルーチンは `schedule`(coro を現在のループに投入する callable)経由で実行する。
qasync 環境では Qt と asyncio が同一ループのため asyncio.ensure_future で委譲できる。
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.preview import PreviewWidget

Scheduler = Callable[[Awaitable[Any]], Any]

ACTIVITY_TYPES = ["playing", "listening", "watching", "competing"]


class ConfigWindow(QWidget):
    def __init__(self, engine: Any, schedule: Scheduler, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._schedule = schedule
        self.setWindowTitle("Wara's-discordRPC 設定")

        tabs = QTabWidget()
        tabs.addTab(self._build_sources_tab(), "ソース一覧")
        tabs.addTab(self._build_manual_tab(), "手動モード")
        self._preview = PreviewWidget()
        tabs.addTab(self._preview, "プレビュー")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)

        engine.add_listener(self.refresh)
        self.refresh()

    # ---- ソース一覧タブ ----
    def _build_sources_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["ソース", "種別", "有効", "優先度", "固定", "操作"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table)
        return widget

    def _rebuild_source_rows(self, sources: list[dict[str, Any]]) -> None:
        self._table.setRowCount(len(sources))
        for row, s in enumerate(sources):
            sid = s["source_id"]

            name = s["name"]
            if s["is_active"]:
                name = "▶ " + name
            elif s["stale"]:
                name = "(stale) " + name
            self._table.setItem(row, 0, QTableWidgetItem(name))
            self._table.setItem(row, 1, QTableWidgetItem(s["kind"]))

            enabled = QCheckBox()
            enabled.setChecked(s["enabled"])
            enabled.toggled.connect(lambda checked, i=sid: self._on_enabled(i, checked))
            self._table.setCellWidget(row, 2, enabled)

            prio = QComboBox()
            prio.addItems([str(n) for n in range(0, 11)])
            prio.setCurrentText(str(min(max(s["priority"], 0), 10)))
            prio.currentTextChanged.connect(lambda val, i=sid: self._on_priority(i, val))
            self._table.setCellWidget(row, 3, prio)

            pinned = QCheckBox()
            pinned.setChecked(s["pinned"])
            pinned.toggled.connect(lambda checked, i=sid: self._on_pinned(i, checked))
            self._table.setCellWidget(row, 4, pinned)

            forget = QPushButton("忘れる")
            forget.clicked.connect(lambda _=False, i=sid: self._on_forget(i))
            self._table.setCellWidget(row, 5, forget)

    def _on_enabled(self, source_id: str, checked: bool) -> None:
        self._schedule(self._engine.set_source_enabled(source_id, checked))

    def _on_priority(self, source_id: str, value: str) -> None:
        self._schedule(self._engine.set_source_priority(source_id, int(value)))

    def _on_pinned(self, source_id: str, checked: bool) -> None:
        self._schedule(self._engine.set_source_pinned(source_id, checked))

    def _on_forget(self, source_id: str) -> None:
        self._schedule(self._engine.forget_source(source_id))

    # ---- 手動モードタブ ----
    def _build_manual_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        self._m_activity = QComboBox()
        self._m_activity.addItems(ACTIVITY_TYPES)
        self._m_details = QLineEdit()
        self._m_state = QLineEdit()
        self._m_large_image = QLineEdit()
        self._m_large_text = QLineEdit()
        self._m_small_image = QLineEdit()
        self._m_small_text = QLineEdit()

        form.addRow("activity_type", self._m_activity)
        form.addRow("details", self._m_details)
        form.addRow("state", self._m_state)
        form.addRow("large_image", self._m_large_image)
        form.addRow("large_text", self._m_large_text)
        form.addRow("small_image", self._m_small_image)
        form.addRow("small_text", self._m_small_text)

        self._m_error = QLabel("")
        self._m_error.setStyleSheet("color: #c0392b;")
        form.addRow(self._m_error)

        buttons = QHBoxLayout()
        apply_btn = QPushButton("反映してオンライン化")
        apply_btn.clicked.connect(self._on_apply_manual)
        clear_btn = QPushButton("手動を消す")
        clear_btn.clicked.connect(lambda: self._schedule(self._engine.clear_manual()))
        buttons.addWidget(apply_btn)
        buttons.addWidget(clear_btn)
        container = QWidget()
        container.setLayout(buttons)
        form.addRow(container)

        self._load_manual_into_form()
        return widget

    def _load_manual_into_form(self) -> None:
        manual = self._engine.config.get("manual") or {}
        self._m_activity.setCurrentText(manual.get("activity_type", "playing"))
        self._m_details.setText(manual.get("details", "") or "")
        self._m_state.setText(manual.get("state", "") or "")
        self._m_large_image.setText(manual.get("large_image", "") or "")
        self._m_large_text.setText(manual.get("large_text", "") or "")
        self._m_small_image.setText(manual.get("small_image", "") or "")
        self._m_small_text.setText(manual.get("small_text", "") or "")

    def manual_form_data(self) -> dict[str, Any]:
        """フォーム入力を ManualData 互換の dict に変換する(空欄は除外)。"""
        data: dict[str, Any] = {"activity_type": self._m_activity.currentText()}
        fields = {
            "details": self._m_details,
            "state": self._m_state,
            "large_image": self._m_large_image,
            "large_text": self._m_large_text,
            "small_image": self._m_small_image,
            "small_text": self._m_small_text,
        }
        for key, widget in fields.items():
            text = widget.text().strip()
            if text:
                data[key] = text
        return data

    def _on_apply_manual(self) -> None:
        from pydantic import ValidationError

        from core.models import ManualData

        data = self.manual_form_data()
        try:
            ManualData.model_validate(data)
        except ValidationError as exc:
            self._m_error.setText(self._first_error_message(exc))
            return
        self._m_error.setText("")
        self._schedule(self._engine.apply_manual(data))

    @staticmethod
    def _first_error_message(exc: Any) -> str:
        try:
            first = exc.errors()[0]
            return f"入力エラー: {first.get('msg', str(exc))}"
        except Exception:
            return "入力エラー"

    # ---- 共通 ----
    def refresh(self) -> None:
        snapshot = self._engine.snapshot()
        self._rebuild_source_rows(snapshot["sources"])
        self._preview.refresh(snapshot)
