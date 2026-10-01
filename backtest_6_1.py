# ============================================================
# 台股飆股雷達 6.1 Backtest
# Taiwan Stock Radar 6.1 - Backtest
#
# 功能：
# 1. ALL：全市場回測
# 2. SINGLE：指定單一股票，例如 3563
# 3. MULTI：指定多檔股票，例如 3563,2330,2454
#
# 6.1 核心條件：
# - 今日漲幅 >= 3%
# - 今日成交量 >= 前5日平均成交量 × 1.8
# - 今日成交金額 > 2,000萬元
# - MA10 正乖離 <= 8%
# - MA20 正乖離 <= 12%
# - KD 9K 向上或平穩
# - RSI 5T 向上或平穩
# - MACD DIF(12,26) 向上或平穩
#
# 回測：
# +1 / +3 / +5 / +10 / +20 個交易日
# 並計算期間內最高漲幅、最低跌幅
# ============================================================

import os
import json
import time
import math
import warnings
import requests
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

VERSION = "6.1-BACKTEST"
# ============================================================
# Telegram 回測 Bot
# ============================================================

BACKTEST_TELEGRAM_BOT_TOKEN = os.getenv(
    "BACKTEST_TELEGRAM_BOT_TOKEN",
    ""
)

BACKTEST_TELEGRAM_CHAT_ID = os.getenv(
    "BACKTEST_TELEGRAM_CHAT_ID",
    ""
)
# ============================================================
# 6.1 條件
# ============================================================

MIN_GAIN = 3.0
MIN_VOLUME_RATIO = 1.8
MIN_TURNOVER = 20_000_000

MAX_MA10_DEVIATION = 8.0
MAX_MA20_DEVIATION = 12.0

# ============================================================
# GitHub Actions 環境變數
# ============================================================

MODE = os.getenv("MODE", "SINGLE").upper()

STOCK_CODES = os.getenv(
    "STOCK_CODES",
    "3563"
).strip()

START_DATE = os.getenv(
    "START_DATE",
    "2025-10-01"
).strip()

END_DATE = os.getenv(
    "END_DATE",
    "2026-09-30"
).strip()

# ============================================================
# 股票代號處理
# ============================================================

def normalize_code(code):
    code = str(code).strip()

    if not code:
        return ""

    # 已經是 Yahoo 格式
    if code.endswith(".TW") or code.endswith(".TWO"):
        return code

    return code


def get_yahoo_symbol(code):
    code = normalize_code(code)

    if code.endswith(".TW") or code.endswith(".TWO"):
        return code

    return code + ".TW"


def get_codes():
    """
    ALL：
        先使用環境變數 STOCK_CODES。
        若沒有指定，使用預設股票池。

    SINGLE：
        只回測一檔。

    MULTI：
        逗號分隔多檔。
    """

    if MODE == "SINGLE":
        return [normalize_code(STOCK_CODES.split(",")[0])]

    if MODE == "MULTI":
        return [
            normalize_code(x)
            for x in STOCK_CODES.split(",")
            if normalize_code(x)
        ]

    # --------------------------------------------------------
    # ALL 模式
    #
    # 這裡先使用常見大型/熱門股票池作為回測測試用。
    #
    # 真正完整全市場回測，下一階段再接你的
    # TWSE + TPEx 股票清單。
    # --------------------------------------------------------

    default_codes = [
        "1101", "1102", "1216",
        "1301", "1303",
        "1402", "1476",
        "1504", "1513", "1560",
        "1605", "1707",
        "2002", "2105",
        "2201", "2207",
        "2301", "2303", "2308", "2317",
        "2324", "2330", "2344", "2353",
        "2357", "2368", "2376", "2379",
        "2382", "2395", "2408", "2409",
        "2412", "2454", "2474", "2498",
        "2603", "2609",
        "2610", "2615",
        "2801", "2881", "2882", "2884",
        "2891", "2892",
        "2912",
        "3008", "3034", "3037",
        "3045", "3231",
        "3443", "3481",
        "3533", "3563",
        "3661", "3711",
        "4904",
        "4938",
        "5274",
        "5483",
        "6669",
        "8046",
        "8069",
        "8299"
    ]

    return default_codes


# ============================================================
# 技術指標
# ============================================================

