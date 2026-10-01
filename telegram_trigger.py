# ============================================================
# Taiwan Stock Radar 6.1
# Telegram Backtest Trigger
#
# 正式版
#
# 功能：
#
# 1. Telegram 指令：
#
#    回測2435
#    回測3563
#    回測2330
#    回測2485
#
#    → SINGLE
#
#
# 2. Telegram 多檔指令：
#
#    回測2435,2330,3563
#
#    → MULTI
#
#
# 3. Telegram 全市場指令：
#
#    回測全部
#
#    → ALL
#
#
# 4. 不限定特定股票
#
#    任何 4 碼股票代號都可以指定
#
#
# 5. 每一筆 Telegram 訊息只處理一次
#
# 6. 使用 telegram_offset.txt
#    避免同一筆訊息重複執行
#
# 7. GitHub Actions 使用 repository_dispatch
#
# 8. GitHub Dispatch 成功後才更新 Offset
#
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


# ============================================================
# Offset 檔案
# ============================================================

OFFSET_FILE = "telegram_offset.txt"


# ============================================================
# GitHub Dispatch API
# ============================================================

GITHUB_DISPATCH_URL = (
    f"https://api.github.com/repos/"
    f"{GITHUB_OWNER}/"
    f"{GITHUB_REPO}/dispatches"
)


# ============================================================
# Telegram API
# ============================================================

TELEGRAM_API = (
    f"https://api.telegram.org/bot"
    f"{TELEGRAM_BOT_TOKEN}"
)


# ============================================================
# 顯示標題
# ============================================================

def print_header():

    print("=" * 70)

    print(
        "🤖 Taiwan Stock Radar 6.1 Telegram Trigger"
    )

    print("=" * 70)


# ============================================================
# 讀取 Offset
# ============================================================

