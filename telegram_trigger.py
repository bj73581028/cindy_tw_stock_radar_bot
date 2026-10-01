import os
import requests
import re

# ============================================================
# Taiwan Stock Radar 6.1
# Telegram Backtest Trigger
#
# 功能：
# Telegram 輸入：
#   回測2435
#
# → GitHub Actions
# → repository_dispatch
# → 原本的 backtest_6_1.py
#
# 不使用 telegram_offset.txt
# ============================================================


# ============================================================
# 基本設定
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

DEFAULT_START_DATE = "2025-10-01"
DEFAULT_END_DATE = "2026-09-30"


# ============================================================
# Telegram API
# ============================================================

def telegram_api(method, params=None):

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/"
        f"{method}"
    )

    try:

        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        print(
            f"📡 Telegram HTTP Status："
            f"{response.status_code}"
        )

        if response.status_code != 200:

            print(
                "❌ Telegram API 錯誤："
                f"{response.text}"
            )

            return None

        data = response.json()

        if not data.get("ok"):

            print(
                "❌ Telegram API 回傳錯誤："
                f"{data}"
            )

            return None

        return data.get("result", [])

    except Exception as e:

        print(
            f"❌ Telegram API 連線錯誤：{e}"
        )

        return None


# ============================================================
# 發送 Telegram 訊息
# ============================================================

def send_telegram(chat_id, text):

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/"
        f"sendMessage"
    )

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

            print("📤 Telegram 回覆成功")

            return True

        print(
            f"❌ Telegram 回覆失敗："
            f"{response.status_code}"
        )

        print(response.text)

        return False

    except Exception as e:

        print(
            f"❌ Telegram 回覆錯誤：{e}"
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
    # 回測幫助
    # --------------------------------------------------------

    if text in [
        "回測幫助",
        "回測說明",
        "help"
    ]:

        return {
            "type": "help"
        }

    # --------------------------------------------------------
    # 單一股票
    #
    # 回測2435
    # 回測 2435
    # --------------------------------------------------------

    match = re.match(
        r"^回測\s*([0-9]{4})$",
        text
    )

    if match:

        return {
            "type": "backtest",
            "mode": "SINGLE",
            "stock_codes": match.group(1)
        }

    # --------------------------------------------------------
    # 多檔股票
    #
    # 回測2435,2485
    # 回測2435 2485
    # --------------------------------------------------------

    match = re.match(
        r"^回測\s*([0-9,\s]+)$",
        text
    )

    if match:

        codes = re.findall(
            r"\d{4}",
            match.group(1)
        )

        if codes:

            return {
                "type": "backtest",
                "mode": "MULTI",
                "stock_codes": ",".join(codes)
            }

    # --------------------------------------------------------
    # 全市場
    # --------------------------------------------------------

    if text in [
        "回測全部",
        "回測ALL",
        "回測 ALL"
    ]:

        return {
            "type": "backtest",
            "mode": "ALL",
            "stock_codes": ""
        }

    return None


# ============================================================
# 觸發 GitHub Actions
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

        "Accept": (
            "application/vnd.github+json"
        ),

        "Authorization": (
            f"Bearer {GITHUB_TOKEN}"
        ),

        "X-GitHub-Api-Version": (
            "2022-11-28"
        )
    }

    payload = {

        "event_type": "telegram_backtest",

        "client_payload": {

            "mode": mode,

            "stock_codes": stock_codes,

            "start_date": (
                DEFAULT_START_DATE
            ),

            "end_date": (
                DEFAULT_END_DATE
            )
        }
    }

    print(
        "🚀 正在觸發 GitHub Backtest..."
    )

    print(
        f"📌 Mode：{mode}"
    )

    print(
        f"📌 Stock Codes："
        f"{stock_codes}"
    )

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20
        )

        print(
            f"🐙 GitHub HTTP Status："
            f"{response.status_code}"
        )

        if response.status_code == 204:

            print(
                "✅ GitHub Backtest "
                "觸發成功"
            )

            return True

        print(
            "❌ GitHub Backtest "
            "觸發失敗"
        )

        print(response.text)

        return False

    except Exception as e:

        print(
            f"❌ GitHub API 錯誤：{e}"
        )

        return False


# ============================================================
# 執行回測
# ============================================================