def calculate_rsi(series, period=5):
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_kd(df, period=9):
    low_n = df["Low"].rolling(period).min()
    high_n = df["High"].rolling(period).max()

    denominator = (high_n - low_n).replace(0, np.nan)

    rsv = (
        (df["Close"] - low_n)
        / denominator
        * 100
    )

    k = rsv.ewm(
        alpha=1 / 3,
        adjust=False
    ).mean()

    d = k.ewm(
        alpha=1 / 3,
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

    macd = dif - dea

    return dif, dea, macd


# ============================================================
# 取得歷史資料
# ============================================================

def download_stock(code, start_date, end_date):

    symbol = get_yahoo_symbol(code)

    # 技術指標需要前置資料
    start_dt = pd.to_datetime(start_date) - pd.Timedelta(days=120)

    end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=35)

    print(
        f"下載 {symbol}："
        f"{start_dt.date()} ~ {end_dt.date()}"
    )

    try:

        df = yf.download(
            symbol,
            start=start_dt.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            auto_adjust=False,
            progress=False,
            threads=False
        )

    except Exception as e:

        print(
            f"❌ {code} 下載失敗：{e}"
        )

        return None

    if df is None or df.empty:
        print(f"⚠️ {code} 沒有資料")
        return None

    # --------------------------------------------------------
    # yfinance 有時會產生 MultiIndex
    # --------------------------------------------------------

    if isinstance(df.columns, pd.MultiIndex):

        try:
            df.columns = df.columns.get_level_values(0)
        except Exception:
            pass

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
                f"⚠️ {code} 缺少欄位：{col}"
            )
            return None

    df = df[required].copy()

    for col in required:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.dropna()

    if len(df) < 80:
        print(
            f"⚠️ {code} 歷史資料不足"
        )
        return None

    return df


# ============================================================
# 建立技術指標
# ============================================================

def prepare_indicators(df):

    df = df.copy()

    # --------------------------------------------------------
    # 均線
    # --------------------------------------------------------

    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA10"] = df["Close"].rolling(10).mean()
    df["MA20"] = df["Close"].rolling(20).mean()

    # --------------------------------------------------------
    # 5日平均成交量
    #
    # 非常重要：
    # 使用「前5個完整交易日」
    # 不把今天成交量算進平均值。
    # --------------------------------------------------------

    df["VOL5_PREV"] = (
        df["Volume"]
        .shift(1)
        .rolling(5)
        .mean()
    )

    # --------------------------------------------------------
    # 今日量比
    # --------------------------------------------------------

    df["VOLUME_RATIO"] = (
        df["Volume"]
        / df["VOL5_PREV"]
    )

    # --------------------------------------------------------
    # 成交金額
    # --------------------------------------------------------

    df["TURNOVER"] = (
        df["Close"]
        * df["Volume"]
    )

    # --------------------------------------------------------
    # 漲幅
    # --------------------------------------------------------

    df["GAIN"] = (
        df["Close"]
        / df["Close"].shift(1)
        - 1
    ) * 100

    # --------------------------------------------------------
    # MA10 / MA20 正乖離
    # --------------------------------------------------------

    df["MA10_DEV"] = (
        df["Close"]
        / df["MA10"]
        - 1
    ) * 100

    df["MA20_DEV"] = (
        df["Close"]
        / df["MA20"]
        - 1
    ) * 100

    # --------------------------------------------------------
    # KD
    # --------------------------------------------------------

    df["K"], df["D"] = calculate_kd(
        df,
        period=9
    )

    # --------------------------------------------------------
    # RSI 5T
    # --------------------------------------------------------

    df["RSI5"] = calculate_rsi(
        df["Close"],
        period=5
    )

    # --------------------------------------------------------
    # MACD DIF 12/26
    # --------------------------------------------------------

    (
        df["DIF"],
        df["DEA"],
        df["MACD"]
    ) = calculate_macd(
        df["Close"]
    )

    return df


# ============================================================
# 趨勢判斷
# ============================================================

def is_up_or_flat(series, tolerance=0.0):
    """
    判斷最近兩個數值：
    今天 >= 昨天
    就視為向上／平穩。

    這符合目前 6.1：
    不要求一定交叉。
    """

    if len(series) < 2:
        return False

    a = series.iloc[-2]
    b = series.iloc[-1]

    if pd.isna(a) or pd.isna(b):
        return False

    return b >= a - tolerance


# ============================================================
# 6.1 條件判斷
# ============================================================

