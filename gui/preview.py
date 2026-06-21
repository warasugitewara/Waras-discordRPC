"""現在の RPC プレビューカード + 接続/active source インジケータ。"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class PreviewWidget(QWidget):
    """engine.snapshot() を受け取り、現在表示中の presence を要約表示する。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self._status = QLabel("Discord: -")
        self._active = QLabel("Active source: -")

        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card_layout = QVBoxLayout(card)
        self._title = QLabel("(no presence)")
        self._title.setTextFormat(Qt.TextFormat.PlainText)
        self._details = QLabel("")
        self._state = QLabel("")
        self._meta = QLabel("")
        self._meta.setWordWrap(True)
        for w in (self._title, self._details, self._state, self._meta):
            card_layout.addWidget(w)

        layout.addWidget(self._status)
        layout.addWidget(self._active)
        layout.addWidget(card)
        layout.addStretch(1)

    def refresh(self, snapshot: dict[str, Any]) -> None:
        connected = snapshot.get("discord_connected", False)
        self._status.setText(f"Discord: {'接続中' if connected else '未接続'}")
        active_id = snapshot.get("active_source_id")
        self._active.setText(f"Active source: {active_id or '-'}")

        preview = snapshot.get("preview")
        if not preview:
            self._title.setText("(表示中の presence なし)")
            self._details.setText("")
            self._state.setText("")
            self._meta.setText("")
            return

        self._title.setText(f"[{preview.get('activity_type', 'playing')}]")
        self._details.setText(preview.get("details", ""))
        self._state.setText(preview.get("state", ""))

        meta_parts: list[str] = []
        for key in ("large_image", "large_text", "small_image", "small_text"):
            if preview.get(key):
                meta_parts.append(f"{key}={preview[key]}")
        if preview.get("buttons"):
            labels = ", ".join(b["label"] for b in preview["buttons"])
            meta_parts.append(f"buttons: {labels}")
        if "start" in preview or "end" in preview:
            meta_parts.append("timestamps: あり")
        self._meta.setText(" / ".join(meta_parts))
