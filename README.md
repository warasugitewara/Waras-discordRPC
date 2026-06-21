# Wara's-discordRPC

> スマホなどに組み込まれた送信側信号をpcで受信しDiscordRPCに配信するプロジェクトです

スマホ(Android)で動く自作アプリ/ツールの状態を、PC(Windows 11)の Discord に
**Rich Presence(RPC)** として表示するための **中継ツール(Bridge)**。

Discord のローカル IPC(名前付きパイプ)は同じ PC 上のプロセスからしか叩けない。
そこで「Android → PC へ信号送信 → PC 側がローカル Discord へ RPC を設定」という構成を取る。
本リポジトリは **受信側(PC常駐ツール)** を対象とする。Android 側は別途(後日)実装する。

## ステータス
- **設計完了 / 実装未着手(v1)**。まだソースコードは無い(仕様のみ)。
- 権威ある仕様(SoT):
  - 設計全体 … [`docs/DESIGN.md`](docs/DESIGN.md)
  - 通信契約(Android↔PC)… [`docs/PROTOCOL.md`](docs/PROTOCOL.md)

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

## クイックスタート
> 実装後に追記。現時点ではコード未配置。
> 実装は [`AGENTS.md`](AGENTS.md) の手順に従い、[`docs/DESIGN.md`](docs/DESIGN.md) の
> 「実装順序」マイルストーン1(雛形+config)から着手する。
