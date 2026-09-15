import os
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


# =========================
# Telegram
# =========================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    response = requests.post(url, data=data, timeout=30)
    response.raise_for_status()


# =========================
# 股票清單
# =========================
STOCKS = [
    "2330.TW", "2317.TW", "2454.TW", "2308.TW",
    "2382.TW", "3231.TW", "3037.TW", "3661.TW",
    "3035.TW", "2376.TW", "2356.TW", "2377.TW",
    "2408.TW", "2344.TW", "3711.TW", "2303.TW",
    "3034.TW", "2379.TW", "2409.TW", "2449.TW",
    "2481.TW", "6690.TW", "3675.TW", "8358.TW",
    "2351.TW", "2458.TW", "2368.TW", "2327.TW",
    "3006.TW", "3017.TW", "3324.TW", "3443.TW",
    "3665.TW", "4966.TW", "5274.TW", "6239.TW",
    "6515.TW", "6643.TW", "6789.TW", "3443.TW",
    "2383.TW", "3211.TW", "3702.TW", "2404.TW",
    "2618.TW", "2610.TW", "2603.TW", "2609.TW",
    "2002.TW", "1301.TW", "1303.TW", "1216.TW",
    "1101.TW", "1402.TW", "2881.TW", "2882.TW",
    "2884.TW", "2886.TW", "2891.TW", "2892.TW",
    "2883.TW", "5871.TW", "5880.TW", "2880.TW"
]


# =========================
# 飆股評分
# =========================
def calculate_score(df):

    if len(df) < 60:
        return None

    df = df.dropna().copy()

    close = float(df["Close"].iloc[-1])
    previous_close = float(df["Close"].iloc[-2])

    change_pct = (close / previous_close - 1) * 100

    volume = float(df["Volume"].iloc[-1])

    avg5 = df["Volume"].iloc[-6:-1].mean()
    avg20 = df["Volume"].iloc[-21:-1].mean()

    if avg5 <= 0 or avg20 <= 0:
        return None

    volume_ratio_5 = volume / avg5
    volume_ratio_20 = volume / avg20

    ma5 = df["Close"].rolling(5).mean().iloc[-1]
    ma20 = df["Close"].rolling(20).mean().iloc[-1]

    ma20_previous = df["Close"].rolling(20).mean().iloc[-2]

    high20 = df["Close"].iloc[-21:-1].max()

    high252 = df["Close"].iloc[-252:].max()

    price20 = df["Close"].iloc[-21]

    gain20 = (close / price20 - 1) * 100

    score = 0
    reasons = []

    # 成交量
    if volume_ratio_5 >= 2:
        score += 15
        reasons.append("5日量爆2倍")
    elif volume_ratio_5 >= 1.5:
        score += 8
        reasons.append("5日量增")

    if volume_ratio_20 >= 1.5:
        score += 5
        reasons.append("20日量增")

    # 漲幅
    if 3 <= change_pct <= 9:
        score += 10
        reasons.append("強勢上漲")

    elif change_pct > 9:
        score -= 15
        reasons.append("漲幅過大")

    # 突破20日高
    if close > high20:
        score += 10
        reasons.append("突破20日高")

    # 均線
    if close > ma20:
        score += 5
        reasons.append("站上MA20")

    if ma5 > ma20:
        score += 5
        reasons.append("MA5>MA20")

    if ma20 > ma20_previous:
        score += 5
        reasons.append("MA20上升")

    # 接近52週高
    if high252 > 0:
        distance = (high252 - close) / high252 * 100

        if distance <= 15:
            score += 5
            reasons.append("接近52週高")

    # 避免短期漲太多
    if gain20 > 25:
        score -= 10
        reasons.append("20日漲幅過大")

    return {
        "score": score,
        "close": close,
        "change_pct": change_pct,
        "volume_ratio_5": volume_ratio_5,
        "volume_ratio_20": volume_ratio_20,
        "gain20": gain20,
        "reasons": reasons
    }


# =========================
# 主程式
# =========================
def main():

    today = datetime.now()

    results = []

    print("🚀 開始執行飆股雷達")

    for ticker in STOCKS:

        try:

            print(f"分析 {ticker}")

            df = yf.download(
                ticker,
                period="1y",
                interval="1d",
                auto_adjust=False,
                progress=False
            )

            if df.empty:
                continue

            # yfinance 有時會產生 MultiIndex
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            required = ["Close", "Volume"]

            if not all(x in df.columns for x in required):
                continue

            result = calculate_score(df)

            if result is None:
                continue

            if result["score"] < 50:
                continue

            results.append({
                "ticker": ticker,
                **result
            })

        except Exception as e:

            print(f"{ticker} 發生錯誤：{e}")

    # =========================
    # 排序
    # =========================
    results.sort(
        key=lambda x: (
            x["score"],
            x["volume_ratio_5"]
        ),
        reverse=True
    )

    # =========================
    # Telegram
    # =========================
    lines = []

    lines.append(
        f"🚨 飆股雷達 3.0｜{today.strftime('%Y/%m/%d')}"
    )

    lines.append(
        f"📊 本次掃描：{len(STOCKS)} 檔"
    )

    lines.append("")

    if not results:

        lines.append(
            "今日沒有符合條件的股票。"
        )

    else:

        for rank, item in enumerate(results[:10], 1):

            ticker = item["ticker"].replace(".TW", "")

            score = item["score"]
            change = item["change_pct"]
            volume_ratio = item["volume_ratio_5"]

            lines.append(
                f"{rank}. {ticker}"
            )

            lines.append(
                f"⭐ {score}分｜"
                f"📈 {change:+.2f}%｜"
                f"🔥 5日量 {volume_ratio:.1f}倍"
            )

            lines.append(
                "📌 " + "、".join(item["reasons"])
            )

            if change >= 8:
                status = "🔴 避免追高"
            elif "突破20日高" in item["reasons"]:
                status = "🟡 突破後觀察"
            else:
                status = "🟢 等待拉回"

            lines.append(
                f"➡️ {status}"
            )

            lines.append("")

    lines.append(
        "⚠️ 雷達僅供選股參考，不代表買進建議。"
    )

    message = "\n".join(lines)

    send_telegram(message)

    print(message)


if __name__ == "__main__":
    main()
