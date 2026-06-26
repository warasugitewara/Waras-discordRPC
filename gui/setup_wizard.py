"""初回セットアップウィザード(QDialog)。

config/.env が未設定(Application ID 未入力)で起動したとき、トレイ常駐の前に
接続情報(Application ID / Bridge Token / ネットワークモード)を入力させる。
保存は呼び出し側(app.py)が values() を受け取って行う。
"""
from __future__ import annotations

import secrets as secrets_mod
from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QWidget,
)

from gui.config_window import NETWORK_MODES


class SetupWizard(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Wara's-discordRPC 初期設定")

        form = QFormLayout(self)

        intro = QLabel(
            "はじめに接続情報を設定します。\n"
            "Application ID は Discord Developer Portal で作成したアプリの ID です。"
        )
        intro.setWordWrap(True)
        form.addRow(intro)

        link = QLabel(
            '<a href="https://discord.com/developers/applications">'
            "Discord Developer Portal を開く</a>"
        )
        link.setOpenExternalLinks(True)
        form.addRow(link)

        self._client_id = QLineEdit()
        self._token = QLineEdit(secrets_mod.token_urlsafe(24))
        self._mode = QComboBox()
        self._mode.addItems([label for label, _ in NETWORK_MODES])

        form.addRow("Application ID", self._client_id)
        form.addRow("Bridge Token", self._token)
        form.addRow("ネットワークモード", self._mode)

        note = QLabel(
            "Bridge Token は送信側(スマホ等)と共有する合言葉です(自動生成済み)。\n"
            "ネットワークモード: ローカルのみ=この PC 内 / LAN全体=同一LAN / "
            "カスタムIP=指定IPに bind。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555;")
        form.addRow(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _mode_value(self) -> str:
        label = self._mode.currentText()
        for lbl, value in NETWORK_MODES:
            if lbl == label:
                return value
        return "local"

    def values(self) -> dict[str, Any]:
        """入力値を返す。network_mode は内部値(local/lan/custom)。"""
        return {
            "client_id": self._client_id.text().strip(),
            "bridge_token": self._token.text().strip(),
            "network_mode": self._mode_value(),
        }
