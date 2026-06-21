import asyncio
from unittest.mock import AsyncMock

import pytest
from pypresence.exceptions import PipeClosed

from core.discord_rpc import DiscordRPC


def make_rpc(presence_client=None, on_state_change=None):
    return DiscordRPC(
        client_id="123",
        on_state_change=on_state_change,
        presence_client=presence_client or AsyncMock(),
    )


async def test_start_connects_and_notifies_connected():
    states = []
    client = AsyncMock()
    rpc = make_rpc(client, on_state_change=states.append)

    rpc.start()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert rpc.connected is True
    assert states == ["connected"]
    client.connect.assert_awaited_once()

    await rpc.stop()


async def test_connect_failure_retries_with_backoff(monkeypatch):
    sleep_calls = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay):
        sleep_calls.append(delay)
        await real_sleep(0)  # 実際にイベントループへ制御を返す(テストコルーチンを進行させる)

    monkeypatch.setattr("core.discord_rpc.asyncio.sleep", fake_sleep)

    client = AsyncMock()
    client.connect.side_effect = [PipeClosed(), PipeClosed(), None]
    rpc = make_rpc(client)

    rpc.start()
    for _ in range(10):
        if rpc.connected:
            break
        await real_sleep(0)

    assert rpc.connected is True
    assert sleep_calls[:2] == [1.0, 2.0]

    await rpc.stop()


async def test_set_activity_sends_payload_with_mapped_activity_type():
    client = AsyncMock()
    rpc = make_rpc(client)
    rpc.start()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    ok = await rpc.set_activity({"details": "Working", "activity_type": "listening"})

    assert ok is True
    client.update.assert_awaited_once_with(details="Working", activity_type=2)

    await rpc.stop()


async def test_set_activity_failure_marks_disconnected():
    states = []
    client = AsyncMock()
    rpc = make_rpc(client, on_state_change=states.append)
    rpc.start()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    client.update.side_effect = PipeClosed()
    ok = await rpc.set_activity({"details": "Working"})

    assert ok is False
    assert rpc.connected is False
    assert states == ["connected", "disconnected"]

    await rpc.stop()


async def test_set_activity_skips_when_not_connected():
    client = AsyncMock()
    rpc = make_rpc(client)  # start() を呼ばないので未接続

    ok = await rpc.set_activity({"details": "Working"})

    assert ok is False
    client.update.assert_not_called()


async def test_clear_skips_when_not_connected():
    client = AsyncMock()
    rpc = make_rpc(client)

    ok = await rpc.clear()

    assert ok is False
    client.clear.assert_not_called()


async def test_clear_success():
    client = AsyncMock()
    rpc = make_rpc(client)
    rpc.start()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    ok = await rpc.clear()

    assert ok is True
    client.clear.assert_awaited_once()

    await rpc.stop()


async def test_stop_clears_when_connected():
    client = AsyncMock()
    rpc = make_rpc(client)
    rpc.start()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    await rpc.stop()

    client.clear.assert_awaited_once()
    assert rpc.connected is False
