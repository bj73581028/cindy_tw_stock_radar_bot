# ============================================================
# 台股飆股雷達 6.0
# Taiwan Stock Radar 6.0
#
# 核心條件：
# 1. 今日漲幅 >= 3%
# 2. 今日成交量 >= 5日平均量 × 1.8
# 3. 今日成交金額 > 2,000萬元
# 4. 產業排名 Top 30%
# 5. 基本面良好
# 6. KD 9K 向上或平穩
# 7. RSI 5T 向上或平穩
# 8. RSI 10T 輔助觀察
# 9. MACD DIF(12,26) 向上或平穩
# 10. 支撐 / 壓力位
# 11. 三線共振
# 12. 100分制排名
# 13. Telegram 通知
# 14. CSV / JSON / HTML Dashboard
#
# 執行時間：
# GitHub Actions：台灣時間週一～週五 15:00
# ============================================================

import os
import json
import math
import time
import warnings
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")


# ============================================================
# 基本設定
# ============================================================

VERSION = "6.1"

TW_TZ = ZoneInfo("Asia/Taipei")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MIN_GAIN = 3.0
MIN_VOLUME_RATIO = 1.8
MIN_TURNOVER = 20_000_000

TOP_INDUSTRY_PERCENT = 30
MAX_MA10_DEVIATION = 8.0
MAX_MA20_DEVIATION = 12.0

MAX_TICKERS = 2006

REQUEST_TIMEOUT = 20

RESULT_CSV = "radar_results.csv"
RESULT_JSON = "radar_results.json"
DASHBOARD_HTML = "dashboard.html"


# ============================================================
# 工具
# ============================================================

def now_tw():
    return datetime.now(TW_TZ)


def now_text():
    return now_tw().strftime("%Y/%m/%d %H:%M")


def safe_float(value, default=np.nan):
    try:
        if value is None:
            return default

        if isinstance(value, str):
            value = value.replace(",", "").replace("%", "").strip()

        return float(value)
    except Exception:
        return default


def fmt_num(value, digits=2):
    if value is None or pd.isna(value):
        return "-"
    return f"{value:.{digits}f}"


def fmt_money(value):
    if value is None or pd.isna(value):
        return "-"
    if value >= 100_000_000:
        return f"{value / 100_000_000:.2f}億"
    if value >= 10_000:
        return f"{value / 10_000:.1f}萬"
    return f"{value:,.0f}"


def trend_symbol(trend):
    mapping = {
        "強勢向上": "🚀",
        "溫和向上": "↗️",
        "平穩": "➡️",
        "略為向下": "↘️",
        "明顯向下": "🔻",
        "資料不足": "❔",
    }
    return mapping.get(trend, "➡️")


def grade(score):
    if score >= 90:
        return "S"
    elif score >= 80:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 60:
        return "C"
    return "D"


# ============================================================
# HTTP
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131 Safari/537.36"
    )
})


