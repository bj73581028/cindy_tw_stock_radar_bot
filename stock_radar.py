import os
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# ============================================================
# Telegram
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


# ============================================================
# 基本設定
# ============================================================

MIN_SCORE = 60
TOP_N = 15

# 台股主要股票池
# .TW = 上市
# .TWO = 上櫃
#
# 先使用大型及熱門股票建立穩定版本，
# 後續可再擴充完整市場股票清單。
STOCKS = [
    # 半導體
    "2330.TW", "2454.TW", "2303.TW", "2379.TW",
    "2408.TW", "3034.TW", "3035.TW", "3044.TW",
    "3711.TW", "3661.TW", "4966.TW", "5274.TW",
    "6488.TWO", "6515.TW", "6643.TW", "6690.TW",
    "2449.TW", "6770.TW",

    # AI / 電腦 / 伺服器
    "2317.TW", "2382.TW", "2356.TW", "2357.TW",
    "3231.TW", "2376.TW", "2377.TW", "2395.TW",
    "2308.TW", "3017.TW", "6669.TW", "2383.TW",
    "3706.TW", "2324.TW", "2353.TW",

    # IC / 電子零組件
    "2301.TW", "2327.TW", "2344.TW", "2368.TW",
    "2379.TW", "2385.TW", "2395.TW", "2409.TW",
    "2458.TW", "2474.TW", "2476.TW", "2481.TW",
    "2492.TW", "3006.TW", "3037.TW", "3305.TW",
    "3324.TW", "3443.TW", "3533.TW", "3702.TW",
    "4938.TW", "5483.TWO", "6239.TW", "8046.TW",
    "8048.TW", "8358.TW",

    # 網通 / 通訊
    "2412.TW", "3045.TW", "4904.TW", "2345.TW",
    "3596.TW", "6285.TW", "5388.TWO",

    # 被動元件
    "2327.TW", "2492.TW", "3026.TW", "8042.TW",

    # 光電
    "3481.TW", "2406.TW", "3008.TW", "6116.TW",

    # PCB / CCL
    "3037.TW", "2368.TW", "3044.TW", "6274.TWO",
    "8358.TW", "6213.TWO",

    # 航運
    "2603.TW", "2609.TW", "2610.TW", "2618.TW",

    # 金融
    "2880.TW", "2881.TW", "2882.TW", "2883.TW",
    "2884.TW", "2885.TW", "2886.TW", "2887.TW",
    "2888.TW", "2889.TW", "2890.TW", "2891.TW",
    "2892.TW", "5880.TW", "5871.TW",

    # 傳產
    "1101.TW", "1102.TW", "1216.TW",
    "1301.TW", "1303.TW", "1402.TW",
    "2002.TW", "2207.TW", "2308.TW",

    # 其他熱門
    "2105.TW", "2542.TW", "2606.TW",
    "2707.TW", "2727.TW", "2912.TW",
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

        # Yahoo 有時會回傳 MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        columns = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        for column in columns:
            if column not in df.columns:
                return None

        df = df[columns].copy()

        df = df.replace(
            [np.inf, -np.inf],
            np.nan
        )

        df = df.dropna()

        if len(df) < 60:
            return None

        return df

    except Exception as e:

        print(
            f"{ticker} 下載失敗：{e}"
        )

        return None


# ============================================================
# 技術面評分
# ============================================================

def technical_score(df):

    close = float(
        df["Close"].iloc[-1]
    )

    previous_close = float(
        df["Close"].iloc[-2]
    )

    volume = float(
        df["Volume"].iloc[-1]
    )

    if previous_close <= 0:
        return 0, []

    change_pct = (
        close / previous_close - 1
    ) * 100

    # -------------------------
    # 成交量
    # -------------------------

    avg5 = float(
        df["Volume"]
        .iloc[-6:-1]
        .mean()
    )

    avg20 = float(
        df["Volume"]
        .iloc[-21:-1]
        .mean()
    )

    if avg5 <= 0 or avg20 <= 0:
        return 0, []

    volume_ratio_5 = volume / avg5
    volume_ratio_20 = volume / avg20

    score = 0
    reasons = []

    # 5日量
    if volume_ratio_5 >= 3:
        score += 20
        reasons.append("5日均量3倍以上")

    elif volume_ratio_5 >= 2:
        score += 15
        reasons.append("5日均量2倍以上")

    elif volume_ratio_5 >= 1.5:
        score += 8
        reasons.append("5日量增")

    # 20日量
    if volume_ratio_20 >= 2:
        score += 8
        reasons.append("20日量爆發")

    elif volume_ratio_20 >= 1.5:
        score += 5
        reasons.append("20日量增")

    # -------------------------
    # 漲幅
    # -------------------------

    if 3 <= change_pct <= 7:

        score += 12
        reasons.append("強勢上漲")

    elif 1 <= change_pct < 3:

        score += 5
        reasons.append("溫和上漲")

    elif 7 < change_pct <= 9:

        score += 7
        reasons.append("高檔強勢")

    elif change_pct > 9:

        score -= 15
        reasons.append("單日漲幅過大")

    elif change_pct < -3:

        score -= 10
        reasons.append("今日轉弱")

    # -------------------------
    # MA
    # -------------------------

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

    ma60 = (
        df["Close"]
        .rolling(60)
        .mean()
        .iloc[-1]
    )

    ma20_previous = (
        df["Close"]
        .rolling(20)
        .mean()
        .iloc[-2]
    )

    if close > ma20:

        score += 5
        reasons.append("站上MA20")

    if ma5 > ma20:

        score += 5
        reasons.append("MA5>MA20")

    if ma20 > ma20_previous:

        score += 5
        reasons.append("MA20上升")

    if ma20 > ma60:

        score += 4
        reasons.append("MA20>MA60")

    # -------------------------
    # 突破20日高
    # -------------------------

    high20 = (
        df["High"]
        .iloc[-21:-1]
        .max()
    )

    breakout20 = close > high20

    if breakout20:

        score += 12
        reasons.append("突破20日高")

    # -------------------------
    # 52週高點
    # -------------------------

    high252 = (
        df["High"]
        .iloc[-252:]
        .max()
    )

    if high252 > 0:

        distance = (
            (high252 - close)
            / high252
        ) * 100

    else:

        distance = 100

    if distance <= 10:

        score += 5
        reasons.append("接近52週高")

    elif distance <= 20:

        score += 3
        reasons.append("接近前高")

    # -------------------------
    # 20日漲幅
    # -------------------------

    close20 = (
        df["Close"]
        .iloc[-21]
    )

    gain20 = (
        close / close20 - 1
    ) * 100

    if gain20 > 35:

        score -= 20
        reasons.append("20日漲幅過大")

    elif gain20 > 25:

        score -= 10
        reasons.append("20日漲幅偏大")

    elif 10 <= gain20 <= 25:

        score += 5
        reasons.append("20日趨勢強")

    # -------------------------
    # 成交金額
    # -------------------------

    turnover = close * volume

    if turnover >= 40_000_000:
        score += 5
        reasons.append("成交金額達4,000萬")

    elif turnover >= 20_000_000:
        score += 3
        reasons.append("成交金額達2,000萬")

    return score, reasons


# ============================================================
# 防追高判斷
# ============================================================

def chase_filter(df):

    close = float(
        df["Close"].iloc[-1]
    )

    previous = float(
        df["Close"].iloc[-2]
    )

    change = (
        close / previous - 1
    ) * 100

    close20 = float(
        df["Close"].iloc[-21]
    )

    gain20 = (
        close / close20 - 1
    ) * 100

    # 單日超過9%
    if change > 9:

        return (
            False,
            "🔴 單日漲幅過大，避免追高"
        )

    # 20日漲幅超過35%
    if gain20 > 35:

        return (
            False,
            "🔴 短線漲幅過大，避免追高"
        )

    return (
        True,
        ""
    )


# ============================================================
# 個股分析
# ============================================================

def analyze_stock(ticker):

    df = download_stock(ticker)

    if df is None:
        return None

    technical_points, reasons = (
        technical_score(df)
    )

    if technical_points < MIN_SCORE:
        return None

    can_watch, warning = (
        chase_filter(df)
    )

    close = float(
        df["Close"].iloc[-1]
    )

    previous = float(
        df["Close"].iloc[-2]
    )

    change = (
        close / previous - 1
    ) * 100

    volume = float(
        df["Volume"].iloc[-1]
    )

    avg5 = float(
        df["Volume"].iloc[-6:-1]
        .mean()
    )

    avg20 = float(
        df["Volume"].iloc[-21:-1]
        .mean()
    )

    volume5 = (
        volume / avg5
        if avg5 > 0
        else 0
    )

    volume20 = (
        volume / avg20
        if avg20 > 0
        else 0
    )

    turnover = (
        close * volume
    )

    high20 = (
        df["High"]
        .iloc[-21:-1]
        .max()
    )

    breakout = close > high20

    ma20 = (
        df["Close"]
        .rolling(20)
        .mean()
        .iloc[-1]
    )

    ma5 = (
        df["Close"]
        .rolling(5)
        .mean()
        .iloc[-1]
    )

    # -------------------------
    # 最終評等
    # -------------------------

    if not can_watch:

        status = warning

    elif (
        breakout
        and volume5 >= 2
        and 3 <= change <= 8
    ):

        status = (
            "🟢 爆量突破，列入強勢觀察"
        )

    elif (
        close > ma20
        and ma5 > ma20
        and volume5 >= 1.5
    ):

        status = (
            "🟢 多頭趨勢，等待拉回"
        )

    elif volume5 >= 2:

        status = (
            "🟡 爆量異動，持續觀察"
        )

    else:

        status = (
            "⚪ 技術面偏強"
        )

    return {

        "ticker": ticker,

        "score": technical_points,

        "close": close,

        "change": change,

        "volume5": volume5,

        "volume20": volume20,

        "turnover": turnover,

        "breakout": breakout,

        "status": status,

        "reasons": reasons

    }


# ============================================================
# 主程式
# ============================================================

def main():

    print("=" * 60)

    print(
        "🚀 台股飆股雷達 4.0"
    )

    print("=" * 60)

    print(
        f"股票池：{len(STOCKS)} 檔"
    )

    results = []

    for index, ticker in enumerate(
        STOCKS,
        1
    ):

        print(
            f"[{index}/{len(STOCKS)}] "
            f"分析 {ticker}"
        )

        try:

            result = analyze_stock(
                ticker
            )

            if result is not None:

                results.append(
                    result
                )

        except Exception as e:

            print(
                f"{ticker} 分析失敗：{e}"
            )

    # -------------------------
    # 排名
    # -------------------------

    results.sort(

        key=lambda x: (
            x["score"],
            x["volume5"],
            x["change"]
        ),

        reverse=True
    )

    today = datetime.now()

    lines = []

    lines.append(
        "🚨 台股飆股雷達 4.0"
    )

    lines.append(
        f"📅 {today.strftime('%Y/%m/%d %H:%M')}"
    )

    lines.append(
        f"🔎 掃描：{len(STOCKS)} 檔"
    )

    lines.append(
        f"🎯 符合條件：{len(results)} 檔"
    )

    lines.append("")

    if not results:

        lines.append(
            "⚪ 今日沒有符合條件的股票。"
        )

    else:

        for rank, item in enumerate(
            results[:TOP_N],
            1
        ):

            ticker = (
                item["ticker"]
                .replace(".TW", "")
                .replace(".TWO", "")
            )

            turnover_billion = (
                item["turnover"]
                / 100_000_000
            )

            lines.append(
                f"🏆 第{rank}名｜{ticker}"
            )

            lines.append(
                f"⭐ {item['score']}分"
            )

            lines.append(
                f"💰 股價 {item['close']:.2f}"
                f"｜📈 {item['change']:+.2f}%"
            )

            lines.append(
                f"🔥 5日量 "
                f"{item['volume5']:.1f}倍"
                f"｜20日量 "
                f"{item['volume20']:.1f}倍"
            )

            lines.append(
                f"💵 成交金額 "
                f"{turnover_billion:.2f}億"
            )

            lines.append(
                "📌 "
                + "、".join(
                    item["reasons"]
                )
            )

            lines.append(
                f"➡️ {item['status']}"
            )

            lines.append("")

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    lines.append(
        "📌 使用方式："
    )

    lines.append(
        "60分以上＝值得研究"
    )

    lines.append(
        "80分以上＝強勢關注"
    )

    lines.append(
        "90分以上＝極強異動"
    )

    lines.append("")

    lines.append(
        "⚠️ 本工具為技術面選股工具，"
        "僅供研究參考，不代表買進建議。"
    )

    message = "\n".join(
        lines
    )

    print("\n")
    print(message)

    send_telegram(
        message
    )

    print(
        "\n✅ Telegram 發送成功"
    )


# ============================================================
# 執行
# ============================================================

if __name__ == "__main__":

    main()
