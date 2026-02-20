"""trigger_watcher

ローカルまたは SFTP 上の `trigger.txt` の出現をポーリング監視するスクリプト。

利用者は設定セクションの値を編集することで、監視先やリトライ回数を変更できます。
"""

import os
import sys
import time
from datetime import datetime

# ===== 設定（担当者が手で変更する想定のエリア） =====
# 監視対象タイプ: "local" または "sftp"
WATCH_TYPE = "local"

# ---- 共通 ----
TRIGGER_FILE = "trigger.txt"
CHECK_INTERVAL_SECONDS = 3
MAX_RETRY = 10

# ---- local 用 ----
TARGET_DIR = r"/path/to/your/directory"  # 監視するローカルディレクトリ

# ---- sftp 用 ----
SFTP_HOST = "sftp.example.com"
SFTP_PORT = 22
SFTP_USERNAME = "your_username"
SFTP_PASSWORD = "your_password"  # 一旦は直書き。将来的には環境変数の利用を推奨。

# 将来的に環境変数を使う場合の例（必要になったらコメントアウトを外す）
# SFTP_PASSWORD = os.getenv("SFTP_PASSWORD", "")

SFTP_TARGET_DIR = "/path/to/remote/directory"  # 監視するリモートディレクトリ
# ========================================================


def _log(level: str, message: str, attempt: int | None = None, total: int | None = None) -> None:
    """タイムスタンプ付きでログを標準出力へ出力する。

    Args:
        level: ログレベル。例: ``INFO`` / ``ERROR`` / ``SUCCESS``。
        message: 出力するログ本文。
        attempt: 現在の試行回数（m回目）。
        total: 最大試行回数（n回）。
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    progress = ""
    if attempt is not None and total is not None:
        progress = f" [{total}回中{attempt}回目]"
    print(f"[{timestamp}] [{level}]{progress} {message}")


def _wait_for_local_trigger() -> int:
    """ローカルファイルシステム上の trigger ファイルを待機する。"""
    target_path = os.path.join(TARGET_DIR, TRIGGER_FILE)

    for attempt in range(1, MAX_RETRY + 1):
        _log("INFO", f"ローカルパスを確認中: {target_path}", attempt, MAX_RETRY)

        if os.path.exists(target_path):
            _log("SUCCESS", "trigger.txt をローカルファイルシステム上で検知しました。", attempt, MAX_RETRY)
            return 0

        if attempt < MAX_RETRY:
            _log("INFO", f"未検知のため {CHECK_INTERVAL_SECONDS} 秒待機します。", attempt, MAX_RETRY)
            time.sleep(CHECK_INTERVAL_SECONDS)

    _log("ERROR", f"{MAX_RETRY} 回試行しましたが trigger.txt が見つかりませんでした。")
    return 1


def _wait_for_sftp_trigger() -> int:
    """SFTP サーバー上の trigger ファイルを待機する。"""
    try:
        import paramiko
    except ImportError:
        _log("ERROR", "SFTP モードでは 'paramiko' が必要です。pip install paramiko で導入してください。")
        return 1

    remote_trigger_path = f"{SFTP_TARGET_DIR.rstrip('/')}/{TRIGGER_FILE}"

    for attempt in range(1, MAX_RETRY + 1):
        _log(
            "INFO",
            f"SFTP パスを確認中: {SFTP_HOST}:{remote_trigger_path}",
            attempt,
            MAX_RETRY,
        )

        transport = None
        sftp = None
        try:
            transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
            transport.connect(username=SFTP_USERNAME, password=SFTP_PASSWORD)
            sftp = paramiko.SFTPClient.from_transport(transport)

            # stat が成功すればファイルは存在
            sftp.stat(remote_trigger_path)
            _log("SUCCESS", "trigger.txt を SFTP サーバー上で検知しました。", attempt, MAX_RETRY)
            return 0
        except FileNotFoundError:
            if attempt < MAX_RETRY:
                _log("INFO", f"未検知のため {CHECK_INTERVAL_SECONDS} 秒待機します。", attempt, MAX_RETRY)
                time.sleep(CHECK_INTERVAL_SECONDS)
            else:
                _log("ERROR", f"{MAX_RETRY} 回試行しましたが trigger.txt が見つかりませんでした。")
        except Exception as exc:
            _log("ERROR", f"SFTP チェックに失敗しました: {exc}", attempt, MAX_RETRY)
            if attempt < MAX_RETRY:
                _log("INFO", f"{CHECK_INTERVAL_SECONDS} 秒後に再試行します。", attempt, MAX_RETRY)
                time.sleep(CHECK_INTERVAL_SECONDS)
            else:
                return 1
        finally:
            if sftp is not None:
                sftp.close()
            if transport is not None:
                transport.close()

    return 1


def wait_for_trigger() -> int:
    """設定された監視方式で trigger ファイルの出現を待機する。"""
    watch_type = WATCH_TYPE.lower().strip()

    if watch_type == "local":
        return _wait_for_local_trigger()
    if watch_type == "sftp":
        return _wait_for_sftp_trigger()

    _log("ERROR", f"未対応の WATCH_TYPE: {WATCH_TYPE}。'local' または 'sftp' を指定してください。")
    return 1


if __name__ == "__main__":
    sys.exit(wait_for_trigger())
