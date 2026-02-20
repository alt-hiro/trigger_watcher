import os
import sys
import time

# ===== 設定 =====
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
# =================


def _wait_for_local_trigger() -> int:
    target_path = os.path.join(TARGET_DIR, TRIGGER_FILE)

    for attempt in range(1, MAX_RETRY + 1):
        print(f"[INFO] Attempt {attempt}/{MAX_RETRY} - Checking local path: {target_path}")

        if os.path.exists(target_path):
            print("[SUCCESS] trigger.txt found on local filesystem.")
            return 0

        if attempt < MAX_RETRY:
            print(f"[INFO] Not found. Waiting {CHECK_INTERVAL_SECONDS} seconds...")
            time.sleep(CHECK_INTERVAL_SECONDS)

    print(f"[ERROR] trigger.txt not found after {MAX_RETRY} attempts.")
    return 1


def _wait_for_sftp_trigger() -> int:
    try:
        import paramiko
    except ImportError:
        print("[ERROR] SFTP mode requires 'paramiko'. Install it with: pip install paramiko")
        return 1

    remote_trigger_path = f"{SFTP_TARGET_DIR.rstrip('/')}/{TRIGGER_FILE}"

    for attempt in range(1, MAX_RETRY + 1):
        print(
            f"[INFO] Attempt {attempt}/{MAX_RETRY} - "
            f"Checking SFTP path: {SFTP_HOST}:{remote_trigger_path}"
        )

        transport = None
        sftp = None
        try:
            transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
            transport.connect(username=SFTP_USERNAME, password=SFTP_PASSWORD)
            sftp = paramiko.SFTPClient.from_transport(transport)

            # stat が成功すればファイルは存在
            sftp.stat(remote_trigger_path)
            print("[SUCCESS] trigger.txt found on SFTP server.")
            return 0
        except FileNotFoundError:
            if attempt < MAX_RETRY:
                print(f"[INFO] Not found. Waiting {CHECK_INTERVAL_SECONDS} seconds...")
                time.sleep(CHECK_INTERVAL_SECONDS)
            else:
                print(f"[ERROR] trigger.txt not found after {MAX_RETRY} attempts.")
        except Exception as exc:
            print(f"[ERROR] SFTP check failed: {exc}")
            if attempt < MAX_RETRY:
                print(f"[INFO] Retrying in {CHECK_INTERVAL_SECONDS} seconds...")
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
    watch_type = WATCH_TYPE.lower().strip()

    if watch_type == "local":
        return _wait_for_local_trigger()
    if watch_type == "sftp":
        return _wait_for_sftp_trigger()

    print(f"[ERROR] Unsupported WATCH_TYPE: {WATCH_TYPE}. Use 'local' or 'sftp'.")
    return 1


if __name__ == "__main__":
    sys.exit(wait_for_trigger())
