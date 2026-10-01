# ============================================================
# Telegram → GitHub Actions 回測觸發器
# Taiwan Stock Radar 6.1
#
# 功能：
# Telegram 輸入：
#
#   回測2435
#   回測2435,2330,3563
#   回測2435 2025-10-01 2026-09-30
#   回測幫助
#
# → 自動通知 GitHub Actions
# → 使用既有 backtest_6_1.py 執行回測
# ============================================================

import os
import time
import requests


# ============================================================
# 環境變數
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

GITHUB_TOKEN = os.getenv("MY_GITHUB_TOKEN", "")

GITHUB_OWNER = os.getenv(
    "GITHUB_OWNER",
    "bj73581028"
)

GITHUB_REPO = os.getenv(
    "GITHUB_REPO",
    "cindy_tw_stock_radar_bot"
)

GITHUB_BRANCH = os.getenv(
    "GITHUB_BRANCH",
    "main"
)


DEFAULT_START_DATE = "2025-10-01"
DEFAULT_END_DATE = "2026-09-30"


# ============================================================
# Telegram API
# ============================================================

def telegram_url(method):

    return (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/"
        f"{method}"
    )


# ============================================================
# 發送 Telegram 訊息
# ============================================================

def send_telegram(chat_id, message):

    if not TELEGRAM_BOT_TOKEN:

        print(
            "❌ 沒有 TELEGRAM_BOT_TOKEN"
        )

        return


    url = telegram_url(
        "sendMessage"
    )


    payload = {

        "chat_id":
            chat_id,

        "text":
            message
    }


    try:

        response = requests.post(

            url,

            data=payload,

            timeout=30
        )


        print(
            "Telegram 回應：",
            response.status_code
        )


    except Exception as e:

        print(
            "❌ Telegram 發送失敗：",
            e
        )


# ============================================================
# 觸發 GitHub Actions
# ============================================================

def trigger_github_backtest(
    mode,
    stock_codes,
    start_date,
    end_date
):

    if not GITHUB_TOKEN:

        print(
            "❌ 沒有 MY_GITHUB_TOKEN"
        )

        return False


    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_OWNER}/"
        f"{GITHUB_REPO}/dispatches"
    )


    headers = {

        "Authorization":
            f"Bearer {GITHUB_TOKEN}",

        "Accept":
            "application/vnd.github+json",

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
                start_date,

            "end_date":
                end_date
        }
    }


    try:

        response = requests.post(

            url,

            headers=headers,

            json=payload,

            timeout=30
        )


        print(
            "GitHub HTTP Status：",
            response.status_code
        )


        if response.status_code == 204:

            print(
                "✅ GitHub Actions 已成功觸發"
            )

            return True


        print(
            "❌ GitHub Actions 觸發失敗"
        )

        print(
            response.text
        )


    except Exception as e:

        print(
            "❌ GitHub API 錯誤：",
            e
        )


    return False


# ============================================================
# 解析 Telegram 指令
# ============================================================

def parse_command(text):

    text = text.strip()


    # --------------------------------------------------------
    # 回測幫助
    # --------------------------------------------------------

    if text in [
        "回測幫助",
        "/help",
        "help"
    ]:

        return {
            "type": "help"
        }


    # --------------------------------------------------------
    # 回測
    # --------------------------------------------------------

    if text.startswith("回測"):

        content = text[2:].strip()


        if not content:

            return {
                "type": "help"
            }


        parts = content.split()


        stock_codes = parts[0]


        start_date = DEFAULT_START_DATE

        end_date = DEFAULT_END_DATE


        if len(parts) >= 2:

            start_date = parts[1]


        if len(parts) >= 3:

            end_date = parts[2]


        return {

            "type":
                "backtest",

            "mode":
                (
                    "SINGLE"
                    if "," not in stock_codes
                    else "MULTI"
                ),

            "stock_codes":
                stock_codes,

            "start_date":
                start_date,

            "end_date":
                end_date
        }


    # --------------------------------------------------------
    # 未知指令
    # --------------------------------------------------------

    return {
        "type": "unknown"
    }


# ============================================================
# 取得 Telegram Updates
# ============================================================

