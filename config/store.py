"""config.json(GUI編集可)と .env(秘密)の読み書き。"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv, set_key

CONFIG_VERSION = 1

DEFAULT_CONFIG: dict[str, Any] = {
    "version": CONFIG_VERSION,
    # network_mode: "local"=127.0.0.1 / "lan"=0.0.0.0 / "custom"=bind の指定IP
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


def resolve_bind(config: dict[str, Any]) -> str:
    """network_mode を待ち受け bind アドレスへ解決する。

    "lan"=全インターフェース(0.0.0.0) / "custom"=設定の bind(指定IP) /
    それ以外("local" 既定や未知値)=ループバック(127.0.0.1, 誤公開を防ぐ安全側)。
    """
    mode = config.get("network_mode", "local")
    if mode == "lan":
        return "0.0.0.0"
    if mode == "custom":
        return config.get("bind", "127.0.0.1")
    return "127.0.0.1"


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
        # 旧 network_mode="twingate"(local/twingate の2値時代)の移行:
        # bind がループバック/未設定なら旧実装の「0.0.0.0 昇格」を保存するため lan、
        # 明示 IP が指定されていれば custom(そのIPで待ち受け)へ。
        if merged.get("network_mode") == "twingate":
            bind = str(merged.get("bind", "")).strip()
            if bind in ("", "127.0.0.1", "localhost", "::1"):
                merged["network_mode"] = "lan"
            else:
                merged["network_mode"] = "custom"
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

    @staticmethod
    def save(
        env_path: Path | str,
        *,
        bridge_token: str,
        discord_client_id: str,
    ) -> None:
        """.env の BRIDGE_TOKEN / DISCORD_CLIENT_ID を更新する(他キーは保持、無ければ作成)。"""
        path = Path(env_path)
        if not path.exists():
            path.touch()
        set_key(str(path), "BRIDGE_TOKEN", bridge_token)
        set_key(str(path), "DISCORD_CLIENT_ID", discord_client_id)
