from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestServer
from pydantic import ValidationError

from core.presence_manager import PresenceManager
from core.receiver import create_app
from core.sources import SourceRegistry
from tools.send_test import build_envelope, build_parser, send_http, send_repeatedly, send_ws

BRIDGE_TOKEN = "secret-token"


# --- build_parser / build_envelope (argsからモデル構築) ---


def parse(argv: list[str]):
    return build_parser().parse_args(argv)


def test_generic_minimal_builds_presence_envelope():
    args = parse(["--kind", "generic", "--source", "tasker-status", "--details", "Working"])
    envelope = build_envelope(args)

    assert envelope.op == "presence"
    assert envelope.source_id == "tasker-status"
    assert envelope.data.kind == "generic"
    assert envelope.data.details == "Working"
    assert envelope.data.activity_type == "playing"


def test_generic_with_buttons_builds_button_list():
    args = parse(
        [
            "--kind", "generic", "--source", "tasker-status", "--details", "Working",
            "--button", "Open", "https://example.com",
        ]
    )
    envelope = build_envelope(args)

    assert len(envelope.data.buttons) == 1
    assert envelope.data.buttons[0].label == "Open"
    assert envelope.data.buttons[0].url == "https://example.com"


def test_generic_button_invalid_url_scheme_raises_validation_error():
    args = parse(
        [
            "--kind", "generic", "--source", "tasker-status", "--details", "Working",
            "--button", "Open", "ftp://example.com",
        ]
    )
    with pytest.raises(ValidationError):
        build_envelope(args)


def test_generic_more_than_two_buttons_raises_validation_error():
    args = parse(
        [
            "--kind", "generic", "--source", "tasker-status", "--details", "Working",
            "--button", "A", "https://a.example.com",
            "--button", "B", "https://b.example.com",
            "--button", "C", "https://c.example.com",
        ]
    )
    with pytest.raises(ValidationError):
        build_envelope(args)


def test_music_builds_presence_envelope():
    args = parse(
        [
            "--kind", "music", "--source", "phone-music",
            "--title", "Strobe", "--artist", "deadmau5",
            "--duration-ms", "634000", "--position-ms", "42000",
        ]
    )
    envelope = build_envelope(args)

    assert envelope.data.kind == "music"
    assert envelope.data.title == "Strobe"
    assert envelope.data.artist == "deadmau5"
    assert envelope.data.duration_ms == 634000
    assert envelope.data.paused is False


def test_music_paused_flag():
    args = parse(
        ["--kind", "music", "--source", "phone-music", "--title", "Strobe", "--artist", "deadmau5", "--paused"]
    )
    envelope = build_envelope(args)

    assert envelope.data.paused is True


def test_clear_with_source_builds_clear_envelope():
    args = parse(["--clear", "--source", "phone-music"])
    envelope = build_envelope(args)

    assert envelope.op == "clear"
    assert envelope.source_id == "phone-music"


def test_clear_without_source_clears_all():
    args = parse(["--clear"])
    envelope = build_envelope(args)

    assert envelope.op == "clear"
    assert envelope.source_id is None


def test_presence_without_source_raises_value_error():
    args = parse(["--kind", "generic", "--details", "Working"])
    with pytest.raises(ValueError, match="--source"):
        build_envelope(args)


def test_repeat_flag_defaults_to_none():
    args = parse(["--kind", "generic", "--source", "tasker-status", "--details", "Working"])
    assert args.repeat is None


def test_repeat_flag_parses_float_seconds():
    args = parse(
        ["--kind", "generic", "--source", "tasker-status", "--details", "Working", "--repeat", "10"]
    )
    assert args.repeat == 10.0


# --- send_repeatedly (TTL失効を防ぐための継続送信ループ) ---


async def test_send_repeatedly_calls_send_one_until_it_stops():
    calls = []

    async def send_one() -> None:
        calls.append(1)
        if len(calls) == 3:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        await send_repeatedly(send_one, interval=0)

    assert len(calls) == 3


# --- send_http / send_ws (実サーバへの送受信) ---


def make_app():
    registry = SourceRegistry()
    discord_rpc = AsyncMock()
    discord_rpc.set_activity.return_value = True
    discord_rpc.clear.return_value = True
    discord_rpc.connected = True
    presence_manager = PresenceManager(registry, discord_rpc, config={})
    app = create_app(
        bridge_token=BRIDGE_TOKEN,
        registry=registry,
        presence_manager=presence_manager,
        discord_rpc=discord_rpc,
        ttl_seconds=30.0,
    )
    return app, registry


@pytest.fixture
async def server():
    app, registry = make_app()
    srv = TestServer(app)
    await srv.start_server()
    srv.registry = registry
    yield srv
    await srv.close()


async def test_send_http_presence_success(server):
    base_url = f"http://{server.host}:{server.port}"
    payload = {
        "op": "presence", "kind": "generic", "source_id": "tasker-status",
        "data": {"kind": "generic", "details": "Working"},
    }

    status, body = await send_http(base_url, "/presence", BRIDGE_TOKEN, payload)

    assert status == 200
    assert body == {"ok": True}
    assert server.registry.get("tasker-status") is not None


async def test_send_http_wrong_token_rejected(server):
    base_url = f"http://{server.host}:{server.port}"
    payload = {
        "op": "presence", "kind": "generic", "source_id": "tasker-status",
        "data": {"kind": "generic", "details": "Working"},
    }

    status, body = await send_http(base_url, "/presence", "wrong-token", payload)

    assert status == 401
    assert body["ok"] is False


async def test_send_ws_presence_returns_ack(server):
    base_url = f"http://{server.host}:{server.port}"
    payload = {
        "op": "presence", "kind": "generic", "source_id": "tasker-status",
        "seq": 1, "data": {"kind": "generic", "details": "Working"},
    }

    result = await send_ws(base_url, BRIDGE_TOKEN, payload)

    assert result == {"op": "ack", "seq": 1}


async def test_send_ws_clear_returns_none_when_no_ack(server):
    base_url = f"http://{server.host}:{server.port}"
    payload = {"op": "clear", "source_id": "tasker-status"}

    result = await send_ws(base_url, BRIDGE_TOKEN, payload)

    assert result is None
