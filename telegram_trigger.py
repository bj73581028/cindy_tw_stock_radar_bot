import os
import time
import requests


# ============================================================
# Taiwan Stock Radar 6.1
# Telegram → GitHub Actions 回測觸發器
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

OFFSET_FILE = "telegram_offset.txt"


# ============================================================
# Telegram API
# ============================================================

def telegram_url(method):
    return (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/{method}"
    )


def send_telegram(chat_id, message):

    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN 未設定")
        return False

    try:

        response = requests.post(
            telegram_url("sendMessage"),
            data={
                "chat_id": chat_id,
                "text": message
            },
            timeout=30
        )

        print(
            "📤 Telegram 發送：",
            response.status_code
        )

        if response.ok:
            return True

        print(
            "❌ Telegram 發送失敗：",
            response.text
        )

        return False

    except Exception as e:

        print(
            "❌ Telegram 發送錯誤：",
            e
        )

        return False


# ============================================================
# Offset
# ============================================================

def load_offset():

    if not os.path.exists(OFFSET_FILE):
        return None

    try:

        with open(
            OFFSET_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            value = f.read().strip()

            if value:
                return int(value)

    except Exception as e:

        print(
            "⚠️ Offset 讀取失敗：",
            e
        )

    return None


def save_offset(offset):

    try:

        with open(
            OFFSET_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(str(offset))

        print(
            f"💾 Offset 已保存：{offset}"
        )

        return True

    except Exception as e:

        print(
            "❌ Offset 保存失敗：",
            e
        )

        return False


# ============================================================
# Telegram getUpdates
# ============================================================

def get_updates(offset=None):

    params = {
        "timeout": 1,
        "allowed_updates": ["message"]
    }

    if offset is not None:
        params["offset"] = offset

    try:

        response = requests.get(
            telegram_url("getUpdates"),
            params=params,
            timeout=10
        )

        print(
            "📡 Telegram HTTP Status：",
            response.status_code
        )

        if not response.ok:

            print(
                "❌ Telegram API 錯誤：",
                response.text
            )

            return []

        data = response.json()

        if not data.get("ok"):

            print(
                "❌ Telegram API 回傳錯誤：",
                data
            )

            return []

        results = data.get(
            "result",
            []
        )

        print(
            f"📨 Telegram 新訊息：{len(results)} 筆"
        )

        return results

    except Exception as e:

        print(
            "❌ Telegram getUpdates 錯誤：",
            e
        )

        return []


# ============================================================
# 解析指令
# ============================================================

def parse_command(text):

    text = text.strip()

    if text in [
        "回測幫助",
        "/help",
        "help"
    ]:

        return {
            "type": "help"
        }

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

        mode = (
            "MULTI"
            if "," in stock_codes
            else "SINGLE"
        )

        return {

            "type": "backtest",

            "mode": mode,

            "stock_codes": stock_codes,

            "start_date": start_date,

            "end_date": end_date
        }

    return {
        "type": "unknown"
    }


# ============================================================
# GitHub Actions
# ============================================================

def trigger_github_backtest(
    mode,
    stock_codes,
    start_date,
    end_date
):

    if not GITHUB_TOKEN:

        print(
            "❌ MY_GITHUB_TOKEN 未設定"
        )

        return False

    url = (
        f"https://api.github.com/repos/"
        f"{GITHUB_OWNER}/"
        f"{GITHUB_REPO}/"
        f"dispatches"
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
            "🐙 GitHub HTTP Status：",
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

        return False

    except Exception as e:

        print(
            "❌ GitHub API 錯誤：",
            e
        )

        return False


# ============================================================
# 處理回測
# ============================================================

def process_backtest(
    chat_id,
    command
):

    mode = command["mode"]

    stock_codes = command["stock_codes"]

    start_date = command["start_date"]

    end_date = command["end_date"]


    # 日期檢查

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

            return

    except Exception:

        send_telegram(
            chat_id,
            """⚠️ 日期格式錯誤。

請使用：

YYYY-MM-DD

例如：

回測2435 2025-10-01 2026-09-30"""
        )

        return


    # 通知使用者

    send_telegram(
        chat_id,
        f"""🚀 已收到回測指令

📌 股票：{stock_codes}
🔎 模式：{mode}
📅 期間：{start_date} ～ {end_date}

⏳ 正在啟動 GitHub Actions...
完成後會收到回測結果。"""
    )


    # 觸發原本回測 Workflow

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
3. GitHub Token 權限
4. repository_dispatch 設定"""
        )


# ============================================================
# 第一次初始化
# ============================================================

def initialize_offset():

    print("")
    print("🧹 第一次初始化 Telegram Offset")
    print("正在清除舊訊息，只保留之後的新指令...")

    updates = get_updates()

    if not updates:

        print(
            "ℹ️ 目前沒有需要清除的舊訊息"
        )

        return None

    last_update_id = updates[-1].get(
        "update_id"
    )

    if last_update_id is None:

        return None

    new_offset = last_update_id + 1

    save_offset(new_offset)

    print(
        f"✅ 舊訊息已略過"
    )

    print(
        f"➡️ 下一次只處理 update_id >= {new_offset}"
    )

    return new_offset


# ============================================================
# 主程式
# ============================================================

def main():

    print("=" * 70)

    print(
        "🤖 Taiwan Stock Radar 6.1 Telegram Trigger"
    )

    print("=" * 70)


    if not TELEGRAM_BOT_TOKEN:

        print(
            "❌ TELEGRAM_BOT_TOKEN 未設定"
        )

        return


    if not GITHUB_TOKEN:

        print(
            "❌ MY_GITHUB_TOKEN 未設定"
        )

        return


    print(
        "✅ Token 設定正常"
    )


    # --------------------------------------------------------
    # 讀取 Offset
    # --------------------------------------------------------

    offset = load_offset()


    # --------------------------------------------------------
    # 第一次執行
    # --------------------------------------------------------

    if offset is None:

        initialize_offset()

        print("")
        print(
            "⏭️ 第一次初始化完成，本次不執行任何回測。"
        )

        return


    print(
        f"📌 目前 Offset：{offset}"
    )


    # --------------------------------------------------------
    # 取得新訊息
    # --------------------------------------------------------

    updates = get_updates(
        offset
    )


    if not updates:

        print(
            "ℹ️ 目前沒有新的 Telegram 指令"
        )

        return


    # --------------------------------------------------------
    # 處理訊息
    # --------------------------------------------------------

    highest_update_id = offset - 1


    for update in updates:

        update_id = update.get(
            "update_id"
        )

        if update_id is None:
            continue


        if update_id > highest_update_id:

            highest_update_id = update_id


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
            f"📩 收到 Telegram：{text}"
        )


        command = parse_command(
            text
        )


        # ----------------------------------------------------
        # 幫助
        # ----------------------------------------------------

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

⏳ 回測完成後會自動把結果傳回 Telegram。"""
            )

            continue


        # ----------------------------------------------------
        # 不明指令
        # ----------------------------------------------------

        if command["type"] == "unknown":

            send_telegram(
                chat_id,
                """⚠️ 我看不懂這個指令。

請輸入：

回測2435

或：

回測幫助"""
            )

            continue


        # ----------------------------------------------------
        # 回測
        # ----------------------------------------------------

        if command["type"] == "backtest":

            process_backtest(
                chat_id,
                command
            )


    # --------------------------------------------------------
    # 保存最新 Offset
    # --------------------------------------------------------

    if highest_update_id >= offset:

        new_offset = highest_update_id + 1

        save_offset(
            new_offset
        )


    print(
        "✅ Telegram Trigger 執行完成"
    )


# ============================================================
# Entry
# ============================================================

if __name__ == "__main__":

    main()