def check_6_1(df, idx):

    if idx < 30:
        return None

    row = df.iloc[idx]

    # --------------------------------------------------------
    # 基本資料
    # --------------------------------------------------------

    if pd.isna(row["GAIN"]):
        return None

    if pd.isna(row["VOLUME_RATIO"]):
        return None

    if pd.isna(row["TURNOVER"]):
        return None

    # --------------------------------------------------------
    # 1. 今日漲幅 >= 3%
    # --------------------------------------------------------

    if row["GAIN"] < MIN_GAIN:
        return None

    # --------------------------------------------------------
    # 2. 今日量 >= 前5日平均量 × 1.8
    # --------------------------------------------------------

    if row["VOLUME_RATIO"] < MIN_VOLUME_RATIO:
        return None

    # --------------------------------------------------------
    # 3. 成交金額 > 2,000萬
    # --------------------------------------------------------

    if row["TURNOVER"] <= MIN_TURNOVER:
        return None

    # --------------------------------------------------------
    # 4. MA10乖離
    # --------------------------------------------------------

    if pd.isna(row["MA10_DEV"]):
        return None

    if row["MA10_DEV"] > MAX_MA10_DEVIATION:
        return None

    # --------------------------------------------------------
    # 5. MA20乖離
    # --------------------------------------------------------

    if pd.isna(row["MA20_DEV"]):
        return None

    if row["MA20_DEV"] > MAX_MA20_DEVIATION:
        return None

    # --------------------------------------------------------
    # 6. KD 9K 向上／平穩
    # --------------------------------------------------------

    k_values = df["K"].iloc[:idx + 1].dropna()

    if len(k_values) < 2:
        return None

    if not is_up_or_flat(k_values):
        return None

    # --------------------------------------------------------
    # 7. RSI 5T 向上／平穩
    # --------------------------------------------------------

    rsi_values = df["RSI5"].iloc[:idx + 1].dropna()

    if len(rsi_values) < 2:
        return None

    if not is_up_or_flat(rsi_values):
        return None

    # --------------------------------------------------------
    # 8. MACD DIF 12/26 向上／平穩
    # --------------------------------------------------------

    dif_values = df["DIF"].iloc[:idx + 1].dropna()

    if len(dif_values) < 2:
        return None

    if not is_up_or_flat(dif_values):
        return None

    return {
        "date": df.index[idx],
        "close": float(row["Close"]),
        "gain": float(row["GAIN"]),
        "volume": float(row["Volume"]),
        "vol5": float(row["VOL5_PREV"]),
        "volume_ratio": float(row["VOLUME_RATIO"]),
        "turnover": float(row["TURNOVER"]),
        "ma10": float(row["MA10"]),
        "ma20": float(row["MA20"]),
        "ma10_dev": float(row["MA10_DEV"]),
        "ma20_dev": float(row["MA20_DEV"]),
        "k": float(row["K"]),
        "d": float(row["D"]),
        "rsi5": float(row["RSI5"]),
        "dif": float(row["DIF"]),
        "dea": float(row["DEA"]),
    }


# ============================================================
# 回測未來表現
# ============================================================

def calculate_forward_returns(
    df,
    signal_idx,
    signal_price
):

    result = {}

    horizons = [
        1,
        3,
        5,
        10,
        20
    ]

    for h in horizons:

        future_idx = signal_idx + h

        if future_idx >= len(df):

            result[f"return_{h}d"] = np.nan

        else:

            future_close = float(
                df.iloc[future_idx]["Close"]
            )

            result[f"return_{h}d"] = (
                future_close
                / signal_price
                - 1
            ) * 100

    # --------------------------------------------------------
    # 後續20交易日最大漲幅
    # --------------------------------------------------------

    future_start = signal_idx + 1

    future_end = min(
        signal_idx + 20,
        len(df) - 1
    )

    if future_start <= future_end:

        future_high = df.iloc[
            future_start:future_end + 1
        ]["High"].max()

        future_low = df.iloc[
            future_start:future_end + 1
        ]["Low"].min()

        result["max_gain_20d"] = (
            future_high
            / signal_price
            - 1
        ) * 100

        result["max_loss_20d"] = (
            future_low
            / signal_price
            - 1
        ) * 100

    else:

        result["max_gain_20d"] = np.nan
        result["max_loss_20d"] = np.nan

    return result


# ============================================================
# 單檔股票回測
# ============================================================

