import os
import requests
import pandas as pd
from datetime import datetime, timedelta

# =========================
# Telegram 設定
# =========================
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    response = requests.post(url, data=data)
    response.raise_for_status()


# =========================
# FinMind API
# =========================
API_URL = "https://api.finmindtrade.com/api/v4/data"


def get_stock_data(stock_id, start_date):
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": start_date,
    }

    response = requests.get(API_URL, params=params)
    response.raise_for_status()

    data = response.json()

    if "data" not in data:
        return pd.DataFrame()

    return pd.DataFrame(data["data"])


# =========================
# 股票清單
# 第一版先掃描常見熱門股票
# =========================
STOCKS = [
    "2330", "2317", "2454", "2382", "3231",
    "3017", "3661", "3665", "3037", "2308",
    "2344", "3711", "2379", "3034", "3443",
    "2481", "3675", "6690", "8358", "2351",
    "2368", "2408", "3481", "2376", "2603",
    "2615", "2881", "2882", "2891", "2892"
]


# =========================
# 飆股評分
# =========================
def calculate_score(df):

    if len(df) < 25:
        return None

    df = df.copy()

    df["close"] = pd.to_numeric(df["close"])
    df["Trading_Volume"] = pd.to_numeric(df["Trading_Volume"])

    df["MA5"] = df["close"].rolling(5).mean()
    df["MA20"] = df["close"].rolling(20).mean()

    latest = df.iloc[-1]

    price = latest["close"]
    volume = latest["Trading_Volume"]

    avg5_volume = df["Trading_Volume"].iloc[-6:-1].mean()
    avg20_volume = df["Trading_Volume"].iloc[-21:-1].mean()

    score = 0
    reasons = []

    # 1. 今日量 / 5日均量 >= 2倍
    if avg5_volume > 0 and volume / avg5_volume >= 2:
        score += 15
        reasons.append("爆量")

    # 2. 今日量 / 20日均量 >= 1.5倍
    if avg20_volume > 0 and volume / avg20_volume >= 1.5:
        score += 5
        reasons.append("量能放大")

    # 3. 今日漲幅
    prev_close = df["close"].iloc[-2]

    change_pct = (price / prev_close - 1) * 100

    if 3 <= change_pct <= 9:
        score += 10
        reasons.append(f"漲幅 {change_pct:.1f}%")

    # 4. 突破20日高點
    high20 = df["close"].iloc[-21:-1].max()

    if price > high20:
        score += 10
        reasons.append("突破20日高")

    # 5. 站上MA20
    if price > latest["MA20"]:
        score += 5
        reasons.append("站上MA20")

    # 6. MA5 > MA20
    if latest["MA5"] > latest["MA20"]:
        score += 5
        reasons.append("MA5>MA20")

    # 7. MA20上升
    if len(df) >= 21:
        old_ma20 = df["MA20"].iloc[-6]

        if latest["MA20"] > old_ma20:
            score += 5
            reasons.append("MA20上升")

    # 8. 距離52週高點15%以內
    if len(df) >= 250:
        high52 = df["close"].iloc[-250:].max()

        distance = (high52 - price) / high52

        if distance <= 0.15:
            score += 5
            reasons.append("接近52週高")

    return {
        "score": score,
        "price": price,
        "change": change_pct,
        "volume_ratio": volume / avg5_volume if avg5_volume else 0,
        "reasons": reasons
    }


# =========================
# 主程式
# =========================
def main():

    end_date = datetime.now()
    start_date = end_date - timedelta(days=400)

    results = []

    for stock_id in STOCKS:

        try:

            df = get_stock_data(
                stock_id,
                start_date.strftime("%Y-%m-%d")
            )

            if df.empty:
                continue

            result = calculate_score(df)

            if result is None:
                continue

            if result["score"] >= 50:

                results.append({
                    "stock": stock_id,
                    **result
                })

        except Exception as e:

            print(f"{stock_id} 發生錯誤：{e}")

    # 分數由高到低
    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # =========================
    # Telegram 訊息
    # =========================

    today = datetime.now().strftime("%Y-%m-%d")

    message = f"<b>🚀 台股飆股雷達</b>\n"
    message += f"📅 {today}\n\n"

    if not results:

        message += "今日沒有符合條件的股票。\n"
        message += "建議：等待量價結構轉強。"

    else:

        message += f"🔥 共發現 {len(results)} 檔候選股\n\n"

        for i, stock in enumerate(results[:10], 1):

            message += (
                f"<b>{i}. {stock['stock']}</b> "
                f"⭐ {stock['score']}分\n"
            )

            message += (
                f"價格：{stock['price']:.2f} "
                f"漲幅：{stock['change']:.2f}%\n"
            )

            message += (
                f"量比：{stock['volume_ratio']:.2f}倍\n"
            )

            if stock["reasons"]:
                message += (
                    "條件：" +
                    "、".join(stock["reasons"]) +
                    "\n"
                )

            message += "\n"

    send_telegram(message)

    print("Telegram 通知已發送")


if __name__ == "__main__":
    main()