def get_json(url, params=None, timeout=REQUEST_TIMEOUT):
    try:
        r = SESSION.get(
            url,
            params=params,
            timeout=timeout
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[WARN] API失敗：{url}")
        print(e)
        return None


# ============================================================
# TWSE 股票清單
# ============================================================

def get_twse_stocks():
    print("📡 取得 TWSE 股票清單...")

    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"

    data = get_json(url)

    if not data:
        return []

    stocks = []

    for item in data:

        code = str(item.get("Code", "")).strip()
        name = str(item.get("Name", "")).strip()

        if not code:
            continue

        if not code.isdigit():
            continue

        # 排除ETF、權證等常見商品
        if code.startswith(("00", "01", "02", "03")):
            continue

        stocks.append({
            "code": code,
            "name": name,
            "market": "TWSE",
        })

    return stocks


# ============================================================
# TPEx 股票清單
# ============================================================

def get_tpex_stocks():
    print("📡 取得 TPEx 股票清單...")

    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"

    data = get_json(url)

    if not data:
        return []

    stocks = []

    for item in data:

        code = str(
            item.get("SecuritiesCompanyCode")
            or item.get("SecuritiesCompanyCode")
            or item.get("Code")
            or ""
        ).strip()

        name = str(
            item.get("CompanyName")
            or item.get("Name")
            or ""
        ).strip()

        if not code or not code.isdigit():
            continue

        if code.startswith(("00", "01", "02", "03")):
            continue

        stocks.append({
            "code": code,
            "name": name,
            "market": "TPEx",
        })

    return stocks


# ============================================================
# 股票清單
# ============================================================

def get_stock_universe():

    twse = get_twse_stocks()
    tpex = get_tpex_stocks()

    stocks = twse + tpex

    unique = {}

    for s in stocks:
        unique[s["code"]] = s

    stocks = list(unique.values())

    print(f"📊 TWSE：{len(twse)}")
    print(f"📊 TPEx：{len(tpex)}")
    print(f"📊 股票總數：{len(stocks)}")

    return stocks


# ============================================================
# 技術指標
# ============================================================

def calculate_rsi(series, period=14):

    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_kd(df):

    low_min = df["Low"].rolling(9).min()
    high_max = df["High"].rolling(9).max()

    rsv = (
        (df["Close"] - low_min)
        / (high_max - low_min)
        * 100
    )

    rsv = rsv.replace(
        [np.inf, -np.inf],
        np.nan
    )

    k = rsv.ewm(
        com=2,
        adjust=False
    ).mean()

    d = k.ewm(
        com=2,
        adjust=False
    ).mean()

    return k, d


def calculate_macd(series):

    ema12 = series.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = series.ewm(
        span=26,
        adjust=False
    ).mean()

    dif = ema12 - ema26

    dea = dif.ewm(
        span=9,
        adjust=False
    ).mean()

    histogram = dif - dea

    return dif, dea, histogram


# ============================================================
# 趨勢判斷
# ============================================================

def linear_slope(values):

    values = pd.Series(values).dropna()

    if len(values) < 3:
        return np.nan

    x = np.arange(len(values))

    try:
        slope = np.polyfit(x, values.values, 1)[0]
        return slope
    except Exception:
        return np.nan


def indicator_trend(
    series,
    strong_threshold=0.0,
    mild_threshold=0.0,
    normalize=False
):

    s = pd.Series(series).dropna()

    if len(s) < 5:
        return "資料不足"

    recent = s.tail(5)

    slope = linear_slope(recent)

    if pd.isna(slope):
        return "資料不足"

    if normalize:

        base = abs(recent.mean())

        if base < 1e-8:
            base = 1

        slope = slope / base * 100

    else:

        # 使用最近數值的波動程度進行標準化
        volatility = recent.diff().abs().mean()

        if pd.notna(volatility) and volatility > 0:
            slope = slope / volatility

    if slope >= 0.8:
        return "強勢向上"

    if slope >= 0.2:
        return "溫和向上"

    if slope > -0.2:
        return "平穩"

    if slope > -0.8:
        return "略為向下"

    return "明顯向下"


# ============================================================
# 趨勢分數
# ============================================================

def trend_score(trend):

    scores = {
        "強勢向上": 10,
        "溫和向上": 9,
        "平穩": 7,
        "略為向下": 3,
        "明顯向下": 0,
        "資料不足": 3,
    }

    return scores.get(trend, 3)


# ============================================================
# 支撐／壓力
# ============================================================

def local_supports(df, current_price):

    supports = []

    lows = df["Low"].tail(60)

    for i in range(2, len(lows) - 2):

        value = lows.iloc[i]

        left = lows.iloc[i - 2:i]
        right = lows.iloc[i + 1:i + 3]

        if value <= left.min() and value <= right.min():

            if value < current_price:
                supports.append(float(value))

    # MA
    ma20 = df["Close"].rolling(20).mean().iloc[-1]
    ma60 = df["Close"].rolling(60).mean().iloc[-1]

    for ma in [ma20, ma60]:

        if pd.notna(ma) and ma < current_price:
            supports.append(float(ma))

    # 近期低點
    low20 = df["Low"].tail(20).min()
    low60 = df["Low"].tail(60).min()

    if pd.notna(low20) and low20 < current_price:
        supports.append(float(low20))

    if pd.notna(low60) and low60 < current_price:
        supports.append(float(low60))

    supports = sorted(set(round(x, 2) for x in supports), reverse=True)

    return supports[:3]


def local_resistances(df, current_price):

    resistances = []

    highs = df["High"].tail(60)

    for i in range(2, len(highs) - 2):

        value = highs.iloc[i]

        left = highs.iloc[i - 2:i]
        right = highs.iloc[i + 1:i + 3]

        if value >= left.max() and value >= right.max():

            if value > current_price:
                resistances.append(float(value))

    ma20 = df["Close"].rolling(20).mean().iloc[-1]
    ma60 = df["Close"].rolling(60).mean().iloc[-1]

    for ma in [ma20, ma60]:

        if pd.notna(ma) and ma > current_price:
            resistances.append(float(ma))

    high20 = df["High"].tail(20).max()
    high60 = df["High"].tail(60).max()

    if pd.notna(high20) and high20 > current_price:
        resistances.append(float(high20))

    if pd.notna(high60) and high60 > current_price:
        resistances.append(float(high60))

    resistances = sorted(
        set(round(x, 2) for x in resistances)
    )

    return resistances[:3]


# ============================================================
# 基本面
# ============================================================

def get_fundamentals(symbol):

    try:

        ticker = yf.Ticker(symbol)

        info = ticker.get_info()

        eps = safe_float(
            info.get("trailingEps")
        )

        roe = safe_float(
            info.get("returnOnEquity")
        )

        revenue_growth = safe_float(
            info.get("revenueGrowth")
        )

        profit_margin = safe_float(
            info.get("profitMargins")
        )

        score = 0

        if pd.notna(eps) and eps > 0:
            score += 5

        if pd.notna(roe):

            if roe >= 0.15:
                score += 8

            elif roe >= 0.10:
                score += 6

            elif roe >= 0:
                score += 3

        if pd.notna(revenue_growth):

            if revenue_growth >= 0.10:
                score += 5

            elif revenue_growth >= 0:
                score += 3

        if pd.notna(profit_margin) and profit_margin > 0:
            score += 2

        # 基本面達標
        good = score >= 10

        return {
            "fundamental_score": min(score, 20),
            "fundamental_good": good,
            "eps": eps,
            "roe": roe,
            "revenue_growth": revenue_growth,
            "profit_margin": profit_margin,
        }

    except Exception as e:

        return {
            "fundamental_score": 0,
            "fundamental_good": False,
            "eps": np.nan,
            "roe": np.nan,
            "revenue_growth": np.nan,
            "profit_margin": np.nan,
        }


# ============================================================
# 產業資訊
# ============================================================

def get_industry(info):

    industry = (
        info.get("industry")
        or info.get("sector")
        or "其他"
    )

    return str(industry)


# ============================================================
# 股票歷史資料
# ============================================================

def get_history(symbol):

    try:

        ticker = yf.Ticker(symbol)

        df = ticker.history(
            period="1y",
            interval="1d",
            auto_adjust=False
        )

        if df is None or df.empty:
            return None

        df = df.copy()

        df = df.dropna(
            subset=["Close", "Volume"]
        )

        if len(df) < 70:
            return None

        return df

    except Exception as e:

        print(
            f"[WARN] 歷史資料失敗 {symbol}: {e}"
        )

        return None


# ============================================================
# 技術分析
# ============================================================

def analyze_technical(df):

    close = df["Close"]
    volume = df["Volume"]

    current_price = float(close.iloc[-1])

    previous_close = float(close.iloc[-2])

    gain = (
        (current_price / previous_close) - 1
    ) * 100

    avg_volume_5 = volume.iloc[-6:-1].mean()

    if avg_volume_5 <= 0:
        volume_ratio = np.nan
    else:
        volume_ratio = (
            volume.iloc[-1] / avg_volume_5
        )

    turnover = (
        current_price
        * float(volume.iloc[-1])
    )

    # MA
    ma10 = close.rolling(10).mean()
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    # KD
    k, d = calculate_kd(df)

    # RSI
    rsi5 = calculate_rsi(close, 5)
    rsi10 = calculate_rsi(close, 10)

    # MACD
    dif, dea, histogram = calculate_macd(close)

    kd_trend = indicator_trend(
        k,
        normalize=True
    )

    rsi5_trend = indicator_trend(
        rsi5,
        normalize=True
    )

    macd_trend = indicator_trend(
        dif,
        normalize=False
    )

    # RSI10只作輔助
    rsi10_trend = indicator_trend(
        rsi10,
        normalize=True
    )

    # ========================================================
    # 趨勢硬性條件
    # ========================================================

    bad_trends = {
        "明顯向下"
    }

    technical_pass = (
        kd_trend not in bad_trends
        and rsi5_trend not in bad_trends
        and macd_trend not in bad_trends
    )

    # ========================================================
    # 三線共振
    # ========================================================

    resonance = (
        kd_trend in {"強勢向上", "溫和向上"}
        and
        rsi5_trend in {"強勢向上", "溫和向上"}
        and
        macd_trend in {"強勢向上", "溫和向上"}
    )

    # ========================================================
    # 支撐 / 壓力
    # ========================================================

    supports = local_supports(
        df,
        current_price
    )

    resistances = local_resistances(
        df,
        current_price
    )

    s1 = supports[0] if len(supports) > 0 else np.nan
    s2 = supports[1] if len(supports) > 1 else np.nan
    s3 = supports[2] if len(supports) > 2 else np.nan

    r1 = resistances[0] if len(resistances) > 0 else np.nan
    r2 = resistances[1] if len(resistances) > 1 else np.nan
    r3 = resistances[2] if len(resistances) > 2 else np.nan

    support_distance = (
        ((current_price - s1) / current_price) * 100
        if pd.notna(s1)
        else np.nan
    )

    resistance_distance = (
        ((r1 - current_price) / current_price) * 100
        if pd.notna(r1)
        else np.nan
    )

    # ========================================================
    # 52週高點
    # ========================================================

    high_52w = df["High"].tail(252).max()

    distance_from_52w_high = (
        (high_52w - current_price)
        / high_52w
        * 100
        if high_52w > 0
        else np.nan
    )

    # ========================================================
    # 20日漲幅
    # ========================================================

    if len(close) >= 21:

        gain_20d = (
            current_price
            / close.iloc[-21]
            - 1
        ) * 100

    else:
        gain_20d = np.nan

    # ========================================================
    # MA狀態
    # ========================================================

    ma20_value = ma20.iloc[-1]

    ma10_value = ma10.iloc[-1]
    ma10_deviation = ((current_price - ma10_value) / ma10_value * 100) if pd.notna(ma10_value) and ma10_value > 0 else np.nan
    ma20_deviation = ((current_price - ma20_value) / ma20_value * 100) if pd.notna(ma20_value) and ma20_value > 0 else np.nan

    # 6.1 低乖離過濾：排除股價向上遠離 MA10 / MA20 的股票
    if pd.notna(ma10_deviation) and ma10_deviation > MAX_MA10_DEVIATION:
        return None
    if pd.notna(ma20_deviation) and ma20_deviation > MAX_MA20_DEVIATION:
        return None
    ma60_value = ma60.iloc[-1]

    ma_score = 0

    if current_price > ma20_value:
        ma_score += 3

    if ma20_value > ma60_value:
        ma_score += 2

    if len(ma20.dropna()) >= 5:

        if ma20.iloc[-1] > ma20.iloc[-5]:
            ma_score += 2

    # ========================================================
    # 技術分數
    # ========================================================

    technical_score = 0

    # 量能 20分
    if volume_ratio >= 3.0:
        volume_score = 20

    elif volume_ratio >= 2.5:
        volume_score = 18

    elif volume_ratio >= 2.0:
        volume_score = 16

    elif volume_ratio >= 1.8:
        volume_score = 14

    else:
        volume_score = 0

    technical_score += volume_score

    # 漲幅 10分
    if gain >= 7:
        gain_score = 10

    elif gain >= 5:
        gain_score = 8

    elif gain >= 4:
        gain_score = 6

    elif gain >= 3:
        gain_score = 5

    else:
        gain_score = 0

    technical_score += gain_score

    # KD
    kd_score = trend_score(kd_trend)

    # RSI
    rsi_score = trend_score(rsi5_trend)

    # MACD
    macd_score = trend_score(macd_trend)

    # 技術總分
    technical_score += (
        kd_score
        + rsi_score
        + macd_score
    )

    if resonance:
        technical_score += 5

    technical_score += ma_score

    return {
        "price": current_price,
        "gain": gain,
        "volume": float(volume.iloc[-1]),
        "avg_volume_5": avg_volume_5,
        "volume_ratio": volume_ratio,
        "turnover": turnover,

        "ma5": ma5.iloc[-1],
        "ma10": ma10_value,
        "ma10_deviation": ma10_deviation,
        "ma20_deviation": ma20_deviation,
        "ma20": ma20_value,
        "ma60": ma60_value,

        "k": k.iloc[-1],
        "d": d.iloc[-1],

        "rsi5": rsi5.iloc[-1],
        "rsi10": rsi10.iloc[-1],

        "dif": dif.iloc[-1],
        "dea": dea.iloc[-1],
        "macd_histogram": histogram.iloc[-1],

        "kd_trend": kd_trend,
        "rsi5_trend": rsi5_trend,
        "rsi10_trend": rsi10_trend,
        "macd_trend": macd_trend,

        "resonance": resonance,

        "technical_pass": technical_pass,
        "technical_score": technical_score,

        "support1": s1,
        "support2": s2,
        "support3": s3,

        "resistance1": r1,
        "resistance2": r2,
        "resistance3": r3,

        "support_distance": support_distance,
        "resistance_distance": resistance_distance,

        "high_52w": high_52w,
        "distance_from_52w_high": distance_from_52w_high,

        "gain_20d": gain_20d,

        "ma_score": ma_score,
    }


# ============================================================
# 產業排名
# ============================================================

def calculate_industry_ranking(results):

    if not results:
        return results

    df = pd.DataFrame(results)

    if df.empty:
        return results

    if "industry" not in df.columns:
        for r in results:
            r["industry_rank_percent"] = 100
            r["industry_score"] = 0
        return results

    # 以產業平均今日漲幅 + 20日漲幅計算產業強度
    grouped = (
        df.groupby("industry")
        .agg(
            industry_gain=("gain", "mean"),
            industry_gain20=("gain_20d", "mean"),
            industry_count=("code", "count")
        )
        .reset_index()
    )

    grouped["industry_strength"] = (
        grouped["industry_gain"] * 0.6
        + grouped["industry_gain20"] * 0.4
    )

    grouped = grouped.sort_values(
        "industry_strength",
        ascending=False
    ).reset_index(drop=True)

    total_industries = len(grouped)

    rank_map = {}

    for idx, row in grouped.iterrows():

        rank = idx + 1

        percentile = (
            rank / total_industries * 100
        )

        rank_map[row["industry"]] = (
            rank,
            percentile
        )

    for r in results:

        rank, percentile = rank_map.get(
            r["industry"],
            (total_industries, 100)
        )

        r["industry_rank"] = rank
        r["industry_rank_percent"] = percentile

        if percentile <= 10:
            r["industry_score"] = 15

        elif percentile <= 20:
            r["industry_score"] = 13

        elif percentile <= 30:
            r["industry_score"] = 11

        elif percentile <= 50:
            r["industry_score"] = 7

        else:
            r["industry_score"] = 3

    return results


# ============================================================
# 支撐壓力分數
# ============================================================

def support_resistance_score(r):

    score = 0

    support_distance = r.get(
        "support_distance",
        np.nan
    )

    resistance_distance = r.get(
        "resistance_distance",
        np.nan
    )

    # 距離支撐不要太遠
    if pd.notna(support_distance):

        if support_distance <= 5:
            score += 3

        elif support_distance <= 8:
            score += 2

        elif support_distance <= 12:
            score += 1

    # 上方壓力至少有一定空間
    if pd.notna(resistance_distance):

        if resistance_distance >= 10:
            score += 2

        elif resistance_distance >= 5:
            score += 1

    return min(score, 5)


# ============================================================
# 總分
# ============================================================

def calculate_final_score(r):

    # --------------------------------------------------------
    # 量能 20
    # --------------------------------------------------------

    volume_ratio = r["volume_ratio"]

    if volume_ratio >= 3:
        volume_score = 20

    elif volume_ratio >= 2.5:
        volume_score = 18

    elif volume_ratio >= 2:
        volume_score = 16

    elif volume_ratio >= 1.8:
        volume_score = 14

    else:
        volume_score = 0

    # --------------------------------------------------------
    # 產業 15
    # --------------------------------------------------------

    industry_score = r.get(
        "industry_score",
        0
    )

    # --------------------------------------------------------
    # 基本面 20
    # --------------------------------------------------------

    fundamental_score = r.get(
        "fundamental_score",
        0
    )

    # --------------------------------------------------------
    # 成交金額 10
    # --------------------------------------------------------

    turnover = r["turnover"]

    if turnover >= 500_000_000:
        turnover_score = 10

    elif turnover >= 200_000_000:
        turnover_score = 9

    elif turnover >= 100_000_000:
        turnover_score = 8

    elif turnover >= 50_000_000:
        turnover_score = 7

    elif turnover >= 20_000_000:
        turnover_score = 5

    else:
        turnover_score = 0

    # --------------------------------------------------------
    # KD 10
    # --------------------------------------------------------

    kd_score = trend_score(
        r["kd_trend"]
    )

    # --------------------------------------------------------
    # RSI 10
    # --------------------------------------------------------

    rsi_score = trend_score(
        r["rsi5_trend"]
    )

    # --------------------------------------------------------
    # MACD 10
    # --------------------------------------------------------

    macd_score = trend_score(
        r["macd_trend"]
    )

    # --------------------------------------------------------
    # 支撐壓力 5
    # --------------------------------------------------------

    sr_score = support_resistance_score(r)

    # --------------------------------------------------------
    # 原始分數
    #
    # 20 + 15 + 20 + 10 + 10 + 10 + 10 + 5 = 100
    #
    # 但KD/RSI/MACD使用10分
    # --------------------------------------------------------

    total = (
        volume_score
        + industry_score
        + fundamental_score
        + turnover_score
        + kd_score
        + rsi_score
        + macd_score
        + sr_score
    )

    # 三線共振額外加分後進行上限控制
    if r["resonance"]:
        total += 5

    total = min(total, 100)

    r["volume_score"] = volume_score
    r["turnover_score"] = turnover_score
    r["kd_score"] = kd_score
    r["rsi_score"] = rsi_score
    r["macd_score"] = macd_score
    r["support_resistance_score"] = sr_score

    r["score"] = total
    r["grade"] = grade(total)

    return r


# ============================================================
# 單一股票分析
# ============================================================

def analyze_stock(stock):

    code = stock["code"]

    symbol = f"{code}.TW"

    if stock["market"] == "TPEx":
        symbol = f"{code}.TWO"

    try:

        print(
            f"🔎 {code} {stock['name']} "
            f"({stock['market']})"
        )

        df = get_history(symbol)

        if df is None:
            return None

        tech = analyze_technical(df)

        # ====================================================
        # 硬性條件
        # ====================================================

        if tech["gain"] < MIN_GAIN:
            return None

        if (
            pd.isna(tech["volume_ratio"])
            or tech["volume_ratio"] < MIN_VOLUME_RATIO
        ):
            return None

        if tech["turnover"] <= MIN_TURNOVER:
            return None

        if not tech["technical_pass"]:
            return None

        # ====================================================
        # 基本面
        # ====================================================

        fund = get_fundamentals(symbol)

        if not fund["fundamental_good"]:
            return None

        # ====================================================
        # Yahoo info
        # ====================================================

        try:

            ticker = yf.Ticker(symbol)

            info = ticker.get_info()

            industry = get_industry(info)

        except Exception:

            industry = "其他"

        result = {
            **stock,
            **tech,
            **fund,
            "industry": industry,
        }

        return result

    except Exception as e:

        print(
            f"[WARN] 分析失敗 {code}: {e}"
        )

        return None


# ============================================================
# 產業 Top30% 篩選
# ============================================================

def filter_top_industry(results):

    if not results:
        return []

    df = pd.DataFrame(results)

    if df.empty:
        return []

    # 至少有產業資料
    if "industry_rank_percent" not in df.columns:
        return results

    filtered = []

    for r in results:

        percentile = r.get(
            "industry_rank_percent",
            100
        )

        if percentile <= TOP_INDUSTRY_PERCENT:

            filtered.append(r)

    return filtered


# ============================================================
# 排序
# ============================================================

def rank_results(results):

    if not results:
        return []

    for r in results:
        calculate_final_score(r)

    results = sorted(
        results,
        key=lambda x: (
            x.get("score", 0),
            x.get("gain", 0),
            x.get("volume_ratio", 0)
        ),
        reverse=True
    )

    for i, r in enumerate(results, 1):
        r["rank"] = i

    return results


# ============================================================
# Telegram
# ============================================================

def telegram_send(message):

    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ 未設定 TELEGRAM_BOT_TOKEN")
        return False

    if not TELEGRAM_CHAT_ID:
        print("⚠️ 未設定 TELEGRAM_CHAT_ID")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:

        r = SESSION.post(
            url,
            json=payload,
            timeout=20
        )

        if r.ok:
            return True

        print(
            "Telegram失敗：",
            r.text
        )

        return False

    except Exception as e:

        print(
            "Telegram錯誤：",
            e
        )

        return False


# ============================================================
# Telegram 單檔格式
# ============================================================

def stock_message(r):

    rank = r["rank"]

    grade_icon = {
        "S": "🔥",
        "A": "⭐",
        "B": "🔹",
        "C": "▫️",
        "D": "⚪",
    }.get(r["grade"], "▫️")

    resonance = (
        "🔥 三線共振"
        if r["resonance"]
        else "—"
    )

    s1 = fmt_num(r["support1"])
    s2 = fmt_num(r["support2"])
    s3 = fmt_num(r["support3"])

    r1 = fmt_num(r["resistance1"])
    r2 = fmt_num(r["resistance2"])
    r3 = fmt_num(r["resistance3"])

    industry_rank = (
        f"{r.get('industry_rank', '-')}"
    )

    return (
        f"<b>#{rank}｜{r['code']} {r['name']}</b>\n"
        f"{grade_icon} <b>{r['score']}分｜{r['grade']}級</b>\n"
        f"💰 股價：{fmt_num(r['price'])}\n"
        f"📈 今日：+{fmt_num(r['gain'])}%\n"
        f"🔊 今日量：{r['volume']:,.0f}張\n"
        f"📊 5日均量：{r['avg_volume_5']:,.0f}張\n"
        f"📈 今日量／5日量：{fmt_num(r['volume_ratio'], 1)}倍\n"
        f"💵 成交金額：{fmt_money(r['turnover'])}\n"
        f"🏭 產業：{r['industry']}\n"
        f"🏆 產業排名：{industry_rank}\n"
        f"\n"
        f"📊 KD：{trend_symbol(r['kd_trend'])}"
        f"{r['kd_trend']} "
        f"K={fmt_num(r['k'])}\n"
        f"📊 RSI5：{trend_symbol(r['rsi5_trend'])}"
        f"{r['rsi5_trend']} "
        f"{fmt_num(r['rsi5'])}\n"
        f"📊 RSI10：{trend_symbol(r['rsi10_trend'])}"
        f"{r['rsi10_trend']} "
        f"{fmt_num(r['rsi10'])}\n"
        f"📊 MACD DIF：{trend_symbol(r['macd_trend'])}"
        f"{r['macd_trend']} "
        f"{fmt_num(r['dif'], 3)}\n"
        f"{resonance}\n"
        f"\n"
        f"🟢 支撐："
        f"S1 {s1}｜S2 {s2}｜S3 {s3}\n"
        f"🔴 壓力："
        f"R1 {r1}｜R2 {r2}｜R3 {r3}\n"
        f"\n"
        f"📌 52週高點："
        f"{fmt_num(r['high_52w'])}\n"
        f"📌 距52週高："
        f"{fmt_num(r['distance_from_52w_high'])}%\n"
    )


# ============================================================
# Telegram 總訊息
# ============================================================

def send_telegram_report(results, scanned):

    if not results:

        message = (
            f"📡 <b>台股飆股雷達 {VERSION}</b>\n"
            f"📅 {now_text()}\n\n"
            f"🔎 掃描：{scanned} 檔\n"
            f"❌ 今日沒有符合目前選股條件的股票\n\n"
            f"條件：\n"
            f"• 今日漲幅 ≥ 3%\n"
            f"• 量 ≥ 5日均量 × 1.8\n"
            f"• 成交金額 > 2,000萬\n"
            f"• 產業 Top30%\n"
            f"• 基本面良好\n"
            f"• KD / RSI5 / MACD DIF 不明顯向下"
        )

        telegram_send(message)

        return

    header = (
        f"🚨 <b>台股飆股雷達 {VERSION}</b>\n"
        f"📅 {now_text()}\n"
        f"🔎 掃描：{scanned} 檔\n"
        f"🎯 入選：{len(results)} 檔\n"
        f"━━━━━━━━━━━━━━\n"
    )

    # Telegram：TOP 10 整合成一則訊息
    # 若符合條件不足 10 檔，就全部顯示。
    top_results = results[:10]

    messages = []
    for r in top_results:
        messages.append(stock_message(r))

    combined_message = (
        header
        + "\n".join(
            f"🏆 <b>第{i}名</b>\n{msg}"
            for i, msg in enumerate(messages, 1)
        )
        + "\n━━━━━━━━━━━━━━"
    )

    # Telegram 單則訊息上限約 4096 字元，預留安全空間自動分段。
    max_length = 3900

    if len(combined_message) <= max_length:
        telegram_send(combined_message)
    else:
        current_message = header

        for i, msg in enumerate(messages, 1):
            section = f"🏆 <b>第{i}名</b>\n{msg}\n━━━━━━━━━━━━━━"

            if len(current_message) + len(section) + 2 <= max_length:
                current_message += "\n" + section
            else:
                telegram_send(current_message)
                time.sleep(0.5)
                current_message = header + "\n" + section

        if current_message != header:
            telegram_send(current_message)


# ============================================================
# CSV
# ============================================================

def save_csv(results):

    if not results:
        pd.DataFrame().to_csv(
            RESULT_CSV,
            index=False,
            encoding="utf-8-sig"
        )
        return

    df = pd.DataFrame(results)

    columns = [
        "rank",
        "code",
        "name",
        "market",
        "industry",
        "industry_rank",
        "industry_rank_percent",

        "score",
        "grade",

        "price",
        "gain",
        "volume",
        "avg_volume_5",
        "volume_ratio",
        "turnover",

        "fundamental_score",
        "eps",
        "roe",
        "revenue_growth",

        "k",
        "d",
        "kd_trend",

        "rsi5",
        "rsi5_trend",

        "rsi10",
        "rsi10_trend",

        "dif",
        "dea",
        "macd_histogram",
        "macd_trend",

        "resonance",

        "support1",
        "support2",
        "support3",

        "resistance1",
        "resistance2",
        "resistance3",

        "support_distance",
        "resistance_distance",

        "high_52w",
        "distance_from_52w_high",
        "gain_20d",
    ]

    columns = [
        c for c in columns
        if c in df.columns
    ]

    df = df[columns]

    df.to_csv(
        RESULT_CSV,
        index=False,
        encoding="utf-8-sig"
    )

    print(
        f"💾 已輸出 {RESULT_CSV}"
    )


# ============================================================
# JSON
# ============================================================

def clean_for_json(value):

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating,)):

        if np.isnan(value):
            return None

        return float(value)

    if pd.isna(value):
        return None

    return value


