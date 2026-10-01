import os
import requests
import re

# ============================================================
# Taiwan Stock Radar 6.1
# Telegram Backtest Trigger
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GITHUB_TOKEN = os.getenv("MY_GITHUB_TOKEN", "")

GITHUB_OWNER = os.getenv("GITHUB_OWNER", "bj73581028")
GITHUB_REPO = os.getenv("GITHUB_REPO", "cindy_tw_stock_radar_bot")

OFFSET_FILE = "telegram_offset.txt"

DEFAULT_START_DATE = "2025-10-01"
DEFAULT_END_DATE = "2026-09-30"


# ============================================================
# Telegram
# ============================================================

def telegram_api(method, params=None):

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"

    try:
        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        print(f"📡 Telegram HTTP Status：{response.status_code}")

        if response.status_code != 200:
            print(f"❌ Telegram API 錯誤：{response.text}")
            return None

        data = response.json()

        if not data.get("ok"):
            print(f"❌ Telegram API 回傳錯誤：{data}")
            return None

        return data.get("result", [])

    except Exception as e:
        print(f"❌ Telegram API 連線錯誤：{e}")
        return None


def send_telegram(chat_id, text):

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

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

        print(f"❌ Telegram 回覆失敗：{response.status_code}")
        print(response.text)

        return False

    except Exception as e:

        print(f"❌ Telegram 回覆錯誤：{e}")

        return False


# ============================================================
# Offset
# ============================================================

def load_offset():

    if not os.path.exists(OFFSET_FILE):
        return None

    try:

        with open(OFFSET_FILE, "r", encoding="utf-8") as f:
            value = f.read().strip()

        if value:
            return int(value)

    except Exception as e:

        print(f"⚠️ Offset 讀取失敗：{e}")

    return None


def save_offset(offset):

    try:

        with open(OFFSET_FILE, "w", encoding="utf-8") as f:
            f.write(str(offset))

        print(f"💾 Offset 已保存：{offset}")

    except Exception as e:

        print(f"❌ Offset 保存失敗：{e}")


# ============================================================
# Get Telegram Updates
# ============================================================

def get_updates(offset=None):

    params = {
        "timeout": 1,
        "allowed_updates": ["message"]
    }

    if offset is not None:
        params["offset"] = offset

    return telegram_api("getUpdates", params)


# ============================================================
# Parse command
# ============================================================

def parse_command(text):

    if not text:
        return None

    text = text.strip()

    # ------------------------------
    # 回測幫助
    # ------------------------------

    if text in ["回測幫助", "回測說明", "help"]:

        return {
            "type": "help"
        }

    # ------------------------------
    # 單一股票
    # 例如：
    # 回測2435
    # 回測 2435
    # ------------------------------

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

    # ------------------------------
    # 多檔股票
    # 例如：
    # 回測2435,2485
    # ------------------------------

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

    # ------------------------------
    # 全市場
    # ------------------------------

    if text in ["回測全部", "回測ALL", "回測 ALL"]:

        return {
            "type": "backtest",
            "mode": "ALL",
            "stock_codes": ""
        }

    return None


# ============================================================
# GitHub Repository Dispatch
# ============================================================

def trigger_github_backtest(
    mode,
    stock_codes,
    start_date=DEFAULT_START_DATE,
    end_date=DEFAULT_END_DATE
):

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_OWNER}/"
        f"{GITHUB_REPO}/dispatches"
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
            "start_date": start_date,
            "end_date": end_date
        }
    }

    print("🚀 正在觸發 GitHub Backtest...")

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

            print("✅ GitHub Backtest 觸發成功")

            return True

        print("❌ GitHub Backtest 觸發失敗")
        print(response.text)

        return False

    except Exception as e:

        print(f"❌ GitHub API 錯誤：{e}")

        return False


# ============================================================
# Process Backtest
# ============================================================