def backtest_stock(code):

    print("")
    print("=" * 70)
    print(f"開始回測：{code}")
    print("=" * 70)

    df = download_stock(
        code,
        START_DATE,
        END_DATE
    )

    if df is None:
        return []

    df = prepare_indicators(df)

    # --------------------------------------------------------
    # 只在正式回測期間產生訊號
    # --------------------------------------------------------

    start_ts = pd.Timestamp(
        START_DATE
    )

    end_ts = pd.Timestamp(
        END_DATE
    )

    results = []

    for idx in range(len(df)):

        current_date = df.index[idx]

        # yfinance index 通常是 Timestamp
        if hasattr(current_date, "tz_localize"):

            try:
                current_date = current_date.tz_localize(None)
            except Exception:
                pass

        if current_date < start_ts:
            continue

        if current_date > end_ts:
            continue

        signal = check_6_1(
            df,
            idx
        )

        if signal is None:
            continue

        forward = calculate_forward_returns(
            df,
            idx,
            signal["close"]
        )

        result = {
            "code": code,
            "date": current_date.strftime("%Y-%m-%d"),
            "price": signal["close"],
            "gain": signal["gain"],
            "volume": signal["volume"],
            "vol5": signal["vol5"],
            "volume_ratio": signal["volume_ratio"],
            "turnover": signal["turnover"],
            "ma10": signal["ma10"],
            "ma20": signal["ma20"],
            "ma10_dev": signal["ma10_dev"],
            "ma20_dev": signal["ma20_dev"],
            "k": signal["k"],
            "d": signal["d"],
            "rsi5": signal["rsi5"],
            "dif": signal["dif"],
            "dea": signal["dea"],
        }

        result.update(forward)

        results.append(result)

    print(
        f"✅ {code}："
        f"找到 {len(results)} 次 6.1 訊號"
    )

    return results


# ============================================================
# 總結
# ============================================================

def create_summary(results_df):

    if results_df.empty:

        return pd.DataFrame([{
            "signals": 0,
            "avg_return_1d": np.nan,
            "avg_return_3d": np.nan,
            "avg_return_5d": np.nan,
            "avg_return_10d": np.nan,
            "avg_return_20d": np.nan,
            "win_rate_1d": np.nan,
            "win_rate_3d": np.nan,
            "win_rate_5d": np.nan,
            "win_rate_10d": np.nan,
            "win_rate_20d": np.nan,
            "avg_max_gain_20d": np.nan,
            "avg_max_loss_20d": np.nan,
        }])

    summary = {
        "signals": len(results_df),

        "avg_return_1d":
            results_df["return_1d"].mean(),

        "avg_return_3d":
            results_df["return_3d"].mean(),

        "avg_return_5d":
            results_df["return_5d"].mean(),

        "avg_return_10d":
            results_df["return_10d"].mean(),

        "avg_return_20d":
            results_df["return_20d"].mean(),

        "win_rate_1d":
            (
                results_df["return_1d"] > 0
            ).mean() * 100,

        "win_rate_3d":
            (
                results_df["return_3d"] > 0
            ).mean() * 100,

        "win_rate_5d":
            (
                results_df["return_5d"] > 0
            ).mean() * 100,

        "win_rate_10d":
            (
                results_df["return_10d"] > 0
            ).mean() * 100,

        "win_rate_20d":
            (
                results_df["return_20d"] > 0
            ).mean() * 100,

        "avg_max_gain_20d":
            results_df["max_gain_20d"].mean(),

        "avg_max_loss_20d":
            results_df["max_loss_20d"].mean(),
    }

    return pd.DataFrame([summary])


# ============================================================
# HTML Dashboard
# ============================================================

