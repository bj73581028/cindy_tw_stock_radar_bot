import os
import re
import requests

# ============================================================
# Taiwan Stock Radar 6.1 Backtest
# Telegram Trigger
# ============================================================

# ⚠️ 這裡改用「原本回測 Bot」的 Token
BACKTEST_TELEGRAM_BOT_TOKEN = os.getenv(
    "BACKTEST_TELEGRAM_BOT_TOKEN",
    ""
)

# GitHub PAT
GITHUB_TOKEN = os.getenv(
    "MY_GITHUB_TOKEN",
    ""
)

GITHUB_OWNER = "bj73581028"
GITHUB_REPO = "cindy_tw_stock_radar_bot"

# 原本回測期間
DEFAULT_START_DATE = "2025-10-01"
DEFAULT_END_DATE = "2026-09-30"

TELEGRAM_API = (
    f"https://api.telegram.org/bot"
    f"{BACKTEST_TELEGRAM_BOT_TOKEN}"
)


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

        print(
            f"📡 Telegram {method} HTTP Status："
            f"{response.status_code}"
        )

        if response.status_code != 200:

            print(response.text)

            return None

        data = response.json()

        if not data.get("ok"):

            print(
                f"❌ Telegram API 錯誤：{data}"
            )

            return None

        return data.get("result")

    except Exception as e:

        print(
            f"❌ Telegram API 連線錯誤：{e}"
        )

        return None


# ============================================================
# 發送 Telegram 訊息
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

            print("✅ Telegram 訊息發送成功")

            return True

        print(
            f"❌ Telegram 發送失敗："
            f"{response.status_code}"
        )

        print(response.text)

        return False

    except Exception as e:

        print(
            f"❌ Telegram 發送錯誤：{e}"
        )

        return False


# ============================================================
# 解析 Telegram 指令
# ============================================================

def parse_command(text):

    if not text:

        return None

    text = text.strip()

    # --------------------------------------------------------
    # 說明
    # --------------------------------------------------------

    if text in [
        "回測幫助",
        "回測說明",
        "help",
        "/help"
    ]:

        return {
            "mode": "HELP",
            "stock_codes": []
        }


    # --------------------------------------------------------
    # 全市場
    # --------------------------------------------------------

    if text in [
        "回測全部",
        "回測ALL",
        "回測 ALL",
        "回測 all"
    ]:

        return {
            "mode": "ALL",
            "stock_codes": []
        }


    # --------------------------------------------------------
    # 股票回測
    #
    # 回測2435
    # 回測 2435
    # 回測2435,2485
    # 回測 2435 2485
    # --------------------------------------------------------

    if text.startswith("回測"):

        content = text[2:].strip()

        content = content.replace(
            "，",
            ","
        )

        content = content.replace(
            "、",
            ","
        )

        content = content.replace(
            " ",
            ","
        )

        codes = re.findall(
            r"\d{4}",
            content
        )

        if codes:

            # 去除重複股票代號
            codes = list(
                dict.fromkeys(codes)
            )

            if len(codes) == 1:

                mode = "SINGLE"

            else:

                mode = "MULTI"

            return {
                "mode": mode,
                "stock_codes": codes
            }


    return None


# ============================================================
# 觸發原本的 Backtest Workflow
# ============================================================

