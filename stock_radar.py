import os
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta


# ============================================================
# Telegram 設定
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


# ============================================================
# 台股股票池
#
# 先使用主要上市／櫃股票。
# 後續可以再擴充完整股票清單。
# ============================================================

STOCKS = [
    "1101.TW", "1216.TW", "1301.TW", "1303.TW",
    "1402.TW", "2002.TW", "2301.TW", "2303.TW",
    "2308.TW", "2317.TW", "2327.TW", "2330.TW",
    "2344.TW", "2352.TW", "2353.TW", "2356.TW",
    "2357.TW", "2360.TW", "2368.TW", "2376.TW",
    "2377.TW", "2379.TW", "2382.TW", "2383.TW",
    "2385.TW", "2395.TW", "2408.TW", "2409.TW",
    "2412.TW", "2421.TW", "2439.TW", "2449.TW",
    "2454.TW", "2458.TW", "2474.TW", "2476.TW",
    "2481.TW", "2492.TW", "3006.TW", "3017.TW",
    "3034.TW", "3035.TW", "3037.TW", "3044.TW",
    "3231.TW", "3305.TW", "3324.TW", "3443.TW",
    "3481.TW", "3533.TW", "3661.TW", "3675.TW",
    "3702.TW", "3711.TW", "4904.TW", "4938.TW",
    "4966.TW", "5274.TW", "5269.TW", "5483.TW",
    "6239.TW", "6415.TW", "6515.TW", "6643.TW",
    "6690.TW", "6789.TW", "8046.TW", "8048.TW",
    "8358.TW", "8454.TW",

    "2603.TW", "2609.TW", "2610.TW", "2618.TW",
    "2707.TW", "2727.TW",

    "2880.TW", "2881.TW", "2882.TW", "2883.TW",
    "2884.TW", "2885.TW", "2886.TW", "2887.TW",
    "2888.TW", "2889.TW", "2890.TW", "2891.TW",
    "2892.TW",

    "5880.TW", "5871.TW"
]


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:
        raise Exception("找不到 TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID:
        raise Exception("找不到 TELEGRAM_CHAT_ID")

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        },
        timeout=30
    )

    response.raise_for_status()


# ============================================================
# 下載股票資料
# ============================================================

def download_stock(ticker):

    try:

        df = yf.download(
            ticker,
            period="1y",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False
        )

        if df is None or df.empty:
            return None

        # yfinance 某些版本可能回傳 MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        for column in required:
            if column not in df.columns:
                return None

        df = df[required].copy()

        df = df.dropna()

        return df

    except Exception as e:

        print(f"{ticker} 下載失敗：{e}")

        return None


# ============================================================
# 計算飆股分數
# ============================================================

def calculate_score(df):

    if len(df) < 60:
        return None

    close = float(df["Close"].iloc[-1])

    previous_close = float(df["Close"].iloc[-2])

    if previous_close <= 0:
        return None

    change_pct = (
        close / previous_close - 1
    ) * 100


    # --------------------------------------------------------
    # 成交量
    # --------------------------------------------------------

    volume_today = float(
        df["Volume"].iloc[-1]
    )

    avg_volume_5 = float(
        df["Volume"].iloc[-6:-1].mean()
    )

    avg_volume_20 = float(
        df["Volume"].iloc[-21:-1].mean()
    )

    if avg_volume_5 <= 0:
        return None

    if avg_volume_20 <= 0:
        return None

    volume_ratio_5 = (
        volume_today / avg_volume_5
    )

    volume_ratio_20 = (
        volume_today / avg_volume_20
    )


    # --------------------------------------------------------
    # 均線
    # --------------------------------------------------------

    ma5 = (
        df["Close"]
        .rolling(5)
        .mean()
        .iloc[-1]
    )

    ma20 = (
        df["Close"]
        .rolling(20)
        .mean()
        .iloc[-1]
    )

    ma20_previous = (
        df["Close"]
        .rolling(20)
        .mean()
        .iloc[-2]
    )


    # --------------------------------------------------------
    # 20日突破
    # --------------------------------------------------------

    high20_previous = (
        df["High"]
        .iloc[-21:-1]
        .max()
    )

    breakout20 = close > high20_previous


    # --------------------------------------------------------
    # 52週高點
    # --------------------------------------------------------

    high252 = (
        df["High"]
        .iloc[-252:]
        .max()
    )

    if high252 > 0:

        distance_from_high = (
            (high252 - close)
            / high252
            * 100
        )

    else:

        distance_from_high = 100


    # --------------------------------------------------------
    # 20日漲幅
    # --------------------------------------------------------

    close_20_days_ago = (
        df["Close"].iloc[-21]
    )

    if close_20_days_ago <= 0:
        return None

    gain20 = (
        close / close_20_days_ago - 1
    ) * 100


    # --------------------------------------------------------
    # 成交金額
    # --------------------------------------------------------

    turnover = (
        close * volume_today
    )


    # ========================================================
    # 評分
    # ========================================================

    score = 0

    reasons = []


    # --------------------------------------------------------
    # 1. 5日量能
    # --------------------------------------------------------

    if volume_ratio_5 >= 3:

        score += 20
        reasons.append("5日量爆3倍")

    elif volume_ratio_5 >= 2:

        score += 15
        reasons.append("5日量爆2倍")

    elif volume_ratio_5 >= 1.5:

        score += 8
        reasons.append("5日量增")


    # --------------------------------------------------------
    # 2. 20日量能
    # --------------------------------------------------------

    if volume_ratio_20 >= 2:

        score += 8
        reasons.append("20日量爆2倍")

    elif volume_ratio_20 >= 1.5:

        score += 5
        reasons.append("20日量增")


    # --------------------------------------------------------
    # 3. 今日漲幅
    # --------------------------------------------------------

    if 3 <= change_pct <= 7:

        score += 12
        reasons.append("強勢上漲")

    elif 7 < change_pct <= 9:

        score += 8
        reasons.append("高檔強勢")

    elif change_pct > 9:

        score -= 15
        reasons.append("漲幅過大")

    elif change_pct < -3:

        score -= 10
        reasons.append("今日轉弱")


    # --------------------------------------------------------
    # 4. 突破20日高
    # --------------------------------------------------------

    if breakout20:

        score += 12
        reasons.append("突破20日高")


    # --------------------------------------------------------
    # 5. 站上MA20
    # --------------------------------------------------------

    if close > ma20:

        score += 5
        reasons.append("站上MA20")


    # --------------------------------------------------------
    # 6. MA5 > MA20
    # --------------------------------------------------------

    if ma5 > ma20:

        score += 5
        reasons.append("MA5>MA20")


    # --------------------------------------------------------
    # 7. MA20上升
    # --------------------------------------------------------

    if ma20 > ma20_previous:

        score += 5
        reasons.append("MA20上升")


    # --------------------------------------------------------
    # 8. 接近52週高點
    # --------------------------------------------------------

    if distance_from_high <= 15:

        score += 5
        reasons.append("接近52週高")


    # --------------------------------------------------------
    # 9. 避免20日漲幅過大
    # --------------------------------------------------------

    if gain20 > 30:

        score -= 15
        reasons.append("20日漲幅過大")

    elif gain20 > 25:

        score -= 8
        reasons.append("20日漲幅偏大")


    # --------------------------------------------------------
    # 10. 成交金額
    # --------------------------------------------------------

    # 3000萬元以上
    if turnover >= 30_000_000:

        score += 3
        reasons.append("成交金額達3000萬")

    # 3億元以上
    if turnover >= 300_000_000:

        score += 5
        reasons.append("成交金額達3億")


    # --------------------------------------------------------
    # 操作狀態
    # --------------------------------------------------------

    if change_pct >= 8:

        status = "🔴 避免追高"

    elif breakout20 and volume_ratio_5 >= 2:

        status = "🟡 突破＋量增，觀察拉回"

    elif close > ma20 and ma5 > ma20:

        status = "🟢 多頭排列，等待切入"

    else:

        status = "⚪ 持續觀察"


    return {
        "score": score,
        "close": close,
        "change_pct": change_pct,
        "volume_ratio_5": volume_ratio_5,
        "volume_ratio_20": volume_ratio_20,
        "breakout20": breakout20,
        "distance_from_high": distance_from_high,
        "gain20": gain20,
        "turnover": turnover,
        "status": status,
        "reasons": reasons
    }


