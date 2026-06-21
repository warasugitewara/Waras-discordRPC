# AGENTS.md — エージェント向け作業ガイド

本リポジトリで作業する AI エージェント(Claude Code / Codex / その他)向けの共通指示。
Claude Code は `CLAUDE.md` 経由でここを参照する。**着手前に必ず本ファイルと `docs/` を読む。**

## 現状
- **設計のみ完了、コード未実装**。まず仕様を読んでから着手する。
- 権威ある情報源(SoT):
  - 設計全体 … [`docs/DESIGN.md`](docs/DESIGN.md)
  - 通信契約(Android↔PC)… [`docs/PROTOCOL.md`](docs/PROTOCOL.md)
- **推測で API/構成を足さない。** 仕様に無い判断が要るときはユーザーに確認する。

## このプロジェクトの要点(必ず踏まえる)
- 目的: Android からの信号を受けて **ローカル Discord に Rich Presence を表示する PC 常駐ツール**。
- スタック: **Python + PySide6 + pypresence + aiohttp + qasync**(勝手に変更しない)。
- **Discord は 1 アプリ(client_id)= 1 プレゼンス枠**。複数ソースは合成不可 → **調停で 1 つ**を選ぶ。
- **レート ~1 更新/15 秒**・同一 activity は再送しない(短時間に連投すると presence が消える)。
- **フィールド制限**: details / state ≤ 128 文字、button label ≤ 32 文字・最大 2 個・URL は `http(s)`。
- **並行性**: 状態変更は単一 qasync(asyncio)ループ上のみで行う。GUI(Qt)コールバックはループへ委譲。
- **ネットワーク**: Twingate 前提・既定 bind は `127.0.0.1`。**公開ポート開放しない**。
- **秘密情報**: コード埋め込み禁止。`.env`(`BRIDGE_TOKEN` / `DISCORD_CLIENT_ID`)で管理。
  `.env` / `config.json` は **git 管理外**(`.gitignore` 済み)。

## 実装の進め方
`docs/DESIGN.md` の「実装順序(マイルストーン)」に従い、各段を検証しながら 1→8 で進める:
1. 雛形+config(pytest が回る) → 2. models → 3. discord_rpc →
4. sources + mapper + presence_manager → 5. receiver → 6. GUI →
7. tools/send_test + 手動E2E → 8. 配布(PyInstaller)。

**着手前に確認(リスク3点)**:
- pypresence `AioPresence.update()` が受ける引数(特に `activity_type` / `buttons`)を実バージョンで確認。
- 外部 URL 画像(`large_image`)の受理可否を実機 Discord で確認(不可なら external-assets でキー化)。
- qasync 上で aiohttp `AppRunner` と pypresence を同居させたときの動作(ループ共有)。

## ルール(ユーザー方針)
- **要求箇所のみ変更**。無関係なリファクタ/整形/不要な削除をしない。
- 受信側は **Python**(ユーザーの TS 標準とは別。理由は DESIGN 参照)。型安全・例外処理は丁寧に。
- **commit / push は事前承認**。自動コミット禁止。コミットは **日本語 Conventional Commits**。
- 破壊的操作・通信断リスクのある操作は事前確認。

## ディレクトリ構成(予定)
```
Waras-discordRPC/
  README.md  AGENTS.md  CLAUDE.md  .gitignore
  docs/        DESIGN.md  PROTOCOL.md
  app.py
  core/        discord_rpc.py  receiver.py  models.py  mapper.py  sources.py  presence_manager.py
  config/      store.py
  gui/         tray.py  config_window.py  preview.py
  tools/       send_test.py
  assets/      tray_icon.ico ほか
  tests/       test_models.py  test_mapper.py  test_sources.py  test_presence_manager.py  test_receiver.py  test_config.py
  .env.example  config.example.json
  requirements.txt  pyproject.toml(任意)  build.spec  start.bat  build.bat
```
