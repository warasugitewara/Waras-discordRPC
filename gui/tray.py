"""システムトレイ常駐(開始/停止状態の表示・設定を開く・終了)。"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QStyle, QSystemTrayIcon, QWidget


class Tray:
    def __init__(
        self,
        engine: Any,
        on_open_settings: Callable[[], None],
        on_quit: Callable[[], None],
        icon: QIcon | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._engine = engine
        self._tray = QSystemTrayIcon(parent)
        self._tray.setIcon(icon or self._default_icon(parent))

        menu = QMenu()
        self._status_action = QAction("状態: 起動中…", menu)
        self._status_action.setEnabled(False)
        menu.addAction(self._status_action)
        menu.addSeparator()

        open_action = QAction("設定を開く", menu)
        open_action.triggered.connect(on_open_settings)
        menu.addAction(open_action)

        quit_action = QAction("終了", menu)
        quit_action.triggered.connect(on_quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(
            lambda reason: on_open_settings()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )

        engine.add_listener(self.refresh)

    def show(self) -> None:
        self._tray.show()
        self.refresh()

    def refresh(self) -> None:
        snapshot = self._engine.snapshot()
        discord = "接続中" if snapshot["discord_connected"] else "未接続"
        active = snapshot["active_source_id"] or "なし"
        text = f"Discord: {discord} / 表示中: {active}"
        self._status_action.setText(f"状態: {text}")
        self._tray.setToolTip(f"Wara's-discordRPC — {text}")

    @staticmethod
    def _default_icon(parent: QWidget | None) -> QIcon:
        if parent is not None:
            return parent.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        return QIcon()