def process_backtest(chat_id, command):

    mode = command["mode"]
    stock_codes = command["stock_codes"]

    if mode == "SINGLE":

        message = (
            "🔎 收到回測指令\n\n"
            f"📌 股票：{stock_codes}\n"
            f"📅 回測期間：{DEFAULT_START_DATE} ～ {DEFAULT_END_DATE}\n\n"
            "⏳ 正在啟動 GitHub 回測..."
        )

    elif mode == "MULTI":

        message = (
            "🔎 收到多檔回測指令\n\n"
            f"📌 股票：{stock_codes}\n"
            f"📅 回測期間：{DEFAULT_START_DATE} ～ {DEFAULT_END_DATE}\n\n"
            "⏳ 正在啟動 GitHub 回測..."
        )

    else:

        message = (
            "🔎 收到全市場回測指令\n\n"
            f"📅 回測期間：{DEFAULT_START_DATE} ～ {DEFAULT_END_DATE}\n\n"
            "⏳ 正在啟動 GitHub 回測..."
        )

    send_telegram(
        chat_id,
        message
    )

    success = trigger_github_backtest(
        mode=mode,
        stock_codes=stock_codes
    )

    if not success:

        send_telegram(
            chat_id,
            "❌ GitHub 回測啟動失敗，請檢查 GitHub Token 權限。"
        )


# ============================================================
# Help
# ============================================================

def send_help(chat_id):

    message = (
        "📊 Taiwan Stock Radar 6.1 回測指令\n\n"
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
    print("🤖 Taiwan Stock Radar 6.1 Telegram Trigger")
    print("=" * 70)

    if not TELEGRAM_BOT_TOKEN:

        print("❌ TELEGRAM_BOT_TOKEN 未設定")
        return

    if not GITHUB_TOKEN:

        print("❌ MY_GITHUB_TOKEN 未設定")
        return

    print("✅ Token 設定正常")

    offset = load_offset()

    if offset is None:

        print("🆕 找不到 telegram_offset.txt")
        print("📡 第一次抓取 Telegram 新訊息...")

        updates = get_updates()

        if updates is None:

            print("❌ 無法取得 Telegram 訊息")
            return

        print(
            f"📨 Telegram 新訊息："
            f"{len(updates)} 筆"
        )

    else:

        print(
            f"📌 目前 Offset：{offset}"
        )

        updates = get_updates(offset)

        if updates is None:

            print("❌ 無法取得 Telegram 訊息")
            return

        print(
            f"📨 Telegram 新訊息："
            f"{len(updates)} 筆"
        )

    # ========================================================
    # 沒有新訊息
    # ========================================================

    if not updates:

        print("ℹ️ 目前沒有新的 Telegram 指令")

        # 第一次沒有訊息也要建立 offset
        if offset is None:

            print("💾 建立初始 Offset")

            # 再抓一次最新 update_id
            latest = get_updates()

            if latest:

                new_offset = (
                    max(
                        u["update_id"]
                        for u in latest
                    ) + 1
                )

            else:

                # 沒有任何 Telegram 訊息
                new_offset = 0

            save_offset(new_offset)

        return

    # ========================================================
    # 處理訊息
    # ========================================================

    highest_update_id = None

    for update in updates:

        update_id = update.get("update_id")

        if update_id is not None:

            if (
                highest_update_id is None
                or update_id > highest_update_id
            ):

                highest_update_id = update_id

        message = update.get("message")

        if not message:
            continue

        chat = message.get("chat", {})

        chat_id = chat.get("id")

        text = message.get("text", "")

        username = (
            message
            .get("from", {})
            .get("username", "")
        )

        print(
            f"📩 Telegram："
            f"{text} "
            f"(@{username})"
        )

        command = parse_command(text)

        if not command:

            print("⏭️ 不是有效回測指令")

            continue

        if command["type"] == "help":

            send_help(chat_id)

            continue

        if command["type"] == "backtest":

            process_backtest(
                chat_id,
                command
            )

    # ========================================================
    # 保存 Offset
    # ========================================================

    if highest_update_id is not None:

        new_offset = highest_update_id + 1

        save_offset(new_offset)

    print("=" * 70)
    print("✅ Telegram Trigger 執行完成")
    print("=" * 70)


if __name__ == "__main__":

    main()
