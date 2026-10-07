# ============================================================
# Taiwan Stock Radar 6.1
# Telegram 技術分析機器人
#
# 功能：
# 1. 輸入股票代號，例如：3563
# 2. 輸入股票名稱，例如：牧德
# 3. /分析 3563
# 4. /分析 牧德
# 5. 大盤 / TWII / TAIEX
#
# 分析內容：
# - 現價
# - 今日漲跌
# - 今日成交量
# - 5日平均成交量
# - 量比
# - 成交金額
# - MA5 / MA10 / MA20 / MA60
# - MA10 / MA20 乖離
# - KD
# - RSI5 / RSI10
# - MACD DIF / DEA
# - 三線共振
# - 支撐 S1 / S2 / S3
# - 壓力 R1 / R2 / R3
# - 52週高點
# - 距離52週高點
# - 20日漲跌
#
# 大盤：
# - ^TWII
# - MA5 / MA10 / MA20 / MA60
# - KD
# - RSI
# - MACD
# - 支撐 / 壓力
# - 52週高點
# - 市場多空狀態
#
# 注意：
# 本程式「不是回測程式」
# 不會執行 SINGLE / MULTI / ALL
# 不會要求輸入日期區間
# 不會計算未來 +1 / +3 / +5 / +10 / +20
# ============================================================


import os
import time
import warnings
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf


# ============================================================
# 基本設定
# ============================================================

warnings.filterwarnings("ignore")

VERSION = "6.1-TECH-BOT-20261007"

print("🔥🔥🔥 RUNNING NEW 6.1 TECH BOT 🔥🔥🔥")
print("VERSION =", VERSION)

TZ = ZoneInfo("Asia/Taipei")

TOKEN = os.getenv("BACKTEST_TELEGRAM_BOT_TOKEN", "").strip()

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
})


# ============================================================
# 大盤設定
# ============================================================

MARKET_SYMBOL = "^TWII"

MARKET_KEYWORDS = {
    "大盤",
    "台股大盤",
    "加權",
    "加權指數",
    "台灣加權",
    "台股",
    "TAIEX",
    "TWII",
    "^TWII"
}


# ============================================================
# 基本工具
# ============================================================

def now():
    return datetime.now(TZ)


