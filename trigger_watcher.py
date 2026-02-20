import os
import time
import sys

# ===== 設定 =====
TARGET_DIR = r"/path/to/your/directory"  # 監視するディレクトリ
TRIGGER_FILE = "trigger.txt"
CHECK_INTERVAL_SECONDS = 3  # 5分 = 300秒
MAX_RETRY = 10
# =================

def wait_for_trigger():
    target_path = os.path.join(TARGET_DIR, TRIGGER_FILE)

    for attempt in range(1, MAX_RETRY + 1):
        print(f"[INFO] Attempt {attempt}/{MAX_RETRY} - Checking: {target_path}")

        if os.path.exists(target_path):
            print("[SUCCESS] trigger.txt found.")
            return 0  # 正常終了

        if attempt < MAX_RETRY:
            print("[INFO] Not found. Waiting 5 minutes...")
            time.sleep(CHECK_INTERVAL_SECONDS)

    print("[ERROR] trigger.txt not found after 100 attempts.")
    return 1  # 異常終了


if __name__ == "__main__":
    exit_code = wait_for_trigger()
    sys.exit(exit_code)
