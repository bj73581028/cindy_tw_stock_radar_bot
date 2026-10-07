# ============================================================
# Taiwan Stock Radar 6.1 Backtest
# 台股飆股雷達 6.1 歷史回測版
#
# 支援：
# /backtest 3563
# /backtest 2435
# /backtest 大盤
# /backtest TWII
# /backtest TAIEX
# /backtest MULTI 2330,2454,3563
# /backtest ALL
#
# 核心：
# 1. 漲幅 >= 3%
# 2. 今日量 >= 前5個完整交易日平均量 × 1.8
# 3. 成交金額 > 2,000萬元
# 4. MA10乖離 <= 8%
# 5. MA20乖離 <= 12%
# 6. KD 9K 上升或持平
# 7. RSI5 上升或持平
# 8. MACD DIF 上升或持平
# 9. 技術面共振
#
# 回測：
# +1 / +3 / +5 / +10 / +20 日
# 20日最大漲幅
# 20日最大跌幅
#
# 大盤：
# ^TWII
#
# ============================================================

import os
import re
import json
import time
import math
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf


# ============================================================
# 基本設定
# ============================================================

VERSION = "6.1-BACKTEST"

TZ = ZoneInfo("Asia/Taipei")

TOKEN = os.getenv("BACKTEST_TELEGRAM_BOT_TOKEN", "").strip()

CHAT_ID_ENV = os.getenv("BACKTEST_TELEGRAM_CHAT_ID", "").strip()

START_DATE = os.getenv(
    "BACKTEST_START_DATE",
    "2025-10-01"
)

END_DATE = os.getenv(
    "BACKTEST_END_DATE",
    "2026-09-30"
)

# 最少需要的歷史資料
MIN_HISTORY = 100

# ============================================================
# 6.1 條件
# ============================================================

MIN_GAIN = 3.0

VOLUME_RATIO_MIN = 1.8

MIN_TURNOVER = 20_000_000

MAX_MA10_DEV = 8.0

MAX_MA20_DEV = 12.0


# ============================================================
# 大盤設定
# ============================================================

MARKET_SYMBOL = "^TWII"

MARKET_KEYWORDS = {
    "大盤",
    "台股大盤",
    "加權",
    "加權指數",
    "TAIEX",
    "TWII",
    "^TWII",
}


# ============================================================
# 股票代號
# ============================================================

DEFAULT_STOCKS = [
    "1101", "1102", "1216", "1301", "1303",
    "2002", "2301", "2303", "2308", "2317",
    "2327", "2330", "2345", "2357", "2368",
    "2379", "2382", "2395", "2408", "2412",
    "2454", "2603", "2609", "2610", "2618",
    "3034", "3037", "3045", "3231", "3443",
    "3661", "3711", "4904", "4938", "5269",
    "5274", "5483", "6239", "6415", "6669",
    "6770", "8046", "8069", "8299",
]


# ============================================================
# Telegram
# ============================================================

TELEGRAM_API = (
    f"https://api.telegram.org/bot{TOKEN}"
    if TOKEN
    else ""
)

OFFSET_FILE = "telegram_offset.txt"


def telegram(method, payload=None, timeout=60):
    """
    Telegram API
    """
    if not TOKEN:
        print("❌ BACKTEST_TELEGRAM_BOT_TOKEN 未設定")
        return None

    url = f"{TELEGRAM_API}/{method}"

    try:
        r = requests.post(
            url,
            json=payload or {},
            timeout=timeout
        )

        print(
            f"📡 Telegram HTTP Status：{r.status_code}"
        )

        if r.status_code != 200:
            print(r.text[:1000])
            return None

        return r.json()

    except Exception as e:
        print("❌ Telegram API 錯誤：", e)
        return None


def send(chat_id, text):
    """
    傳送 Telegram 訊息
    """

    if not chat_id:
        return False

    result = telegram(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    )

    return bool(result and result.get("ok"))


# ============================================================
# Offset
# ============================================================

def load_offset():
    """
    讀取 Telegram offset
    """

    try:
        if os.path.exists(OFFSET_FILE):
            with open(
                OFFSET_FILE,
                "r",
                encoding="utf-8"
            ) as f:
                value = f.read().strip()

            if value:
                return int(value)

    except Exception as e:
        print("⚠️ 讀取 Offset 失敗：", e)

    return 0


def save_offset(offset):
    """
    儲存 Telegram offset
    """

    try:
        with open(
            OFFSET_FILE,
            "w",
            encoding="utf-8"
        ) as f:
            f.write(str(offset))

    except Exception as e:
        print("⚠️ 儲存 Offset 失敗：", e)


# ============================================================
# Telegram Help
# ============================================================

def help_text():

    return f"""
<b>🇹🇼 Taiwan Stock Radar {VERSION}</b>

<b>📌 單股回測</b>

/backtest 3563
/backtest 2435

<b>📌 大盤回測</b>

/backtest 大盤
/backtest TWII
/backtest TAIEX

<b>📌 多檔回測</b>

/backtest MULTI 2330,2454,3563

<b>📌 全部股票</b>

/backtest ALL

<b>📅 回測期間</b>
{START_DATE} ～ {END_DATE}

<b>📊 6.1 核心條件</b>
• 漲幅 ≥ {MIN_GAIN}%
• 量比 ≥ {VOLUME_RATIO_MIN}
• 成交金額 > 2,000萬元
• MA10乖離 ≤ {MAX_MA10_DEV}%
• MA20乖離 ≤ {MAX_MA20_DEV}%
• KD 9K 上升／持平
• RSI5 上升／持平
• MACD DIF 上升／持平

<b>📈 回測</b>
+1 / +3 / +5 / +10 / +20 日
20日最大漲幅／最大跌幅
"""