def log(msg):
    print(f"[{now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def fmt(v, digits=2):
    try:
        if v is None:
            return "-"
        if pd.isna(v):
            return "-"
        return f"{float(v):,.{digits}f}"
    except Exception:
        return "-"


def pct(v, digits=2):
    try:
        if v is None:
            return "-"
        if pd.isna(v):
            return "-"
        return f"{float(v):+,.{digits}f}%"
    except Exception:
        return "-"


def icon(v):
    try:
        if float(v) > 0:
            return "🟢"
        if float(v) < 0:
            return "🔴"
        return "🟡"
    except Exception:
        return "🟡"


# ============================================================
# 判斷是不是大盤
# ============================================================

def is_market_query(q):

    if q is None:
        return False

    q = str(q).strip()
    q = q.replace("\u3000", "")

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
# Telegram API
# ============================================================

def telegram(method, payload=None, timeout=30):

    if not TOKEN:
        raise RuntimeError(
            "BACKTEST_TELEGRAM_BOT_TOKEN 未設定"
        )

    url = f"https://api.telegram.org/bot{TOKEN}/{method}"

    try:

        r = SESSION.post(
            url,
            json=payload or {},
            timeout=timeout
        )

        log(
            f"Telegram {method} HTTP Status："
            f"{r.status_code}"
        )

        r.raise_for_status()

        return r.json()

    except Exception as e:

        log(
            f"❌ Telegram {method} 發生錯誤：{e}"
        )

        return {}


def send(chat_id, text):

    if not chat_id:
        return

    telegram(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
    )


# ============================================================
# 取得股票清單
# ============================================================

def stock_list():

    stocks = []

    # --------------------------------------------------------
    # TWSE
    # --------------------------------------------------------

    try:

        url = (
            "https://openapi.twse.com.tw/"
            "v1/exchangeReport/STOCK_DAY_ALL"
        )

        r = SESSION.get(
            url,
            timeout=20
        )

        r.raise_for_status()

        data = r.json()

        for x in data:

            code = str(
                x.get("Code", "")
            ).strip()

            name = str(
                x.get("Name", "")
            ).strip()

            if not code:
                continue

            if not code.isdigit():
                continue

            if len(code) != 4:
                continue

            if code.startswith(
                ("00", "01", "02", "03")
            ):
                continue

            stocks.append({
                "code": code,
                "name": name,
                "market": "TWSE"
            })

        log(
            f"TWSE 股票數：{len(stocks)}"
        )

    except Exception as e:

        log(
            f"⚠️ TWSE 股票清單取得失敗：{e}"
        )

    # --------------------------------------------------------
    # TPEx
    # --------------------------------------------------------

    try:

        url = (
            "https://www.tpex.org.tw/"
            "openapi/v1/tpex_mainboard_quotes"
        )

        r = SESSION.get(
            url,
            timeout=20
        )

        r.raise_for_status()

        data = r.json()

        for x in data:

            code = str(
                x.get("SecuritiesCompanyCode", "")
            ).strip()

            name = str(
                x.get("CompanyName", "")
            ).strip()

            if not code:
                continue

            if not code.isdigit():
                continue

            if len(code) != 4:
                continue

            if code.startswith(
                ("00", "01", "02", "03")
            ):
                continue

            stocks.append({
                "code": code,
                "name": name,
                "market": "TPEx"
            })

        log(
            f"TPEx 加入後股票數：{len(stocks)}"
        )

    except Exception as e:

        log(
            f"⚠️ TPEx 股票清單取得失敗：{e}"
        )

    # --------------------------------------------------------
    # 去除重複
    # --------------------------------------------------------

    result = []

    seen = set()

    for x in stocks:

        key = (
            x["market"],
            x["code"]
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(x)

    log(
        f"📊 最終股票清單：{len(result)}"
    )

    return result


# ============================================================
# Yahoo Finance 歷史資料
# ============================================================

def yf_history(symbol, period="1y"):

    log(
        f"📡 取得 Yahoo Finance：{symbol}"
    )

    try:

        d = yf.download(
            symbol,
            period=period,
            interval="1d",
            auto_adjust=False,
            actions=False,
            progress=False,
            threads=False
        )

        if d is None or d.empty:

            log(
                f"❌ {symbol} 沒有資料"
            )

            return None

        # ----------------------------------------------------
        # MultiIndex 處理
        # ----------------------------------------------------

        if isinstance(d.columns, pd.MultiIndex):

            cols0 = list(
                d.columns.get_level_values(0)
            )

            cols1 = list(
                d.columns.get_level_values(1)
            )

            if symbol in cols1:

                try:

                    d = d.xs(
                        symbol,
                        axis=1,
                        level=1
                    )

                except Exception:
                    pass

            elif symbol in cols0:

                try:

                    d = d.xs(
                        symbol,
                        axis=1,
                        level=0
                    )

                except Exception:
                    pass

            else:

                try:

                    d.columns = [
                        x[0]
                        for x in d.columns
                    ]

                except Exception:
                    pass

        # ----------------------------------------------------
        # 日期處理
        # ----------------------------------------------------

        d = d.copy()

        if not isinstance(
            d.index,
            pd.DatetimeIndex
        ):

            d.index = pd.to_datetime(
                d.index,
                errors="coerce"
            )

        d = d[
            ~d.index.isna()
        ]

        try:

            if d.index.tz is not None:

                d.index = d.index.tz_convert(
                    TZ
                ).tz_localize(None)

        except Exception:

            try:

                d.index = d.index.tz_localize(
                    None
                )

            except Exception:
                pass

        # ----------------------------------------------------
        # 必要欄位
        # ----------------------------------------------------

        required = [
            "Open",
            "High",
            "Low",
            "Close"
        ]

        for col in required:

            if col not in d.columns:

                log(
                    f"❌ {symbol} 缺少欄位：{col}"
                )

                return None

        # ----------------------------------------------------
        # 數值轉換
        # ----------------------------------------------------

        for col in [
            "Open",
            "High",
            "Low",
            "Close"
        ]:

            d[col] = pd.to_numeric(
                d[col],
                errors="coerce"
            )

        if "Volume" in d.columns:

            d["Volume"] = pd.to_numeric(
                d["Volume"],
                errors="coerce"
            )

        d = d.dropna(
            subset=[
                "Open",
                "High",
                "Low",
                "Close"
            ]
        )

        if len(d) < 70:

            log(
                f"❌ {symbol} 有效資料不足："
                f"{len(d)}"
            )

            return None

        return d

    except Exception as e:

        log(
            f"❌ Yahoo {symbol} 錯誤：{e}"
        )

        return None


# ============================================================
# 股票歷史資料
# ============================================================

def stock_history(symbol):

    d = yf_history(
        symbol,
        "1y"
    )

    if d is None:
        return None

    if "Volume" not in d.columns:

        d["Volume"] = 0

    d["Volume"] = pd.to_numeric(
        d["Volume"],
        errors="coerce"
    ).fillna(0)

    return d


# ============================================================
# 找股票
# ============================================================

def find_stock(q):

    if q is None:
        return None, None

    q = str(q).strip()

    q = q.replace(
        "\u3000",
        ""
    )

    # --------------------------------------------------------
    # 清除指令
    # --------------------------------------------------------

    if q.startswith("/分析"):

        q = q[
            len("/分析"):
        ].strip()

    elif q.lower().startswith(
        "/analyze"
    ):

        q = q[
            len("/analyze"):
        ].strip()

    # --------------------------------------------------------
    # 大盤
    # --------------------------------------------------------

    if is_market_query(q):

        return {
            "code": "TWII",
            "name": "加權指數",
            "market": "TWSE",
            "symbol": "^TWII"
        }, None

    # --------------------------------------------------------
    # 股票清單
    # --------------------------------------------------------

    stocks = stock_list()

    if not stocks:

        return None, (
            "❌ 無法取得股票清單，"
            "請稍後再試。"
        )

    # --------------------------------------------------------
    # 代號
    # --------------------------------------------------------

    if q.isdigit():

        exact = [
            x for x in stocks
            if x["code"] == q
        ]

        # 先找股票清單
        for x in exact:

            symbol = (
                f'{x["code"]}.TW'
                if x["market"] == "TWSE"
                else
                f'{x["code"]}.TWO'
            )

            d = stock_history(symbol)

            if d is not None:

                x = x.copy()

                x["symbol"] = symbol

                return x, None

        # ----------------------------------------------------
        # fallback
        # ----------------------------------------------------

        for suffix in [
            ".TW",
            ".TWO"
        ]:

            symbol = q + suffix

            d = stock_history(symbol)

            if d is not None:

                return {
                    "code": q,
                    "name": q,
                    "market": (
                        "TWSE"
                        if suffix == ".TW"
                        else "TPEx"
                    ),
                    "symbol": symbol
                }, None

        return None, (
            f"❌ 找不到股票 {q} "
            f"或目前無法取得 Yahoo 資料。"
        )

    # --------------------------------------------------------
    # 名稱
    # --------------------------------------------------------

    exact_name = [
        x for x in stocks
        if x["name"] == q
    ]

    partial_name = [
        x for x in stocks
        if q in x["name"]
    ]

    candidates = (
        exact_name
        if exact_name
        else partial_name
    )

    for x in candidates:

        symbol = (
            f'{x["code"]}.TW'
            if x["market"] == "TWSE"
            else
            f'{x["code"]}.TWO'
        )

        d = stock_history(symbol)

        if d is not None:

            x = x.copy()

            x["symbol"] = symbol

            return x, None

    return None, (
        f"❌ 找不到「{q}」對應股票。"
    )


# ============================================================
# KD
# ============================================================

def kd(d):

    high = d["High"]

    low = d["Low"]

    close = d["Close"]

    low9 = low.rolling(
        9
    ).min()

    high9 = high.rolling(
        9
    ).max()

    denominator = (
        high9 - low9
    ).replace(
        0,
        np.nan
    )

    rsv = (
        (close - low9)
        / denominator
        * 100
    )

    k = rsv.ewm(
        com=2,
        adjust=False
    ).mean()

    j = (
        3 * k
        - 2 * k.ewm(
            com=2,
            adjust=False
        ).mean()
    )

    dline = k.ewm(
        com=2,
        adjust=False
    ).mean()

    return k, dline, j


# ============================================================
# RSI
# ============================================================

def rsi(close, p=14):

    delta = close.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = gain.ewm(
        alpha=1 / p,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / p,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan
    )

    result = 100 - (
        100 / (1 + rs)
    )

    return result


# ============================================================
# MACD
# ============================================================

def macd(close):

    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    dif = ema12 - ema26

    dea = dif.ewm(
        span=9,
        adjust=False
    ).mean()

    hist = dif - dea

    return dif, dea, hist


# ============================================================
# 趨勢
# ============================================================

def trend(s, norm=True):

    try:

        if len(s) < 6:
            return 0

        a = float(
            s.iloc[-1]
        )

        b = float(
            s.iloc[-6]
        )

        if pd.isna(a) or pd.isna(b):
            return 0

        if a > b:
            return 1

        if a < b:
            return -1

        return 0

    except Exception:

        return 0


# ============================================================
# 支撐
# ============================================================

def supports(d, price):

    levels = []

    low = d["Low"]

    # 最近局部低點
    try:

        for i in range(
            max(2, len(d) - 80),
            len(d) - 2
        ):

            if (
                low.iloc[i] <= low.iloc[i - 1]
                and
                low.iloc[i] <= low.iloc[i + 1]
                and
                low.iloc[i] < price
            ):

                levels.append(
                    float(low.iloc[i])
                )

    except Exception:
        pass

    # 均線
    for n in [
        10,
        20,
        60
    ]:

        if len(d) >= n:

            ma = (
                d["Close"]
                .rolling(n)
                .mean()
                .iloc[-1]
            )

            if (
                pd.notna(ma)
                and ma < price
            ):

                levels.append(
                    float(ma)
                )

    # 近期低點
    for n in [
        20,
        60
    ]:

        if len(d) >= n:

            x = (
                d["Low"]
                .tail(n)
                .min()
            )

            if (
                pd.notna(x)
                and x < price
            ):

                levels.append(
                    float(x)
                )

    levels = sorted(
        set(
            round(x, 2)
            for x in levels
        ),
        reverse=True
    )

    result = []

    for x in levels:

        if x < price:

            if not result:

                result.append(x)

            elif all(
                abs(x - y)
                / max(y, 0.01)
                > 0.01
                for y in result
            ):

                result.append(x)

        if len(result) >= 3:
            break

    return result


# ============================================================
# 壓力
# ============================================================

def resistances(d, price):

    levels = []

    high = d["High"]

    # 最近局部高點
    try:

        for i in range(
            max(2, len(d) - 80),
            len(d) - 2
        ):

            if (
                high.iloc[i] >= high.iloc[i - 1]
                and
                high.iloc[i] >= high.iloc[i + 1]
                and
                high.iloc[i] > price
            ):

                levels.append(
                    float(high.iloc[i])
                )

    except Exception:
        pass

    # 均線
    for n in [
        10,
        20,
        60
    ]:

        if len(d) >= n:

            ma = (
                d["Close"]
                .rolling(n)
                .mean()
                .iloc[-1]
            )

            if (
                pd.notna(ma)
                and ma > price
            ):

                levels.append(
                    float(ma)
                )

    # 近期高點
    for n in [
        20,
        60
    ]:

        if len(d) >= n:

            x = (
                d["High"]
                .tail(n)
                .max()
            )

            if (
                pd.notna(x)
                and x > price
            ):

                levels.append(
                    float(x)
                )

    levels = sorted(
        set(
            round(x, 2)
            for x in levels
        )
    )

    result = []

    for x in levels:

        if x > price:

            if not result:

                result.append(x)

            elif all(
                abs(x - y)
                / max(y, 0.01)
                > 0.01
                for y in result
            ):

                result.append(x)

        if len(result) >= 3:
            break

    return result


# ============================================================
# 三線共振
# ============================================================

def resonance(
    close,
    ma20,
    kd_k,
    rsi5,
    dif
):

    score = 0

    # 股價 / MA20
    if close > ma20:
        score += 1
    else:
        score -= 1

    # KD
    if kd_k >= 50:
        score += 1
    else:
        score -= 1

    # RSI
    if rsi5 >= 50:
        score += 1
    else:
        score -= 1

    # MACD
    if dif >= 0:
        score += 1
    else:
        score -= 1

    if score >= 3:
        return "🔥 多方共振"

    if score >= 1:
        return "🟢 偏多"

    if score <= -3:
        return "🔴 空方共振"

    return "🟡 震盪"


# ============================================================
# 個股分析
# ============================================================

def analyze_stock(stock):

    symbol = stock["symbol"]

    d = stock_history(symbol)

    if d is None:

        return None, (
            "❌ 無法取得股票歷史資料。"
        )

    close = d["Close"]

    price = float(
        close.iloc[-1]
    )

    prev = float(
        close.iloc[-2]
    )

    change = (
        price / prev - 1
    ) * 100 if prev else np.nan

    # --------------------------------------------------------
    # 成交量
    # --------------------------------------------------------

    today_volume = float(
        d["Volume"].iloc[-1]
    )

    if len(d) >= 6:

        avg5 = float(
            d["Volume"]
            .iloc[-6:-1]
            .mean()
        )

    else:

        avg5 = np.nan

    volume_ratio = (
        today_volume / avg5
        if avg5 and avg5 > 0
        else np.nan
    )

    turnover = (
        price * today_volume
    )

    # --------------------------------------------------------
    # 均線
    # --------------------------------------------------------

    ma5 = (
        close
        .rolling(5)
        .mean()
        .iloc[-1]
    )

    ma10 = (
        close
        .rolling(10)
        .mean()
        .iloc[-1]
    )

    ma20 = (
        close
        .rolling(20)
        .mean()
        .iloc[-1]
    )

    ma60 = (
        close
        .rolling(60)
        .mean()
        .iloc[-1]
    )

    dev10 = (
        (price / ma10 - 1) * 100
        if ma10
        else np.nan
    )

    dev20 = (
        (price / ma20 - 1) * 100
        if ma20
        else np.nan
    )

    # --------------------------------------------------------
    # KD
    # --------------------------------------------------------

    k, kd_d, j = kd(d)

    k_now = float(
        k.iloc[-1]
    )

    d_now = float(
        kd_d.iloc[-1]
    )

    k_prev = float(
        k.iloc[-2]
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    rsi5_series = rsi(
        close,
        5
    )

    rsi10_series = rsi(
        close,
        10
    )

    rsi5_now = float(
        rsi5_series.iloc[-1]
    )

    rsi10_now = float(
        rsi10_series.iloc[-1]
    )

    rsi5_prev = float(
        rsi5_series.iloc[-2]
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    dif_series, dea_series, hist_series = macd(
        close
    )

    dif_now = float(
        dif_series.iloc[-1]
    )

    dea_now = float(
        dea_series.iloc[-1]
    )

    hist_now = float(
        hist_series.iloc[-1]
    )

    dif_prev = float(
        dif_series.iloc[-2]
    )

    # --------------------------------------------------------
    # 支撐 / 壓力
    # --------------------------------------------------------

    s_levels = supports(
        d,
        price
    )

    r_levels = resistances(
        d,
        price
    )

    while len(s_levels) < 3:
        s_levels.append(np.nan)

    while len(r_levels) < 3:
        r_levels.append(np.nan)

    # --------------------------------------------------------
    # 52週高點
    # --------------------------------------------------------

    high52 = float(
        d["High"].tail(252).max()
    )

    distance52 = (
        (price / high52 - 1)
        * 100
        if high52
        else np.nan
    )

    # --------------------------------------------------------
    # 20日漲跌
    # --------------------------------------------------------

    if len(close) >= 21:

        price20 = float(
            close.iloc[-21]
        )

        gain20 = (
            price / price20 - 1
        ) * 100

    else:

        gain20 = np.nan

    # --------------------------------------------------------
    # 三線共振
    # --------------------------------------------------------

    resonance_text = resonance(
        price,
        ma20,
        k_now,
        rsi5_now,
        dif_now
    )

    # --------------------------------------------------------
    # 狀態
    # --------------------------------------------------------

    score = 0

    if price > ma20:
        score += 2
    else:
        score -= 2

    if trend(close) > 0:
        score += 1
    else:
        score -= 1

    if k_now > d_now:
        score += 1
    else:
        score -= 1

    if rsi5_now >= 50:
        score += 1
    else:
        score -= 1

    if dif_now > dea_now:
        score += 2
    else:
        score -= 2

    if volume_ratio >= 1.8:
        score += 1

    if dev10 <= 8:
        score += 1
    else:
        score -= 1

    if dev20 <= 12:
        score += 1
    else:
        score -= 1

    if score >= 6:

        status = "🟢 強勢"

    elif score >= 3:

        status = "🟡 偏多"

    elif score <= -4:

        status = "🔴 偏弱"

    else:

        status = "🟠 震盪"

    # --------------------------------------------------------
    # 追高風險
    # --------------------------------------------------------

    chase = []

    if dev10 > 5:
        chase.append(
            "MA10乖離偏高"
        )

    if dev20 > 8:
        chase.append(
            "MA20乖離偏高"
        )

    if rsi5_now >= 75:
        chase.append(
            "RSI偏熱"
        )

    if distance52 >= -2:
        chase.append(
            "接近52週高點"
        )

    if chase:

        chase_text = (
            "⚠️ "
            + "、".join(chase)
        )

    else:

        chase_text = (
            "✅ 暫無明顯追高警訊"
        )

    result = {

        "stock": stock,
        "price": price,
        "change": change,

        "today_volume": today_volume,
        "avg5": avg5,
        "volume_ratio": volume_ratio,
        "turnover": turnover,

        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma60": ma60,

        "dev10": dev10,
        "dev20": dev20,

        "k": k_now,
        "d": d_now,
        "j": float(j.iloc[-1]),

        "rsi5": rsi5_now,
        "rsi10": rsi10_now,

        "dif": dif_now,
        "dea": dea_now,
        "hist": hist_now,

        "supports": s_levels,
        "resistances": r_levels,

        "high52": high52,
        "distance52": distance52,

        "gain20": gain20,

        "resonance": resonance_text,

        "score": score,
        "status": status,

        "chase": chase_text
    }

    return result, None


# ============================================================
# 個股報告
# ============================================================

def stock_report(x):

    s = x["stock"]

    sup = x["supports"]

    res = x["resistances"]

    return f"""
<b>📊 台股技術分析 6.1</b>

<b>{s["code"]} {s["name"]}</b>
市場：{s["market"]}

💰 現價：<b>{fmt(x["price"])}</b>
{icon(x["change"])} 今日：<b>{pct(x["change"])}</b>
📈 20日：{pct(x["gain20"])}

━━━━━━━━━━━━━━
<b>📦 成交量</b>

今日量：{fmt(x["today_volume"] / 1000, 0)} 張
5日均量：{fmt(x["avg5"] / 1000, 0)} 張
量比：<b>{fmt(x["volume_ratio"], 2)} 倍</b>
成交金額：約 {fmt(x["turnover"] / 100000000, 2)} 億

━━━━━━━━━━━━━━
<b>📐 均線</b>

MA5：{fmt(x["ma5"])}
MA10：{fmt(x["ma10"])}
MA20：{fmt(x["ma20"])}
MA60：{fmt(x["ma60"])}

MA10乖離：{pct(x["dev10"])}
MA20乖離：{pct(x["dev20"])}

━━━━━━━━━━━━━━
<b>📈 技術指標</b>

KD：K {fmt(x["k"])} ／ D {fmt(x["d"])}
J：{fmt(x["j"])}

RSI5：{fmt(x["rsi5"])}
RSI10：{fmt(x["rsi10"])}

MACD DIF：{fmt(x["dif"])}
MACD DEA：{fmt(x["dea"])}
MACD柱：{fmt(x["hist"])}

━━━━━━━━━━━━━━
<b>🎯 支撐 / 壓力</b>

S1：{fmt(sup[0])}
S2：{fmt(sup[1])}
S3：{fmt(sup[2])}

R1：{fmt(res[0])}
R2：{fmt(res[1])}
R3：{fmt(res[2])}

━━━━━━━━━━━━━━
<b>📊 趨勢判斷</b>

三線共振：{x["resonance"]}
技術評分：<b>{x["score"]}</b>
目前狀態：<b>{x["status"]}</b>

━━━━━━━━━━━━━━
<b>🏔 52週位置</b>

52週高點：{fmt(x["high52"])}
距離52週高點：{pct(x["distance52"])}

━━━━━━━━━━━━━━

{x["chase"]}

<i>資料來源：Yahoo Finance
技術分析僅供參考，非投資建議。</i>
""".strip()


# ============================================================
# 大盤分析
# ============================================================

def analyze_market():

    d = yf_history(
        MARKET_SYMBOL,
        "1y"
    )

    if d is None:

        return None, (
            "❌ 無法取得台股大盤資料。"
        )

    close = d["Close"]

    price = float(
        close.iloc[-1]
    )

    prev = float(
        close.iloc[-2]
    )

    change = (
        price / prev - 1
    ) * 100

    # --------------------------------------------------------
    # 均線
    # --------------------------------------------------------

    ma5 = (
        close
        .rolling(5)
        .mean()
        .iloc[-1]
    )

    ma10 = (
        close
        .rolling(10)
        .mean()
        .iloc[-1]
    )

    ma20 = (
        close
        .rolling(20)
        .mean()
        .iloc[-1]
    )

    ma60 = (
        close
        .rolling(60)
        .mean()
        .iloc[-1]
    )

    dev10 = (
        (price / ma10 - 1)
        * 100
    )

    dev20 = (
        (price / ma20 - 1)
        * 100
    )

    # --------------------------------------------------------
    # KD
    # --------------------------------------------------------

    k, kd_d, j = kd(d)

    k_now = float(
        k.iloc[-1]
    )

    d_now = float(
        kd_d.iloc[-1]
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    rsi5_series = rsi(
        close,
        5
    )

    rsi10_series = rsi(
        close,
        10
    )

    rsi5_now = float(
        rsi5_series.iloc[-1]
    )

    rsi10_now = float(
        rsi10_series.iloc[-1]
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    dif_series, dea_series, hist_series = macd(
        close
    )

    dif_now = float(
        dif_series.iloc[-1]
    )

    dea_now = float(
        dea_series.iloc[-1]
    )

    hist_now = float(
        hist_series.iloc[-1]
    )

    # --------------------------------------------------------
    # 支撐 / 壓力
    # --------------------------------------------------------

    s_levels = supports(
        d,
        price
    )

    r_levels = resistances(
        d,
        price
    )

    while len(s_levels) < 3:
        s_levels.append(np.nan)

    while len(r_levels) < 3:
        r_levels.append(np.nan)

    # --------------------------------------------------------
    # 52週高點
    # --------------------------------------------------------

    high52 = float(
        d["High"].tail(252).max()
    )

    distance52 = (
        (price / high52 - 1)
        * 100
    )

    # --------------------------------------------------------
    # 20日漲跌
    # --------------------------------------------------------

    if len(close) >= 21:

        gain20 = (
            price
            / float(close.iloc[-21])
            - 1
        ) * 100

    else:

        gain20 = np.nan

    # --------------------------------------------------------
    # 市場成交量
    # --------------------------------------------------------

    volume_ratio = np.nan

    if "Volume" in d.columns:

        volume = pd.to_numeric(
            d["Volume"],
            errors="coerce"
        )

        if len(volume) >= 6:

            avg5 = float(
                volume
                .iloc[-6:-1]
                .mean()
            )

            today_volume = float(
                volume.iloc[-1]
            )

            if avg5 > 0:

                volume_ratio = (
                    today_volume / avg5
                )

    # --------------------------------------------------------
    # 評分
    # --------------------------------------------------------

    score = 0

    if price > ma20:
        score += 2
    else:
        score -= 2

    if trend(close) > 0:
        score += 2
    else:
        score -= 2

    if k_now > d_now:
        score += 1
    else:
        score -= 1

    if rsi5_now >= 50:
        score += 1
    else:
        score -= 1

    if dif_now > dea_now:
        score += 2
    else:
        score -= 2

    if gain20 > 3:
        score += 1

    elif gain20 < -3:
        score -= 1

    # --------------------------------------------------------
    # 市場狀態
    # --------------------------------------------------------

    if score >= 5:

        status = "🟢 偏多"

    elif score >= 2:

        status = "🟡 震盪偏多"

    elif score <= -5:

        status = "🔴 偏空"

    else:

        status = "🟠 震盪"

    # --------------------------------------------------------
    # 追高風險
    # --------------------------------------------------------

    warnings_list = []

    if dev10 > 5:
        warnings_list.append(
            "大盤乖離MA10偏高"
        )

    if dev20 > 8:
        warnings_list.append(
            "大盤乖離MA20偏高"
        )

    if rsi5_now >= 75:
        warnings_list.append(
            "RSI偏熱"
        )

    if distance52 >= -2:
        warnings_list.append(
            "接近52週高點"
        )

    if warnings_list:

        risk = (
            "⚠️ "
            + "、".join(
                warnings_list
            )
        )

    else:

        risk = (
            "✅ 暫無明顯過熱訊號"
        )

    result = {

        "price": price,
        "change": change,
        "gain20": gain20,

        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma60": ma60,

        "dev10": dev10,
        "dev20": dev20,

        "k": k_now,
        "d": d_now,
        "j": float(j.iloc[-1]),

        "rsi5": rsi5_now,
        "rsi10": rsi10_now,

        "dif": dif_now,
        "dea": dea_now,
        "hist": hist_now,

        "supports": s_levels,
        "resistances": r_levels,

        "high52": high52,
        "distance52": distance52,

        "volume_ratio": volume_ratio,

        "score": score,
        "status": status,

        "risk": risk
    }

    return result, None


# ============================================================
# 大盤報告
# ============================================================

def market_report(x):

    sup = x["supports"]

    res = x["resistances"]

    volume_text = (
        f"{fmt(x['volume_ratio'], 2)} 倍"
        if pd.notna(x["volume_ratio"])
        else "資料無法取得"
    )

    return f"""
<b>🇹🇼 台股大盤技術分析 6.1</b>

<b>加權指數 TAIEX</b>

💰 現在：<b>{fmt(x["price"])}</b>
{icon(x["change"])} 今日：<b>{pct(x["change"])}</b>
📈 20日：{pct(x["gain20"])}

━━━━━━━━━━━━━━
<b>📦 大盤成交量</b>

量比：<b>{volume_text}</b>

━━━━━━━━━━━━━━
<b>📐 均線</b>

MA5：{fmt(x["ma5"])}
MA10：{fmt(x["ma10"])}
MA20：{fmt(x["ma20"])}
MA60：{fmt(x["ma60"])}

MA10乖離：{pct(x["dev10"])}
MA20乖離：{pct(x["dev20"])}

━━━━━━━━━━━━━━
<b>📈 技術指標</b>

KD：K {fmt(x["k"])} ／ D {fmt(x["d"])}
J：{fmt(x["j"])}

RSI5：{fmt(x["rsi5"])}
RSI10：{fmt(x["rsi10"])}

MACD DIF：{fmt(x["dif"])}
MACD DEA：{fmt(x["dea"])}
MACD柱：{fmt(x["hist"])}

━━━━━━━━━━━━━━
<b>🎯 大盤支撐 / 壓力</b>

S1：{fmt(sup[0])}
S2：{fmt(sup[1])}
S3：{fmt(sup[2])}

R1：{fmt(res[0])}
R2：{fmt(res[1])}
R3：{fmt(res[2])}

━━━━━━━━━━━━━━
<b>🏔 52週位置</b>

52週高點：{fmt(x["high52"])}
距離52週高點：{pct(x["distance52"])}

━━━━━━━━━━━━━━
<b>📊 大盤判斷</b>

技術評分：<b>{x["score"]}</b>
市場狀態：<b>{x["status"]}</b>

{x["risk"]}

━━━━━━━━━━━━━━

<i>資料來源：Yahoo Finance
大盤資料為日線技術分析，僅供參考。</i>
""".strip()


# ============================================================
# 使用說明
# ============================================================

def help_text():

    return """
<b>📊 台股技術分析機器人 6.1</b>

直接輸入：

<code>3563</code>
→ 分析牧德

<code>牧德</code>
→ 分析牧德

<code>/分析 3563</code>
→ 分析3563

<code>/分析 牧德</code>
→ 分析牧德

<b>大盤：</b>

<code>大盤</code>
<code>台股</code>
<code>加權</code>
<code>TWII</code>
<code>TAIEX</code>

→ 分析台股大盤

━━━━━━━━━━━━━━

<b>個股分析包含：</b>

• 現價
• 今日漲跌
• 今日成交量
• 5日平均成交量
• 量比
• MA5 / MA10 / MA20 / MA60
• MA10 / MA20乖離
• KD
• RSI5 / RSI10
• MACD
• 三線共振
• 支撐 S1～S3
• 壓力 R1～R3
• 52週高點
• 距離52週高點
• 20日漲跌

<b>這不是回測機器人。</b>

不需要輸入日期。
不需要 SINGLE / MULTI / ALL。
不會計算未來報酬。
""".strip()


# ============================================================
# Telegram Update
# ============================================================

def handle_update(u):

    try:

        message = u.get(
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

        text = str(
            message.get(
                "text",
                ""
            )
        ).strip()

        if not chat_id or not text:

            return

        log(
            f"📨 收到訊息：{text} "
            f"chat_id={chat_id}"
        )

        # ----------------------------------------------------
        # Help
        # ----------------------------------------------------

        if (
            text.startswith("/start")
            or
            text.startswith("/help")
        ):

            send(
                chat_id,
                help_text()
            )

            return

        # ----------------------------------------------------
        # 取得查詢內容
        # ----------------------------------------------------

        q = text

        if text.startswith(
            "/分析"
        ):

            q = text[
                len("/分析"):
            ].strip()

        elif text.lower().startswith(
            "/analyze"
        ):

            q = text[
                len("/analyze"):
            ].strip()

        elif text.startswith(
            "/分析大盤"
        ):

            q = "大盤"

        q = q.replace(
            "\u3000",
            ""
        ).strip()

        # ----------------------------------------------------
        # 大盤
        # ----------------------------------------------------

        if is_market_query(q):

            send(
                chat_id,
                "📡 正在抓取台股大盤 TAIEX 技術資料...\n"
                "請稍候。"
            )

            result, err = analyze_market()

            if err:

                send(
                    chat_id,
                    err
                )

                return

            send(
                chat_id,
                market_report(result)
            )

            return

        # ----------------------------------------------------
        # 個股
        # ----------------------------------------------------

        send(
            chat_id,
            f"🔎 正在分析：<b>{q}</b>\n"
            f"📡 正在抓取最新技術資料..."
        )

        stock, err = find_stock(q)

        if err:

            send(
                chat_id,
                err
            )

            return

        if stock is None:

            send(
                chat_id,
                "❌ 找不到這檔股票。"
            )

            return

        log(
            f"🎯 找到股票："
            f"{stock['code']} "
            f"{stock['name']} "
            f"{stock['symbol']}"
        )

        result, err = analyze_stock(
            stock
        )

        if err:

            send(
                chat_id,
                err
            )

            return

        send(
            chat_id,
            stock_report(result)
        )

    except Exception as e:

        log(
            f"❌ handle_update 錯誤：{e}"
        )

        try:

            if chat_id:

                send(
                    chat_id,
                    "❌ 分析時發生錯誤，"
                    "請稍後再試。"
                )

        except Exception:
            pass


# ============================================================
# 主程式
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("🚀 Taiwan Stock Radar 6.1")
    print("🚀 TECHNICAL ANALYSIS BOT")
    print("🚫 NOT BACKTEST")
    print("=" * 70)

    log(
        f"版本：{VERSION}"
    )

    # --------------------------------------------------------
    # Token
    # --------------------------------------------------------

    if not TOKEN:

        log(
            "❌ BACKTEST_TELEGRAM_BOT_TOKEN 未設定"
        )

        return

    log(
        "✅ Telegram Token 已讀取"
    )

    # --------------------------------------------------------
    # getMe
    # --------------------------------------------------------

    me = telegram(
        "getMe",
        timeout=20
    )

    if not me.get("ok"):

        log(
            "❌ Telegram Bot Token 無法使用"
        )

        return

    bot_username = (
        me.get("result", {})
        .get("username", "")
    )

    log(
        f"🤖 Bot：@{bot_username}"
    )

    # --------------------------------------------------------
    # Webhook
    # --------------------------------------------------------

    webhook = telegram(
        "getWebhookInfo",
        timeout=20
    )

    webhook_url = (
        webhook
        .get("result", {})
        .get("url", "")
    )

    if webhook_url:

        log(
            "⚠️ Telegram 目前存在 Webhook："
            f"{webhook_url}"
        )

        log(
            "⚠️ 本程式使用 getUpdates，"
            "請先移除 Webhook。"
        )

        return

    # --------------------------------------------------------
    # 開始接收 Telegram
    # --------------------------------------------------------

    offset = 0

    log(
        "📡 開始等待 Telegram 訊息..."
    )

    # GitHub Actions 每次執行最多抓約 230 秒
    end_time = (
        time.time()
        + 230
    )

    while time.time() < end_time:

        try:

            remaining = int(
                end_time
                - time.time()
            )

            if remaining <= 0:
                break

            timeout = min(
                20,
                remaining
            )

            response = telegram(
                "getUpdates",
                {
                    "offset": offset,
                    "timeout": timeout,
                    "allowed_updates": [
                        "message"
                    ]
                },
                timeout=timeout + 10
            )

            if not response.get("ok"):

                log(
                    "⚠️ getUpdates 失敗"
                )

                time.sleep(3)

                continue

            updates = response.get(
                "result",
                []
            )

            if not updates:
                continue

            for u in updates:

                update_id = u.get(
                    "update_id"
                )

                try:

                    handle_update(u)

                except Exception as e:

                    log(
                        f"❌ 處理 Update 失敗：{e}"
                    )

                # ------------------------------------------------
                # 非常重要：
                # 處理完才推進 offset
                # ------------------------------------------------

                if (
                    update_id is not None
                    and
                    update_id >= offset
                ):

                    offset = (
                        update_id + 1
                    )

                    log(
                        f"🔢 Offset 更新：{offset}"
                    )

        except KeyboardInterrupt:

            log(
                "🛑 手動停止"
            )

            break

        except Exception as e:

            log(
                f"⚠️ 主迴圈錯誤：{e}"
            )

            time.sleep(3)

    log(
        "⏹ 本次 GitHub Actions 執行結束"
    )


# ============================================================
# Entry
# ============================================================

if __name__ == "__main__":

    main()
