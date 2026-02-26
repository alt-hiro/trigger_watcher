"""trigger_watcher

ローカルまたは SFTP 上の trigger ファイルの出現をポーリング監視するスクリプト。

利用者は設定セクションの値を編集することで、監視先やリトライ回数を変更できます。
"""

import base64
import fnmatch
import json
import os
import socket
import sys
import time
import urllib.request
from io import StringIO
from pathlib import Path
from datetime import datetime

# ===== 設定（担当者が手で変更する想定のエリア） =====
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
# ========================================================


MESSAGE_BY_STATUS_CODE = {
    100: "正常に BlueYonder からデータが出力されました。",
    200: "指定した時間になりましたが、まだ BlueYonder から Outbound ファイルが出力されていません。",
    300: "継続して監視をしましたが、BlueYonder から Outbound ファイルが出力されませんでした。",
}

STATUS_LABEL_BY_STATUS_CODE = {
    100: "✅ SUCCESS",
    200: "⚠️ WARN",
    300: "❌ ERROR",
}


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


def send_message(status_code: int) -> None:
    """Webhook にステータスメッセージを送信する。"""
    if not WEBHOOK_URL:
        _log("INFO", "WEBHOOK_URL が未設定のため webhook 送信をスキップします。")
        return

    if status_code not in MESSAGE_BY_STATUS_CODE:
        raise ValueError(f"未対応のステータスコードです: {status_code}")

    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_label = STATUS_LABEL_BY_STATUS_CODE[status_code]
    message = MESSAGE_BY_STATUS_CODE[status_code]
    final_message = f"[{now_text}] STATUS: {status_label}\n{message}"

    payload = {"text": final_message}
    request = urllib.request.Request(
        WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request) as response:
            _log("INFO", f"webhook を送信しました。status={response.status}, code={status_code}")
    except Exception as exc:  # noqa: BLE001
        _log("ERROR", f"webhook 送信に失敗しました。code={status_code}, error={exc}")


def _parse_checkpoint_minutes() -> list[int]:
    """CHECKPOINT_TIMES を分単位へ変換する。"""
    checkpoint_minutes: list[int] = []
    for checkpoint_time in CHECKPOINT_TIMES:
        try:
            hour_text, minute_text = checkpoint_time.split(":", 1)
            minutes = int(hour_text) * 60 + int(minute_text)
        except ValueError as exc:
            raise ValueError(
                f"CHECKPOINT_TIMES の形式が不正です: {checkpoint_time}. 例: '09:00'"
            ) from exc
        checkpoint_minutes.append(minutes)
    return checkpoint_minutes


def _send_checkpoint_message_if_needed(checkpoint_minutes: list[int], sent_checkpoints: set[int]) -> None:
    """指定時刻を過ぎた未送信チェックポイントに対して監視中メッセージを送信する。"""
    now = datetime.now()
    now_minutes = now.hour * 60 + now.minute

    for checkpoint_minute in checkpoint_minutes:
        if checkpoint_minute <= now_minutes and checkpoint_minute not in sent_checkpoints:
            send_message(200)
            sent_checkpoints.add(checkpoint_minute)


def _wait_for_local_trigger(watch_start_timestamp: float, checkpoint_minutes: list[int], sent_checkpoints: set[int]) -> int:
    """ローカルファイルシステム上の trigger ファイルを待機する。"""
    target_dir = Path(TARGET_DIR)

    for attempt in range(1, MAX_RETRY + 1):
        _send_checkpoint_message_if_needed(checkpoint_minutes, sent_checkpoints)
        _log("INFO", f"ローカルパスを確認中: {target_dir}/{TRIGGER_FILE}", attempt, MAX_RETRY)

        try:
            matched_files = [
                target_dir / file_name
                for file_name in os.listdir(target_dir)
                if fnmatch.fnmatchcase(file_name, TRIGGER_FILE)
            ]
        except FileNotFoundError:
            _log("ERROR", f"TARGET_DIR が見つかりません: {target_dir}", attempt, MAX_RETRY)
            return 1

        if matched_files:
            latest_file_path = max(matched_files, key=os.path.getmtime)
            modified_timestamp = os.path.getmtime(latest_file_path)
            if modified_timestamp >= watch_start_timestamp:
                _log(
                    "SUCCESS",
                    f"{latest_file_path.name} をローカルファイルシステム上で検知しました。",
                    attempt,
                    MAX_RETRY,
                )
                return 0

            modified_datetime = datetime.fromtimestamp(modified_timestamp).strftime("%Y-%m-%d %H:%M:%S")
            _log(
                "INFO",
                (
                    "一致ファイルは存在しますが監視対象時刻より古いため未検知として扱います: "
                    f"file={latest_file_path.name}, mtime={modified_datetime}"
                ),
                attempt,
                MAX_RETRY,
            )

        if attempt < MAX_RETRY:
            _log("INFO", f"未検知のため {CHECK_INTERVAL_SECONDS} 秒待機します。", attempt, MAX_RETRY)
            time.sleep(CHECK_INTERVAL_SECONDS)

    _log("ERROR", f"{MAX_RETRY} 回試行しましたが {TRIGGER_FILE} に一致するファイルが見つかりませんでした。")
    return 1


