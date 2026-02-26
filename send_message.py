import json
import urllib.request
from datetime import datetime



WEBHOOK_URL = "https://default02778447afb94b9abdbce0950ea3e1.d0.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/93d7ef38997644c6835712527fc2dad5/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=wIdgHX4UAOT0eCqDXK11n42vFsK2WekEdhBo83uILIg"


# ===== 実行時刻（時分秒）=====
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

STATUS_SUCCESS = "✅ SUCCESS"
STATUS_WARN    = "⚠️ WARN"
STATUS_ERROR   = "❌ ERROR"

STATUS = STATUS_SUCCESS


# ===== ヘッダー生成 =====
MESSAGE_HEADER = f"[{now}] STATUS: {STATUS}"

# ===== メッセージ生成 =====
## SUCCESS
MESSAGE100 = "正常に BlueYonder からデータが出力されました。"

## WARN
MESSAGE200 = "指定した時間になりましたが、まだ BlueYonder から Outbound ファイルが出力されていません。"

## Error
MESSAGE300 = "継続して監視をしましたが、BlueYonder から Outbound ファイルが出力されませんでした。"


FINAL_MESSAGE = f"{MESSAGE_HEADER}\n{MESSAGE100}"

print(FINAL_MESSAGE)

payload = {
    "text": FINAL_MESSAGE
}

req = urllib.request.Request(
    WEBHOOK_URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

with urllib.request.urlopen(req) as res:
    print("Status:", res.status)
