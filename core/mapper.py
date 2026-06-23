"""受信 payload(generic/music/manual)→ Discord activity dict への変換。

入力は core.models で検証済みの dict(`GenericData.model_dump()` 等)を想定する。
設定(client_id/アセット上書き/ブラックリスト)はここでは適用せず、ブラックリストのみ
music の非表示判定に用いる(他の設定適用は config 側の責務)。
"""
from __future__ import annotations

import time
from typing import Any

MAX_BUTTONS = 2

# generic / manual で共通の表示フィールド(値が真のときのみ activity へコピーする)。
_DISPLAY_FIELDS = (
    "details",
    "state",
    "large_image",
    "large_text",
    "small_image",
    "small_text",
)


def _buttons_payload(buttons: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"label": b["label"], "url": b["url"]} for b in buttons[:MAX_BUTTONS]]


def _apply_display_fields(data: dict[str, Any], activity: dict[str, Any]) -> None:
    for key in _DISPLAY_FIELDS:
        if data.get(key):
            activity[key] = data[key]
    if data.get("buttons"):
        activity["buttons"] = _buttons_payload(data["buttons"])


def _is_blacklisted(text: str | None, blacklist: list[str]) -> bool:
    if not text or not blacklist:
        return False
    lowered = text.lower()
    return any(term.lower() in lowered for term in blacklist)


def map_generic(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
    activity: dict[str, Any] = {"activity_type": data.get("activity_type", "playing")}
    _apply_display_fields(data, activity)
    if data.get("start_ms") is not None:
        activity["start"] = data["start_ms"]
    if data.get("end_ms") is not None:
        activity["end"] = data["end_ms"]
    if data.get("party"):
        activity["party_size"] = [data["party"]["size"], data["party"]["max"]]
    return activity


def map_music(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
    blacklist = config.get("blacklist", [])
    if _is_blacklisted(data.get("title"), blacklist) or _is_blacklisted(data.get("artist"), blacklist):
        return None

    activity: dict[str, Any] = {"activity_type": "listening", "details": data["title"]}
    if data.get("artist"):
        activity["state"] = data["artist"]
    if data.get("album"):
        activity["large_text"] = data["album"]
    if data.get("artwork_url"):
        activity["large_image"] = data["artwork_url"]

    paused = data.get("paused", False)
    duration_ms = data.get("duration_ms")
    position_ms = data.get("position_ms")
    if not paused and duration_ms is not None and position_ms is not None:
        start = int(time.time() * 1000) - position_ms
        activity["start"] = start
        activity["end"] = start + duration_ms
    elif paused:
        pause_icon = config.get("assets", {}).get("pause")
        if pause_icon:
            activity["small_image"] = pause_icon
            activity["small_text"] = "Paused"

    return activity


def map_manual(
    data: dict[str, Any],
    config: dict[str, Any],
    online_since_ms: int | None = None,
) -> dict[str, Any] | None:
    activity: dict[str, Any] = {"activity_type": data.get("activity_type", "playing")}
    _apply_display_fields(data, activity)

    timestamp_mode = data.get("timestamp_mode", "none")
    if timestamp_mode == "custom":
        if data.get("start_ms") is not None:
            activity["start"] = data["start_ms"]
        if data.get("end_ms") is not None:
            activity["end"] = data["end_ms"]
    elif timestamp_mode == "online_elapsed" and online_since_ms is not None:
        activity["start"] = online_since_ms

    return activity


def to_activity(kind: str, data: dict[str, Any], config: dict[str, Any], **kwargs: Any) -> dict[str, Any] | None:
    if kind == "generic":
        return map_generic(data, config)
    if kind == "music":
        return map_music(data, config)
    if kind == "manual":
        return map_manual(data, config, online_since_ms=kwargs.get("online_since_ms"))
    raise ValueError(f"unknown kind: {kind}")
