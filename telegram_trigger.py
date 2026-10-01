import os
import requests
import json

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

print("=" * 70)
print("🤖 Taiwan Stock Radar 6.1 Telegram 診斷工具")
print("=" * 70)

if not TELEGRAM_BOT_TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN 沒有設定")
    raise SystemExit(1)

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def telegram_api(method, params=None):
    try:
        response = requests.get(
            f"{BASE_URL}/{method}",
            params=params or {},
            timeout=20
        )

        print(f"📡 {method} HTTP Status：{response.status_code}")

        try:
            data = response.json()
        except Exception:
            print("❌ Telegram 回傳不是 JSON")
            print(response.text)
            return None

        return data

    except Exception as e:
        print(f"❌ API 連線錯誤：{e}")
        return None


# ============================================================
# 1. 測試 Bot Token
# ============================================================

print()
print("【1】檢查 Bot Token")

me = telegram_api("getMe")

if not me or not me.get("ok"):
    print("❌ Bot Token 無效")
    print(me)
    raise SystemExit(1)

bot_info = me["result"]

print("✅ Bot Token 正常")
print(f"🤖 Bot 名稱：{bot_info.get('first_name', '')}")
print(f"🆔 Bot Username：@{bot_info.get('username', '')}")


# ============================================================
# 2. 檢查 Webhook
# ============================================================

print()
print("【2】檢查 Telegram Webhook")

webhook = telegram_api("getWebhookInfo")

if not webhook or not webhook.get("ok"):
    print("❌ 無法取得 Webhook 狀態")
    print(webhook)
else:
    info = webhook["result"]

    webhook_url = info.get("url", "")
    pending = info.get("pending_update_count", 0)

    print(f"🌐 Webhook URL：{webhook_url if webhook_url else '(空白)'}")
    print(f"📨 Pending Updates：{pending}")

    if info.get("last_error_message"):
        print(f"⚠️ Webhook 最後錯誤：{info.get('last_error_message')}")

    if webhook_url:
        print()
        print("❌ 發現 Webhook！")
        print("❗ getUpdates 與 Webhook 不能同時使用")
        print("❗ 這就是目前最需要處理的問題")
    else:
        print("✅ 沒有設定 Webhook")
        print("✅ 可以使用 getUpdates")


# ============================================================
# 3. 取得 Telegram 更新
# ============================================================

print()
print("【3】測試 getUpdates")

updates = telegram_api(
    "getUpdates",
    {
        "limit": 100,
        "timeout": 1,
        "allowed_updates": ["message"]
    }
)

if not updates:
    print("❌ getUpdates 沒有取得回應")
    raise SystemExit(1)

if not updates.get("ok"):
    print("❌ getUpdates 發生錯誤")
    print(json.dumps(updates, ensure_ascii=False, indent=2))
    raise SystemExit(1)

result = updates.get("result", [])

print(f"📨 Telegram 新訊息：{len(result)} 筆")

if len(result) == 0:
    print()
    print("⚠️ 目前 Telegram 沒有傳給這個 Bot 的待處理訊息")
else:
    print()
    print("🎉 有收到 Telegram 訊息！")
    print("-" * 70)

    for update in result:

        update_id = update.get("update_id")

        message = update.get("message", {})

        chat = message.get("chat", {})
        chat_id = chat.get("id")

        text = message.get("text", "")

        print(f"Update ID：{update_id}")
        print(f"Chat ID：{chat_id}")
        print(f"訊息：{text}")
        print("-" * 70)


# ============================================================
# 4. 最後結論
# ============================================================

print()
print("=" * 70)
print("🔎 診斷完成")
print("=" * 70)

if webhook and webhook.get("ok"):
    info = webhook["result"]

    if info.get("url"):
        print("❌ 結論：Bot 有 Webhook，請先移除 Webhook。")
    elif len(result) == 0:
        print("⚠️ 結論：Webhook 正常，但目前沒有待處理 Telegram 訊息。")
        print()
        print("👉 請重新在 Telegram 傳一次：")
        print("   回測2435")
        print()
        print("👉 然後重新執行 GitHub Actions。")
    else:
        print("✅ 結論：Telegram 已正常收到訊息。")
        print("👉 下一步可以恢復回測觸發程式。")
