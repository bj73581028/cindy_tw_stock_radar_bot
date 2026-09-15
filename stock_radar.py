import os
import requests

FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN")

url = "https://api.finmindtrade.com/api/v4/data"

headers = {
    "Authorization": f"Bearer {FINMIND_TOKEN}"
}

params = {
    "dataset": "TaiwanStockInfo"
}

response = requests.get(
    url,
    headers=headers,
    params=params,
    timeout=60
)

print("HTTP Status:", response.status_code)
print("FinMind Response:", response.text[:1000])

response.raise_for_status()

data = response.json()

if data.get("status") != 200:
    raise Exception(data)

print("✅ FinMind API 連線成功！")
print("取得資料筆數：", len(data.get("data", [])))