def save_json(results):

    clean_results = []

    for r in results:

        item = {}

        for k, v in r.items():

            try:
                item[k] = clean_for_json(v)
            except Exception:
                item[k] = str(v)

        clean_results.append(item)

    with open(
        RESULT_JSON,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            clean_results,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"💾 已輸出 {RESULT_JSON}"
    )


# ============================================================
# HTML Dashboard
# ============================================================

def html_escape(value):

    if value is None:
        return ""

    text = str(value)

    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_dashboard(results, scanned):

    rows = ""

    for r in results:

        grade_class = (
            "s-grade"
            if r["grade"] == "S"
            else "a-grade"
            if r["grade"] == "A"
            else "normal-grade"
        )

        resonance = (
            "🔥"
            if r["resonance"]
            else ""
        )

        rows += f"""
        <tr>
            <td>{r['rank']}</td>
            <td>
                <b>{html_escape(r['code'])}</b><br>
                {html_escape(r['name'])}
            </td>
            <td>{html_escape(r['industry'])}</td>
            <td class="{grade_class}">
                {r['score']} / {r['grade']}
            </td>
            <td>{fmt_num(r['price'])}</td>
            <td class="up">
                +{fmt_num(r['gain'])}%
            </td>
            <td>
                {fmt_num(r['volume_ratio'], 1)}x
            </td>
            <td>
                {fmt_money(r['turnover'])}
            </td>
            <td>
                {trend_symbol(r['kd_trend'])}
                {html_escape(r['kd_trend'])}
            </td>
            <td>
                {trend_symbol(r['rsi5_trend'])}
                {html_escape(r['rsi5_trend'])}
            </td>
            <td>
                {trend_symbol(r['macd_trend'])}
                {html_escape(r['macd_trend'])}
            </td>
            <td>
                {resonance}
            </td>
            <td>
                {fmt_num(r['support1'])}
            </td>
            <td>
                {fmt_num(r['resistance1'])}
            </td>
        </tr>
        """

    html = f"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>台股飆股雷達 6.0</title>

