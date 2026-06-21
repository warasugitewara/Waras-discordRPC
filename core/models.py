"""pydanticモデル: GenericData/MusicData/ManualData と受信封筒。

Discordの制限(文字数・buttons数・URLスキーム)を検証する。
仕様はdocs/PROTOCOL.md(通信契約)とdocs/DESIGN.md(マッピング)をSoTとする。
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

ActivityType = Literal["playing", "listening", "watching", "competing"]
TimestampMode = Literal["none", "online_elapsed", "custom"]

TEXT_FIELD_MAX_LEN = 128
BUTTON_LABEL_MAX_LEN = 32
MAX_BUTTONS = 2


class Button(BaseModel):
    label: str = Field(max_length=BUTTON_LABEL_MAX_LEN)
    url: str

    @model_validator(mode="after")
    def _validate_url_scheme(self) -> "Button":
        if not (self.url.startswith("http://") or self.url.startswith("https://")):
            raise ValueError("button url must start with http:// or https://")
        return self


class Party(BaseModel):
    size: int
    max: int


class GenericData(BaseModel):
    kind: Literal["generic"] = "generic"
    details: str | None = Field(default=None, max_length=TEXT_FIELD_MAX_LEN)
    state: str | None = Field(default=None, max_length=TEXT_FIELD_MAX_LEN)
    activity_type: ActivityType = "playing"
    large_image: str | None = None
    large_text: str | None = Field(default=None, max_length=TEXT_FIELD_MAX_LEN)
    small_image: str | None = None
    small_text: str | None = Field(default=None, max_length=TEXT_FIELD_MAX_LEN)
    start_ms: int | None = None
    end_ms: int | None = None
    buttons: list[Button] = Field(default_factory=list, max_length=MAX_BUTTONS)
    party: Party | None = None

    @model_validator(mode="after")
    def _require_details_or_state(self) -> "GenericData":
        if not self.details and not self.state:
            raise ValueError("generic data requires at least one of details/state")
        return self


class MusicData(BaseModel):
    kind: Literal["music"] = "music"
    title: str = Field(max_length=TEXT_FIELD_MAX_LEN)
    artist: str = Field(max_length=TEXT_FIELD_MAX_LEN)
    album: str | None = Field(default=None, max_length=TEXT_FIELD_MAX_LEN)
    artwork_url: str | None = None
    duration_ms: int | None = None
    position_ms: int | None = None
    paused: bool = False
    app_name: str | None = None
    source_url: str | None = None


class ManualData(BaseModel):
    """GUIで入力する手動モードのプレゼンス。source_id="manual" として扱う。"""

    activity_type: ActivityType = "playing"
    details: str | None = Field(default=None, max_length=TEXT_FIELD_MAX_LEN)
    state: str | None = Field(default=None, max_length=TEXT_FIELD_MAX_LEN)
    large_image: str | None = None
    large_text: str | None = Field(default=None, max_length=TEXT_FIELD_MAX_LEN)
    small_image: str | None = None
    small_text: str | None = Field(default=None, max_length=TEXT_FIELD_MAX_LEN)
    buttons: list[Button] = Field(default_factory=list, max_length=MAX_BUTTONS)
    timestamp_mode: TimestampMode = "none"
    start_ms: int | None = None
    end_ms: int | None = None

    @model_validator(mode="after")
    def _require_details_or_state(self) -> "ManualData":
        if not self.details and not self.state:
            raise ValueError("manual data requires at least one of details/state")
        return self

    @model_validator(mode="after")
    def _require_start_ms_for_custom_timestamp(self) -> "ManualData":
        if self.timestamp_mode == "custom" and self.start_ms is None:
            raise ValueError("timestamp_mode=custom requires start_ms")
        return self


PresenceData = Annotated[Union[GenericData, MusicData], Field(discriminator="kind")]


class PresenceEnvelope(BaseModel):
    """WS/HTTPで受信する presence メッセージ(op="presence")。"""

    op: Literal["presence"] = "presence"
    kind: Literal["generic", "music"]
    source_id: str = Field(min_length=1)
    source_name: str | None = None
    seq: int | None = None
    data: PresenceData

    @model_validator(mode="before")
    @classmethod
    def _inject_kind_into_data(cls, values: object) -> object:
        if isinstance(values, dict):
            data = values.get("data")
            if isinstance(data, dict) and "kind" not in data:
                values = {**values, "data": {**data, "kind": values.get("kind")}}
        return values


class ClearEnvelope(BaseModel):
    """WS/HTTPで受信する clear メッセージ(op="clear")。source_id省略=全クリア。"""

    op: Literal["clear"] = "clear"
    source_id: str | None = None