def trigger_github_backtest(
    mode,
    stock_codes
):

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_OWNER}/"
        f"{GITHUB_REPO}/dispatches"
    )

    headers = {

        "Accept":
            "application/vnd.github+json",

        "Authorization":
            f"Bearer {GITHUB_TOKEN}",

        "X-GitHub-Api-Version":
            "2022-11-28"
    }

    payload = {

        "event_type":
            "telegram_backtest",

        "client_payload": {

            "mode":
                mode,

            "stock_codes":
                stock_codes,

            "start_date":
                DEFAULT_START_DATE,

            "end_date":
                DEFAULT_END_DATE
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
            "📡 GitHub Dispatch HTTP Status："
            f"{response.status_code}"
        )

        if response.status_code == 204:

            print(
                "✅ 原本的 Backtest Workflow 已觸發"
            )

            return True

        print(
            "❌ GitHub Dispatch 失敗"
        )

        print(response.text)

        return False

    except Exception as e:

        print(
            f"❌ GitHub API 錯誤：{e}"
        )

        return False


# ============================================================
# 處理回測指令
# ============================================================

def process_backtest(
    chat_id,
    mode,
    stock_codes
):

    # --------------------------------------------------------
    # HELP
    # --------------------------------------------------------

    if mode == "HELP":

        message = """📊 Taiwan Stock Radar 6.1 Backtest

可使用以下指令：

📌 單一股票
回測2435

📌 多檔股票
回測2435,2485

📌 全市場
回測全部

📅 預設回測期間
2025-10-01 ～ 2026-09-30
"""

        send_telegram(
            chat_id,
            message
        )

        return


    # --------------------------------------------------------
    # SINGLE
    # --------------------------------------------------------

    if mode == "SINGLE":

        stock_text = stock_codes[0]

        message = f"""🚀 Taiwan Stock Radar 6.1 Backtest

📌 股票：{stock_text}
📅 回測期間：{DEFAULT_START_DATE} ～ {DEFAULT_END_DATE}

⏳ 已收到指令，正在啟動回測...
"""


    # --------------------------------------------------------
    # MULTI
    # --------------------------------------------------------

    elif mode == "MULTI":

        stock_text = ", ".join(
            stock_codes
        )

        message = f"""🚀 Taiwan Stock Radar 6.1 Backtest

📌 股票：{stock_text}
📅 回測期間：{DEFAULT_START_DATE} ～ {DEFAULT_END_DATE}

⏳ 已收到指令，正在啟動回測...
"""


    # --------------------------------------------------------
    # ALL
    # --------------------------------------------------------

    elif mode == "ALL":

        message = f"""🚀 Taiwan Stock Radar 6.1 Backtest

📌 模式：全市場回測
📅 回測期間：{DEFAULT_START_DATE} ～ {DEFAULT_END_DATE}

⏳ 已收到指令，正在啟動回測...
"""


    else:

        return


    # --------------------------------------------------------
    # 先回覆 Telegram
    # --------------------------------------------------------

    send_telegram(
        chat_id,
        message
    )


    # --------------------------------------------------------
    # 觸發原本 Backtest Workflow
    # --------------------------------------------------------

    success = trigger_github_backtest(
        mode,
        stock_codes
    )


    if not success:

        send_telegram(

            chat_id,

            "❌ Backtest Workflow 啟動失敗。\n"
            "請至 GitHub Actions 查看錯誤訊息。"
        )


# ============================================================
# 主程式
# ============================================================

def main():

    print("=" * 70)

    print(
        "🤖 Taiwan Stock Radar 6.1 Backtest "
        "Telegram Trigger"
    )

    print("=" * 70)


    # --------------------------------------------------------
    # 檢查 Token
    # --------------------------------------------------------

    if not BACKTEST_TELEGRAM_BOT_TOKEN:

        print(
            "❌ BACKTEST_TELEGRAM_BOT_TOKEN "
            "沒有設定"
        )

        return


    if not GITHUB_TOKEN:

        print(
            "❌ MY_GITHUB_TOKEN "
            "沒有設定"
        )

        return


    print(
        "✅ Backtest Telegram Token 設定正常"
    )


    # --------------------------------------------------------
    # 確認目前連到哪一個 Bot
    # --------------------------------------------------------

    bot_info = telegram_api(
        "getMe"
    )

    if bot_info:

        print(
            f"🤖 Bot 名稱："
            f"{bot_info.get('first_name', '')}"
        )

        print(
            f"🆔 Bot Username："
            f"@{bot_info.get('username', '')}"
        )


    # --------------------------------------------------------
    # 取得 Telegram 訊息
    # --------------------------------------------------------

    print(
        "📡 正在取得 Backtest Telegram 新訊息..."
    )

    updates = telegram_api(

        "getUpdates",

        {
            "limit": 100,
            "timeout": 1,
            "allowed_updates": [
                "message"
            ]
        }
    )


    if updates is None:

        print(
            "❌ 無法取得 Telegram 更新"
        )

        return


    print(
        f"📨 Telegram 新訊息："
        f"{len(updates)} 筆"
    )


    if len(updates) == 0:

        print(
            "ℹ️ 目前沒有 Backtest Telegram 指令"
        )

        return


    # --------------------------------------------------------
    # 處理所有訊息
    # --------------------------------------------------------

    for update in updates:

        message = update.get(
            "message",
            {}
        )

        chat = message.get(
            "chat",
            {}
        )

        chat_id = chat.get(
            "id"
        )

        text = message.get(
            "text",
            ""
        )


        print("-" * 70)

        print(
            f"📩 收到訊息：{text}"
        )

        print(
            f"🆔 Chat ID：{chat_id}"
        )


        command = parse_command(
            text
        )


        if command is None:

            print(
                "⚠️ 無法辨識此指令"
            )

            continue


        mode = command[
            "mode"
        ]

        stock_codes = command[
            "stock_codes"
        ]


        print(
            f"📊 回測模式：{mode}"
        )

        print(
            f"📌 股票代號："
            f"{stock_codes}"
        )


        process_backtest(

            chat_id,

            mode,

            stock_codes
        )


# ============================================================
# 執行
# ============================================================

if __name__ == "__main__":

    main()
