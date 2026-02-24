"""trigger_watcher

ローカルまたは SFTP 上の `trigger.txt` の出現をポーリング監視するスクリプト。

利用者は設定セクションの値を編集することで、監視先やリトライ回数を変更できます。
"""

import base64
import os
import socket
import sys
import time
from io import StringIO
from datetime import datetime

# ===== 設定（担当者が手で変更する想定のエリア） =====
# 監視対象タイプ: "local" または "sftp"
WATCH_TYPE = "local"

# ---- 共通 ----
TRIGGER_FILE = "trigger.txt"
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

SFTP_USE_HTTP_PROXY_RAW = os.getenv("SFTP_USE_HTTP_PROXY", "false")
SFTP_USE_HTTP_PROXY = SFTP_USE_HTTP_PROXY_RAW.lower() in ("1", "true", "yes", "on")  # True のとき HTTP proxy (CONNECT) 経由で SFTP 接続する
SFTP_HTTP_PROXY_HOST = os.getenv("SFTP_HTTP_PROXY_HOST", "")
SFTP_HTTP_PROXY_PORT = int(os.getenv("SFTP_HTTP_PROXY_PORT", "8080"))
SFTP_HTTP_PROXY_USERNAME = os.getenv("SFTP_HTTP_PROXY_USERNAME", "")  # 任意
SFTP_HTTP_PROXY_PASSWORD = os.getenv("SFTP_HTTP_PROXY_PASSWORD", "")  # 任意

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


def _wait_for_local_trigger(watch_start_timestamp: float) -> int:
    """ローカルファイルシステム上の trigger ファイルを待機する。"""
    target_path = os.path.join(TARGET_DIR, TRIGGER_FILE)

    for attempt in range(1, MAX_RETRY + 1):
        _log("INFO", f"ローカルパスを確認中: {target_path}", attempt, MAX_RETRY)

        if os.path.exists(target_path):
            modified_timestamp = os.path.getmtime(target_path)
            if modified_timestamp >= watch_start_timestamp:
                _log("SUCCESS", "trigger.txt をローカルファイルシステム上で検知しました。", attempt, MAX_RETRY)
                return 0

            modified_datetime = datetime.fromtimestamp(modified_timestamp).strftime("%Y-%m-%d %H:%M:%S")
            _log(
                "INFO",
                (
                    "trigger.txt は存在しますが監視対象時刻より古いため未検知として扱います: "
                    f"mtime={modified_datetime}"
                ),
                attempt,
                MAX_RETRY,
            )

        if attempt < MAX_RETRY:
            _log("INFO", f"未検知のため {CHECK_INTERVAL_SECONDS} 秒待機します。", attempt, MAX_RETRY)
            time.sleep(CHECK_INTERVAL_SECONDS)

    _log("ERROR", f"{MAX_RETRY} 回試行しましたが trigger.txt が見つかりませんでした。")
    return 1


def _wait_for_sftp_trigger(watch_start_timestamp: float) -> int:
    """SFTP サーバー上の trigger ファイルを待機する。"""
    try:
        import paramiko
    except ImportError:
        _log("ERROR", "SFTP モードでは 'paramiko' が必要です。pip install paramiko で導入してください。")
        return 1

    remote_trigger_path = f"{SFTP_TARGET_DIR.rstrip('/')}/{TRIGGER_FILE}"
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

    def _connect_transport(transport: "paramiko.Transport") -> None:
        if auth_method == "password":
            if not SFTP_PASSWORD:
                raise ValueError("SFTP_PASSWORD が未設定です。環境変数に設定してください。")
            transport.connect(username=SFTP_USERNAME, password=SFTP_PASSWORD)
            return

        if auth_method == "key":
            private_key_content = os.getenv(SFTP_PRIVATE_KEY_ENV, "")
            if not private_key_content:
                raise ValueError(
                    f"{SFTP_PRIVATE_KEY_ENV} が未設定です。秘密鍵を環境変数へ設定してください。"
                )

            normalized_key = private_key_content.replace("\\n", "\n")
            key_stream = StringIO(normalized_key)

            load_key_errors = []
            private_key = None
            for key_cls in (
                paramiko.RSAKey,
                paramiko.Ed25519Key,
                paramiko.ECDSAKey,
                paramiko.DSSKey,
            ):
                key_stream.seek(0)
                try:
                    private_key = key_cls.from_private_key(
                        key_stream,
                        password=SFTP_PRIVATE_KEY_PASSPHRASE or None,
                    )
                    break
                except Exception as exc:  # noqa: PERF203
                    load_key_errors.append(f"{key_cls.__name__}: {exc}")

            if private_key is None:
                raise ValueError(
                    "秘密鍵の読み込みに失敗しました。"
                    f"試行結果: {' | '.join(load_key_errors)}"
                )

            transport.connect(username=SFTP_USERNAME, pkey=private_key)
            return

        raise ValueError(
            "未対応の SFTP_AUTH_METHOD です。'password' または 'key' を指定してください。"
        )

    for attempt in range(1, MAX_RETRY + 1):
        _log(
            "INFO",
            f"SFTP パスを確認中: {SFTP_HOST}:{remote_trigger_path}",
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

            file_stat = sftp.stat(remote_trigger_path)
            modified_timestamp = file_stat.st_mtime
            if modified_timestamp >= watch_start_timestamp:
                _log("SUCCESS", "trigger.txt を SFTP サーバー上で検知しました。", attempt, MAX_RETRY)
                return 0

            modified_datetime = datetime.fromtimestamp(modified_timestamp).strftime("%Y-%m-%d %H:%M:%S")
            _log(
                "INFO",
                (
                    "trigger.txt は存在しますが監視対象時刻より古いため未検知として扱います: "
                    f"mtime={modified_datetime}"
                ),
                attempt,
                MAX_RETRY,
            )
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
            if proxy_socket is not None:
                proxy_socket.close()

    return 1


def wait_for_trigger() -> int:
    """設定された監視方式で trigger ファイルの出現を待機する。"""
    watch_type = WATCH_TYPE.lower().strip()
    watch_start_timestamp = time.time() - (LOOKBACK_HOURS * 60 * 60)
    watch_start_datetime = datetime.fromtimestamp(watch_start_timestamp).strftime("%Y-%m-%d %H:%M:%S")
    _log(
        "INFO",
        (
            "監視対象時刻を設定しました。"
            f"この時刻以降に更新された {TRIGGER_FILE} を検知します: {watch_start_datetime}"
        ),
    )

    if watch_type == "local":
        return _wait_for_local_trigger(watch_start_timestamp)
    if watch_type == "sftp":
        return _wait_for_sftp_trigger(watch_start_timestamp)

    _log("ERROR", f"未対応の WATCH_TYPE: {WATCH_TYPE}。'local' または 'sftp' を指定してください。")
    return 1


if __name__ == "__main__":
    sys.exit(wait_for_trigger())
