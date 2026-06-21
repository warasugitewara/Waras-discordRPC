# Wara's-discordRPC

> スマホなどに組み込まれた送信側信号をpcで受信しDiscordRPCに配信するプロジェクトです

スマホ(Android)で動く自作アプリ/ツールの状態を、PC(Windows 11)の Discord に
**Rich Presence(RPC)** として表示するための **中継ツール(Bridge)**。

Discord のローカル IPC(名前付きパイプ)は同じ PC 上のプロセスからしか叩けない。
そこで「Android → PC へ信号送信 → PC 側がローカル Discord へ RPC を設定」という構成を取る。
本リポジトリは **受信側(PC常駐ツール)** を対象とする。Android 側は別途(後日)実装する。

## ステータス
- **実装中(v1)**。[`docs/DESIGN.md`](docs/DESIGN.md)「実装順序(マイルストーン)」の **1〜5 完了 / 6〜8 未着手**。
- 権威ある仕様(SoT):
  - 設計全体 … [`docs/DESIGN.md`](docs/DESIGN.md)
  - 通信契約(Android↔PC)… [`docs/PROTOCOL.md`](docs/PROTOCOL.md)

### 進捗(マイルストーン)
| # | マイルストーン | 状態 | 主なファイル |
|---|---|---|---|
| 1 | 雛形+config | ✅ 完了 | `config/store.py`, `requirements.txt`, `.env.example`, `config.example.json` |
| 2 | models | ✅ 完了 | `core/models.py`(GenericData/MusicData/ManualData/受信封筒) |
| 3 | discord_rpc | ✅ 完了 | `core/discord_rpc.py`(pypresence AioPresenceラッパ、再接続/状態通知) |
| 4 | sources + mapper + presence_manager | ✅ 完了 | `core/sources.py`, `core/mapper.py`, `core/presence_manager.py` |
| 5 | receiver | ✅ 完了 | `core/receiver.py`(WS `/ws` + HTTP `/presence,/clear,/health`) |
| 6 | GUI | 🟨 実装済(実機未検証) | `core/engine.py`(結線+周期tick), `gui/tray.py`, `gui/config_window.py`, `gui/preview.py`, `app.py` |
| 7 | tools/send_test + 手動E2E | ⬜ 未着手 | `tools/send_test.py` |
| 8 | 配布(PyInstaller) | ⬜ 未着手 | `build.spec`, `start.bat`, `build.bat` |

- `core/` の受信〜調停〜Discord送信に加え、**`core/engine.py`(GUI非依存のオーケストレータ)** と
  **Qt GUI(`gui/` + `app.py`)** を実装済み。engine は受信サーバ・調停・Discord送信を結線し、
  周期 tick で TTL 失効反映と保留更新の合体フラッシュを行う。
- テスト: `pytest` で **81件すべて成功**。GUI はオフスクリーン(`QT_QPA_PLATFORM=offscreen`)での
  構築/データ反映スモークテストのみ。Qt ランタイムが無い環境では `tests/test_gui.py` は自動 skip。
- **未検証(要 Windows 11 実機)**: ① GUI の実描画・**システムトレイ常駐**(オフスクリーンでは
  トレイ不可)、② qasync(Qt ループ)上で aiohttp `AppRunner` と pypresence(名前付きパイプ IPC)を
  同居させた際の動作、③ 実 Discord への RPC 反映。詳細は [`AGENTS.md`](AGENTS.md) の「既知のリスク」。
  実機確認は次工程のマイルストーン7(`tools/send_test.py` + 手動E2E)で行う。

## リポジトリの歩き方
| 見る人 | まず読む |
|---|---|
| 人間(概要把握) | この README → [`docs/DESIGN.md`](docs/DESIGN.md) |
| 実装するエージェント(Sonnet/Opus/他) | [`AGENTS.md`](AGENTS.md) → [`docs/DESIGN.md`](docs/DESIGN.md) → [`docs/PROTOCOL.md`](docs/PROTOCOL.md) |
| Android側を作る人 | [`docs/PROTOCOL.md`](docs/PROTOCOL.md)(送受信の契約=SoT) |

## 技術スタック(決定済み)
Python + PySide6(トレイ+設定GUI) + pypresence(Discord IPC) + aiohttp(WS+HTTP) + qasync。
選定理由は [`docs/DESIGN.md`](docs/DESIGN.md) を参照。

## できること(v1 設計目標)
- Android からの信号を **WS(主)/ HTTP(補助)** で受信し、ローカル Discord に RPC 表示。
- **汎用RPC + 音楽再生プリセット**の両対応。
- **複数ソースを GUI で個別管理**(有効/無効・優先度・active固定)。Discord は1枠なので調停で1つを表示。
- **手動モード(RikoRPC風)**: PC側だけで文字/画像を入力して自作プレゼンスを表示。
- **Twingate** のプライベート経由で **IP 接続**(公開ポート開放なし)。

## ライセンス
[MIT License](LICENSE) © 2026 .warasugi

## クイックスタート(開発中)
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest                      # core/ のロジックを Discord 不要で検証
```
- 起動(Windows 11 実機推奨): `.env`(`DISCORD_CLIENT_ID`/`BRIDGE_TOKEN`)を用意し、
  `python app.py` でトレイ常駐 + 受信サーバが起動する(Discord を先に起動しておく)。
  ※ヘッドレス/トレイ無し環境では起動できない。
- 次の作業: [`docs/DESIGN.md`](docs/DESIGN.md)「実装順序」**マイルストーン7(`tools/send_test.py` + 手動E2E)**。
  ここで qasync + aiohttp + pypresence の同居と実 Discord 反映を Windows 11 実機で確認する([`AGENTS.md`](AGENTS.md)参照)。
