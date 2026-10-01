# ============================================================
# Taiwan Stock Radar 6.1
# Telegram Backtest Trigger
#
# 功能：
# 1. 自動讀取 Taiwan Stock Radar 6.1 Backtest Telegram Bot
# 2. 支援：
#       回測2435
#       回測 2435
#       回測2330,2454,3563
#       回測 2330, 2454, 3563
#       回測全部
# 3. 不限制股票代號
# 4. 每筆 Telegram 訊息只處理一次
# 5. 使用 GitHub Actions Cache 保存 Offset
# 6. 自動觸發原本 Backtest Workflow
# 7. GitHub Dispatch 成功後只回覆一次
# ============================================================

import os
import re
import requests


# ============================================================
# 基本設定
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    ""
)

MY_GITHUB_TOKEN = os.getenv(
    "MY_GITHUB_TOKEN",
    ""
)

GITHUB_OWNER = os.getenv(
    "GITHUB_OWNER",
    "bj73581028"
)

GITHUB_REPO = os.getenv(
    "GITHUB_REPO",
    "cindy_tw_stock_radar_bot"
)

GITHUB_EVENT_TYPE = os.getenv(
    "GITHUB_EVENT_TYPE",
    "backtest"
)

# GitHub Actions Cache 還原後使用
OFFSET_FILE = "telegram_offset.txt"


# ============================================================
# API
# ============================================================

TELEGRAM_API = (
    f"https://api.telegram.org/bot"
    f"{TELEGRAM_BOT_TOKEN}"
)

GITHUB_DISPATCH_URL = (
    f"https://api.github.com/repos/"
    f"{GITHUB_OWNER}/"
    f"{GITHUB_REPO}/dispatches"
)


# ============================================================
# 標題
# ============================================================

def print_header():

    print("=" * 70)
    print("🤖 Taiwan Stock Radar 6.1 Telegram Trigger")
    print("=" * 70)


# ============================================================
# Offset
# ============================================================

