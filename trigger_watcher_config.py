"""trigger_watcher の設定値。

担当者はこのファイルの値を編集して監視対象を変更します。
"""

import os

# 監視対象タイプ: "local" または "sftp"
WATCH_TYPE = "local"

# ---- 共通 ----
TRIGGER_FILE = "trigger.txt"  # 例: "trigger.txt" / "Trigger_*.txt"
CHECK_INTERVAL_SECONDS = 3
MAX_RETRY = 10
# 監視起点の許容ラグ（時間）。
# 例: 2 の場合、プログラム実行時刻の 2 時間前以降に更新された trigger を検知対象にする。
LOOKBACK_HOURS = 2

# ---- local 用 ----
TARGET_DIR = r"/path/to/your/directory"  # 監視するローカルディレクトリ

# ---- sftp 用 ----
SFTP_HOST = "sftp.example.com"
SFTP_PORT = 22
SFTP_USERNAME = "your_username"
SFTP_AUTH_METHOD = "password"  # "password" または "key"
SFTP_PASSWORD = os.getenv("SFTP_PASSWORD", "")  # password 認証で利用
SFTP_PRIVATE_KEY_ENV = "SFTP_PRIVATE_KEY"  # key 認証で利用する秘密鍵の環境変数名
SFTP_PRIVATE_KEY_PASSPHRASE = os.getenv("SFTP_PRIVATE_KEY_PASSPHRASE", "")  # 任意
SFTP_PRIVATE_KEY_PATH = os.getenv("SFTP_PRIVATE_KEY_PATH", "")  # key 認証で利用する秘密鍵ファイルパス

SFTP_USE_HTTP_PROXY_RAW = os.getenv("SFTP_USE_HTTP_PROXY", "false")
SFTP_USE_HTTP_PROXY = SFTP_USE_HTTP_PROXY_RAW.lower() in ("1", "true", "yes", "on")  # True のとき HTTP proxy (CONNECT) 経由で SFTP 接続する
SFTP_HTTP_PROXY_HOST = os.getenv("SFTP_HTTP_PROXY_HOST", "")
SFTP_HTTP_PROXY_PORT = int(os.getenv("SFTP_HTTP_PROXY_PORT", "8080"))
SFTP_HTTP_PROXY_USERNAME = os.getenv("SFTP_HTTP_PROXY_USERNAME", "")  # 任意
SFTP_HTTP_PROXY_PASSWORD = os.getenv("SFTP_HTTP_PROXY_PASSWORD", "")  # 任意

SFTP_TARGET_DIR = "/path/to/remote/directory"  # 監視するリモートディレクトリ

# ---- webhook 通知 ----
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
# 監視中の通知を送信する時刻（24時間表記・時:分）
CHECKPOINT_TIMES = ["09:00", "10:00", "11:00"]