def process_backtest(
    chat_id,
    command
):

    mode = command["mode"]

    stock_codes = command["stock_codes"]

    # --------------------------------------------------------
    # 單一股票
    # --------------------------------------------------------

    if mode == "SINGLE":

        message = (
            "🔎 收到回測指令\n\n"
            f"📌 股票：{stock_codes}\n"
            f"📅 回測期間："
            f"{DEFAULT_START_DATE} ～ "
            f"{DEFAULT_END_DATE}\n\n"
            "⏳ 正在啟動 GitHub 回測..."
        )

    # --------------------------------------------------------
    # 多檔
    # --------------------------------------------------------

    elif mode == "MULTI":

        message = (
            "🔎 收到多檔回測指令\n\n"
            f"📌 股票：{stock_codes}\n"
            f"📅 回測期間："
            f"{DEFAULT_START_DATE} ～ "
            f"{DEFAULT_END_DATE}\n\n"
            "⏳ 正在啟動 GitHub 回測..."
        )

    # --------------------------------------------------------
    # 全市場
    # --------------------------------------------------------

    else:

        message = (
            "🔎 收到全市場回測指令\n\n"
            f"📅 回測期間："
            f"{DEFAULT_START_DATE} ～ "
            f"{DEFAULT_END_DATE}\n\n"
            "⏳ 正在啟動 GitHub 回測..."
        )

    # 先通知 Telegram
    send_telegram(
        chat_id,
        message
    )

    # 觸發 GitHub
    success = trigger_github_backtest(
        mode=mode,
        stock_codes=stock_codes
    )

    if not success:

        send_telegram(
            chat_id,
            "❌ GitHub 回測啟動失敗。\n\n"
            "請檢查 MY_GITHUB_TOKEN "
            "權限及 repository_dispatch "
            "設定。"
        )


# ============================================================
# Help
# ============================================================

def send_help(chat_id):

    message = (
        "📊 Taiwan Stock Radar 6.1\n"
        "Telegram 回測指令\n\n"
        "🔹 單一股票\n"
        "回測2435\n\n"
        "🔹 多檔股票\n"
        "回測2435,2485,2330\n\n"
        "🔹 全市場\n"
        "回測全部\n\n"
        "🔹 查看說明\n"
        "回測幫助"
    )

    send_telegram(
        chat_id,
        message
    )


# ============================================================
# Main
# ============================================================

def main():

    print("=" * 70)

    print(
        "🤖 Taiwan Stock Radar 6.1 "
        "Telegram Trigger"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # Token 檢查
    # --------------------------------------------------------

    if not TELEGRAM_BOT_TOKEN:

        print(
            "❌ TELEGRAM_BOT_TOKEN "
            "未設定"
        )

        return

    if not GITHUB_TOKEN:

        print(
            "❌ MY_GITHUB_TOKEN "
            "未設定"
        )

        return

    print(
        "✅ Token 設定正常"
    )

    # --------------------------------------------------------
    # 取得 Telegram 更新
    # --------------------------------------------------------

    print(
        "📡 正在取得 Telegram 新訊息..."
    )

    updates = telegram_api(
        "getUpdates",
        {
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

    # --------------------------------------------------------
    # 沒有訊息
    # --------------------------------------------------------

    if not updates:

        print(
            "ℹ️ 目前沒有 Telegram 指令"
        )

        return

    # --------------------------------------------------------
    # 找出最新的有效訊息
    # --------------------------------------------------------

    highest_update_id = 0

    for update in updates:

        update_id = update.get(
            "update_id",
            0
        )

        if update_id > highest_update_id:

            highest_update_id = update_id

        message = update.get(
            "message"
        )

        if not message:

            continue

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

        print(
            f"📩 Telegram 訊息："
            f"{text}"
        )

        # ----------------------------------------------------
        # 解析指令
        # ----------------------------------------------------

        command = parse_command(
            text
        )

        if not command:

            print(
                "⏭️ 不是有效的回測指令"
            )

            continue

        # ----------------------------------------------------
        # Help
        # ----------------------------------------------------

        if command["type"] == "help":

            send_help(
                chat_id
            )

            continue

        # ----------------------------------------------------
        # Backtest
        # ----------------------------------------------------

        if command["type"] == "backtest":

            process_backtest(
                chat_id,
                command
            )

    print(
        f"📌 本次最高 Update ID："
        f"{highest_update_id}"
    )

    print("=" * 70)

    print(
        "✅ Telegram Trigger 執行完成"
    )

    print("=" * 70)


if __name__ == "__main__":

    main()