def _wait_for_sftp_trigger(watch_start_timestamp: float, checkpoint_minutes: list[int], sent_checkpoints: set[int]) -> int:
    """SFTP サーバー上の trigger ファイルを待機する。"""
    try:
        import paramiko
    except ImportError:
        _log("ERROR", "SFTP モードでは 'paramiko' が必要です。pip install paramiko で導入してください。")
        return 1

    remote_target_dir = SFTP_TARGET_DIR.rstrip("/")
    auth_method = SFTP_AUTH_METHOD.lower().strip()

    def _open_http_proxy_tunnel() -> socket.socket:
        if not SFTP_HTTP_PROXY_HOST:
            raise ValueError(
                "SFTP_USE_HTTP_PROXY=True の場合は SFTP_HTTP_PROXY_HOST を設定してください。"
            )

        proxy_socket = socket.create_connection((SFTP_HTTP_PROXY_HOST, SFTP_HTTP_PROXY_PORT), timeout=10)
        connect_lines = [
            f"CONNECT {SFTP_HOST}:{SFTP_PORT} HTTP/1.1",
            f"Host: {SFTP_HOST}:{SFTP_PORT}",
            "Proxy-Connection: Keep-Alive",
        ]

        if SFTP_HTTP_PROXY_USERNAME:
            auth_raw = f"{SFTP_HTTP_PROXY_USERNAME}:{SFTP_HTTP_PROXY_PASSWORD}".encode("utf-8")
            auth_header = base64.b64encode(auth_raw).decode("ascii")
            connect_lines.append(f"Proxy-Authorization: Basic {auth_header}")

        connect_request = "\r\n".join(connect_lines) + "\r\n\r\n"
        proxy_socket.sendall(connect_request.encode("utf-8"))

        response = b""
        while b"\r\n\r\n" not in response:
            chunk = proxy_socket.recv(4096)
            if not chunk:
                proxy_socket.close()
                raise ConnectionError("HTTP proxy からの応答が途中で切断されました。")
            response += chunk
            if len(response) > 65535:
                proxy_socket.close()
                raise ConnectionError("HTTP proxy の応答ヘッダーが大きすぎます。")

        status_line = response.split(b"\r\n", 1)[0].decode("iso-8859-1", errors="replace")
        if " 200 " not in status_line and not status_line.endswith(" 200"):
            proxy_socket.close()
            raise ConnectionError(f"HTTP proxy トンネル確立に失敗しました: {status_line}")

        return proxy_socket

    def _load_private_key_from_string(key_text: str) -> "paramiko.PKey":
        normalized_key = key_text.replace("\\n", "\n")
        key_stream = StringIO(normalized_key)

        load_key_errors = []
        for key_cls in (
            paramiko.RSAKey,
            paramiko.Ed25519Key,
            paramiko.ECDSAKey,
            paramiko.DSSKey,
        ):
            key_stream.seek(0)
            try:
                return key_cls.from_private_key(
                    key_stream,
                    password=SFTP_PRIVATE_KEY_PASSPHRASE or None,
                )
            except Exception as exc:  # noqa: PERF203
                load_key_errors.append(f"{key_cls.__name__}: {exc}")

        raise ValueError(
            "秘密鍵の読み込みに失敗しました。"
            f"試行結果: {' | '.join(load_key_errors)}"
        )

    def _load_private_key_from_file() -> "paramiko.PKey":
        if not SFTP_PRIVATE_KEY_PATH:
            raise ValueError("SFTP_PRIVATE_KEY_PATH が未設定です。")

        key_path = Path(SFTP_PRIVATE_KEY_PATH).expanduser()
        if not key_path.exists():
            raise ValueError(f"秘密鍵ファイルが見つかりません: {key_path}")

        load_key_errors = []
        for key_cls in (
            paramiko.RSAKey,
            paramiko.Ed25519Key,
            paramiko.ECDSAKey,
            paramiko.DSSKey,
        ):
            try:
                return key_cls.from_private_key_file(
                    str(key_path),
                    password=SFTP_PRIVATE_KEY_PASSPHRASE or None,
                )
            except Exception as exc:  # noqa: PERF203
                load_key_errors.append(f"{key_cls.__name__}: {exc}")

        raise ValueError(
            f"秘密鍵ファイルの読み込みに失敗しました: {key_path}. "
            f"試行結果: {' | '.join(load_key_errors)}"
        )

    def _connect_transport(transport: "paramiko.Transport") -> None:
        if auth_method == "password":
            if not SFTP_PASSWORD:
                raise ValueError("SFTP_PASSWORD が未設定です。環境変数に設定してください。")
            transport.connect(username=SFTP_USERNAME, password=SFTP_PASSWORD)
            return

        if auth_method == "key":
            private_key_content = os.getenv(SFTP_PRIVATE_KEY_ENV, "")
            if private_key_content:
                private_key = _load_private_key_from_string(private_key_content)
            elif SFTP_PRIVATE_KEY_PATH:
                private_key = _load_private_key_from_file()
            else:
                raise ValueError(
                    f"{SFTP_PRIVATE_KEY_ENV} または SFTP_PRIVATE_KEY_PATH が未設定です。"
                    "秘密鍵を環境変数またはファイルで指定してください。"
                )

            transport.connect(username=SFTP_USERNAME, pkey=private_key)
            return

        raise ValueError(
            "未対応の SFTP_AUTH_METHOD です。'password' または 'key' を指定してください。"
        )

    for attempt in range(1, MAX_RETRY + 1):
        _send_checkpoint_message_if_needed(checkpoint_minutes, sent_checkpoints)
        _log(
            "INFO",
            f"SFTP パスを確認中: {SFTP_HOST}:{remote_target_dir}/{TRIGGER_FILE}",
            attempt,
            MAX_RETRY,
        )

        transport = None
        sftp = None
        proxy_socket = None
        try:
            if SFTP_USE_HTTP_PROXY:
                proxy_socket = _open_http_proxy_tunnel()
                transport = paramiko.Transport(proxy_socket)
            else:
                transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))

            _connect_transport(transport)
            sftp = paramiko.SFTPClient.from_transport(transport)

            matched_files = [
                file_attr
                for file_attr in sftp.listdir_attr(remote_target_dir)
                if fnmatch.fnmatchcase(file_attr.filename, TRIGGER_FILE)
            ]

            if not matched_files:
                raise FileNotFoundError

            latest_file = max(matched_files, key=lambda file_attr: file_attr.st_mtime)
            modified_timestamp = latest_file.st_mtime
            if modified_timestamp >= watch_start_timestamp:
                _log("SUCCESS", f"{latest_file.filename} を SFTP サーバー上で検知しました。", attempt, MAX_RETRY)
                return 0

            modified_datetime = datetime.fromtimestamp(modified_timestamp).strftime("%Y-%m-%d %H:%M:%S")
            _log(
                "INFO",
                (
                    "一致ファイルは存在しますが監視対象時刻より古いため未検知として扱います: "
                    f"file={latest_file.filename}, mtime={modified_datetime}"
                ),
                attempt,
                MAX_RETRY,
            )
        except FileNotFoundError:
            if attempt < MAX_RETRY:
                _log("INFO", f"未検知のため {CHECK_INTERVAL_SECONDS} 秒待機します。", attempt, MAX_RETRY)
                time.sleep(CHECK_INTERVAL_SECONDS)
            else:
                _log("ERROR", f"{MAX_RETRY} 回試行しましたが {TRIGGER_FILE} に一致するファイルが見つかりませんでした。")
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
            if proxy_socket is not None:
                proxy_socket.close()

    return 1