def create_dashboard(
    results_df,
    summary_df
):

    filename = "backtest_dashboard.html"

    if results_df.empty:

        html = """
        <html>
        <head>
        <meta charset="utf-8">
        <title>6.1 Backtest</title>
        </head>
        <body>
        <h1>台股飆股雷達 6.1 回測</h1>
        <h2>沒有符合條件的訊號</h2>
        </body>
        </html>
        """

    else:

        row = summary_df.iloc[0]

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">

        <title>台股飆股雷達 6.1 回測</title>

        <style>

        body {{
            font-family: Arial, sans-serif;
            margin: 30px;
            background: #f7f7f7;
        }}

        h1 {{
            margin-bottom: 5px;
        }}

        .card {{
            background: white;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 10px;
        }}

        table {{
            border-collapse: collapse;
            width: 100%;
            background: white;
        }}

        th, td {{
            border: 1px solid #ddd;
            padding: 7px;
            text-align: right;
        }}

        th {{
            background: #eee;
        }}

        </style>

        </head>

        <body>

        <h1>📊 台股飆股雷達 6.1 回測</h1>

        <div class="card">

        <h2>回測設定</h2>

        <p>
        模式：{MODE}
        </p>

        <p>
        股票：{STOCK_CODES}
        </p>

        <p>
        期間：{START_DATE}
        ～ {END_DATE}
        </p>

        </div>

        <div class="card">

        <h2>回測摘要</h2>

        <p>
        訊號數：
        <strong>{int(row["signals"])}</strong>
        </p>

        <p>
        1日平均報酬：
        {row["avg_return_1d"]:.2f}%
        </p>

        <p>
        3日平均報酬：
        {row["avg_return_3d"]:.2f}%
        </p>

        <p>
        5日平均報酬：
        {row["avg_return_5d"]:.2f}%
        </p>

        <p>
        10日平均報酬：
        {row["avg_return_10d"]:.2f}%
        </p>

        <p>
        20日平均報酬：
        {row["avg_return_20d"]:.2f}%
        </p>

        <hr>

        <p>
        1日上漲率：
        {row["win_rate_1d"]:.2f}%
        </p>

        <p>
        3日上漲率：
        {row["win_rate_3d"]:.2f}%
        </p>

        <p>
        5日上漲率：
        {row["win_rate_5d"]:.2f}%
        </p>

        <p>
        10日上漲率：
        {row["win_rate_10d"]:.2f}%
        </p>

        <p>
        20日上漲率：
        {row["win_rate_20d"]:.2f}%
        </p>

        <p>
        20日平均最大漲幅：
        {row["avg_max_gain_20d"]:.2f}%
        </p>

        <p>
        20日平均最大跌幅：
        {row["avg_max_loss_20d"]:.2f}%
        </p>

        </div>

        <div class="card">

        <h2>詳細訊號</h2>

        {results_df.to_html(
            index=False,
            float_format=lambda x: f"{x:.2f}"
        )}

        </div>

        </body>
        </html>
        """

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(html)

    print(
        f"✅ Dashboard 已建立：{filename}"
    )


# ============================================================
# 主程式
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("📊 台股飆股雷達 6.1 BACKTEST")
    print("=" * 70)

    print(f"版本：{VERSION}")
    print(f"模式：{MODE}")
    print(f"股票：{STOCK_CODES}")
    print(f"開始：{START_DATE}")
    print(f"結束：{END_DATE}")

    print("")
    print("6.1條件：")
    print(f"漲幅 >= {MIN_GAIN}%")
    print(f"量比 >= {MIN_VOLUME_RATIO}x")
    print(
        f"成交金額 > "
        f"{MIN_TURNOVER:,}"
    )
    print(
        f"MA10乖離 <= "
        f"{MAX_MA10_DEVIATION}%"
    )
    print(
        f"MA20乖離 <= "
        f"{MAX_MA20_DEVIATION}%"
    )

    codes = get_codes()

    print("")
    print(
        f"準備回測 {len(codes)} 檔股票"
    )

    all_results = []

    for i, code in enumerate(codes, 1):

        print(
            f"\n[{i}/{len(codes)}] "
            f"{code}"
        )

        try:

            results = backtest_stock(
                code
            )

            all_results.extend(
                results
            )

        except Exception as e:

            print(
                f"❌ {code} 發生錯誤：{e}"
            )

        # 避免過度頻繁請求 Yahoo
        time.sleep(0.5)

    # --------------------------------------------------------
    # 建立結果 DataFrame
    # --------------------------------------------------------

    results_df = pd.DataFrame(
        all_results
    )

    if not results_df.empty:

        results_df = results_df.sort_values(
            by=[
                "date",
                "volume_ratio"
            ],
            ascending=[
                True,
                False
            ]
        )

    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    results_file = (
        "backtest_results.csv"
    )

    results_df.to_csv(
        results_file,
        index=False,
        encoding="utf-8-sig"
    )

    print("")
    print(
        f"✅ 詳細結果：{results_file}"
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary_df = create_summary(
        results_df
    )

    summary_file = (
        "backtest_summary.csv"
    )

    summary_df.to_csv(
        summary_file,
        index=False,
        encoding="utf-8-sig"
    )

    print(
        f"✅ 摘要結果：{summary_file}"
    )

    # --------------------------------------------------------
    # Dashboard
    # --------------------------------------------------------

    create_dashboard(
        results_df,
        summary_df
    )
# ============================================================
# Telegram 發送回測結果
# ============================================================
print("====================================")
print("📨 準備發送 Telegram 回測結果")
print("BOT TOKEN 是否存在：", bool(BACKTEST_TELEGRAM_BOT_TOKEN))
print("CHAT ID 是否存在：", bool(BACKTEST_TELEGRAM_CHAT_ID))
print("====================================")
def send_telegram(message):

    if not BACKTEST_TELEGRAM_BOT_TOKEN:
        print("⚠️ 沒有設定 BACKTEST_TELEGRAM_BOT_TOKEN")
        return False

    if not BACKTEST_TELEGRAM_CHAT_ID:
        print("⚠️ 沒有設定 BACKTEST_TELEGRAM_CHAT_ID")
        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{BACKTEST_TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": BACKTEST_TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    try:

        response = requests.post(
            url,
            data=payload,
            timeout=30
        )

        if response.ok:
            print("✅ Telegram 回測結果已送出")
            return True

        print(
            "❌ Telegram 發送失敗：",
            response.text
        )

    except Exception as e:

        print(
            "❌ Telegram 發送錯誤：",
            e
        )

    return False
    # --------------------------------------------------------
    # 終端顯示
    # --------------------------------------------------------

    print("")
    print("=" * 70)
    print("📊 6.1 回測完成")
    print("=" * 70)

    if not results_df.empty:

        row = summary_df.iloc[0]

        print(
            f"訊號數："
            f"{int(row['signals'])}"
        )

        print(
            f"1日平均報酬："
            f"{row['avg_return_1d']:.2f}%"
        )

        print(
            f"3日平均報酬："
            f"{row['avg_return_3d']:.2f}%"
        )

        print(
            f"5日平均報酬："
            f"{row['avg_return_5d']:.2f}%"
        )

        print(
            f"10日平均報酬："
            f"{row['avg_return_10d']:.2f}%"
        )

        print(
            f"20日平均報酬："
            f"{row['avg_return_20d']:.2f}%"
        )

    else:

        print(
            "⚠️ 此期間沒有符合 6.1 "
            "條件的股票。"
        )

    print("")
    print("輸出檔案：")
    print("1. backtest_results.csv")
    print("2. backtest_summary.csv")
    print("3. backtest_dashboard.html")
    # ========================================================
    # Telegram 回測摘要
    # ========================================================

    if not results_df.empty:

        row = summary_df.iloc[0]

        message = f"""