# ============================================================
# 判斷大盤
# ============================================================

def is_market_query(q):

    q = str(q).strip()

    if q in MARKET_KEYWORDS:
        return True

    if q.upper() in {
        "TAIEX",
        "TWII",
        "^TWII"
    }:
        return True

    return False


# ============================================================
# 股票代號清理
# ============================================================

def normalize_symbol(symbol):

    symbol = str(symbol).strip().upper()

    if symbol.endswith(".TW"):
        return symbol

    if symbol.endswith(".TWO"):
        return symbol

    return symbol


def yahoo_symbol(code):

    code = normalize_symbol(code)

    if code in {
        "^TWII",
        "TAIEX",
        "TWII"
    }:
        return "^TWII"

    if code.endswith(".TW") or code.endswith(".TWO"):
        return code

    return f"{code}.TW"


# ============================================================
# 股票名稱
# ============================================================

def get_stock_name(code):

    names = {
        "1101": "台泥",
        "1102": "亞泥",
        "1216": "統一",
        "1301": "台塑",
        "1303": "南亞",
        "2002": "中鋼",
        "2301": "光寶科",
        "2303": "聯電",
        "2308": "台達電",
        "2317": "鴻海",
        "2327": "國巨",
        "2330": "台積電",
        "2345": "智邦",
        "2357": "華碩",
        "2368": "金像電",
        "2379": "瑞昱",
        "2382": "廣達",
        "2395": "研華",
        "2408": "南亞科",
        "2412": "中華電",
        "2454": "聯發科",
        "2603": "長榮",
        "2609": "陽明",
        "2610": "華航",
        "2618": "長榮航",
        "3034": "聯詠",
        "3037": "欣興",
        "3045": "台灣大",
        "3231": "緯創",
        "3443": "創意",
        "3661": "世芯-KY",
        "3711": "日月光投控",
        "4904": "遠傳",
        "4938": "和碩",
        "5269": "祥碩",
        "5274": "信驊",
        "5483": "中美晶",
        "6239": "力成",
        "6415": "矽力*-KY",
        "6669": "緯穎",
        "6770": "力積電",
        "8046": "南電",
        "8069": "元太",
        "8299": "群聯",
    }

    return names.get(str(code), "")


# ============================================================
# 下載歷史資料
# ============================================================

def download_history(
    symbol,
    start_date=START_DATE,
    end_date=END_DATE
):

    ysymbol = yahoo_symbol(symbol)

    print(
        f"📥 下載歷史資料：{ysymbol} "
        f"{start_date} ~ {end_date}"
    )

    # 往前多抓一年，確保 MA60 / RSI / KD 等指標
    try:

        start_dt = pd.to_datetime(start_date) - pd.Timedelta(days=180)
        end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=5)

        df = yf.download(
            ysymbol,
            start=start_dt.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            auto_adjust=False,
            progress=False,
            threads=False,
        )

        if df is None or df.empty:
            print(f"⚠️ 無資料：{ysymbol}")
            return pd.DataFrame()

        # yfinance 新版有時會產生 MultiIndex
        if isinstance(df.columns, pd.MultiIndex):

            if len(df.columns.levels) > 1:

                try:
                    df.columns = df.columns.get_level_values(0)
                except Exception:
                    pass

        df = df.copy()

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        for col in required:

            if col not in df.columns:
                print(
                    f"⚠️ 缺少欄位 {col}：{ysymbol}"
                )
                return pd.DataFrame()

        df = df[required].copy()

        for col in required:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

        df.dropna(
            subset=["Close"],
            inplace=True
        )

        df.sort_index(inplace=True)

        return df

    except Exception as e:

        print(
            f"❌ 下載 {ysymbol} 失敗：{e}"
        )

        return pd.DataFrame()


# ============================================================
# 技術指標
# ============================================================

