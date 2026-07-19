# Wara's-discordRPC

![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-41CD52?logo=qt&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-green)
![status](https://img.shields.io/badge/status-v1%20complete-success)

> スマホ等の外部ソースの状態を、PC のローカル Discord に **Rich Presence** として表示する常駐ブリッジ。

Discord のローカル IPC(名前付きパイプ)は同じ PC 上のプロセスからしか叩けない。そこで
「Android → PC へ信号送信 → PC 側がローカル Discord へ RPC を設定」という構成を取る。
本リポジトリは **受信側(PC 常駐ツール)** を対象とする。

## ✨ Features

- 🎮 汎用 RPC + 🎵 音楽再生プリセット(進捗バー対応)
- 🔀 複数ソースを GUI で個別管理(有効/無効・優先度・pin)→ Discord 1 枠を調停して表示
- ✍️ 手動モード(PC 側だけで自作プレゼンスを表示)
- 🖥️ タスクトレイ常駐 + 設定 GUI(初回セットアップウィザード付き)
- 📡 WebSocket(主)/ HTTP(補助)で受信
- 🔒 Twingate 前提・既定 bind `127.0.0.1`(公開ポート開放なし)

## 🚀 クイックスタート

**配布版(エンドユーザー)**

1. zip を展開して `start.bat` を実行
2. 初回ウィザードで Application ID と Bridge Token を入力
3. タスクトレイに常駐 → Discord に表示

詳しい手順は **[`docs/SETUP.md`](docs/SETUP.md)**。

**開発**

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
pytest                         # Discord 不要でロジック検証
python app.py                  # トレイ常駐 + 受信サーバ(Discord を先に起動)
```

配布用 exe は `build.bat`(PyInstaller onedir)でビルドする。

## 📚 ドキュメント

| 目的 | ドキュメント |
|---|---|
| 導入・使い方 | [`docs/SETUP.md`](docs/SETUP.md) |
| 設計全体(SoT) | [`docs/DESIGN.md`](docs/DESIGN.md) |
| 通信契約 Android↔PC(SoT) | [`docs/PROTOCOL.md`](docs/PROTOCOL.md) |
| 繋がらないときの切り分け | [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)(認証不要の `GET /ping` で経路と設定を分離) |
| エージェント向けガイド | [`AGENTS.md`](AGENTS.md) |

送信側(Android)は別リポジトリ [Waras-AppleMusic-RPC](https://github.com/warasugitewara/Waras-AppleMusic-RPC)。

## 🛠️ 技術スタック

Python + PySide6(トレイ + 設定 GUI)+ pypresence(Discord IPC)+ aiohttp(WS/HTTP)+ qasync。
選定理由は [`docs/DESIGN.md`](docs/DESIGN.md) を参照。

## ✅ ステータス

**v1 実装完了**(マイルストーン 1〜8)。`pytest` **116 件 green**。
実機(Windows 11 + Discord Desktop)で手動 E2E 検証済み。

<details>
<summary>進捗(マイルストーン)と実機検証で修正した不具合</summary>

| # | マイルストーン | 主なファイル |
|---|---|---|
| 1 | 雛形 + config | `config/store.py` |
| 2 | models | `core/models.py` |
| 3 | discord_rpc | `core/discord_rpc.py` |
| 4 | sources + mapper + presence_manager | `core/sources.py` ほか |
| 5 | receiver | `core/receiver.py` |
| 6 | GUI | `core/engine.py`, `gui/`, `app.py` |
| 7 | tools/send_test + 手動 E2E | `tools/send_test.py` |
| 8 | 配布(PyInstaller) | `build.spec`, `start.bat`, `build.bat` |

実機検証で見つけて修正した不具合:

- トレイアイコンが空で非表示(`Tray` に `parent` 未渡し)
- receiver 経由の更新が GUI 一覧に反映されない(`Engine` への通知漏れ)
- pin が複数ソースで同時 ON 可能 → 排他化
- `start.bat` が LF 改行で起動できない → CRLF 化
- packaged exe(`console=False`)で「終了」が効かない(`stdout`/`stderr` が None + `DiscordError` 捕捉漏れ)

</details>

## License

[MIT](LICENSE) © 2026 .warasugi
