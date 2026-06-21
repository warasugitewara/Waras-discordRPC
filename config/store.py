"""config.json(GUI編集可)と .env(秘密)の読み書き。"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

CONFIG_VERSION = 1

DEFAULT_CONFIG: dict[str, Any] = {
    "version": CONFIG_VERSION,
    "network_mode": "local",
    "bind": "127.0.0.1",
    "port": 13520,
    "client_id": "",
    "selection_policy": "priority",
    "sources": {},
    "manual": None,
    "display": {
        "default_activity_type": "playing",
        "show_small_image": True,
    },
    "buttons": [],
    "assets": {
        "play": "play",
        "pause": "pause",
        "idle": "idle",
    },
    "blacklist": [],
    "auto_clear_on_disconnect": True,
    "ttl_seconds": 30,
    "min_update_interval": 15,
}


class ConfigStore:
    """`config.json` の読み込み・保存・バージョン移行を担う。"""

    def __init__(self, config_path: Path | str = "config.json") -> None:
        self.config_path = Path(config_path)

    def load(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return copy.deepcopy(DEFAULT_CONFIG)
        with self.config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return self._migrate(data)

    def save(self, config: dict[str, Any]) -> None:
        with self.config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def _migrate(self, data: dict[str, Any]) -> dict[str, Any]:
        # 既知フィールドの欠損をデフォルトで補完する(v1のみ。将来バージョンはここに分岐を追加)。
        merged = copy.deepcopy(DEFAULT_CONFIG)
        merged.update(data)
        merged["version"] = CONFIG_VERSION
        return merged


@dataclass(frozen=True)
class Secrets:
    bridge_token: str
    discord_client_id: str

    @classmethod
    def load(cls, env_path: Path | str | None = None) -> "Secrets":
        if env_path is not None:
            load_dotenv(env_path)
        else:
            load_dotenv()
        return cls(
            bridge_token=os.environ.get("BRIDGE_TOKEN", ""),
            discord_client_id=os.environ.get("DISCORD_CLIENT_ID", ""),
        )
