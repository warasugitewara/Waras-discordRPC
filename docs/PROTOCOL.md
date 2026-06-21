# 通信契約(Android ↔ PC)— Source of Truth

PC 受信側(本リポジトリ)と将来の Android 送信側が共有する**唯一の仕様**。
両者はこのファイルに従う。変更時は `version` を上げ、双方を更新する。

- 契約バージョン: **1**
- 文字エンコード: UTF-8 / JSON
- 役割: **PC = サーバ(受信)**、**Android = クライアント(送信)**

## 到達(ネットワーク)
- Android は **Twingate のプライベートオーバーレイ経由**で PC の
  **IP(または Twingate Resource DNS):port** へ接続する。
- 経路は Twingate の認証済みオーバーレイ内。**公開ポート開放はしない**。
- PC 側 bind は `network_mode`(`local`=127.0.0.1 / `twingate`=指定IP or 0.0.0.0)で切替。
- TLS はアプリ層では行わない(Twingate が経路を保護)。アプリは平文 HTTP/WS。

## 認証
- 共有トークンによる多層防御。WS / HTTP とも:
  - ヘッダ `Authorization: Bearer <BRIDGE_TOKEN>`(推奨)
  - 補助として WS は `?token=<...>` クエリも許可
- 不一致は **拒否**(HTTP 401 / WS は close)。

## ソース識別(重要)
- すべての presence は **`source_id`(必須)** を伴う。論理 stream の安定 ID。
  - 例: `"phone-music"`, `"phone-game"`, `"tasker-status"`。
  - **同一クライアントでも別 stream は別 `source_id`** にする(PC 側で個別に on/off・優先度管理される)。
- `source_name`(任意): GUI 表示名。未指定なら `source_id` を表示に使う。
- 1 つの WS 接続から **複数の `source_id`** を送ってよい。
- `source_id` 未指定時のフォールバック: `source_name` → 接続由来 ID。

> PC は受信した複数ソースから **1 つだけを Discord に表示**する(Discord は 1 プレゼンス枠)。
> どれを表示するかは PC 側の調停(優先度/pin)で決まる。詳細は [`DESIGN.md`](DESIGN.md)。

---

## WebSocket(主経路)
エンドポイント: `GET /ws`(双方向・push 更新・切断検知で該当ソース失効)。

### Client → Server
```jsonc
// プレゼンス更新
{ "op": "presence", "kind": "generic" | "music",
  "source_id": "phone-music", "source_name": "Phone • Music",
  "seq": 12, "data": { /* kind に対応する data。下記スキーマ参照 */ } }

// クリア(source_id 省略 = この接続の全ソース)
{ "op": "clear", "source_id": "phone-music" }

// キープアライブ
{ "op": "ping" }
```

### Server → Client
```jsonc
{ "op": "ready" }                       // 接続+認証 OK
{ "op": "ack", "seq": 12 }              // presence 受理
{ "op": "pong" }                        // ping 応答
{ "op": "error", "message": "reason" }  // 検証/認証エラー等
```

---

## HTTP(補助経路 / 単発更新)
すべて `Authorization: Bearer <token>` 必須。

| Method | Path | Body | 応答 |
|---|---|---|---|
| POST | `/presence` | `{ "kind", "source_id", "source_name"?, "data" }` | `200 { "ok": true }` |
| POST | `/clear` | `{ "source_id"? }`(省略=全) | `200 { "ok": true }` |
| GET | `/health` | — | `{ "status":"ok", "discord":"connected"|"disconnected", "active_source": str|null }` |

---

## data スキーマ

### kind = "generic"(全フィールド任意、`details` か `state` のいずれかは必須)
| フィールド | 型 | 備考 / 制限 |
|---|---|---|
| `details` | string | 1行目。**≤128 文字** |
| `state` | string | 2行目。**≤128 文字** |
| `activity_type` | enum | `"playing"`(既定)/`"listening"`/`"watching"`/`"competing"` |
| `large_image` | string | アセットキー or 外部 https URL |
| `large_text` | string | ≤128 文字 |
| `small_image` | string | **アセットキー推奨**(URL 直渡しは不安定) |
| `small_text` | string | ≤128 文字 |
| `start_ms` | number | エポック ms。経過時間表示に使用 |
| `end_ms` | number | エポック ms。残り時間表示に使用 |
| `buttons` | array | `[{ "label": string(≤32), "url": "http(s)://..." }]`、**最大2** |
| `party` | object | `{ "size": int, "max": int }` |

### kind = "music"(音楽プリセット。PC 側が listening + 進捗バーへ整形)
| フィールド | 型 | 備考 |
|---|---|---|
| `title` | string | → `details` |
| `artist` | string | → `state` |
| `album` | string | → `large_text` |
| `artwork_url` | string | → `large_image`(外部 URL) |
| `duration_ms` | number | 曲の長さ |
| `position_ms` | number | 現在位置。`start=now-position`,`end=start+duration` を算出し**進捗バー**化 |
| `paused` | bool | true で timestamps 除去 / 一時停止アイコン |
| `app_name` | string | 送信元(任意) |
| `source_url` | string | 任意(ボタン等に利用可) |

> **進捗の更新方針**: 毎秒送らない。`start/end` を一度送れば Discord が経過を描画する。
> 曲変更・再生/一時停止・シーク時のみ送る。

### 手動(manual)モードについて
`kind="manual"` は **PC 内部のソース**(GUI で編集)であり、**ネットワーク契約には現れない**。
Android からは送らない。詳細は [`DESIGN.md`](DESIGN.md) の「マッピング」を参照。

---

## エラー / 受理ルール
- 文字数超過: PC 側で切詰 or 拒否(実装方針は DESIGN 準拠)。`buttons` は **厳格検証**
  (個数 >2、`label`>32、URL が http(s) 以外は拒否)。
- レート: PC は **最小 15s 間隔**で Discord へ反映(超過分は合体)。送信側は高頻度送信を避ける。
- 切断: WS が切れると、その接続が供給したソースは失効(設定により即時 clear / TTL 経過で clear)。

## 送信例

WebSocket(音楽):
```json
{ "op": "presence", "kind": "music", "source_id": "phone-music",
  "source_name": "Phone • Music", "seq": 1,
  "data": { "title": "Strobe", "artist": "deadmau5", "album": "For Lack of a Better Name",
            "artwork_url": "https://example.com/art.jpg",
            "duration_ms": 634000, "position_ms": 42000, "paused": false } }
```

HTTP(汎用):
```bash
curl -X POST http://<PC-IP>:<port>/presence \
  -H "Authorization: Bearer <BRIDGE_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{ "kind": "generic", "source_id": "tasker-status",
        "data": { "details": "Working", "state": "Focus mode",
                  "activity_type": "playing", "large_image": "logo" } }'
```
