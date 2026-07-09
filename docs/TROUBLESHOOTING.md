# トラブルシュート: Twingate 経由でスマホから繋がらないとき

対象構成: Android(Galaxy 等)+ Twingate クライアント → Windows 11 の本ブリッジ。
上から順に確認すると「経路の問題」か「設定の問題」かを最短で切り分けられる。

## 0. まず疎通だけを確認する(/ping)

ブリッジには**認証不要の到達確認エンドポイント** `GET /ping` がある。
スマホの**ブラウザ**で次を開く:

```
http://<PCのTwingateリソースIP または Resource DNS>:13520/ping
```

| 結果 | 意味 | 次に見る場所 |
|---|---|---|
| `{"pong": true}` が表示される | **ネットワーク経路は正常**。原因はアプリ側設定(トークン・ホスト・ポート・source) | → §4 へ |
| タイムアウト / 接続できない | 経路(Twingate / ファイアウォール / bind)の問題 | → §1〜§3 へ |

## 1. PC 側: bind とポートを確認する

- `config.json` の `network_mode` を `twingate` にする。
  - v1.0.x では `network_mode` を変えても **`bind` が `127.0.0.1` のままだと外部から一切到達できなかった**。
    現在は `twingate` モードでループバック bind を自動的に `0.0.0.0` へ昇格し、起動ログに警告を出す。
- 起動ログに `受信サーバ起動: http://0.0.0.0:13520` が出ていることを確認する
  (packaged exe は `app.log` に出力される)。
- **注意**: Twingate の Resource IP(CGNAT 帯 100.x など)は PC のネットワークインターフェースには
  付与されない。`bind` にその IP を書くと起動に失敗する。`0.0.0.0` か PC 自身の LAN IP を使う。
- PC 自身での確認: PowerShell で `curl.exe http://127.0.0.1:13520/ping` → `{"pong": true}` が返ること。

## 2. Windows 11 のファイアウォール(最頻出)

Python(または配布 exe)が `0.0.0.0:13520` で待ち受けていても、
**Windows Defender ファイアウォールの受信規則が無いと外部からの接続は黙って落ちる**
(初回起動時の許可ダイアログで「キャンセル」した場合や、ネットワークが「パブリック」プロファイルの場合に起きやすい)。

管理者 PowerShell で受信許可を追加:

```powershell
New-NetFirewallRule -DisplayName "Waras-discordRPC bridge" `
  -Direction Inbound -Protocol TCP -LocalPort 13520 -Action Allow
```

確認: 同一 LAN の別端末(または Twingate 経由のスマホブラウザ)から `/ping` が開けること。

## 3. Twingate 側の構成

- **Connector はどこで動いているか**: PC を Resource として公開するには、その PC に到達できる
  ネットワーク内(同一 LAN か PC 自身)で Connector が稼働している必要がある。
  Twingate **クライアント**を PC に入れるだけでは PC は Resource にならない(クライアントは発信専用)。
- **Resource 定義**: アドレスは PC の LAN IP(例 `192.168.x.x`)か LAN 内 DNS 名。
  ポート制限をかけている場合は TCP `13520` を許可に含める。
- **スマホ側**: Twingate アプリが「接続済み」で、該当 Resource がリストに見えていること。
  Android の省電力設定で Twingate が殺されると WS も切れる(Twingate アプリを電池最適化から除外)。
- **Resource DNS 名を使う場合**: 名前解決は Twingate トンネル内でのみ機能する。
  スマホのブラウザで `/ping` が IP では通るのに DNS 名で通らないなら、アプリ設定も IP にする。

## 4. 経路が通っているのに連携しない場合

- **`❌ 認証失敗` / close(4001) / HTTP 401**: `BRIDGE_TOKEN`(PC の `.env`)とアプリ側トークンの不一致。
  前後の空白・改行の混入に注意。ブリッジのログに `認証失敗 (peer=...)` が出るようになったので、
  「接続は来ているがトークンが違う」ことはログで確認できる。
- **接続はするのに Discord に出ない**:
  - `GET /health`(要トークン)で `discord` が `connected` か、`active_source` が期待のソースか確認。
  - GUI のソース一覧で該当ソース(`phone-music` / `pomotimer-android`)が**有効**か、
    他ソースに優先度・pin で負けていないか確認。
  - Discord デスクトップが起動しているか、`DISCORD_CLIENT_ID` が設定済みか。
- **表示がすぐ消える**: キープアライブが TTL(既定 30s)内に届いていない。
  スマホ側アプリの電池最適化除外を確認(Doze で送信が止まる)。

## 5. ログの見方

- 開発実行: コンソールに出力。配布 exe(`console=False`): カレントの `app.log`。
- 追加されたログ:
  - `WS 接続確立 (peer=...)` / `WS 切断 (peer=..., close_code=...)`
  - `WS 認証失敗 (peer=...)` / `HTTP /presence 認証失敗 (peer=...)`
  - `GET /ping (peer=...)` — スマホからの疎通テストが PC まで届いたかの確認に使える