def get_updates(offset=None):

    params = {
        "timeout": 30
    }


    if offset is not None:

        params["offset"] = offset


    try:

        response = requests.get(

            telegram_url(
                "getUpdates"
            ),

            params=params,

            timeout=40
        )


        if not response.ok:

            print(
                "❌ Telegram getUpdates 失敗：",
                response.text
            )

            return []


        data = response.json()


        if not data.get("ok"):

            return []


        return data.get(
            "result",
            []
        )


    except Exception as e:

        print(
            "❌ Telegram API 錯誤：",
            e
        )

        return []


# ============================================================
# 主程式
# ============================================================

def main():

    print(
        "=" * 70
    )


    print(
        "🤖 Taiwan Stock Radar 6.1 "
        "Telegram Trigger"
    )


    print(
        "=" * 70
    )


    # --------------------------------------------------------
    # 檢查 Telegram Token
    # --------------------------------------------------------

    if not TELEGRAM_BOT_TOKEN:

        print(
            "❌ TELEGRAM_BOT_TOKEN 未設定"
        )

        return


    # --------------------------------------------------------
    # 檢查 GitHub Token
    # --------------------------------------------------------

    if not GITHUB_TOKEN:

        print(
            "❌ MY_GITHUB_TOKEN 未設定"
        )

        return


    print(
        "✅ Telegram Trigger 啟動"
    )


    print(
        "等待 Telegram 指令..."
    )


    offset = None


    # ========================================================
    # 持續監聽 Telegram
    # ========================================================

    while True:

        updates = get_updates(
            offset
        )


        for update in updates:

            offset = (
                update["update_id"] + 1
            )


            message = update.get(
                "message"
            )


            if not message:

                continue


            chat_id = message.get(
                "chat",
                {}
            ).get(
                "id"
            )


            text = message.get(
                "text",
                ""
            ).strip()


            if not text:

                continue


            print(
                f"📩 Telegram：{text}"
            )


            command = parse_command(
                text
            )


            # =================================================
            # 幫助
            # =================================================

            if command["type"] == "help":

                send_telegram(

                    chat_id,

                    """🤖 台股飆股雷達 6.1

📌 回測單一股票：
回測2435

📌 回測多檔：
回測2435,2330,3563

📌 指定日期：
回測2435 2025-10-01 2026-09-30

📌 查看說明：
回測幫助

⏳ 回測完成後會自動把結果傳回 Telegram。
"""
                )

                continue


            # =================================================
            # 未知指令
            # =================================================

            if command["type"] == "unknown":

                send_telegram(

                    chat_id,

                    """⚠️ 我看不懂這個指令。

請輸入：

回測2435

或：

回測幫助
"""
                )

                continue


            # =================================================
            # 回測
            # =================================================

            if command["type"] == "backtest":

                mode = command[
                    "mode"
                ]

                stock_codes = command[
                    "stock_codes"
                ]

                start_date = command[
                    "start_date"
                ]

                end_date = command[
                    "end_date"
                ]


                # ------------------------------------------------
                # 日期檢查
                # ------------------------------------------------

                try:

                    start_obj = time.strptime(
                        start_date,
                        "%Y-%m-%d"
                    )


                    end_obj = time.strptime(
                        end_date,
                        "%Y-%m-%d"
                    )


                    if start_obj > end_obj:

                        send_telegram(

                            chat_id,

                            "⚠️ 開始日期不能晚於結束日期。"
                        )

                        continue


                except Exception:

                    send_telegram(

                        chat_id,

                        """⚠️ 日期格式錯誤。

請使用：

YYYY-MM-DD

例如：

回測2435 2025-10-01 2026-09-30
"""
                    )

                    continue


                # ------------------------------------------------
                # 通知使用者
                # ------------------------------------------------

                send_telegram(

                    chat_id,

                    f"""🚀 已收到回測指令

📌 股票：{stock_codes}
🔎 模式：{mode}
📅 期間：{start_date} ～ {end_date}

⏳ 正在啟動 GitHub Actions...
完成後會收到回測結果。
"""
                )


                # ------------------------------------------------
                # 觸發 GitHub Actions
                # ------------------------------------------------

                success = trigger_github_backtest(

                    mode,

                    stock_codes,

                    start_date,

                    end_date
                )


                if not success:

                    send_telegram(

                        chat_id,

                        """❌ GitHub Actions 啟動失敗。

請檢查：

1. MY_GITHUB_TOKEN
2. GitHub Repository
3. Actions 權限
"""
                    )


        # --------------------------------------------------------
        # 稍微休息
        # --------------------------------------------------------

        time.sleep(1)


# ============================================================
# 程式入口
# ============================================================

if __name__ == "__main__":

    main()
