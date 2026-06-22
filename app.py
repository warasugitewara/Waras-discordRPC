"""エントリポイント。

config/.env 読込 → QApplication + qasync ループ起動 → Engine を結線 →
トレイ常駐。GUI(Qt)と受信/IPC(asyncio)は qasync により単一ループ・単一
スレッドで同居する。GUI コールバックからの状態変更は asyncio.ensure_future で
同じループに委譲する(SourceRegistry の競合を避ける)。
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Any, Awaitable

from config.store import ConfigStore, Secrets

logger = logging.getLogger(__name__)


def _schedule(coro: Awaitable[Any]) -> "asyncio.Task[Any]":
    """GUI コールバックから engine のコルーチンを現在のループへ投入する。"""
    return asyncio.ensure_future(coro)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)

    # 重い GUI/非同期依存は main 内で遅延 import(テストや headless 解析を妨げない)。
    import qasync
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

    from core.engine import Engine
    from gui.config_window import ConfigWindow
    from gui.tray import Tray

    config = ConfigStore(Path("config.json")).load()
    store = ConfigStore(Path("config.json"))
    secrets = Secrets.load()

    if not secrets.discord_client_id:
        logger.warning("DISCORD_CLIENT_ID が未設定です(.env を確認してください)")

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Wara's-discordRPC")
    app.setQuitOnLastWindowClosed(False)  # ウィンドウを閉じてもトレイ常駐を続ける

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    engine = Engine(config, secrets, store=store)
    window = ConfigWindow(engine, _schedule)

    def open_settings() -> None:
        window.show()
        window.raise_()
        window.activateWindow()

    def quit_app() -> None:
        async def _shutdown() -> None:
            await engine.stop()
            loop.stop()

        asyncio.ensure_future(_shutdown())

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(None, "Wara's-discordRPC", "システムトレイが利用できません。")

    icon_path = Path("assets/tray_icon.png")
    icon = QIcon(str(icon_path)) if icon_path.exists() else None
    if icon is not None:
        app.setWindowIcon(icon)
        window.setWindowIcon(icon)
    tray = Tray(engine, on_open_settings=open_settings, on_quit=quit_app, icon=icon, parent=window)
    tray.show()

    with contextlib_suppress():
        signal.signal(signal.SIGINT, lambda *_: quit_app())

    with loop:
        loop.create_task(engine.start())
        loop.run_forever()
    return 0


def contextlib_suppress() -> Any:
    import contextlib

    # Windows では SIGINT のハンドラ設定が一部制限されるため握りつぶす。
    return contextlib.suppress(ValueError, RuntimeError, AttributeError)


if __name__ == "__main__":
    raise SystemExit(main())
