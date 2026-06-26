# Wara's-discordRPC セットアップガイド

エンドユーザー向けの導入手順。送信側(スマホ等)の通信仕様は [`PROTOCOL.md`](PROTOCOL.md) を参照。

## 必要なもの

- Windows 10 / 11
- Discord デスクトップアプリ(**先に起動しておく**。Rich Presence はローカルの Discord 経由で表示されます)
- Discord アカウント

## 1. Discord アプリ(Application ID)を用意する

1. [Discord Developer Portal](https://discord.com/developers/applications) を開く。
2. 「New Application」を押し、名前を入力する(この名前がプロフィールの「〜をプレイ中」に表示されます)。
3. 作成後の画面で **「Application ID」をコピー**する。これが設定に必要な ID です。
   - **Bot Token / OAuth は不要**です。必要なのは公開情報の Application ID だけです。
4. (任意)左メニュー「Rich Presence」→「Art Assets」で小アイコン(`play` / `pause` / `idle` など)を登録すると、アイコン表示に使えます。

## 2. アプリを起動して初期設定する

1. 配布 zip を展開し、`start.bat` をダブルクリックする。
2. 初回は**セットアップウィザード**が開きます。次を入力してください:
   - **Application ID**: 手順1でコピーした ID
   - **Bridge Token**: 自動生成済み(送信側と共有する合言葉)。変更しても構いません
   - **ネットワークモード**: 下の手順3を参照
3. 「OK」を押すと保存され、タスクトレイに常駐します。

> 設定をやり直したいときは、トレイアイコン →「設定を開く」→「接続」タブで再入力できます。

## 3. ネットワークモードを選ぶ

| モード | bind | 用途 |
|---|---|---|
| ローカルのみ(既定) | `127.0.0.1` | この PC 内からのみ受信。最も安全 |
| LAN全体 | `0.0.0.0` | 同一 LAN の他端末から受信 |
| カスタムIP | 指定 IP | Twingate 等、特定アダプタの IP にのみ bind |

- ポートは既定 `13520`。競合する場合は「接続」タブで変更してください。
- いずれのモードでも **Bridge Token による認証は必須**です。外部公開はせず、Twingate 等の認証付きオーバーレイ経由を推奨します。

> 接続情報(Application ID / Token / bind / port)の変更は、**保存後にアプリを再起動すると反映**されます(トレイ →「終了」→ 再度 `start.bat`)。

## 4. 送信側と接続する

- 送信側(スマホアプリ等)に、この PC の **IP・ポート・Bridge Token** を設定します。
- 認証ヘッダは `Authorization: Bearer <Bridge Token>`。エンドポイントや payload 形式は [`PROTOCOL.md`](PROTOCOL.md) を参照してください。

## トラブルシュート

- **Discord 未接続と表示される**: Discord デスクトップを先に起動してください。トレイの状態表示で接続状況を確認できます。
- **起動しない / すぐ消える**: 配布フォルダの `app.log` を確認してください(エラーが記録されます)。
- **ポートが使えない**: 「接続」タブでポート番号を変更し、再起動してください。
- **設定を変えても反映されない**: 接続情報の変更は再起動後に反映されます。

## 関連

- 通信仕様: [`PROTOCOL.md`](PROTOCOL.md)
- 設計: [`DESIGN.md`](DESIGN.md)
