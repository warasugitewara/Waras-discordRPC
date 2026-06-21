from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from core.presence_manager import PresenceManager
from core.receiver import RateLimiter, create_app
from core.sources import SourceRegistry

BRIDGE_TOKEN = "secret-token"
AUTH_HEADERS = {"Authorization": f"Bearer {BRIDGE_TOKEN}"}


def test_rate_limiter_release_evicts_key():
    limiter = RateLimiter(max_messages=1, window_seconds=60.0)
    key = object()
    assert limiter.allow(key) is True
    assert limiter.allow(key) is False  # 上限到達

    limiter.release(key)

    assert limiter.allow(key) is True  # キー破棄後はリセットされる


def make_client_deps():
    registry = SourceRegistry()
    discord_rpc = AsyncMock()
    discord_rpc.set_activity.return_value = True
    discord_rpc.clear.return_value = True
    discord_rpc.connected = True
    presence_manager = PresenceManager(registry, discord_rpc, config={})
    return registry, discord_rpc, presence_manager


@pytest.fixture
async def client():
    registry, discord_rpc, presence_manager = make_client_deps()
    app = create_app(
        bridge_token=BRIDGE_TOKEN,
        registry=registry,
        presence_manager=presence_manager,
        discord_rpc=discord_rpc,
        ttl_seconds=30.0,
    )
    test_client = TestClient(TestServer(app))
    await test_client.start_server()
    test_client.registry = registry
    test_client.discord_rpc = discord_rpc
    test_client.presence_manager = presence_manager
    yield test_client
    await test_client.close()


async def test_health_requires_auth(client):
    resp = await client.get("/health")
    assert resp.status == 401


async def test_health_reports_status(client):
    resp = await client.get("/health", headers=AUTH_HEADERS)
    body = await resp.json()
    assert resp.status == 200
    assert body == {"status": "ok", "discord": "connected", "active_source": None}


async def test_presence_generic_updates_registry_and_sends_activity(client):
    resp = await client.post(
        "/presence",
        headers=AUTH_HEADERS,
        json={
            "kind": "generic",
            "source_id": "tasker-status",
            "data": {"details": "Working", "state": "Focus mode"},
        },
    )
    body = await resp.json()

    assert resp.status == 200
    assert body == {"ok": True}
    assert client.registry.get("tasker-status") is not None
    client.discord_rpc.set_activity.assert_awaited_once()

    health = await client.get("/health", headers=AUTH_HEADERS)
    health_body = await health.json()
    assert health_body["active_source"] == "tasker-status"


async def test_presence_rejects_wrong_token(client):
    resp = await client.post(
        "/presence",
        headers={"Authorization": "Bearer wrong"},
        json={"kind": "generic", "source_id": "a", "data": {"details": "x"}},
    )
    assert resp.status == 401


async def test_presence_rejects_invalid_payload(client):
    resp = await client.post(
        "/presence",
        headers=AUTH_HEADERS,
        json={"kind": "generic", "source_id": "a", "data": {}},
    )
    assert resp.status == 400


async def test_clear_removes_source_data(client):
    await client.post(
        "/presence",
        headers=AUTH_HEADERS,
        json={"kind": "generic", "source_id": "a", "data": {"details": "x"}},
    )

    resp = await client.post("/clear", headers=AUTH_HEADERS, json={"source_id": "a"})
    body = await resp.json()

    assert resp.status == 200
    assert body == {"ok": True}
    assert client.registry.get("a").data is None


async def test_ws_requires_auth():
    registry, discord_rpc, presence_manager = make_client_deps()
    app = create_app(
        bridge_token=BRIDGE_TOKEN,
        registry=registry,
        presence_manager=presence_manager,
        discord_rpc=discord_rpc,
    )
    async with TestClient(TestServer(app)) as test_client:
        ws = await test_client.ws_connect("/ws")
        msg = await ws.receive()
        assert msg.type.name == "CLOSE"
        assert msg.data == 4001


async def test_ws_presence_flow_and_disconnect_clears_source():
    registry, discord_rpc, presence_manager = make_client_deps()
    app = create_app(
        bridge_token=BRIDGE_TOKEN,
        registry=registry,
        presence_manager=presence_manager,
        discord_rpc=discord_rpc,
    )
    async with TestClient(TestServer(app)) as test_client:
        ws = await test_client.ws_connect(f"/ws?token={BRIDGE_TOKEN}")

        ready = await ws.receive_json()
        assert ready == {"op": "ready"}

        await ws.send_json(
            {
                "op": "presence",
                "kind": "music",
                "source_id": "phone-music",
                "seq": 1,
                "data": {"title": "Strobe", "artist": "deadmau5"},
            }
        )
        ack = await ws.receive_json()
        assert ack == {"op": "ack", "seq": 1}
        assert registry.get("phone-music") is not None

        await ws.close()

    assert registry.get("phone-music").data is None


async def test_ws_ping_pong():
    registry, discord_rpc, presence_manager = make_client_deps()
    app = create_app(
        bridge_token=BRIDGE_TOKEN,
        registry=registry,
        presence_manager=presence_manager,
        discord_rpc=discord_rpc,
    )
    async with TestClient(TestServer(app)) as test_client:
        ws = await test_client.ws_connect(f"/ws?token={BRIDGE_TOKEN}")
        await ws.receive_json()  # ready

        await ws.send_json({"op": "ping"})
        pong = await ws.receive_json()
        assert pong == {"op": "pong"}


async def test_ws_rate_limit_triggers_error_op():
    registry, discord_rpc, presence_manager = make_client_deps()
    app = create_app(
        bridge_token=BRIDGE_TOKEN,
        registry=registry,
        presence_manager=presence_manager,
        discord_rpc=discord_rpc,
        rate_limiter=RateLimiter(max_messages=2, window_seconds=60.0),
    )
    async with TestClient(TestServer(app)) as test_client:
        ws = await test_client.ws_connect(f"/ws?token={BRIDGE_TOKEN}")
        await ws.receive_json()  # ready

        for _ in range(2):
            await ws.send_json({"op": "ping"})
            await ws.receive_json()

        await ws.send_json({"op": "ping"})
        result = await ws.receive_json()
        assert result == {"op": "error", "message": "rate limit exceeded"}