def load_offset():

    if not os.path.exists(
        OFFSET_FILE
    ):

        print(
            "🆕 找不到 telegram_offset.txt"
        )

        return None

    try:

        with open(
            OFFSET_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            content = f.read().strip()

        if not content:

            print(
                "⚠️ Offset 檔案是空的"
            )

            return None

        offset = int(content)

        print(
            f"📂 已讀取 Offset：{offset}"
        )

        return offset

    except Exception as e:

        print(
            f"⚠️ Offset 讀取失敗：{e}"
        )

        return None


# ============================================================
# 儲存 Offset
# ============================================================

def save_offset(offset):

    try:

        with open(
            OFFSET_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                str(offset)
            )

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
        "timeout": 10
    }

    if offset is not None:

        params["offset"] = offset

    try:

        response = requests.get(
            url,
            params=params,
            timeout=30
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

            print(
                data
            )

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
# 解析 Telegram 指令
# ============================================================

def parse_command(text):

    if not text:

        return None

    text = text.strip()


    # ========================================================
    # ALL
    #
    # 支援：
    #
    # 回測全部
    # 回測 全部
    # ========================================================

    if re.fullmatch(
        r"回測\s*全部",
        text
    ):

        return {
            "mode": "ALL",
            "codes": []
        }


    # ========================================================
    # 股票指令
    #
    # 支援：
    #
    # 回測2435
    # 回測 2435
    #
    # 回測2435,2330
    # 回測 2435, 2330
    #
    # 不限制特定股票
    # ========================================================

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


    if not codes:

        return None


    # ========================================================
    # 去除同一指令內重複股票
    #
    # 例如：
    #
    # 回測2435,2435,3563
    #
    # 變成：
    #
    # 2435,3563
    # ========================================================

    unique_codes = []


    for code in codes:

        if code not in unique_codes:

            unique_codes.append(
                code
            )


    # ========================================================
    # 判斷模式
    # ========================================================

    if len(unique_codes) == 1:

        mode = "SINGLE"

    else:

        mode = "MULTI"


    return {
        "mode": mode,
        "codes": unique_codes
    }


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
# 觸發 GitHub Actions Backtest
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


    # ========================================================
    # ALL 模式
    # ========================================================

    if mode == "ALL":

        stock_codes = ""


    else:

        stock_codes = ",".join(
            codes
        )


    # ========================================================
    # GitHub repository_dispatch
    # ========================================================

    payload = {

        "event_type":
            GITHUB_EVENT_TYPE,

        "client_payload": {

            "mode":
                mode,

            "stock_codes":
                stock_codes,

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


        # ====================================================
        # 204 = repository_dispatch 成功
        # ====================================================

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
# 處理單筆 Telegram 訊息
# ============================================================

def process_update(update):

    update_id = update.get(
        "update_id"
    )


    message = update.get(
        "message"
    )


    # ========================================================
    # 沒有 message
    # ========================================================

    if not message:

        return True


    # ========================================================
    # 取得文字
    # ========================================================

    text = message.get(
        "text",
        ""
    ).strip()


    # ========================================================
    # Chat
    # ========================================================

    chat = message.get(
        "chat",
        {}
    )


    chat_id = chat.get(
        "id"
    )


    if not chat_id:

        print(
            "⚠️ 找不到 Chat ID"
        )

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
    # 解析指令
    # ========================================================

    command = parse_command(
        text
    )


    # ========================================================
    # 無效指令
    # ========================================================

    if command is None:

        print(
            "ℹ️ 不是有效的回測指令，跳過"
        )

        return True


    # ========================================================
    # 取得模式
    # ========================================================

    mode = command["mode"]

    codes = command["codes"]


    print(
        f"📊 回測模式：{mode}"
    )


    if mode == "ALL":

        print(
            "📌 股票：全市場"
        )

    else:

        print(
            f"📌 股票代號：{codes}"
        )


    # ========================================================
    # 觸發 GitHub
    # ========================================================

    github_ok = (
        trigger_github_backtest(
            mode,
            codes,
            chat_id
        )
    )


    # ========================================================
    # GitHub 成功
    # ========================================================

    if github_ok:


        if mode == "ALL":

            stock_text = (
                "🌐 全市場"
            )

        else:

            stock_text = (
                ", ".join(codes)
            )


        message_text = (
            "✅ 已收到你的回測指令\n\n"
            f"📊 模式：{mode}\n"
            f"📌 股票：{stock_text}\n\n"
            "🚀 Backtest 已開始執行\n"
            "完成後會回傳回測結果。"
        )


        send_telegram_message(
            chat_id,
            message_text
        )


        return True


    # ========================================================
    # GitHub 失敗
    # ========================================================

    message_text = (
        "❌ 回測啟動失敗\n\n"
        f"📊 模式：{mode}\n"
    )


    if mode == "ALL":

        message_text += (
            "📌 股票：全市場\n\n"
        )

    else:

        message_text += (
            f"📌 股票："
            f"{', '.join(codes)}\n\n"
        )


    message_text += (
        "請檢查 GitHub Token 或 "
        "Workflow 設定。"
    )


    send_telegram_message(
        chat_id,
        message_text
    )


    # ========================================================
    # GitHub 失敗
    #
    # 不更新 Offset
    #
    # 下一次可以重新嘗試
    # ========================================================

    return False


# ============================================================
# 主程式
# ============================================================

def main():

    print_header()


    # ========================================================
    # Token 檢查
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
    # 沒有 Offset：
    #
    # 不處理舊訊息
    #
    # 直接把目前最後一筆 Update ID + 1
    # 當成下一次開始的位置
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

                update.get(
                    "update_id",
                    0
                )

                for update in updates

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


            print(
                "ℹ️ 目前沒有 Telegram 訊息"
            )


            save_offset(0)


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


    # ========================================================
    # 沒有新訊息
    # ========================================================

    if not updates:

        print(
            "ℹ️ 目前沒有 Telegram 指令"
        )

        return


    # ========================================================
    # 逐筆處理
    # ========================================================

    next_offset = offset


    for update in updates:


        update_id = update.get(
            "update_id"
        )


        if update_id is None:

            continue


        # ====================================================
        # 跳過已經處理過的訊息
        # ====================================================

        if update_id < next_offset:

            print(
                f"⏭️ 跳過已處理 Update ID："
                f"{update_id}"
            )

            continue


        # ====================================================
        # 處理訊息
        # ====================================================

        success = process_update(
            update
        )


        # ====================================================
        # 成功
        #
        # Update ID + 1
        #
        # 防止下次再次執行
        # ====================================================

        if success:


            next_offset = (
                update_id + 1
            )


            save_offset(
                next_offset
            )


        # ====================================================
        # GitHub 失敗
        #
        # 不更新 Offset
        #
        # 下次重新嘗試
        # ====================================================

        else:


            print("")


            print(
                "⚠️ 此筆訊息未成功處理"
            )


            print(
                "⏸️ 不更新 Offset，"
                "下次可以重新嘗試"
            )


            break


    print("")

    print("=" * 70)


    print(
        "🏁 Telegram Trigger 執行完成"
    )


    print("=" * 70)


# ============================================================
# 程式入口
# ============================================================

if __name__ == "__main__":

    main()
