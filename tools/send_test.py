"""動作確認用の送信スクリプト。docs/PROTOCOL.md 準拠の presence/clear を WS/HTTP で送出する。

例:
    python tools/send_test.py --kind generic --source tasker-status --details Working
    python tools/send_test.py --kind music --source phone-music --title Strobe --artist deadmau5 \
        --duration-ms 634000 --position-ms 42000
    python tools/send_test.py --clear --source phone-music
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.store import ConfigStore, Secrets  # noqa: E402
from core.models import Button, ClearEnvelope, GenericData, MusicData, PresenceEnvelope  # noqa: E402

WS_RESPONSE_TIMEOUT_SECONDS = 2.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=["ws", "http"], default="ws")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument(
        "--repeat",
        type=float,
        default=None,
        metavar="SECONDS",
        help="指定秒間隔で同じpayloadをCtrl+Cまで再送し続ける(TTL失効を防ぐ手動E2E用)",
    )

    parser.add_argument("--clear", action="store_true", help="presenceの代わりにclearを送信する")
    parser.add_argument("--kind", choices=["generic", "music"])
    parser.add_argument("--source", help="source_id")
    parser.add_argument("--source-name", default=None)

    # generic用
    parser.add_argument("--details")
    parser.add_argument("--state")
    parser.add_argument(
        "--activity-type", choices=["playing", "listening", "watching", "competing"], default="playing"
    )
    parser.add_argument("--large-image")
    parser.add_argument("--large-text")
    parser.add_argument("--small-image")
    parser.add_argument("--small-text")
    parser.add_argument("--start-ms", type=int, default=None)
    parser.add_argument("--end-ms", type=int, default=None)
    parser.add_argument(
        "--button", nargs=2, metavar=("LABEL", "URL"), action="append", default=None
    )

    # music用
    parser.add_argument("--title")
    parser.add_argument("--artist")
    parser.add_argument("--album")
    parser.add_argument("--artwork-url")
    parser.add_argument("--duration-ms", type=int, default=None)
    parser.add_argument("--position-ms", type=int, default=None)
    parser.add_argument("--paused", action="store_true")

    return parser


def build_envelope(args: argparse.Namespace) -> PresenceEnvelope | ClearEnvelope:
    """argparse の結果から検証済みの envelope を構築する。不正な値は ValidationError/ValueError を送出する。"""
    if args.clear:
        return ClearEnvelope(source_id=args.source)

    if not args.source:
        raise ValueError("--source is required (presenceの送信には source_id が必要です)")

    if args.kind == "generic":
        buttons = [Button(label=label, url=url) for label, url in (args.button or [])]
        data: GenericData | MusicData = GenericData(
            details=args.details,
            state=args.state,
            activity_type=args.activity_type,
            large_image=args.large_image,
            large_text=args.large_text,
            small_image=args.small_image,
            small_text=args.small_text,
            start_ms=args.start_ms,
            end_ms=args.end_ms,
            buttons=buttons,
        )
    else:
        data = MusicData(
            title=args.title,
            artist=args.artist,
            album=args.album,
            artwork_url=args.artwork_url,
            duration_ms=args.duration_ms,
            position_ms=args.position_ms,
            paused=args.paused,
        )

    return PresenceEnvelope(
        kind=args.kind,
        source_id=args.source,
        source_name=args.source_name,
        data=data,
    )


async def send_http(base_url: str, path: str, token: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """HTTPで payload を送信し、(status, body) を返す。"""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{base_url}{path}", json=payload, headers={"Authorization": f"Bearer {token}"}
        ) as resp:
            body = await resp.json()
            return resp.status, body


async def send_ws(base_url: str, token: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """WSで payload を送信し、サーバ応答(ack/error)を返す。応答が無ければ None。"""
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(ws_url, headers={"Authorization": f"Bearer {token}"}) as ws:
            await ws.receive_json()  # {"op": "ready"}
            await ws.send_json(payload)
            try:
                async with asyncio.timeout(WS_RESPONSE_TIMEOUT_SECONDS):
                    return await ws.receive_json()
            except (asyncio.TimeoutError, TimeoutError):
                return None


async def send_repeatedly(send_one: Any, interval: float) -> None:
    """send_one() を interval 秒おきに呼び続ける。send_one が例外を出したら抜ける(Ctrl+C用)。"""
    while True:
        await send_one()
        await asyncio.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    secrets = Secrets.load()
    config = ConfigStore().load()
    host = args.host or config["bind"]
    port = args.port or config["port"]
    token = args.token or secrets.bridge_token

    try:
        envelope = build_envelope(args)
    except Exception as exc:  # ValidationError / ValueError
        print(f"ERROR: invalid payload: {exc}", file=sys.stderr)
        return 1

    payload = envelope.model_dump(mode="json", exclude_none=True)
    base_url = f"http://{host}:{port}"
    path = "/clear" if args.clear else "/presence"

    failed = False

    async def send_once() -> None:
        nonlocal failed
        if args.transport == "ws":
            result = await send_ws(base_url, token, payload)
            if result is not None and result.get("op") == "error":
                print(f"ERROR: server rejected: {result.get('message')}", file=sys.stderr)
                failed = True
                return
            print(f"OK: {result}")
        else:
            status, body = await send_http(base_url, path, token, payload)
            if status >= 400:
                print(f"ERROR: HTTP {status}: {body}", file=sys.stderr)
                failed = True
                return
            print(f"OK: HTTP {status}: {body}")

    try:
        if args.repeat is None:
            asyncio.run(send_once())
        else:
            try:
                asyncio.run(send_repeatedly(send_once, args.repeat))
            except KeyboardInterrupt:
                print("\n停止しました(Ctrl+C)")
    except aiohttp.ClientError as exc:
        print(f"ERROR: connection failed: {exc}", file=sys.stderr)
        return 1

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