<style>

body {{
    font-family:
        Arial,
        "Microsoft JhengHei",
        sans-serif;

    background: #f5f7fa;

    margin: 0;

    color: #222;
}}

.header {{
    background: #111827;

    color: white;

    padding: 25px;

    text-align: center;
}}

.header h1 {{
    margin: 0 0 10px 0;
}}

.summary {{
    display: flex;

    flex-wrap: wrap;

    gap: 15px;

    padding: 20px;
}}

.card {{
    background: white;

    border-radius: 12px;

    padding: 18px;

    min-width: 180px;

    box-shadow:
        0 2px 8px rgba(0,0,0,0.08);
}}

.card-title {{
    color: #6b7280;

    font-size: 14px;
}}

.card-value {{
    font-size: 26px;

    font-weight: bold;

    margin-top: 5px;
}}

.table-container {{
    background: white;

    margin: 20px;

    border-radius: 12px;

    overflow-x: auto;

    box-shadow:
        0 2px 8px rgba(0,0,0,0.08);
}}

table {{
    border-collapse: collapse;

    width: 100%;

    min-width: 1500px;
}}

th {{
    background: #1f2937;

    color: white;

    padding: 12px;

    white-space: nowrap;
}}

td {{
    padding: 10px;

    border-bottom: 1px solid #e5e7eb;

    text-align: center;

    white-space: nowrap;
}}