<b>📊 台股飆股雷達 6.1 回測</b>

🔎 模式：{MODE}
📌 股票：{STOCK_CODES}
📅 期間：{START_DATE} ～ {END_DATE}

<b>📈 平均報酬</b>

+1日：{row["avg_return_1d"]:.2f}%
+3日：{row["avg_return_3d"]:.2f}%
+5日：{row["avg_return_5d"]:.2f}%
+10日：{row["avg_return_10d"]:.2f}%
+20日：{row["avg_return_20d"]:.2f}%

<b>🎯 上漲機率</b>

+1日：{row["win_rate_1d"]:.2f}%
+3日：{row["win_rate_3d"]:.2f}%
+5日：{row["win_rate_5d"]:.2f}%
+10日：{row["win_rate_10d"]:.2f}%
+20日：{row["win_rate_20d"]:.2f}%

<b>📊 其他統計</b>

符合訊號：{int(row["signals"])} 次
20日平均最大漲幅：{row["avg_max_gain_20d"]:.2f}%
20日平均最大跌幅：{row["avg_max_loss_20d"]:.2f}%

📁 詳細結果已產生 CSV 與 Dashboard。
"""

    else:

        message = f"""
<b>📊 台股飆股雷達 6.1 回測</b>

📌 股票：{STOCK_CODES}
📅 期間：{START_DATE} ～ {END_DATE}

⚠️ 此期間沒有符合 6.1 條件的訊號。
"""

    send_telegram(message)

if __name__ == "__main__":
    main()