def wait_for_trigger() -> int:
    """設定された監視方式で trigger ファイルの出現を待機する。"""
    watch_type = WATCH_TYPE.lower().strip()
    checkpoint_minutes = _parse_checkpoint_minutes()
    sent_checkpoints: set[int] = set()
    watch_start_timestamp = time.time() - (LOOKBACK_HOURS * 60 * 60)
    watch_start_datetime = datetime.fromtimestamp(watch_start_timestamp).strftime("%Y-%m-%d %H:%M:%S")
    _log(
        "INFO",
        (
            "監視対象時刻を設定しました。"
            f"この時刻以降に更新された {TRIGGER_FILE} に一致するファイルを検知します: {watch_start_datetime}"
        ),
    )

    if watch_type == "local":
        return _wait_for_local_trigger(watch_start_timestamp, checkpoint_minutes, sent_checkpoints)
    if watch_type == "sftp":
        return _wait_for_sftp_trigger(watch_start_timestamp, checkpoint_minutes, sent_checkpoints)

    _log("ERROR", f"未対応の WATCH_TYPE: {WATCH_TYPE}。'local' または 'sftp' を指定してください。")
    return 1


if __name__ == "__main__":
    try:
        exit_code = wait_for_trigger()
    except Exception as exc:  # noqa: BLE001
        _log("ERROR", f"予期せぬエラーで終了します: {exc}")
        send_message(300)
        sys.exit(1)

    if exit_code == 0:
        send_message(100)
    else:
        send_message(300)

    sys.exit(exit_code)