tr:hover {{
    background: #f9fafb;
}}

.up {{
    font-weight: bold;
}}

.s-grade {{
    font-weight: bold;

    font-size: 18px;
}}

.a-grade {{
    font-weight: bold;
}}

.normal-grade {{
    font-weight: bold;
}}

.footer {{
    text-align: center;

    color: #6b7280;

    padding: 25px;
}}

</style>
</head>

<body>

<div class="header">

<h1>🚨 台股飆股雷達 6.0</h1>

<div>
📅 {now_text()}
</div>

</div>

<div class="summary">

<div class="card">

<div class="card-title">
掃描股票
</div>

<div class="card-value">
{scanned}
</div>

</div>

<div class="card">

<div class="card-title">
符合條件
</div>

<div class="card-value">
{len(results)}
</div>

</div>

<div class="card">

<div class="card-title">
S級
</div>

<div class="card-value">
{sum(1 for r in results if r['grade'] == 'S')}
</div>

</div>

<div class="card">

<div class="card-title">
A級
</div>

<div class="card-value">
{sum(1 for r in results if r['grade'] == 'A')}
</div>

</div>

</div>

<div class="table-container">

<table>

<thead>

<tr>

<th>排名</th>
<th>股票</th>
<th>產業</th>
<th>分數</th>
<th>股價</th>
<th>今日漲幅</th>
<th>量比</th>
<th>成交金額</th>
<th>KD 9K</th>
<th>RSI 5T</th>
<th>MACD DIF</th>
<th>共振</th>
<th>支撐 S1</th>
<th>壓力 R1</th>