def calculate_indicators(df):

    df = df.copy()

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # --------------------------------------------------------
    # 均線
    # --------------------------------------------------------

    df["MA5"] = close.rolling(5).mean()
    df["MA10"] = close.rolling(10).mean()
    df["MA20"] = close.rolling(20).mean()
    df["MA60"] = close.rolling(60).mean()

    # --------------------------------------------------------
    # 乖離
    # --------------------------------------------------------

    df["MA10_DEV"] = (
        (close / df["MA10"]) - 1
    ) * 100

    df["MA20_DEV"] = (
        (close / df["MA20"]) - 1
    ) * 100

    # --------------------------------------------------------
    # 漲幅
    # --------------------------------------------------------

    df["GAIN_1D"] = (
        close / close.shift(1) - 1
    ) * 100

    df["GAIN_20D"] = (
        close / close.shift(20) - 1
    ) * 100

    # --------------------------------------------------------
    # 成交量
    #
    # 今日量 / 前5個完整交易日平均量
    # --------------------------------------------------------

    df["VOL5"] = volume.shift(1).rolling(5).mean()

    df["VOLUME_RATIO"] = (
        volume / df["VOL5"]
    )

    # --------------------------------------------------------
    # 成交金額
    # --------------------------------------------------------

    df["TURNOVER"] = (
        close * volume
    )

    # --------------------------------------------------------
    # KD
    # --------------------------------------------------------

    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()

    denominator = high9 - low9

    denominator = denominator.replace(
        0,
        np.nan
    )

    rsv = (
        (close - low9) /
        denominator *
        100
    )

    df["K"] = rsv.ewm(
        com=2,
        adjust=False
    ).mean()

    df["D"] = df["K"].ewm(
        com=2,
        adjust=False
    ).mean()

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / 14,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / 14,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan
    )

    df["RSI14"] = (
        100 -
        (100 / (1 + rs))
    )

    # 5期 RSI
    avg_gain5 = gain.ewm(
        alpha=1 / 5,
        adjust=False
    ).mean()

    avg_loss5 = loss.ewm(
        alpha=1 / 5,
        adjust=False
    ).mean()

    rs5 = avg_gain5 / avg_loss5.replace(
        0,
        np.nan
    )

    df["RSI5"] = (
        100 -
        (100 / (1 + rs5))
    )

    # 10期 RSI
    avg_gain10 = gain.ewm(
        alpha=1 / 10,
        adjust=False
    ).mean()

    avg_loss10 = loss.ewm(
        alpha=1 / 10,
        adjust=False
    ).mean()

    rs10 = avg_gain10 / avg_loss10.replace(
        0,
        np.nan
    )

    df["RSI10"] = (
        100 -
        (100 / (1 + rs10))
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    df["DIF"] = ema12 - ema26

    df["MACD_SIGNAL"] = df["DIF"].ewm(
        span=9,
        adjust=False
    ).mean()

    df["MACD_HIST"] = (
        df["DIF"] -
        df["MACD_SIGNAL"]
    )

    # --------------------------------------------------------
    # 52週高
    # --------------------------------------------------------

    df["HIGH_52W"] = (
        high.shift(1)
        .rolling(252)
        .max()
    )

    df["DIST_52W_HIGH"] = (
        close / df["HIGH_52W"] - 1
    ) * 100

    return df


# ============================================================
# 趨勢
# ============================================================

def trend_text(current, previous):

    if pd.isna(current) or pd.isna(previous):
        return "—"

    if current > previous:
        return "↑"

    if current < previous:
        return "↓"

    return "→"


# ============================================================
# 支撐
# ============================================================

def calculate_supports(df, i):

    start = max(0, i - 60)

    x = df.iloc[start:i + 1].copy()

    if len(x) < 10:
        return [np.nan, np.nan, np.nan]

    lows = x["Low"].dropna()

    if lows.empty:
        return [np.nan, np.nan, np.nan]

    values = sorted(
        lows.tolist(),
        reverse=True
    )

    supports = []

    current = float(
        df.iloc[i]["Close"]
    )

    for v in values:

        if v <= current:

            if not supports:
                supports.append(v)

            elif abs(v - supports[-1]) / max(
                abs(supports[-1]),
                0.0001
            ) > 0.01:

                supports.append(v)

        if len(supports) >= 3:
            break

    while len(supports) < 3:
        supports.append(np.nan)

    return supports


# ============================================================
# 壓力
# ============================================================

def calculate_resistances(df, i):

    start = max(0, i - 60)

    x = df.iloc[start:i + 1].copy()

    if len(x) < 10:
        return [np.nan, np.nan, np.nan]

    highs = x["High"].dropna()

    if highs.empty:
        return [np.nan, np.nan, np.nan]

    values = sorted(
        highs.tolist()
    )

    current = float(
        df.iloc[i]["Close"]
    )

    resistances = []

    for v in values:

        if v >= current:

            if not resistances:
                resistances.append(v)

            elif abs(v - resistances[-1]) / max(
                abs(resistances[-1]),
                0.0001
            ) > 0.01:

                resistances.append(v)

        if len(resistances) >= 3:
            break

    while len(resistances) < 3:
        resistances.append(np.nan)

    return resistances


# ============================================================
# 共振
# ============================================================

def resonance(df, i):

    row = df.iloc[i]

    score = 0

    # 均線
    if (
        row["MA5"] > row["MA10"] >
        row["MA20"]
    ):
        score += 1

    # KD
    if (
        not pd.isna(row["K"]) and
        not pd.isna(row["D"]) and
        row["K"] >= row["D"]
    ):
        score += 1

    # MACD
    if (
        not pd.isna(row["DIF"]) and
        not pd.isna(row["MACD_SIGNAL"]) and
        row["DIF"] >= row["MACD_SIGNAL"]
    ):
        score += 1

    if score >= 3:
        return "🔥 三線共振"

    if score == 2:
        return "🟡 2線共振"

    if score == 1:
        return "⚪ 1線"

    return "⚫ 無共振"


# ============================================================
# 6.1 訊號判斷
# ============================================================

def check_signal(df, i):

    if i < MIN_HISTORY:
        return False, []

    row = df.iloc[i]

    required = [
        "Close",
        "Volume",
        "MA10",
        "MA20",
        "MA60",
        "GAIN_1D",
        "GAIN_20D",
        "VOL5",
        "VOLUME_RATIO",
        "K",
        "D",
        "RSI5",
        "DIF",
        "MACD_SIGNAL",
    ]

    for col in required:

        if pd.isna(row[col]):
            return False, []

    reasons = []

    # --------------------------------------------------------
    # 1. 漲幅
    # --------------------------------------------------------

    if row["GAIN_1D"] >= MIN_GAIN:
        reasons.append("漲幅")

    else:
        return False, reasons

    # --------------------------------------------------------
    # 2. 量比
    # --------------------------------------------------------

    if row["VOLUME_RATIO"] >= VOLUME_RATIO_MIN:
        reasons.append("量能")

    else:
        return False, reasons

    # --------------------------------------------------------
    # 3. 成交金額
    # --------------------------------------------------------

    if row["TURNOVER"] >= MIN_TURNOVER:
        reasons.append("成交金額")

    else:
        return False, reasons

    # --------------------------------------------------------
    # 4. MA10乖離
    # --------------------------------------------------------

    if row["MA10_DEV"] <= MAX_MA10_DEV:
        reasons.append("MA10低乖離")

    else:
        return False, reasons

    # --------------------------------------------------------
    # 5. MA20乖離
    # --------------------------------------------------------

    if row["MA20_DEV"] <= MAX_MA20_DEV:
        reasons.append("MA20低乖離")

    else:
        return False, reasons

    # --------------------------------------------------------
    # 6. KD K上升或持平
    # --------------------------------------------------------

    if i >= 1:

        if (
            row["K"] >=
            df.iloc[i - 1]["K"]
        ):
            reasons.append("KD↑")

        else:
            return False, reasons

    # --------------------------------------------------------
    # 7. RSI5上升或持平
    # --------------------------------------------------------

    if i >= 1:

        if (
            row["RSI5"] >=
            df.iloc[i - 1]["RSI5"]
        ):
            reasons.append("RSI↑")

        else:
            return False, reasons

    # --------------------------------------------------------
    # 8. MACD DIF上升或持平
    # --------------------------------------------------------

    if i >= 1:

        if (
            row["DIF"] >=
            df.iloc[i - 1]["DIF"]
        ):
            reasons.append("MACD↑")

        else:
            return False, reasons

    return True, reasons


# ============================================================
# 計算訊號完整資料
# ============================================================

def build_signal_record(
    df,
    i,
    code,
    name,
    market=False
):

    row = df.iloc[i]

    date = df.index[i]

    if hasattr(date, "date"):
        date_text = str(date.date())
    else:
        date_text = str(date)

    supports = calculate_supports(
        df,
        i
    )

    resistances = calculate_resistances(
        df,
        i
    )

    current = float(row["Close"])

    s_dist = np.nan

    if not pd.isna(supports[0]):
        s_dist = (
            current / supports[0] - 1
        ) * 100

    r_dist = np.nan

    if not pd.isna(resistances[0]):
        r_dist = (
            resistances[0] / current - 1
        ) * 100

    # --------------------------------------------------------
    # 未來報酬
    # --------------------------------------------------------

    future = {}

    for h in [1, 3, 5, 10, 20]:

        j = i + h

        if j < len(df):

            future[h] = (
                df.iloc[j]["Close"] /
                current - 1
            ) * 100

        else:

            future[h] = np.nan

    # --------------------------------------------------------
    # 未來20日最高 / 最低
    # --------------------------------------------------------

    end_i = min(
        i + 20,
        len(df) - 1
    )

    if end_i > i:

        future_high = df.iloc[
            i + 1:end_i + 1
        ]["High"].max()

        future_low = df.iloc[
            i + 1:end_i + 1
        ]["Low"].min()

        max_gain_20 = (
            future_high / current - 1
        ) * 100

        max_loss_20 = (
            future_low / current - 1
        ) * 100

    else:

        max_gain_20 = np.nan
        max_loss_20 = np.nan

    record = {
        "date": date_text,
        "code": code,
        "name": name,
        "market": market,

        "close": current,

        "gain_1d": float(row["GAIN_1D"]),
        "gain_20d": float(row["GAIN_20D"]),

        "volume": float(row["Volume"]),
        "vol5": float(row["VOL5"]),
        "volume_ratio": float(row["VOLUME_RATIO"]),

        "turnover": float(row["TURNOVER"]),

        "s1": supports[0],
        "s2": supports[1],
        "s3": supports[2],

        "r1": resistances[0],
        "r2": resistances[1],
        "r3": resistances[2],

        "s1_dist": s_dist,
        "r1_dist": r_dist,

        "ma5": float(row["MA5"]),
        "ma10": float(row["MA10"]),
        "ma20": float(row["MA20"]),
        "ma60": float(row["MA60"]),

        "ma10_dev": float(row["MA10_DEV"]),
        "ma20_dev": float(row["MA20_DEV"]),

        "k": float(row["K"]),
        "d": float(row["D"]),

        "rsi5": float(row["RSI5"]),
        "rsi10": float(row["RSI10"]),

        "dif": float(row["DIF"]),

        "resonance": resonance(df, i),

        "high_52w": row["HIGH_52W"],
        "dist_52w_high": row["DIST_52W_HIGH"],

        "ret_1": future[1],
        "ret_3": future[3],
        "ret_5": future[5],
        "ret_10": future[10],
        "ret_20": future[20],

        "max_gain_20": max_gain_20,
        "max_loss_20": max_loss_20,
    }

    return record


# ============================================================
# 單一標的回測
# ============================================================

def backtest_symbol(
    symbol,
    name=None,
    market=False
):

    symbol = normalize_symbol(symbol)

    if market:

        yahoo = MARKET_SYMBOL
        display_code = "TWII"
        display_name = "加權指數"

    else:

        yahoo = yahoo_symbol(symbol)
        display_code = symbol
        display_name = (
            name
            if name
            else get_stock_name(symbol)
        )

    print(
        f"\n{'=' * 70}"
    )

    print(
        f"📊 開始回測："
        f"{display_code} {display_name}"
    )

    df = download_history(
        yahoo,
        START_DATE,
        END_DATE
    )

    if df.empty:

        return {
            "code": display_code,
            "name": display_name,
            "records": [],
            "error": "無法取得歷史資料"
        }

    df = calculate_indicators(df)

    # --------------------------------------------------------
    # 只在指定回測期間內找訊號
    # --------------------------------------------------------

    start_ts = pd.to_datetime(
        START_DATE
    )

    end_ts = pd.to_datetime(
        END_DATE
    )

    mask = (
        df.index >= start_ts
    ) & (
        df.index <= end_ts
    )

    test_indices = [
        i
        for i, idx in enumerate(df.index)
        if mask[i]
    ]

    records = []

    for i in test_indices:

        try:

            ok, reasons = check_signal(
                df,
                i
            )

            if not ok:
                continue

            record = build_signal_record(
                df,
                i,
                display_code,
                display_name,
                market=market
            )

            record["reasons"] = reasons

            records.append(record)

        except Exception as e:

            print(
                f"⚠️ {display_code} "
                f"{df.index[i]} 計算錯誤：{e}"
            )

    print(
        f"✅ {display_code} "
        f"找到 {len(records)} 個訊號"
    )

    return {
        "code": display_code,
        "name": display_name,
        "records": records,
        "error": ""
    }


# ============================================================
# 格式化數字
# ============================================================

def fmt_num(x, digits=2):

    try:

        if x is None or pd.isna(x):
            return "—"

        return f"{float(x):,.{digits}f}"

    except Exception:

        return "—"


def fmt_pct(x):

    try:

        if x is None or pd.isna(x):
            return "—"

        return f"{float(x):+.2f}%"

    except Exception:

        return "—"


def fmt_volume(x):

    try:

        if x is None or pd.isna(x):
            return "—"

        return f"{float(x) / 1000:,.1f}張"

    except Exception:

        return "—"


def fmt_money(x):

    try:

        if x is None or pd.isna(x):
            return "—"

        if abs(x) >= 100_000_000:
            return f"{x / 100_000_000:.2f}億"

        if abs(x) >= 10_000:
            return f"{x / 10_000:.0f}萬"

        return f"{x:,.0f}"

    except Exception:

        return "—"


# ============================================================
# 單筆訊號報告
# ============================================================

def signal_report(r):

    text = []

    text.append(
        f"📅 <b>{r['date']}</b>"
    )

    text.append(
        f"💰 股價：<b>{fmt_num(r['close'])}</b>"
        f"｜當日：<b>{fmt_pct(r['gain_1d'])}</b>"
    )

    text.append(
        f"📈 20日漲幅：{fmt_pct(r['gain_20d'])}"
    )

    text.append(
        f"📊 今日量：{fmt_volume(r['volume'])}"
    )

    text.append(
        f"📊 5日均量：{fmt_volume(r['vol5'])}"
    )

    text.append(
        f"🔥 量比：<b>{fmt_num(r['volume_ratio'], 2)}x</b>"
    )

    text.append(
        f"💵 成交金額：{fmt_money(r['turnover'])}"
    )

    text.append("")

    text.append(
        f"🟢 支撐："
        f"S1 {fmt_num(r['s1'])} "
        f"/ S2 {fmt_num(r['s2'])} "
        f"/ S3 {fmt_num(r['s3'])}"
    )

    text.append(
        f"📏 距S1：{fmt_pct(r['s1_dist'])}"
    )

    text.append(
        f"🔴 壓力："
        f"R1 {fmt_num(r['r1'])} "
        f"/ R2 {fmt_num(r['r2'])} "
        f"/ R3 {fmt_num(r['r3'])}"
    )

    text.append(
        f"📏 距R1：{fmt_pct(r['r1_dist'])}"
    )

    text.append("")

    text.append(
        f"📐 MA5 {fmt_num(r['ma5'])}"
        f"｜MA10 {fmt_num(r['ma10'])}"
        f"｜MA20 {fmt_num(r['ma20'])}"
    )

    text.append(
        f"📐 MA60 {fmt_num(r['ma60'])}"
    )

    text.append(
        f"📏 MA10乖離：{fmt_pct(r['ma10_dev'])}"
        f"｜MA20乖離：{fmt_pct(r['ma20_dev'])}"
    )

    text.append("")

    text.append(
        f"🎯 KD：K {fmt_num(r['k'])}"
        f" / D {fmt_num(r['d'])}"
    )

    text.append(
        f"📊 RSI5：{fmt_num(r['rsi5'])}"
        f"｜RSI10：{fmt_num(r['rsi10'])}"
    )

    text.append(
        f"📉 MACD DIF：{fmt_num(r['dif'], 3)}"
    )

    text.append(
        f"🔥 {r['resonance']}"
    )

    text.append("")

    text.append(
        f"🏔️ 52週高：{fmt_num(r['high_52w'])}"
        f"｜距高點：{fmt_pct(r['dist_52w_high'])}"
    )

    text.append("")

    text.append("<b>📈 後續報酬</b>")

    text.append(
        f"+1日：{fmt_pct(r['ret_1'])}"
        f"｜+3日：{fmt_pct(r['ret_3'])}"
    )

    text.append(
        f"+5日：{fmt_pct(r['ret_5'])}"
        f"｜+10日：{fmt_pct(r['ret_10'])}"
    )

    text.append(
        f"+20日：{fmt_pct(r['ret_20'])}"
    )

    text.append(
        f"🚀 20日最高：{fmt_pct(r['max_gain_20'])}"
        f"｜🔻最低：{fmt_pct(r['max_loss_20'])}"
    )

    return "\n".join(text)


# ============================================================
# 回測摘要
# ============================================================

def summarize_records(records):

    if not records:

        return {
            "count": 0
        }

    result = {
        "count": len(records)
    }

    for h in [
        1,
        3,
        5,
        10,
        20
    ]:

        key = f"ret_{h}"

        values = [
            r[key]
            for r in records
            if not pd.isna(r[key])
        ]

        if values:

            result[f"avg_{h}"] = float(
                np.mean(values)
            )

            result[f"win_{h}"] = float(
                np.mean(
                    np.array(values) > 0
                ) * 100
            )

        else:

            result[f"avg_{h}"] = np.nan
            result[f"win_{h}"] = np.nan

    max_gains = [
        r["max_gain_20"]
        for r in records
        if not pd.isna(r["max_gain_20"])
    ]

    max_losses = [
        r["max_loss_20"]
        for r in records
        if not pd.isna(r["max_loss_20"])
    ]

    result["avg_max_gain_20"] = (
        float(np.mean(max_gains))
        if max_gains
        else np.nan
    )

    result["avg_max_loss_20"] = (
        float(np.mean(max_losses))
        if max_losses
        else np.nan
    )

    return result


# ============================================================
# 摘要報告
# ============================================================

def summary_report(
    result
):

    code = result["code"]
    name = result["name"]
    records = result["records"]

    text = []

    text.append(
        f"📊 <b>{code} {name}</b>"
    )

    text.append(
        f"📅 回測：{START_DATE} ～ {END_DATE}"
    )

    if result.get("error"):

        text.append(
            f"❌ {result['error']}"
        )

        return "\n".join(text)

    summary = summarize_records(
        records
    )

    count = summary["count"]

    text.append(
        f"🔎 符合6.1條件："
        f"<b>{count}</b> 次"
    )

    if count == 0:

        text.append(
            "\n⚠️ 此期間沒有符合目前6.1條件的訊號。"
        )

        return "\n".join(text)

    text.append("")

    text.append("<b>📈 平均後續報酬</b>")

    text.append(
        f"+1日：{fmt_pct(summary['avg_1'])}"
        f"｜勝率 {fmt_num(summary['win_1'],1)}%"
    )

    text.append(
        f"+3日：{fmt_pct(summary['avg_3'])}"
        f"｜勝率 {fmt_num(summary['win_3'],1)}%"
    )

    text.append(
        f"+5日：{fmt_pct(summary['avg_5'])}"
        f"｜勝率 {fmt_num(summary['win_5'],1)}%"
    )

    text.append(
        f"+10日：{fmt_pct(summary['avg_10'])}"
        f"｜勝率 {fmt_num(summary['win_10'],1)}%"
    )

    text.append(
        f"+20日：{fmt_pct(summary['avg_20'])}"
        f"｜勝率 {fmt_num(summary['win_20'],1)}%"
    )

    text.append("")

    text.append(
        f"🚀 20日平均最大漲幅："
        f"{fmt_pct(summary['avg_max_gain_20'])}"
    )

    text.append(
        f"🔻 20日平均最大跌幅："
        f"{fmt_pct(summary['avg_max_loss_20'])}"
    )

    text.append("")

    # 最近5筆
    text.append(
        "<b>📌 最近訊號</b>"
    )

    for r in records[-5:][::-1]:

        text.append(
            f"{r['date']}｜"
            f"{fmt_pct(r['gain_1d'])}｜"
            f"量比 {fmt_num(r['volume_ratio'],2)}x"
        )

    return "\n".join(text)


# ============================================================
# 詳細訊號
# ============================================================

def latest_signal_report(
    result,
    max_records=5
):

    records = result["records"]

    if not records:
        return ""

    text = []

    text.append(
        f"\n<b>📋 最近 {min(max_records, len(records))} 次訊號明細</b>"
    )

    for r in records[-max_records:][::-1]:

        text.append("")

        text.append(
            signal_report(r)
        )

    return "\n".join(text)


# ============================================================
# MULTI
# ============================================================

def run_multi(codes):

    results = []

    for code in codes:

        code = code.strip()

        if not code:
            continue

        result = backtest_symbol(
            code,
            get_stock_name(code),
            False
        )

        results.append(result)

    return results


# ============================================================
# MULTI 報告
# ============================================================

def multi_report(results):

    text = []

    text.append(
        "<b>📊 Taiwan Stock Radar 6.1 MULTI 回測</b>"
    )

    text.append(
        f"📅 {START_DATE} ～ {END_DATE}"
    )

    text.append("")

    for result in results:

        summary = summarize_records(
            result["records"]
        )

        text.append(
            f"━━━━━━━━━━━━━━"
        )

        text.append(
            f"<b>{result['code']} "
            f"{result['name']}</b>"
        )

        if result.get("error"):

            text.append(
                f"❌ {result['error']}"
            )

            continue

        text.append(
            f"訊號：{summary['count']} 次"
        )

        if summary["count"]:

            text.append(
                f"+5日："
                f"{fmt_pct(summary['avg_5'])}"
                f"｜勝率 "
                f"{fmt_num(summary['win_5'],1)}%"
            )

            text.append(
                f"+20日："
                f"{fmt_pct(summary['avg_20'])}"
                f"｜勝率 "
                f"{fmt_num(summary['win_20'],1)}%"
            )

            text.append(
                f"20日最大漲："
                f"{fmt_pct(summary['avg_max_gain_20'])}"
            )

    return "\n".join(text)


# ============================================================
# ALL
# ============================================================

def run_all():

    results = []

    total = len(DEFAULT_STOCKS)

    print(
        f"🚀 ALL 回測開始，共 {total} 檔"
    )

    for n, code in enumerate(
        DEFAULT_STOCKS,
        1
    ):

        print(
            f"[{n}/{total}] "
            f"{code}"
        )

        result = backtest_symbol(
            code,
            get_stock_name(code),
            False
        )

        results.append(result)

    return results


# ============================================================
# ALL 摘要
# ============================================================

def all_report(results):

    rows = []

    for result in results:

        summary = summarize_records(
            result["records"]
        )

        if summary["count"] <= 0:
            continue

        rows.append(
            {
                "code": result["code"],
                "name": result["name"],
                "signals": summary["count"],
                "avg5": summary["avg_5"],
                "win5": summary["win_5"],
                "avg20": summary["avg_20"],
                "win20": summary["win_20"],
                "maxgain": summary["avg_max_gain_20"],
                "maxloss": summary["avg_max_loss_20"],
            }
        )

    if not rows:

        return (
            "<b>📊 ALL 回測</b>\n\n"
            "⚠️ 此期間沒有符合6.1條件的股票。"
        )

    rows.sort(
        key=lambda x: (
            x["avg20"]
            if not pd.isna(x["avg20"])
            else -999
        ),
        reverse=True
    )

    text = []

    text.append(
        "<b>📊 Taiwan Stock Radar 6.1 ALL 回測</b>"
    )

    text.append(
        f"📅 {START_DATE} ～ {END_DATE}"
    )

    text.append(
        f"🔎 有訊號：{len(rows)} 檔"
    )

    text.append("")

    text.append(
        "<b>🏆 +20日平均報酬排行</b>"
    )

    for n, x in enumerate(
        rows[:20],
        1
    ):

        text.append(
            f"{n}. "
            f"<b>{x['code']} {x['name']}</b> "
            f"訊號{x['signals']}次｜"
            f"+20日 {fmt_pct(x['avg20'])}｜"
            f"勝率 {fmt_num(x['win20'],1)}%"
        )

    return "\n".join(text)


# ============================================================
# 執行單一指令
# ============================================================

def execute_command(
    chat_id,
    command
):

    command = str(command).strip()

    print(
        "🧩 執行指令：",
        repr(command)
    )

    # --------------------------------------------------------
    # /start /help
    # --------------------------------------------------------

    if (
        command.startswith("/start")
        or command.startswith("/help")
    ):

        send(
            chat_id,
            help_text()
        )

        return

    # --------------------------------------------------------
    # /backtest
    # --------------------------------------------------------

    if command.startswith("/backtest"):

        q = command[
            len("/backtest"):
        ].strip()

        print(
            "🔎 Backtest 查詢內容：",
            repr(q)
        )

        if not q:

            send(
                chat_id,
                help_text()
            )

            return

        # ----------------------------------------------------
        # 大盤
        # ----------------------------------------------------

        if is_market_query(q):

            send(
                chat_id,
                (
                    "📊 <b>台股大盤歷史回測</b>\n"
                    f"📅 {START_DATE} ～ {END_DATE}\n"
                    "🔎 標的：^TWII\n\n"
                    "⏳ 正在逐日回測，請稍候..."
                )
            )

            try:

                result = backtest_symbol(
                    MARKET_SYMBOL,
                    "加權指數",
                    True
                )

                msg = summary_report(
                    result
                )

                msg += latest_signal_report(
                    result,
                    5
                )

                send(
                    chat_id,
                    msg
                )

            except Exception as e:

                print(
                    traceback.format_exc()
                )

                send(
                    chat_id,
                    f"❌ 大盤回測失敗：{e}"
                )

            return

        # ----------------------------------------------------
        # MULTI
        # ----------------------------------------------------

        if q.upper().startswith("MULTI"):

            rest = q[5:].strip()

            rest = rest.replace(
                " ",
                ""
            )

            codes = [
                x
                for x in rest.split(",")
                if x
            ]

            if not codes:

                send(
                    chat_id,
                    (
                        "⚠️ MULTI 格式錯誤\n\n"
                        "例如：\n"
                        "/backtest MULTI 2330,2454,3563"
                    )
                )

                return

            send(
                chat_id,
                (
                    "📊 <b>MULTI 回測開始</b>\n"
                    f"📌 股票數：{len(codes)} 檔\n"
                    f"📅 {START_DATE} ～ {END_DATE}\n\n"
                    "⏳ 請稍候..."
                )
            )

            try:

                results = run_multi(
                    codes
                )

                msg = multi_report(
                    results
                )

                send(
                    chat_id,
                    msg
                )

            except Exception as e:

                print(
                    traceback.format_exc()
                )

                send(
                    chat_id,
                    f"❌ MULTI 回測失敗：{e}"
                )

            return

        # ----------------------------------------------------
        # ALL
        # ----------------------------------------------------

        if q.upper() == "ALL":

            send(
                chat_id,
                (
                    "🚀 <b>ALL 全市場回測開始</b>\n"
                    f"📊 預計：{len(DEFAULT_STOCKS)} 檔\n"
                    f"📅 {START_DATE} ～ {END_DATE}\n\n"
                    "⏳ GitHub Actions 正在執行，"
                    "這可能需要較長時間。"
                )
            )

            try:

                results = run_all()

                msg = all_report(
                    results
                )

                send(
                    chat_id,
                    msg
                )

            except Exception as e:

                print(
                    traceback.format_exc()
                )

                send(
                    chat_id,
                    f"❌ ALL 回測失敗：{e}"
                )

            return

        # ----------------------------------------------------
        # 單股
        # ----------------------------------------------------

        # 移除可能的空白
        stock_query = q.strip()

        # 股票代號只接受數字
        match = re.search(
            r"\b(\d{4,6})\b",
            stock_query
        )

        if not match:

            send(
                chat_id,
                (
                    f"⚠️ 找不到「{stock_query}」\n\n"
                    "請輸入正確台股代號，例如：\n"
                    "/backtest 3563\n"
                    "/backtest 2435\n"
                    "/backtest 大盤"
                )
            )

            return

        code = match.group(1)

        send(
            chat_id,
            (
                f"📊 <b>{code} "
                f"{get_stock_name(code)}</b>\n"
                f"📅 {START_DATE} ～ {END_DATE}\n\n"
                "⏳ 歷史回測開始..."
            )
        )

        try:

            result = backtest_symbol(
                code,
                get_stock_name(code),
                False
            )

            msg = summary_report(
                result
            )

            msg += latest_signal_report(
                result,
                5
            )

            send(
                chat_id,
                msg
            )

        except Exception as e:

            print(
                traceback.format_exc()
            )

            send(
                chat_id,
                (
                    f"❌ {code} 回測失敗："
                    f"{e}"
                )
            )

        return

    # --------------------------------------------------------
    # 直接輸入股票代號
    # --------------------------------------------------------

    if re.fullmatch(
        r"\d{4,6}",
        command
    ):

        execute_command(
            chat_id,
            "/backtest " + command
        )

        return

    # --------------------------------------------------------
    # 其他文字
    # --------------------------------------------------------

    send(
        chat_id,
        (
            "⚠️ 我看不懂這個指令。\n\n"
            "請使用：\n"
            "/backtest 3563\n"
            "/backtest 2435\n"
            "/backtest 大盤\n"
            "/backtest MULTI 2330,2454,3563\n"
            "/backtest ALL"
        )
    )


# ============================================================
# Telegram Update
# ============================================================

def handle_update(update):

    message = update.get(
        "message",
        {}
    )

    chat = message.get(
        "chat",
        {}
    )

    chat_id = chat.get(
        "id"
    )

    text = message.get(
        "text"
    )

    if not chat_id or not text:
        return

    text = str(text).strip()

    print(
        "📨 收到 Telegram：",
        text,
        "chat_id=",
        chat_id
    )

    execute_command(
        chat_id,
        text
    )


# ============================================================
# Telegram Polling
# ============================================================

def polling():

    if not TOKEN:

        print(
            "❌ BACKTEST_TELEGRAM_BOT_TOKEN 未設定"
        )

        return

    offset = load_offset()

    print(
        "=================================================="
    )

    print(
        f"🤖 Taiwan Stock Radar {VERSION}"
    )

    print(
        "🔑 Token 設定正常"
    )

    print(
        f"📂 已讀取 Offset：{offset}"
    )

    print(
        "📡 正在取得 Telegram 新訊息..."
    )

    # --------------------------------------------------------
    # 如果環境變數有 CHAT_ID，直接使用
    # --------------------------------------------------------

    if CHAT_ID_ENV:

        print(
            f"💬 CHAT_ID：{CHAT_ID_ENV}"
        )

    while True:

        try:

            payload = {
                "timeout": 20,
                "limit": 100,
            }

            if offset > 0:
                payload["offset"] = offset

            result = telegram(
                "getUpdates",
                payload,
                timeout=40
            )

            if not result:

                time.sleep(3)

                continue

            if not result.get("ok"):

                print(
                    "❌ Telegram getUpdates 失敗：",
                    result
                )

                time.sleep(5)

                continue

            updates = result.get(
                "result",
                []
            )

            if not updates:

                print(
                    "📭 目前沒有新訊息"
                )

                # GitHub Actions 不需要永久等待
                break

            print(
                f"📨 收到 {len(updates)} 個 Update"
            )

            # ------------------------------------------------
            # 依序處理
            # ------------------------------------------------

            for update in updates:

                update_id = update.get(
                    "update_id"
                )

                print(
                    "🔢 Update ID：",
                    update_id
                )

                try:

                    handle_update(
                        update
                    )

                except Exception as e:

                    print(
                        "❌ 處理 Update 失敗：",
                        e
                    )

                    print(
                        traceback.format_exc()
                    )

                # ------------------------------------------------
                # 關鍵：
                # 已處理 update_id 後，
                # offset 必須設成 update_id + 1
                # ------------------------------------------------

                if update_id is not None:

                    offset = (
                        int(update_id) + 1
                    )

                    save_offset(
                        offset
                    )

                    print(
                        "💾 已儲存 Offset：",
                        offset
                    )

            # GitHub Actions 單次執行
            break

        except KeyboardInterrupt:

            print(
                "🛑 手動停止"
            )

            break

        except Exception as e:

            print(
                "❌ Polling 錯誤：",
                e
            )

            print(
                traceback.format_exc()
            )

            time.sleep(5)


# ============================================================
# Main
# ============================================================

def main():

    print(
        "============================================================"
    )

    print(
        f"🇹🇼 Taiwan Stock Radar {VERSION}"
    )

    print(
        "📅 回測期間：",
        START_DATE,
        "~",
        END_DATE
    )

    print(
        "============================================================"
    )

    polling()


if __name__ == "__main__":

    main()
