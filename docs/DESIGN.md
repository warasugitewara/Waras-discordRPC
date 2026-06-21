# Discord RPC Bridge(PC受信側)— 設計(v1)

> 通信契約(Android↔PC のメッセージ仕様)は [`PROTOCOL.md`](PROTOCOL.md) を SoT とする。
> 本書はアーキテクチャと実装方針を定義する。

## 背景・目的
スマホ(Android)で動く自作アプリ/ツールの状態を、PC(Windows 11)の Discord に
**Rich Presence(RPC)** として表示したい。Discord のローカル名前付きパイプは
**その PC で動くプロセスからしか叩けない**ため、「Android → PC へ信号を送り、PC 側が
ローカル Discord へ RPC を設定する中継役(Bridge)」が必要になる。

本書は **受信側 = PC 常駐ツール** の v1 設計。Android 側は別途。
受信は JSON 契約(言語非依存)なので、後で作る Android(Kotlin)実装を縛らない。

参考実装: [MuseHeart-MusicBot-RPC-app](https://github.com/zRitsu/MuseHeart-MusicBot-RPC-app)
(Python + Qt + トレイ + WS 受信 + pypresence。今回と同型で実証済み)。
手動モードの参考: [RikoRPC](https://github.com/ddasutein/RikoRPC)(PC側で文字/画像キーを手入力)。

## スコープ(v1)
- 入力(信号): **両対応** = 汎用RPCブリッジ + 音楽再生プリセット。
- 受信: **WS 主 + HTTP 補助**(両方)。
- 起動形態: **システムトレイ常駐 + 設定GUI**。
- ローカル Discord へ RPC 送信(**Application ID のみ、Bot Token 不要**)。
- **複数ソースの個別管理**: 受信信号を `source_id` で識別(同一クライアントでも別 stream は別ソース)。
  GUI で各ソースを **有効/無効・優先度・active固定(pin)**。Discord は1枠なので調停で勝者1つを表示。
- **手動(ローカル)モード(RikoRPC風)**: Android の信号なしに、PC 側だけで
  details/state/画像/ボタン等を入力して自作プレゼンスを表示。これも 1 つの
  「ソース(`source_id="manual"`)」として同じ仕組みで管理。
- ネットワーク到達は **Twingate のプライベートオーバーレイ経由**を前提(公開ポート開放しない)。
  サーバは到達可能な IP にバインドし、Android は **IP:port で接続**(Twingate 透過のため追加実装不要)。
  既定 bind は `127.0.0.1`(安全側)、GUI の「ネットワークモード」で IP/`0.0.0.0` へ切替。

### 非スコープ(v1外)
- Android 実装、OAuth(AUTHORIZE)系 RPC、Join/Spectate。
- 複数ソースを 1 枠に **合成して同時表示**(Discord 仕様上不可。調停で 1 つを選ぶ)。
- 手動モードの **ローカルファイル画像アップロード**(v1 はアセットキー/外部URLのみ。将来 external-assets で対応)。

## 技術スタックと根拠
**Python + PySide6 + pypresence + aiohttp(+ qasync)**
- 処理速度はどのスタックでも差が出ない(負荷 = 数秒に1回の JSON 受信 + パイプ書込)。
  差が出るのは **常駐メモリと実装の現実性** → トレイ+GUI 要件で重い Electron は除外。
- PySide6 + pypresence + WS は参考 MuseHeart で実証済み = 低リスク・最短で v1。
- `pypresence` が名前付きパイプ IPC を完全に隠蔽(`AioPresence`)。
- `aiohttp` 1 つで WS(`/ws`)+ HTTP(`/presence` 他)両方を最小依存で賄う。
- `qasync` で asyncio を Qt のイベントループ上に載せ、**単一スレッド・単一ループ**で
  GUI/受信/IPC を同居(スレッド間競合を避ける)。
- TS 標準から外す理由: トレイ+GUI+名前付きパイプ IPC の三点同時要件を、低フットプリント
  かつ実証済みで満たせるのがこの構成のため。
- 代替(v1 採用せず): **Rust + Tauri** は常駐メモリ最小だが Rust/ビルド構成増で現実性低下。
  最小フットプリントを最優先する場合のみ将来検討。

依存(最小): `pypresence` / `aiohttp` / `pydantic`(検証) / `PySide6` / `qasync` /
`python-dotenv`。dev: `pytest` / `pytest-asyncio` / `pyinstaller`。

## アーキテクチャ(モジュール構成)
単一プロセス。Qt メインスレッドに qasync で 1 つの asyncio ループを載せ、その上で
受信サーバと Discord IPC を動かす。GUI は設定編集と状態/プレビュー表示のみ。

- `app.py` … エントリ。config 読込 → QApplication + qasync ループ起動 → 各部品を結線。
- `core/discord_rpc.py` … pypresence `AioPresence` ラッパ。connect/再接続(指数バックオフ)、
  `set_activity(activity: dict)`、`clear()`、状態(connected/disconnected)通知。
- `core/receiver.py` … aiohttp `web.Application`。`GET /ws`、`POST /presence`、`POST /clear`、
  `GET /health`。認証・検証後に core へ委譲。詳細は [`PROTOCOL.md`](PROTOCOL.md)。
- `core/models.py` … pydantic モデル(`GenericData` / `MusicData` / `ManualData` / 受信封筒)。
  Discord 制限を検証(details/state/large_text/small_text ≤128、button label ≤32・URL は http(s)、
  buttons 最大2、activity_type ∈ {playing, listening, watching, competing})。
- `core/sources.py` … `SourceRegistry`。ソース(feed/manual)を `source_id` で管理。
  enabled / priority / pin・最新 data・updated_at・expires_at・origin_conn を保持。GUI/受信から更新。
- `core/mapper.py` … 受信 payload(generic/music/manual)→ Discord activity dict 変換。
  設定(client_id, ボタン, アセット上書き, ブラックリスト)を適用。**両対応の核**。
- `core/presence_manager.py` … SourceRegistry を **調停**(後述)して勝者を選定 → mapper → discord_rpc。
  TTL/heartbeat 自動 clear、レート制御(合体・最小15s間隔・同一 activity は再送しない)、WS 切断時 clear。
- `config/store.py` … `config.json`(GUI 編集可)+ `.env`(秘密)読み書き。
- `gui/tray.py` … トレイ常駐(開始/停止/設定を開く/状態/終了)。
- `gui/config_window.py` … 設定画面。タブ: 接続/ネットワーク、**ソース一覧**(各行で
  有効/無効トグル・優先度↑↓・active ピン・stale 表示・「忘れる」)、**手動モード編集**
  (activity_type/details/state/画像/ボタン/タイムスタンプ + プレビュー + オンライン化)、
  表示/アセット上書き/ブラックリスト。
- `gui/preview.py` … 現在の RPC プレビューカード + 接続/active source 状態インジケータ。
- `tools/send_test.py` … 動作確認用の送信スクリプト(WS/HTTP でサンプル payload 送出)。

### データフロー
```
Android → (WS/HTTP) receiver → models検証 → SourceRegistry更新 →
presence_manager調停(勝者選定/TTL/レート) → mapper(activity化) →
discord_rpc(pypresence) → ローカルDiscord
```
- 手動モードは receiver を経ず **GUI → SourceRegistry(`source_id="manual"`)** へ反映。
- GUI ⇔ core は Qt シグナルで状態/プレビューを反映。
- **すべての状態変更は単一の asyncio(qasync)ループ上で実行**(GUI コールバックは
  `run_coroutine_threadsafe` / `call_soon_threadsafe` でループへ委譲)し、SourceRegistry の競合を避ける。

## ソース管理と調停(複数ソース/手動モードの核)
**前提**: Discord は「1 アプリ(client_id)= プロフィール上に 1 プレゼンス枠」。よって複数ソースを
同時に並べることはできず、**有効なソースから 1 つを選んで表示**する(調停)。

**Source(`core/sources.py` の保持単位)**:
```
Source { source_id, name, kind(generic|music|manual), enabled, priority(int),
         pinned(bool), data(dict|None), updated_at, expires_at|None, origin_conn|None }
```
- feed ソースは初出時に自動登録し、以後 GUI に残す(idle 時もトグル可能)。
  enabled / priority / name は config に永続化(`source_id` キー)。data 自体は揮発。
- 手動ソース: `source_id="manual"`、`kind="manual"`、`expires_at=None`(TTL なし)、**data は config 永続**。

**調停 `presence_manager.select_active()`**:
1. 候補 = `enabled` かつ data 有り かつ 未失効(`expires_at` 未到来 or None)のソース。
2. `pinned=True` のソースが候補にあれば最優先。無ければ `(priority desc, updated_at desc)` で先頭。
3. 勝者を mapper で activity 化。**前回送信と同一なら送らない**。最小 15s 間隔でレート制御(合体)。
4. 候補ゼロなら `clear()`(`auto_clear_on_disconnect` / TTL 方針に従う)。
- 再評価トリガ: feed 受信 / GUI トグル・優先度変更・pin 変更 / 手動編集 / TTL 満了タイマ / WS 切断。
- 選定方針(`selection_policy`)は既定 `"priority"`(将来 `"latest"` も可)。

**ライフサイクル**: feed 受信ごとに該当ソースの `data/updated_at` 更新・`expires_at = now + ttl`。
WS 切断時はその conn が供給した `source_id` 群を即時失効(`auto_clear_on_disconnect`)。TTL は保険。

## Discord アクティビティへのマッピング(mapper)
共通: activity へ `client_id` を付与(設定の既定 or ソース別上書き)。

- **generic**: フィールドを概ねそのまま activity へ。`activity_type` 既定 = playing。
  timestamps は `start_ms`/`end_ms`(指定時)。buttons は最大2・http(s) のみ通す。
- **music**: `activity_type=listening`、`details=title`、`state=artist`、
  `large_image=artwork_url`(外部URL)、`large_text=album`。
  **進捗バー**は `position_ms`/`duration_ms` から `start = now - position`、`end = start + duration`
  を算出して付与(= 毎秒送信せずとも Discord が経過を描画)。`paused=true` 時は
  timestamps 除去 or `small_image=pause` アイコン。曲変更/再生・停止/シーク時のみ送信。
- **manual**(GUI 入力): `ManualData` をそのまま activity 化。`activity_type`(4種)、details/state、
  `large_image`/`small_image`(**アセットキー** or 外部 https URL)、large_text/small_text、
  buttons(最大2)、`timestamp_mode`(none / オンライン化時刻からの経過 / custom start_ms·end_ms)。

### 画像の扱い
- 動的アートワークは外部 URL を `large_image` に直渡し(RPC は URL → `mp:external/` でプロキシ受理)。
- 再生/一時停止など固定の小アイコンは、アプリの Art Assets へアップロードした **キー名**を使用
  (`small_image` の URL 直渡しは不安定なため)。
- 不調時のフォールバック: `POST /applications/{app_id}/external-assets` で `mp:` キー化する経路も用意可能。
- 参考: [Setting Rich Presence](https://docs.discord.com/developers/discord-social-sdk/development-guides/setting-rich-presence) /
  [external-assets](https://github.com/discord/discord-api-docs/discussions/6592)。

## 設定(config.json は GUI 編集 / 秘密は .env)
- `.env`: `BRIDGE_TOKEN`(共有トークン), `DISCORD_CLIENT_ID`。`.env.example` を同梱。
- `config.json`(先頭に `version` を持ち将来移行可能に):
  - `network_mode`(`"local"`=127.0.0.1 / `"twingate"`=指定IP or 0.0.0.0)、`bind`(IP)/`port`
  - `client_id` 既定 + ソース別上書き、`selection_policy`(`"priority"`)
  - `sources`(既知ソースの `{ source_id: { name, enabled, priority, pinned } }` を永続)
  - `manual`(手動ソースの `ManualData`)
  - 表示設定(kind 別の既定 activity_type、小アイコン表示等)、buttons 既定(最大2)、
    アセット URL/キー上書き(play/pause/idle)、ブラックリスト(title/artist で非表示)
  - `auto_clear_on_disconnect`、`ttl_seconds`(既定 ~30)、`min_update_interval`(既定 15)
- 秘密はコード埋め込み禁止(Secret Manager > 環境変数 > .env の順)。`.env` は git 管理外。

## 信頼性・再接続・レート制御
- Discord 未起動: IPC 接続失敗 → 指数バックオフ再接続、トレイに「Discord 未接続」表示。
- WS 切断/HTTP 無更新: `auto_clear_on_disconnect` または `ttl_seconds` 経過で該当ソースを失効 → 再調停。
- レート制御: **最小 15s 間隔**で送出し、その間の更新は合体して最新のみ送る。**前回と同一 activity は送らない**
  (Discord は短時間に連投すると presence が消えるため)。音楽進捗は timestamps 任せで再送しない。
- 調停は状態変化のたびに再評価。**勝者交代/内容変化時のみ送信**。
- **単一インスタンス**(多重起動防止)でパイプ競合を回避。終了時は `clear()` してから切断。
- ログ: 接続状態・調停結果・送信 activity・エラーをファイル + トレイ通知に出力。

## セキュリティ
- **Twingate 前提**: PC を Twingate Resource(IP + 対象 port のみ)として公開し、Android は
  Twingate クライアントとしてアクセス。**ポート開放/公開エンドポイント不要**、
  ユーザ単位の認証付きオーバーレイ内通信 = 外部露出を最小化。Cloudflare Tunnel は代替。
- 多層防御: **共有トークン認証 + 受信レート制限**。`network_mode=twingate` でもトークン必須。
- bind は必要 IP のみ。`network_mode=local` 既定で誤公開を防止。
- 入力は pydantic で検証(buttons 数 / URL スキーム / 文字長など)。
- TLS: Twingate オーバーレイ内のためアプリは平文 HTTP/WS で可(経路は Twingate が保護)。

## プロジェクト構成
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

## 実装順序(マイルストーン。各段で検証可能)
1. **雛形+config**: プロジェクト構成・`requirements.txt`・`.env.example`・`config.example.json`・
   `config/store.py`(version 付き読み書き)。`pytest` が回る状態に。
2. **models**: `GenericData`/`MusicData`/`ManualData`/受信封筒 + Discord 長さ・buttons・URL 検証。単体テスト。
3. **discord_rpc**: pypresence `AioPresence` ラッパ(connect/再接続/set_activity/clear/状態通知)。
   実 Discord 任意・基本はモックでテスト。**先に「既知のリスク」の3点を確認**。
4. **sources + mapper + presence_manager**: SourceRegistry、generic/music/manual のマッピング、調停
   (優先度/pin/TTL/同一非再送/15s レート)。Discord 不要のロジック単体・結合テストを厚く。
5. **receiver**: aiohttp WS(`/ws`)+ HTTP(`/presence`,`/clear`,`/health`)+ トークン認証 +
   source_id 処理 + 切断時失効。テストクライアントで結合テスト。
6. **GUI**: qasync で Qt + ループ同居 → tray → config_window(接続/ネットワーク・**ソース一覧**・
   **手動編集**・表示/アセット/ブラックリスト)→ preview。GUI 操作 → SourceRegistry 更新をループへ委譲。
7. **tools/send_test.py + 手動E2E**: ローカル → Twingate の順で目視確認。
8. **配布**: PyInstaller `build.spec`、`start.bat`/`build.bat`。

## 検証(完了基準)
1. **単体(pytest)**: `mapper`(generic/music/manual → activity dict、buttons/URL/timestamps、
   blacklist、長さ制限の切詰/拒否)、`models`(検証・異常系)、`config`(保存/読込・移行)、
   **`sources` + 調停**(優先度/pin/有効無効/TTL 失効で勝者が期待通り変わる)。
2. **結合(pypresence をモック)**: テスト WS/HTTP クライアントで **複数 source_id** の payload 送信 →
   調停で期待ソースが選ばれ discord_rpc が期待 activity で呼ばれること、source 指定 `/clear`・
   TTL・切断時 clear・同一 activity 非再送・15s レート制御を確認(Discord 不要)。
3. **手動E2E(ローカル)**: Discord Developer Portal でアプリ作成(+ 小アイコン用アセットをアップ)→
   `DISCORD_CLIENT_ID` 設定 → Discord 起動 → `tools/send_test.py` で music/generic を **2 ソース**送信 →
   GUI ソース一覧で **片方を off/優先度変更/pin** して表示が切替わることを目視 → **手動モード**で
   任意の details/state/画像キーを入力しオンライン化 → 表示を目視。`/clear` で消える、Discord 再起動時の
   再接続、トレイの開始/停止/状態を確認。※ **ボタンは自分には見えない**ため確認は別アカウント/友人で。
4. **手動E2E(Twingate)**: `network_mode=twingate` で PC IP に bind → PC を Twingate Resource 化 →
   スマホの Twingate クライアントから `http://<PC-IP>:<port>/health` 到達を確認 →
   実機 Android の簡易送信(または send_test 相当)で RPC 反映を目視。トークン不一致が拒否されることも確認。

## 既知のリスク・実装時に確認する点
- pypresence の `AioPresence.update()` が受ける引数(特に `activity_type` と `buttons`)を
  インストール版で確認(版差あり)。無ければ最小実装(handshake + SET_ACTIVITY)に切替可能。
- 外部 URL の `large_image` 受理可否を実機 Discord で確認。不可なら external-assets でキー化。
  手動モードの小アイコン等は確実な **アセットキー**(Dev Portal に事前アップ)を基本とする。
- qasync 上での aiohttp `AppRunner` と pypresence 同居の動作確認(ループ共有)。GUI(Qt)コールバックは
  必ずループへ委譲して SourceRegistry を触る(直接の別スレッド更新は禁止)。
- `source_id` は Android 側の契約。送信元が安定した id を付与する前提を [`PROTOCOL.md`](PROTOCOL.md) に明記済み。
- 名前付きパイプの単一インスタンス制御(多重起動時の挙動)。

## 参考リンク
- Discord RPC（プロトコル）: <https://docs.discord.com/developers/topics/rpc>
- hard-mode（低レベル IPC 仕様）: <https://github.com/discord/discord-rpc/blob/master/documentation/hard-mode.md>
- pypresence: <https://github.com/qwertyquerty/pypresence>
- MuseHeart-RPC-app（同型の参考実装）: <https://github.com/zRitsu/MuseHeart-MusicBot-RPC-app>
- RikoRPC（手動モードの参考）: <https://github.com/ddasutein/RikoRPC>