</tr>

</thead>

<tbody>

{rows}

</tbody>

</table>

</div>

<div class="footer">

台股飆股雷達 6.0｜
條件：漲幅 ≥ 3%／量比 ≥ 1.8／成交金額 > 2,000萬｜
KD／RSI5／MACD DIF 不明顯向下

</div>

</body>

</html>
"""

    with open(
        DASHBOARD_HTML,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(html)

    print(
        f"💾 已輸出 {DASHBOARD_HTML}"
    )


# ============================================================
# 主程式
# ============================================================

def main():

    start_time = time.time()

    print("=" * 70)

    print(
        f"🚨 台股飆股雷達 {VERSION}"
    )

    print(
        f"📅 台灣時間：{now_text()}"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # 股票清單
    # --------------------------------------------------------

    stocks = get_stock_universe()

    if not stocks:

        print(
            "❌ 無法取得股票清單"
        )

        return

    scanned = 0

    candidates = []

    # --------------------------------------------------------
    # 分析股票
    # --------------------------------------------------------

    for stock in stocks:

        if scanned >= MAX_TICKERS:
            break

        scanned += 1

        result = analyze_stock(stock)

        if result is not None:

            candidates.append(result)

        # 避免API過度請求
        if scanned % 20 == 0:

            print(
                f"📊 已掃描 {scanned} / "
                f"{len(stocks)}｜"
                f"候選 {len(candidates)}"
            )

    print("=" * 70)

    print(
        f"🔎 掃描完成：{scanned}"
    )

    print(
        f"🎯 初步候選：{len(candidates)}"
    )

    # --------------------------------------------------------
    # 產業排名
    # --------------------------------------------------------

    candidates = calculate_industry_ranking(
        candidates
    )

    # --------------------------------------------------------
    # 產業Top30%
    # --------------------------------------------------------

    candidates = filter_top_industry(
        candidates
    )

    print(
        f"🏭 產業Top30%：{len(candidates)}"
    )

    # --------------------------------------------------------
    # 最終排名
    # --------------------------------------------------------

    results = rank_results(
        candidates
    )

    print(
        f"🏆 最終入選：{len(results)}"
    )

    print("=" * 70)

    # --------------------------------------------------------
    # 顯示結果
    # --------------------------------------------------------

    for r in results[:20]:

        print(
            f"#{r['rank']} "
            f"{r['code']} "
            f"{r['name']}｜"
            f"{r['score']}分｜"
            f"{r['grade']}｜"
            f"+{r['gain']:.2f}%｜"
            f"量比{r['volume_ratio']:.2f}｜"
            f"{r['kd_trend']}｜"
            f"{r['rsi5_trend']}｜"
            f"{r['macd_trend']}"
        )

    # --------------------------------------------------------
    # 輸出
    # --------------------------------------------------------

    save_csv(results)

    save_json(results)

    build_dashboard(
        results,
        scanned
    )

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    send_telegram_report(
        results,
        scanned
    )

    elapsed = time.time() - start_time

    print("=" * 70)

    print(
        f"✅ 台股飆股雷達 {VERSION} 完成"
    )

    print(
        f"⏱️ 執行時間：{elapsed:.1f} 秒"
    )

    print(
        f"📅 完成時間：{now_text()}"
    )

    print("=" * 70)


# ============================================================
# 執行
# ============================================================

if __name__ == "__main__":
    main()
