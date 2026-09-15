import os
import requests
import pandas as pd
from datetime import datetime, timedelta

# ==========================================
# Telegram
# ==========================================

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    raise RuntimeError("找不到 Telegram Secret")


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    response = requests.post(url, data=data, timeout=30)
    response.raise_for_status()


# ==========================================
# FinMind
# ==========================================

API_URL = "https://api.finmindtrade.com/api/v4/data"


def get_stock_data(stock_id, start_date):

    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": start_date
    }

    response = requests.get(
        API_URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if "data" not in result:
        return pd.DataFrame()

    return pd.DataFrame(result["data"])


# ==========================================
# 股票清單
#
# 這一版先使用較完整的熱門股清單，
# 確認穩定後再擴充成全上市櫃。
# ==========================================

STOCKS = [
    "1101", "1102", "1216", "1301", "1303",
    "1326", "1402", "1476", "1503", "1513",
    "1519", "1605", "1707", "1717", "1722",
    "2002", "2301", "2303", "2308", "2317",
    "2327", "2330", "2344", "2353", "2356",
    "2376", "2379", "2382", "2383", "2385",
    "2395", "2408", "2412", "2454", "2474",
    "2476", "2481", "2498", "2603", "2609",
    "2615", "2618", "2637", "2801", "2881",
    "2882", "2883", "2884", "2885", "2886",
    "2887", "2888", "2889", "2890", "2891",
    "2892", "2912", "3008", "3017", "3023",
    "3034", "3037", "3044", "3231", "3443",
    "3481", "3661", "3665", "3711", "4904",
    "4938", "5347", "5483", "5871", "5876",
    "6125", "6239", "6271", "6690", "8046",
    "8069", "8150", "8358"
]


# ==========================================
# 計算飆股分數
# ==========================================

def calculate_score(df):

    if len(df) < 25:
        return None

    df = df.copy()

    numeric_columns = [
        "close",
        "Trading_Volume"
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df.dropna(
        subset=["close", "Trading_Volume"]
    )

    if len(df) < 25:
        return None

    # -----------------------------
    # 均線
    # -----------------------------

    df["MA5"] = df["close"].rolling(5).mean()
    df["MA20"] = df["close"].rolling(20).mean()

    latest = df.iloc[-1]

    price = float(latest["close"])
    volume = float(latest["Trading_Volume"])

    prev_close = float(df["close"].iloc[-2])

    if prev_close <= 0:
        return None

    change_pct = (
        price / prev_close - 1
    ) * 100

    # -----------------------------
    # 成交量
    # -----------------------------

    avg5_volume = (
        df["Trading_Volume"]
        .iloc[-6:-1]
        .mean()
    )

    avg20_volume = (
        df["Trading_Volume"]
        .iloc[-21:-1]
        .mean()
    )

    if avg5_volume <= 0:
        return None

    volume_ratio_5 = (
        volume / avg5_volume
    )

    volume_ratio_20 = (
        volume / avg20_volume
        if avg20_volume > 0
        else 0
    )

    score = 0
    reasons = []

    # =================================
    # 量能
    # =================================

    if volume_ratio_5 >= 2:
        score += 15
        reasons.append("5日爆量")

    elif volume_ratio_5 >= 1.5:
        score += 8
        reasons.append("量能放大")

    if volume_ratio_20 >= 1.5:
        score += 5
        reasons.append("20日量能放大")

    # =================================
    # 漲幅
    # =================================

    if 3 <= change_pct <= 9:
        score += 10
        reasons.append(
            f"漲幅{change_pct:.1f}%"
        )

    # 避免追太高
    if change_pct > 9:
        score -= 15
        reasons.append("單日漲幅過高")

    # =================================
    # 20日突破
    # =================================

    high20 = (
        df["close"]
        .iloc[-21:-1]
        .max()
    )

    if price > high20:
        score += 10
        reasons.append("突破20日高")

    # =================================
    # MA20
    # =================================

    ma20 = float(latest["MA20"])
    ma5 = float(latest["MA5"])

    if price > ma20:
        score += 5
        reasons.append("站上MA20")

    if ma5 > ma20:
        score += 5
        reasons.append("MA5>MA20")

    # =================================
    # MA20 趨勢
    # =================================

    if len(df) >= 26:

        old_ma20 = (
            df["MA20"].iloc[-6]
        )

        if ma20 > old_ma20:
            score += 5
            reasons.append("MA20上升")

    # =================================
    # 接近52週高
    # =================================

    if len(df) >= 250:

        high52 = (
            df["close"]
            .iloc[-250:]
            .max()
        )

        distance = (
            high52 - price
        ) / high52

        if distance <= 0.15:
            score += 5
            reasons.append("接近52週高")

    # =================================
    # 短期過熱過濾
    # =================================

    if len(df) >= 21:

        price20 = (
            df["close"].iloc[-21]
        )

        gain20 = (
            price / price20 - 1
        ) * 100

        if gain20 > 25:
            score -= 10
            reasons.append("20日漲幅過熱")

    return {
        "score": score,
        "price": price,
        "change": change_pct,
        "volume_ratio_5": volume_ratio_5,
        "volume_ratio_20": volume_ratio_20,
        "reasons": reasons
    }


# ==========================================
# 主程式
# ==========================================

def main():

    print("開始執行台股飆股雷達")

    end_date = datetime.now()

    start_date = (
        end_date - timedelta(days=400)
    )

    results = []

    for stock_id in STOCKS:

        try:

            print(
                f"掃描 {stock_id}"
            )

            df = get_stock_data(
                stock_id,
                start_date.strftime("%Y-%m-%d")
            )

            if df.empty:
                continue

            result = calculate_score(df)

            if result is None:
                continue

            # 至少50分才進入候選名單

            if result["score"] >= 50:

                results.append({
                    "stock": stock_id,
                    **result
                })

        except Exception as e:

            print(
                f"{stock_id} 發生錯誤：{e}"
            )

    # ==================================
    # 排序
    # ==================================

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # ==================================
    # Telegram
    # ==================================

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    message = (
        "<b>🚀 台股飆股雷達 2.0</b>\n"
        f"📅 {today}\n"
        "━━━━━━━━━━━━━━\n"
    )

    if not results:

        message += (
            "\n📭 今日沒有符合條件的候選股。\n\n"
            "市場目前可能尚未出現明確的量價發動訊號。"
        )

    else:

        message += (
            f"\n🔥 今日候選股："
            f"{len(results)} 檔\n\n"
        )

        for i, stock in enumerate(
            results[:10],
            1
        ):

            message += (
                f"<b>{i}. {stock['stock']}</b> "
                f"⭐ {stock['score']}分\n"
            )

            message += (
                f"價格：{stock['price']:.2f}  "
                f"漲幅：{stock['change']:.2f}%\n"
            )

            message += (
                f"5日量比："
                f"{stock['volume_ratio_5']:.2f}倍\n"
            )

            if stock["reasons"]:

                message += (
                    "訊號："
                    + "、".join(
                        stock["reasons"]
                    )
                    + "\n"
                )

            message += "\n"

    message += (
        "━━━━━━━━━━━━━━\n"
        "⚠️ 僅供選股研究參考，"
        "不代表買進訊號。"
    )

    send_telegram(message)

    print("Telegram 通知完成")


if __name__ == "__main__":
    main()
