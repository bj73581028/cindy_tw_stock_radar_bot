import os
import re
import requests

# ============================================================
# 基本設定
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GITHUB_TOKEN = os.getenv("MY_GITHUB_TOKEN", "")

GITHUB_OWNER = "bj73581028"
GITHUB_REPO = "cindy_tw_stock_radar_bot"

DEFAULT_START_DATE = "2025-10-01"
DEFAULT_END_DATE = "2026-09-30"

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# ============================================================
# Telegram API
# ============================================================

def telegram_api(method, params=None):

    url = f"{TELEGRAM_API}/{method}"

    try:
        response = requests.get(
            url,
            params=params or {},
            timeout=20
        )

        print(f"📡 Telegram HTTP Status：{response.status_code}")

        if response.status_code != 200:
            print(response.text)
            return None

        data = response.json()

        if not data.get("ok"):
            print(f"❌ Telegram API 錯誤：{data}")
            return None

        return data.get("result")

    except Exception as e:

        print(f"❌ Telegram API 連線錯誤：{e}")

        return None


# ============================================================
# 發送 Telegram
# ============================================================

def send_telegram(chat_id, text):

    url = f"{TELEGRAM_API}/sendMessage"

    try:

        response = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": text
            },
            timeout=20
        )

        if response.status_code == 200:

            print("✅ Telegram 回覆成功")
            return True

        print(f"❌ Telegram 回覆失敗：{response.status_code}")
        print(response.text)

        return False

    except Exception as e:

        print(f"❌ Telegram 發送錯誤：{e}")

        return False


# ============================================================
# 解析 Telegram 指令
# ============================================================

def parse_command(text):

    if not text:
        return None

    text = text.strip()

    # ----------------------------
    # 說明
    # ----------------------------

    if text in ["回測幫助", "回測說明", "help", "/help"]:

        return {
            "mode": "HELP",
            "stock_codes": []
        }

    # ----------------------------
    # 全部股票
    # ----------------------------

    if text in ["回測全部", "回測ALL", "回測 ALL", "回測 all"]:

        return {
            "mode": "ALL",
            "stock_codes": []
        }

    # ----------------------------
    # 單一 / 多檔
    #
    # 回測2435
    # 回測 2435
    # 回測2435,2485
    # 回測 2435 2485
    # ----------------------------

    if text.startswith("回測"):

        content = text[2:].strip()

        content = content.replace("，", ",")
        content = content.replace("、", ",")
        content = content.replace(" ", ",")

        codes = re.findall(r"\d{4}", content)

        if codes:

            # 去除重複
            codes = list(dict.fromkeys(codes))

            return {
                "mode": "SINGLE" if len(codes) == 1 else "MULTI",
                "stock_codes": codes
            }

    return None


# ============================================================
# 觸發 GitHub Backtest
# ============================================================

def trigger_github_backtest(mode, stock_codes):

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_OWNER}/{GITHUB_REPO}/dispatches"
    )

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    payload = {

        "event_type": "telegram_backtest",

        "client_payload": {

            "mode": mode,

            "stock_codes": stock_codes,

            "start_date": DEFAULT_START_DATE,

            "end_date": DEFAULT_END_DATE
        }
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20
        )

        print(
            f"📡 GitHub Dispatch HTTP Status："
            f"{response.status_code}"
        )

        if response.status_code == 204:

            print("✅ GitHub Backtest Workflow 已觸發")

            return True

        print("❌ GitHub Dispatch 失敗")
        print(response.text)

        return False

    except Exception as e:

        print(f"❌ GitHub API 錯誤：{e}")

        return False


# ============================================================
# 處理回測
# ============================================================

def process_backtest(chat_id, mode, stock_codes):

    if mode == "HELP":

        message = """📚 台股飆股雷達 6.1｜Telegram 回測指令

📌 單一股票
回測2435

📌 多檔股票
回測2435,2485

📌 全市場
回測全部

📅 預設回測期間
2025-10-01 ～ 2026-09-30
"""

        send_telegram(chat_id, message)

        return


    if mode == "SINGLE":

        stock_text = stock_codes[0]

        message = f"""🚀 已收到回測指令

📌 股票：{stock_text}
📅 回測期間：{DEFAULT_START_DATE} ～ {DEFAULT_END_DATE}

⏳ 正在啟動回測...
"""

    elif mode == "MULTI":

        stock_text = ", ".join(stock_codes)

        message = f"""🚀 已收到回測指令

📌 股票：{stock_text}
📅 回測期間：{DEFAULT_START_DATE} ～ {DEFAULT_END_DATE}

⏳ 正在啟動回測...
"""

    else:

        message = f"""🚀 已收到回測指令

📌 模式：{mode}
📅 回測期間：{DEFAULT_START_DATE} ～ {DEFAULT_END_DATE}

⏳ 正在啟動回測...
"""


    send_telegram(chat_id, message)


    # --------------------------------------------------------
    # 觸發 GitHub
    # --------------------------------------------------------

    success = trigger_github_backtest(
        mode,
        stock_codes
    )


    if not success:

        send_telegram(
            chat_id,
            "❌ GitHub 回測 Workflow 啟動失敗，請查看 GitHub Actions。"
        )


# ============================================================
# 主程式
# ============================================================

def main():

    print("=" * 70)
    print("🤖 Taiwan Stock Radar 6.1 Telegram Trigger")
    print("=" * 70)


    # --------------------------------------------------------
    # Token 檢查
    # --------------------------------------------------------

    if not TELEGRAM_BOT_TOKEN:

        print("❌ TELEGRAM_BOT_TOKEN 沒有設定")

        return


    if not GITHUB_TOKEN:

        print("❌ MY_GITHUB_TOKEN 沒有設定")

        return


    print("✅ Token 設定正常")


    # --------------------------------------------------------
    # 取得 Telegram 更新
    # --------------------------------------------------------

    print("📡 正在取得 Telegram 新訊息...")


    updates = telegram_api(
        "getUpdates",
        {
            "limit": 100,
            "timeout": 1,
            "allowed_updates": ["message"]
        }
    )


    if updates is None:

        print("❌ 無法取得 Telegram 更新")

        return


    print(f"📨 Telegram 新訊息：{len(updates)} 筆")


    if len(updates) == 0:

        print("ℹ️ 目前沒有 Telegram 指令")

        return


    # --------------------------------------------------------
    # 處理訊息
    # --------------------------------------------------------

    for update in updates:

        message = update.get("message", {})

        chat = message.get("chat", {})

        chat_id = chat.get("id")

        text = message.get("text", "")


        print("-" * 70)

        print(f"📩 收到訊息：{text}")

        print(f"🆔 Chat ID：{chat_id}")


        command = parse_command(text)


        if command is None:

            print("⚠️ 無法辨識指令")

            continue


        mode = command["mode"]

        stock_codes = command["stock_codes"]


        print(f"📊 回測模式：{mode}")

        print(f"📌 股票代號：{stock_codes}")


        process_backtest(
            chat_id,
            mode,
            stock_codes
        )


if __name__ == "__main__":

    main()
