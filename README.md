# trigger_watcher

`trigger_watcher.py` は、`trigger.txt` が作成されるのを待機するためのシンプルな監視スクリプトです。

- ローカルディレクトリ監視（`WATCH_TYPE = "local"`）
- SFTP 先ディレクトリ監視（`WATCH_TYPE = "sftp"`）

を切り替えて利用できます。

---

## できること

- 指定した場所に `trigger.txt` が存在するかを一定間隔で確認
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

TARGET_DIR = r"/path/to/your/directory"

SFTP_HOST = "sftp.example.com"
SFTP_PORT = 22
SFTP_USERNAME = "your_username"
SFTP_PASSWORD = "your_password"
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
- `SFTP_*`
  - SFTP 接続情報
- `SFTP_TARGET_DIR`
  - リモート監視先ディレクトリ

> 補足: `SFTP_PASSWORD` は現在直書きですが、運用時は環境変数化を推奨します。

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

