# trigger_watcher

`trigger_watcher.py` は、`trigger.txt` が作成されるのを待機するためのシンプルな監視スクリプトです。

- ローカルディレクトリ監視（`WATCH_TYPE = "local"`）
- SFTP 先ディレクトリ監視（`WATCH_TYPE = "sftp"`）

を切り替えて利用できます。

---

## できること

- 指定した場所に `trigger.txt` が存在するかを一定間隔で確認
- `trigger.txt` の更新時刻（mtime）が、監視対象時刻以降かどうかを確認
- 見つかるまで最大 `MAX_RETRY` 回リトライ
- ログに **実行タイムスタンプ** を出力
- ログに **「n回中m回目」**（進捗）を出力

ログ出力例:

```text
[2026-02-20 10:00:00] [INFO] [10回中1回目] ローカルパスを確認中: /tmp/watch/trigger.txt
[2026-02-20 10:00:03] [INFO] [10回中2回目] 未検知のため 3 秒待機します。
[2026-02-20 10:00:06] [SUCCESS] [10回中3回目] trigger.txt をローカルファイルシステム上で検知しました。
```

---

## 使い方

### 1. 設定を編集する（担当者が手でいじる場所）

`trigger_watcher.py` 先頭の **設定セクション** を編集してください。

```python
# ===== 設定（担当者が手で変更する想定のエリア） =====
WATCH_TYPE = "local"
TRIGGER_FILE = "trigger.txt"
CHECK_INTERVAL_SECONDS = 3
MAX_RETRY = 10
LOOKBACK_HOURS = 2

TARGET_DIR = r"/path/to/your/directory"

SFTP_HOST = "sftp.example.com"
SFTP_PORT = 22
SFTP_USERNAME = "your_username"
SFTP_AUTH_METHOD = "password"
SFTP_PASSWORD = os.getenv("SFTP_PASSWORD", "")
SFTP_PRIVATE_KEY_ENV = "SFTP_PRIVATE_KEY"
SFTP_PRIVATE_KEY_PASSPHRASE = os.getenv("SFTP_PRIVATE_KEY_PASSPHRASE", "")

SFTP_USE_HTTP_PROXY = os.getenv("SFTP_USE_HTTP_PROXY", "false").lower() in ("1", "true", "yes", "on")
SFTP_HTTP_PROXY_HOST = os.getenv("SFTP_HTTP_PROXY_HOST", "")
SFTP_HTTP_PROXY_PORT = int(os.getenv("SFTP_HTTP_PROXY_PORT", "8080"))
SFTP_HTTP_PROXY_USERNAME = os.getenv("SFTP_HTTP_PROXY_USERNAME", "")
SFTP_HTTP_PROXY_PASSWORD = os.getenv("SFTP_HTTP_PROXY_PASSWORD", "")

SFTP_TARGET_DIR = "/path/to/remote/directory"
# ========================================================
```

#### 設定項目の説明

- `WATCH_TYPE`
  - `"local"` または `"sftp"`
- `TRIGGER_FILE`
  - 監視対象のファイル名（通常は `trigger.txt`）
- `CHECK_INTERVAL_SECONDS`
  - 見つからなかったときの待機秒数
- `MAX_RETRY`
  - 最大試行回数
- `TARGET_DIR`
  - ローカル監視先ディレクトリ
- `LOOKBACK_HOURS`
  - 監視起点の許容ラグ（時間）
  - 監視対象時刻は「プログラム実行時刻 - `LOOKBACK_HOURS` 時間」
  - 既に `trigger.txt` が存在していても、この時刻より古い更新時刻なら未検知として扱う
- `SFTP_AUTH_METHOD`
  - SFTP 認証方式（`"password"` / `"key"`）
- `SFTP_PASSWORD`
  - `password` 認証時のパスワード（環境変数 `SFTP_PASSWORD` から読み込み）
- `SFTP_PRIVATE_KEY_ENV`
  - `key` 認証時に利用する秘密鍵文字列の環境変数名
  - 例: `SFTP_PRIVATE_KEY` に OpenSSH 形式の秘密鍵本文を設定
- `SFTP_PRIVATE_KEY_PASSPHRASE`
  - 鍵がパスフレーズ付きの場合のパスフレーズ（任意）
- `SFTP_USE_HTTP_PROXY`
  - `True` のとき HTTP proxy（CONNECT）経由で SFTP 接続
- `SFTP_HTTP_PROXY_HOST` / `SFTP_HTTP_PROXY_PORT`
  - HTTP proxy の接続先
- `SFTP_HTTP_PROXY_USERNAME` / `SFTP_HTTP_PROXY_PASSWORD`
  - HTTP proxy の Basic 認証情報（必要な場合のみ）
- `SFTP_TARGET_DIR`
  - リモート監視先ディレクトリ

> 補足: 秘密鍵を 1 行で環境変数に入れる場合は、改行を `\n` として設定しておくと読み込み時に復元されます。

#### 鍵認証を使うときの環境変数例

```bash
export SFTP_AUTH_METHOD="key"
export SFTP_PRIVATE_KEY="-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----"
# パスフレーズ付き鍵の場合のみ
export SFTP_PRIVATE_KEY_PASSPHRASE="your_passphrase"
```

#### HTTP proxy 経由で SFTP 接続するときの環境変数例

```bash
export SFTP_USE_HTTP_PROXY="true"
export SFTP_HTTP_PROXY_HOST="proxy.example.com"
export SFTP_HTTP_PROXY_PORT="8080"
# proxy 認証が必要な場合のみ
export SFTP_HTTP_PROXY_USERNAME="proxy_user"
export SFTP_HTTP_PROXY_PASSWORD="proxy_pass"
```

### 2. 実行する

```bash
python3 trigger_watcher.py
```

### 3. 終了コード

- `0`: trigger ファイルを検知して正常終了
- `1`: 未検知のままリトライ上限到達、設定不正、または SFTP 接続エラー

---

## SFTP モードの依存関係

`WATCH_TYPE = "sftp"` を使う場合は `paramiko` が必要です。

```bash
pip install paramiko
```

---

## コード内ドキュメントについて

本スクリプトでは、Python のドキュメント機能として次を付けています。

- **モジュール docstring**: ファイル全体の目的
- **関数 docstring**: 各関数の役割と引数説明

IDE 上のホバーや `help()` で参照できます。