def load_offset():

    if not os.path.exists(OFFSET_FILE):

        print("🆕 找不到 telegram_offset.txt")

        return None

    try:

        with open(
            OFFSET_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            value = f.read().strip()

        if not value:

            return None

        offset = int(value)

        print(
            f"📂 已讀取 Offset：{offset}"
        )

        return offset

    except Exception as e:

        print(
            f"⚠️ Offset 讀取失敗：{e}"
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
            f"❌ Offset 保存失敗：{e}"
        )

        return False


# ============================================================
# Telegram getUpdates
# ============================================================

def get_updates(offset=None):

    url = (
        f"{TELEGRAM_API}/getUpdates"
    )

    params = {
        "timeout": 5
    }

    if offset is not None:

        params["offset"] = offset

    try:

        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        print(
            "📡 Telegram HTTP Status：",
            response.status_code
        )

        if not response.ok:

            print(
                "❌ Telegram API 錯誤："
            )

            print(
                response.text
            )

            return []

        data = response.json()

        if not data.get("ok"):

            print(
                "❌ Telegram API 回傳失敗："
            )

            print(data)

            return []

        return data.get(
            "result",
            []
        )

    except Exception as e:

        print(
            "❌ Telegram getUpdates 錯誤：",
            repr(e)
        )

        return []


# ============================================================
# Telegram 回覆
# ============================================================

def send_telegram_message(
    chat_id,
    message
):

    url = (
        f"{TELEGRAM_API}/sendMessage"
    )

    payload = {
        "chat_id": chat_id,
        "text": message
    }

    try:

        response = requests.post(
            url,
            data=payload,
            timeout=20
        )

        print(
            "📡 Telegram 回覆 HTTP Status：",
            response.status_code
        )

        if response.ok:

            print(
                "✅ Telegram 訊息發送成功"
            )

            return True

        print(
            "❌ Telegram 訊息發送失敗"
        )

        print(
            response.text
        )

    except Exception as e:

        print(
            "❌ Telegram 發送錯誤：",
            repr(e)
        )

    return False


# ============================================================
# 解析股票指令
# ============================================================

def parse_command(text):

    if not text:

        return None

    text = text.strip()

    # --------------------------------------------------------
    # 回測全部
    # --------------------------------------------------------

    if text in [
        "回測全部",
        "回測 全部",
        "回測所有",
        "回測 所有"
    ]:

        return ["ALL"]


    # --------------------------------------------------------
    # 一般股票回測
    #
    # 支援任何 4 碼股票
    #
    # 回測2435
    # 回測 2435
    # 回測2330,2454,3563
    # --------------------------------------------------------

    pattern = (
        r"^回測\s*"
        r"([0-9]{4}"
        r"(?:\s*,\s*[0-9]{4})*)$"
    )

    match = re.match(
        pattern,
        text
    )

    if not match:

        return None

    codes_text = match.group(1)

    codes = [
        x.strip()
        for x in codes_text.split(",")
        if x.strip()
    ]

    # --------------------------------------------------------
    # 去除重複股票
    # --------------------------------------------------------

    unique_codes = []

    for code in codes:

        if code not in unique_codes:

            unique_codes.append(code)

    return unique_codes


# ============================================================
# 模式
# ============================================================

def get_mode(codes):

    if codes == ["ALL"]:

        return "ALL"

    if len(codes) == 1:

        return "SINGLE"

    return "MULTI"


# ============================================================
# GitHub Dispatch
# ============================================================

def trigger_github_backtest(
    mode,
    codes,
    chat_id
):

    if not MY_GITHUB_TOKEN:

        print(
            "❌ 找不到 MY_GITHUB_TOKEN"
        )

        return False

    payload = {

        "event_type":
            GITHUB_EVENT_TYPE,

        "client_payload": {

            "mode":
                mode,

            "stock_codes":
                ",".join(codes),

            "chat_id":
                str(chat_id)
        }
    }

    headers = {

        "Accept":
            "application/vnd.github+json",

        "Authorization":
            f"Bearer {MY_GITHUB_TOKEN}",

        "X-GitHub-Api-Version":
            "2022-11-28"
    }

    try:

        response = requests.post(
            GITHUB_DISPATCH_URL,
            headers=headers,
            json=payload,
            timeout=30
        )

        print(
            "📡 GitHub Dispatch HTTP Status：",
            response.status_code
        )

        if response.status_code == 204:

            print(
                "✅ 原本的 Backtest Workflow 已觸發"
            )

            return True

        print(
            "❌ GitHub Dispatch 失敗"
        )

        print(
            response.text
        )

    except Exception as e:

        print(
            "❌ GitHub Dispatch 錯誤：",
            repr(e)
        )

    return False


# ============================================================
# 處理訊息
# ============================================================

def process_update(update):

    update_id = update.get(
        "update_id"
    )

    message = update.get(
        "message"
    )

    if not message:

        return True

    text = message.get(
        "text",
        ""
    ).strip()

    chat = message.get(
        "chat",
        {}
    )

    chat_id = chat.get(
        "id"
    )

    if not chat_id:

        return True

    print("")
    print("-" * 70)

    print(
        f"📩 收到訊息：{text}"
    )

    print(
        f"🆔 Chat ID：{chat_id}"
    )

    print(
        f"🆔 Update ID：{update_id}"
    )


    # ========================================================
    # 解析
    # ========================================================

    codes = parse_command(text)

    if codes is None:

        print(
            "ℹ️ 不是有效的回測指令，跳過"
        )

        return True


    # ========================================================
    # 模式
    # ========================================================

    mode = get_mode(codes)

    print(
        f"📊 回測模式：{mode}"
    )

    print(
        f"📌 股票代號：{codes}"
    )


    # ========================================================
    # GitHub
    # ========================================================

    github_ok = trigger_github_backtest(
        mode,
        codes,
        chat_id
    )


    # ========================================================
    # 成功
    # ========================================================

    if github_ok:

        if mode == "ALL":

            stock_text = "全部股票"

        else:

            stock_text = ", ".join(codes)

        message_text = (
            "✅ 已收到你的回測指令\n\n"
            f"📊 模式：{mode}\n"
            f"📌 股票：{stock_text}\n\n"
            "🚀 Backtest 已開始執行\n"
            "完成後會回傳一次回測結果。"
        )

        send_telegram_message(
            chat_id,
            message_text
        )

        return True


    # ========================================================
    # 失敗
    # ========================================================

    message_text = (
        "❌ 回測啟動失敗\n\n"
        f"📊 模式：{mode}\n"
        f"📌 股票：{', '.join(codes)}\n\n"
        "請檢查 GitHub Token 或 Workflow 設定。"
    )

    send_telegram_message(
        chat_id,
        message_text
    )

    return False


# ============================================================
# 主程式
# ============================================================

def main():

    print_header()


    # ========================================================
    # Token
    # ========================================================

    if not TELEGRAM_BOT_TOKEN:

        print(
            "❌ TELEGRAM_BOT_TOKEN 未設定"
        )

        return

    print(
        "✅ Token 設定正常"
    )


    # ========================================================
    # Offset
    # ========================================================

    offset = load_offset()


    # ========================================================
    # 第一次執行
    #
    # 第一次不處理舊訊息。
    # 直接從最後一筆之後開始。
    # ========================================================

    if offset is None:

        print(
            "🆕 第一次初始化 Telegram Offset"
        )

        print(
            "📡 正在取得目前 Telegram 訊息..."
        )

        updates = get_updates()

        if updates:

            latest_update_id = max(
                x.get(
                    "update_id",
                    0
                )
                for x in updates
            )

            new_offset = (
                latest_update_id + 1
            )

            save_offset(
                new_offset
            )

            print("")
            print(
                "ℹ️ 已略過目前舊訊息"
            )

            print(
                f"⏭️ 下一筆從 Update ID "
                f"{new_offset} 開始"
            )

        else:

            save_offset(0)

            print(
                "ℹ️ 目前沒有 Telegram 舊訊息"
            )

        return


    # ========================================================
    # 正常取得新訊息
    # ========================================================

    print(
        "📡 正在取得 Telegram 新訊息..."
    )

    print(
        f"🔢 使用 Offset：{offset}"
    )

    updates = get_updates(
        offset=offset
    )

    print(
        f"📨 Telegram 新訊息："
        f"{len(updates)} 筆"
    )


    if not updates:

        print(
            "ℹ️ 目前沒有 Telegram 指令"
        )

        return


    # ========================================================
    # 處理
    # ========================================================

    next_offset = offset

    for update in updates:

        update_id = update.get(
            "update_id"
        )

        if update_id is None:

            continue


        # ----------------------------------------------------
        # 舊訊息
        # ----------------------------------------------------

        if update_id < next_offset:

            continue


        # ----------------------------------------------------
        # 處理
        # ----------------------------------------------------

        success = process_update(
            update
        )


        # ----------------------------------------------------
        # 成功
        # ----------------------------------------------------

        if success:

            next_offset = (
                update_id + 1
            )

            save_offset(
                next_offset
            )


        # ----------------------------------------------------
        # 失敗
        # ----------------------------------------------------

        else:

            print(
                "⚠️ 此筆訊息處理失敗"
            )

            print(
                "⏸️ Offset 暫不更新"
            )

            break


    print("")
    print("=" * 70)
    print(
        "🏁 Telegram Trigger 執行完成"
    )
    print("=" * 70)


# ============================================================
# Entry
# ============================================================

if __name__ == "__main__":

    main()