# ============================================================
# 主程式
# ============================================================

def main():

    today = datetime.now()

    print("=" * 60)
    print("🚀 台股飆股雷達 3.0")
    print("=" * 60)

    results = []

    total = len(STOCKS)

    print(f"股票池：{total} 檔")


    # ========================================================
    # 逐檔掃描
    # ========================================================

    for index, ticker in enumerate(STOCKS, 1):

        print(
            f"[{index}/{total}] 分析 {ticker}"
        )

        df = download_stock(ticker)

        if df is None:
            continue

        result = calculate_score(df)

        if result is None:
            continue

        # 只留下50分以上
        if result["score"] < 50:
            continue

        results.append({
            "ticker": ticker,
            **result
        })


    # ========================================================
    # 排名
    # ========================================================

    results.sort(
        key=lambda x: (
            x["score"],
            x["volume_ratio_5"],
            x["change_pct"]
        ),
        reverse=True
    )


    # ========================================================
    # Telegram
    # ========================================================

    lines = []

    lines.append(
        f"🚨 台股飆股雷達 3.0"
    )

    lines.append(
        f"📅 {today.strftime('%Y/%m/%d %H:%M')}"
    )

    lines.append(
        f"🔎 掃描股票：{total} 檔"
    )

    lines.append(
        f"🎯 符合50分以上：{len(results)} 檔"
    )

    lines.append("")


    if not results:

        lines.append(
            "⚪ 今日沒有符合條件的股票。"
        )

    else:

        for rank, item in enumerate(
            results[:10],
            1
        ):

            ticker = (
                item["ticker"]
                .replace(".TW", "")
                .replace(".TWO", "")
            )

            score = item["score"]

            change = item["change_pct"]

            volume5 = item["volume_ratio_5"]

            volume20 = item["volume_ratio_20"]

            turnover = item["turnover"]

            turnover_million = (
                turnover / 1_000_000
            )

            lines.append(
                f"🏆 第{rank}名｜{ticker}"
            )

            lines.append(
                f"⭐ {score}分"
                f"｜📈 {change:+.2f}%"
            )

            lines.append(
                f"🔥 5日量 {volume5:.1f}倍"
                f"｜20日量 {volume20:.1f}倍"
            )

            lines.append(
                f"💰 成交金額 "
                f"{turnover_million:.0f}百萬"
            )

            lines.append(
                f"📌 "
                + "、".join(item["reasons"])
            )

            lines.append(
                f"➡️ {item['status']}"
            )

            lines.append("")


    lines.append(
        "⚠️ 本雷達為技術面選股工具，"
        "僅供研究參考，不代表買進建議。"
    )

    message = "\n".join(lines)

    print("\n" + message)

    send_telegram(message)

    print("\n✅ Telegram 發送成功")


# ============================================================
# 執行
# ============================================================

if __name__ == "__main__":
    main()
