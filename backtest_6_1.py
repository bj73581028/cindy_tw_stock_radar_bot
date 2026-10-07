import os
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
# Taiwan Stock Radar 6.1
# 即時技術分析版
#
# 功能：
# 1. 上市股票
# 2. 上櫃股票
# 3. 個股即時技術分析
# 4. 台股大盤 ^TWII 技術分析
# 5. 支撐 / 壓力
# 6. MA5 / MA10 / MA20 / MA60
# 7. KD / RSI / MACD
# 8. 今日量 / 5日均量 / 量比
# 9. 52週高
# 10. Telegram 查詢
#
# ⚠️ 本程式不是回測
# ============================================================

VERSION = "6.1-TECH-BOT"

TZ = ZoneInfo("Asia/Taipei")

TOKEN = os.getenv(
    "BACKTEST_TELEGRAM_BOT_TOKEN",
    ""
)

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent":
        "Mozilla/5.0 TaiwanStockRadar/6.1"
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


def log(*x):
    print(
        now().strftime("%Y-%m-%d %H:%M:%S"),
        *x,
        flush=True
    )


def fmt(x, d=2):

    try:

        if pd.isna(x):
            return "-"

        return f"{float(x):.{d}f}"

    except Exception:

        return "-"


def pct(x):

    try:

        if pd.isna(x):
            return "-"

        return f"{float(x):+.2f}%"

    except Exception:

        return "-"


def icon(t):

    return {
        "強勢向上": "🚀",
        "溫和向上": "↗️",
        "平穩": "➡️",
        "略為向下": "↘️",
        "明顯向下": "🔻",
        "資料不足": "❔"
    }.get(t, "➡️")


# ============================================================
# 判斷是否為大盤
# ============================================================

def is_market_query(q):

    if q is None:
        return False

    q = str(q).strip()

    # 去除全形空白
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

def telegram(
    method,
    params=None,
    post=False
):

    if not TOKEN:

        log(
            "❌ BACKTEST_TELEGRAM_BOT_TOKEN 未讀取"
        )

        return None

    try:

        url = (
            f"https://api.telegram.org/"
            f"bot{TOKEN}/{method}"
        )

        if post:

            r = SESSION.post(
                url,
                json=params or {},
                timeout=40
            )

        else:

            r = SESSION.get(
                url,
                params=params or {},
                timeout=40
            )

        log(
            "Telegram",
            method,
            "HTTP",
            r.status_code
        )

        if not r.ok:

            log(
                "Telegram error:",
                r.text[:1000]
            )

            return None

        data = r.json()

        if not data.get("ok"):

            log(
                "Telegram API error:",
                data
            )

            return None

        return data.get("result")

    except Exception as e:

        log(
            "Telegram exception:",
            repr(e)
        )

        return None


# ============================================================
# 發送 Telegram
# ============================================================

def send(
    chat_id,
    text
):

    return telegram(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        post=True
    )


# ============================================================
# 台股完整名單
# 上市 + 上櫃
# ============================================================

def stock_list():

    out = []

    # --------------------------------------------------------
    # 上市
    # --------------------------------------------------------

    try:

        url = (
            "https://openapi.twse.com.tw/"
            "v1/exchangeReport/STOCK_DAY_ALL"
        )

        r = SESSION.get(
            url,
            timeout=30
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

            if (
                code.isdigit()
                and len(code) == 4
                and name
                and not code.startswith(
                    ("00", "01", "02", "03")
                )
            ):

                out.append({
                    "code": code,
                    "name": name,
                    "market": "TWSE",
                    "symbol": code + ".TW"
                })

        log(
            "TWSE 股票數：",
            len(out)
        )

    except Exception as e:

        log(
            "TWSE list error:",
            repr(e)
        )

    twse_count = len(out)

    # --------------------------------------------------------
    # 上櫃
    # --------------------------------------------------------

    try:

        url = (
            "https://www.tpex.org.tw/"
            "openapi/v1/tpex_mainboard_quotes"
        )

        r = SESSION.get(
            url,
            timeout=30
        )

        r.raise_for_status()

        data = r.json()

        for x in data:

            code = str(
                x.get(
                    "SecuritiesCompanyCode",
                    ""
                )
            ).strip()

            name = str(
                x.get(
                    "CompanyName",
                    ""
                )
            ).strip()

            if (
                code.isdigit()
                and len(code) == 4
                and name
                and not code.startswith(
                    ("00", "01", "02", "03")
                )
            ):

                out.append({
                    "code": code,
                    "name": name,
                    "market": "TPEx",
                    "symbol": code + ".TWO"
                })

        log(
            "TPEx 股票數：",
            len(out) - twse_count
        )

    except Exception as e:

        log(
            "TPEx list error:",
            repr(e)
        )

    # --------------------------------------------------------
    # 去除完全重複
    # 同一代號上市/上櫃可以同時存在
    # --------------------------------------------------------

    seen = set()

    clean = []

    for x in out:

        key = (
            x["market"],
            x["code"]
        )

        if key not in seen:

            seen.add(key)

            clean.append(x)

    log(
        "台股總股票數：",
        len(clean)
    )

    return clean


# ============================================================
# Yahoo Finance 歷史資料
#
# 特別處理新版 yfinance MultiIndex
# ============================================================

def yf_history(
    symbol,
    period="1y"
):

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
                "Yahoo 無資料：",
                symbol
            )

            return None

        # ----------------------------------------------------
        # yfinance MultiIndex
        # ----------------------------------------------------

        if isinstance(
            d.columns,
            pd.MultiIndex
        ):

            levels0 = list(
                d.columns.get_level_values(0)
            )

            levels1 = list(
                d.columns.get_level_values(1)
            )

            if symbol in levels1:

                d = d.xs(
                    symbol,
                    axis=1,
                    level=1
                )

            elif symbol in levels0:

                d = d.xs(
                    symbol,
                    axis=1,
                    level=0
                )

            else:

                d.columns = [
                    c[0]
                    for c in d.columns
                ]

        # ----------------------------------------------------
        # 清理欄位
        # ----------------------------------------------------

        d.columns = [
            str(c).replace(" ", "")
            for c in d.columns
        ]

        need = [
            "Open",
            "High",
            "Low",
            "Close"
        ]

        for c in need:

            if c not in d.columns:

                log(
                    "Yahoo 缺少欄位：",
                    symbol,
                    c
                )

                return None

        d.index = pd.to_datetime(
            d.index
        )

        try:

            if d.index.tz is not None:

                d.index = (
                    d.index
                    .tz_localize(None)
                )

        except Exception:

            pass

        # ----------------------------------------------------
        # 數值化
        # ----------------------------------------------------

        for c in need:

            d[c] = pd.to_numeric(
                d[c],
                errors="coerce"
            )

        if "Volume" in d.columns:

            d["Volume"] = pd.to_numeric(
                d["Volume"],
                errors="coerce"
            )

        # ----------------------------------------------------
        # 大盤 Volume 可能缺值
        # 所以不能把 Volume 當成必要欄位
        # ----------------------------------------------------

        d = d.dropna(
            subset=need
        )

        if len(d) < 70:

            log(
                "歷史資料不足：",
                symbol,
                len(d)
            )

            return None

        return d

    except Exception as e:

        log(
            "Yahoo history error:",
            symbol,
            repr(e)
        )

        return None


# ============================================================
# 個股歷史資料
# ============================================================

def stock_history(symbol):

    d = yf_history(
        symbol,
        "1y"
    )

    if d is None:

        return None

    if "Volume" not in d.columns:

        return None

    d["Volume"] = (
        d["Volume"]
        .fillna(0)
    )

    return d


# ============================================================
# 找股票
# ============================================================

def find_stock(q):

    q = str(q).strip()

    q = q.replace(
        "\u3000",
        ""
    )

    # --------------------------------------------------------
    # /分析
    # --------------------------------------------------------

    if q.startswith("/分析"):

        q = q[3:].strip()

    elif q.lower().startswith(
        "/analyze"
    ):

        q = q[8:].strip()

    # --------------------------------------------------------
    # 大盤優先
    # --------------------------------------------------------

    if is_market_query(q):

        return {
            "code": "TWII",
            "name": "加權指數",
            "market": "TWSE",
            "symbol": MARKET_SYMBOL
        }, None

    # --------------------------------------------------------
    # 空白
    # --------------------------------------------------------

    if not q:

        return (
            None,
            "請輸入股票代號或名稱，例如：3563 或 牧德"
        )

    # --------------------------------------------------------
    # 股票名單
    # --------------------------------------------------------

    names = stock_list()

    # --------------------------------------------------------
    # 股票代號
    # --------------------------------------------------------

    if q.isdigit():

        candidates = [
            x for x in names
            if x["code"] == q
        ]

        # API 名單偶爾失敗
        # 仍然直接嘗試 Yahoo
        if not candidates:

            candidates = [

                {
                    "code": q,
                    "name": q,
                    "market": "TWSE",
                    "symbol": q + ".TW"
                },

                {
                    "code": q,
                    "name": q,
                    "market": "TPEx",
                    "symbol": q + ".TWO"
                }

            ]

        for s in candidates:

            d = stock_history(
                s["symbol"]
            )

            if d is not None:

                # 如果有官方名稱
                for z in names:

                    if (
                        z["code"] == q
                        and z["symbol"]
                        == s["symbol"]
                    ):

                        return z, None

                return s, None

        return (
            None,
            f"找不到「{q}」，請確認股票代號。"
        )

    # --------------------------------------------------------
    # 股票名稱完全符合
    # --------------------------------------------------------

    exact = [
        x for x in names
        if q == x["name"]
    ]

    if len(exact) == 1:

        return exact[0], None

    # --------------------------------------------------------
    # 股票名稱部分符合
    # --------------------------------------------------------

    matches = [
        x for x in names
        if q in x["name"]
    ]

    if len(matches) == 1:

        return matches[0], None

    if matches:

        return (
            None,
            "找到多檔符合：\n"
            + "\n".join(
                f"{x['code']} {x['name']} "
                f"({x['market']})"
                for x in matches[:10]
            )
        )

    return (
        None,
        f"找不到「{q}」，請輸入正確台股代號或名稱。"
    )


# ============================================================
# KD
# ============================================================

def kd(d):

    low9 = (
        d.Low
        .rolling(9)
        .min()
    )

    high9 = (
        d.High
        .rolling(9)
        .max()
    )

    rsv = (
        (d.Close - low9)
        /
        (high9 - low9)
        .replace(0, np.nan)
        * 100
    )

    k = rsv.ewm(
        alpha=1 / 3,
        adjust=False
    ).mean()

    dline = k.ewm(
        alpha=1 / 3,
        adjust=False
    ).mean()

    return k, dline


# ============================================================
# RSI
# ============================================================

def rsi(c, p):

    delta = c.diff()

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

    rs = (
        avg_gain
        /
        avg_loss.replace(
            0,
            np.nan
        )
    )

    return (
        100
        -
        100 / (1 + rs)
    )


# ============================================================
# MACD
# ============================================================

def macd(c):

    ema12 = c.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = c.ewm(
        span=26,
        adjust=False
    ).mean()

    dif = ema12 - ema26

    dea = dif.ewm(
        span=9,
        adjust=False
    ).mean()

    hist = dif - dea

    return (
        dif,
        dea,
        hist
    )


# ============================================================
# 趨勢判斷
# ============================================================

def trend(
    s,
    norm=True
):

    s = s.dropna()

    if len(s) < 6:

        return "資料不足"

    current = float(
        s.iloc[-1]
    )

    old = float(
        s.iloc[-6]
    )

    diff = current - old

    if norm:

        if abs(old) < 0.01:

            return "平穩"

        change = (
            diff
            /
            abs(old)
            * 100
        )

        if change >= 8:

            return "強勢向上"

        if change >= 1:

            return "溫和向上"

        if change <= -8:

            return "明顯向下"

        if change <= -1:

            return "略為向下"

        return "平穩"

    else:

        if diff > 0.05:

            return "強勢向上"

        if diff > 0:

            return "溫和向上"

        if diff < -0.05:

            return "明顯向下"

        if diff < 0:

            return "略為向下"

        return "平穩"


# ============================================================
# 支撐
# ============================================================

def supports(d, p):

    result = []

    lows = d.Low.tail(60)

    for i in range(
        2,
        len(lows) - 2
    ):

        v = lows.iloc[i]

        if (
            v <= lows.iloc[i - 2:i].min()
            and
            v <= lows.iloc[i + 1:i + 3].min()
            and
            v < p
        ):

            result.append(
                float(v)
            )

    # 均線支撐
    for ma in [

        d.Close
        .rolling(10)
        .mean()
        .iloc[-1],

        d.Close
        .rolling(20)
        .mean()
        .iloc[-1],

        d.Close
        .rolling(60)
        .mean()
        .iloc[-1]

    ]:

        if (
            pd.notna(ma)
            and ma < p
        ):

            result.append(
                float(ma)
            )

    # 近期低點
    for v in [

        d.Low.tail(20).min(),

        d.Low.tail(60).min()

    ]:

        if (
            pd.notna(v)
            and v < p
        ):

            result.append(
                float(v)
            )

    return sorted(
        set(
            round(x, 2)
            for x in result
        ),
        reverse=True
    )[:3]


# ============================================================
# 壓力
# ============================================================

def resistances(d, p):

    result = []

    highs = d.High.tail(60)

    for i in range(
        2,
        len(highs) - 2
    ):

        v = highs.iloc[i]

        if (
            v >= highs.iloc[i - 2:i].max()
            and
            v >= highs.iloc[i + 1:i + 3].max()
            and
            v > p
        ):

            result.append(
                float(v)
            )

    # 均線壓力
    for ma in [

        d.Close
        .rolling(10)
        .mean()
        .iloc[-1],

        d.Close
        .rolling(20)
        .mean()
        .iloc[-1],

        d.Close
        .rolling(60)
        .mean()
        .iloc[-1]

    ]:

        if (
            pd.notna(ma)
            and ma > p
        ):

            result.append(
                float(ma)
            )

    # 近期高點
    for v in [

        d.High.tail(20).max(),

        d.High.tail(60).max()

    ]:

        if (
            pd.notna(v)
            and v > p
        ):

            result.append(
                float(v)
            )

    return sorted(
        set(
            round(x, 2)
            for x in result
        )
    )[:3]


# ============================================================
# 個股分析
# ============================================================

def analyze_stock(s):

    d = stock_history(
        s["symbol"]
    )

    if d is None:

        return (
            None,
            "目前無法取得歷史資料，"
            "可能是 Yahoo Finance 暫時無資料。"
        )

    c = d.Close.astype(float)

    v = d.Volume.astype(float)

    price = float(
        c.iloc[-1]
    )

    prev = float(
        c.iloc[-2]
    )

    gain = (
        price / prev - 1
    ) * 100

    # --------------------------------------------------------
    # 成交量
    # 今天 / 前5個完整交易日平均
    # --------------------------------------------------------

    avg5 = float(
        v.iloc[-6:-1].mean()
    )

    volume_ratio = (
        float(v.iloc[-1] / avg5)
        if avg5 > 0
        else np.nan
    )

    # --------------------------------------------------------
    # 均線
    # --------------------------------------------------------

    ma5 = float(
        c.rolling(5)
        .mean()
        .iloc[-1]
    )

    ma10 = float(
        c.rolling(10)
        .mean()
        .iloc[-1]
    )

    ma20 = float(
        c.rolling(20)
        .mean()
        .iloc[-1]
    )

    ma60 = float(
        c.rolling(60)
        .mean()
        .iloc[-1]
    )

    dev10 = (
        (price - ma10)
        /
        ma10
        * 100
    )

    dev20 = (
        (price - ma20)
        /
        ma20
        * 100
    )

    # --------------------------------------------------------
    # 技術指標
    # --------------------------------------------------------

    k, dline = kd(d)

    r5 = rsi(c, 5)

    r10 = rsi(c, 10)

    dif, dea, hist = macd(c)

    kt = trend(k)

    rt = trend(r5)

    r10t = trend(r10)

    mt = trend(
        dif,
        False
    )

    # --------------------------------------------------------
    # 三線共振
    # --------------------------------------------------------

    resonance = (

        kt in {
            "強勢向上",
            "溫和向上"
        }

        and

        rt in {
            "強勢向上",
            "溫和向上"
        }

        and

        mt in {
            "強勢向上",
            "溫和向上"
        }

    )

    # --------------------------------------------------------
    # 支撐 / 壓力
    # --------------------------------------------------------

    ss = supports(
        d,
        price
    )

    rr = resistances(
        d,
        price
    )

    # --------------------------------------------------------
    # 52週高
    # --------------------------------------------------------

    high52 = float(
        d.High.tail(252).max()
    )

    distance52 = (
        (high52 - price)
        /
        high52
        * 100
    )

    # --------------------------------------------------------
    # 20日漲幅
    # --------------------------------------------------------

    gain20 = (

        (price / c.iloc[-21] - 1)
        * 100

        if len(c) >= 21

        else np.nan

    )

    return {

        "stock": s,

        "price": price,

        "gain": gain,

        "today": int(
            v.iloc[-1] / 1000
        ),

        "avg5": int(
            avg5 / 1000
        ),

        "vr": volume_ratio,

        "turn": (
            price
            * float(v.iloc[-1])
        ),

        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma60": ma60,

        "dev10": dev10,
        "dev20": dev20,

        "k": float(
            k.iloc[-1]
        ),

        "d": float(
            dline.iloc[-1]
        ),

        "kt": kt,

        "r5": float(
            r5.iloc[-1]
        ),

        "r10": float(
            r10.iloc[-1]
        ),

        "rt": rt,
        "r10t": r10t,

        "dif": float(
            dif.iloc[-1]
        ),

        "dea": float(
            dea.iloc[-1]
        ),

        "mt": mt,

        "res": resonance,

        "s1": (
            ss[0]
            if len(ss) > 0
            else np.nan
        ),

        "s2": (
            ss[1]
            if len(ss) > 1
            else np.nan
        ),

        "s3": (
            ss[2]
            if len(ss) > 2
            else np.nan
        ),

        "r1": (
            rr[0]
            if len(rr) > 0
            else np.nan
        ),

        "r2": (
            rr[1]
            if len(rr) > 1
            else np.nan
        ),

        "r3": (
            rr[2]
            if len(rr) > 2
            else np.nan
        ),

        "sd": (
            (price - ss[0])
            /
            price
            * 100
            if ss
            else np.nan
        ),

        "rd": (
            (rr[0] - price)
            /
            price
            * 100
            if rr
            else np.nan
        ),

        "h52": high52,

        "dist": distance52,

        "g20": gain20

    }, None


# ============================================================
# 大盤分析
# ============================================================

def analyze_market():

    d = yf_history(
        MARKET_SYMBOL,
        "1y"
    )

    if d is None:

        return (
            None,
            "目前無法取得加權指數歷史資料。"
        )

    c = d.Close.astype(float)

    price = float(
        c.iloc[-1]
    )

    prev = float(
        c.iloc[-2]
    )

    gain = (
        price / prev - 1
    ) * 100

    gain20 = (
        (price / c.iloc[-21] - 1)
        * 100
    )

    # --------------------------------------------------------
    # 均線
    # --------------------------------------------------------

    ma5 = float(
        c.rolling(5)
        .mean()
        .iloc[-1]
    )

    ma10 = float(
        c.rolling(10)
        .mean()
        .iloc[-1]
    )

    ma20 = float(
        c.rolling(20)
        .mean()
        .iloc[-1]
    )

    ma60 = float(
        c.rolling(60)
        .mean()
        .iloc[-1]
    )

    dev10 = (
        (price - ma10)
        /
        ma10
        * 100
    )

    dev20 = (
        (price - ma20)
        /
        ma20
        * 100
    )

    # --------------------------------------------------------
    # 技術指標
    # --------------------------------------------------------

    k, dline = kd(d)

    r5 = rsi(
        c,
        5
    )

    r10 = rsi(
        c,
        10
    )

    dif, dea, hist = macd(c)

    kt = trend(k)

    rt = trend(r5)

    r10t = trend(r10)

    mt = trend(
        dif,
        True
    )

    # --------------------------------------------------------
    # 支撐壓力
    # --------------------------------------------------------

    ss = supports(
        d,
        price
    )

    rr = resistances(
        d,
        price
    )

    # --------------------------------------------------------
    # 52週高
    # --------------------------------------------------------

    high52 = float(
        d.High.tail(252).max()
    )

    distance52 = (
        (high52 - price)
        /
        high52
        * 100
    )

    # --------------------------------------------------------
    # 大盤成交量
    #
    # ^TWII 有些 Yahoo 資料沒有 Volume
    # 因此不能把 Volume 當成大盤分析必要條件
    # --------------------------------------------------------

    volume_ratio = np.nan

    volume_change = np.nan

    if "Volume" in d.columns:

        volume = pd.to_numeric(
            d["Volume"],
            errors="coerce"
        ).fillna(0)

        avg5 = float(
            volume.iloc[-6:-1].mean()
        )

        if avg5 > 0:

            volume_ratio = (
                float(
                    volume.iloc[-1]
                )
                /
                avg5
            )

            volume_change = (
                float(
                    volume.iloc[-1]
                )
                /
                avg5
                - 1
            ) * 100

    # --------------------------------------------------------
    # 大盤評分
    # --------------------------------------------------------

    score = 0

    reasons = []

    # MA20
    if price > ma20:

        score += 2

        reasons.append(
            "指數站上MA20"
        )

    else:

        score -= 2

        reasons.append(
            "指數跌破MA20"
        )

    # MA20方向
    ma20_prev = float(
        c.rolling(20)
        .mean()
        .iloc[-6]
    )

    if ma20 > ma20_prev:

        score += 2

        reasons.append(
            "MA20向上"
        )

    else:

        score -= 2

        reasons.append(
            "MA20向下"
        )

    # KD
    if kt in {
        "強勢向上",
        "溫和向上"
    }:

        score += 1

        reasons.append(
            "KD偏多"
        )

    elif kt in {
        "略為向下",
        "明顯向下"
    }:

        score -= 1

        reasons.append(
            "KD轉弱"
        )

    # RSI
    if rt in {
        "強勢向上",
        "溫和向上"
    }:

        score += 1

        reasons.append(
            "RSI5偏多"
        )

    elif rt in {
        "略為向下",
        "明顯向下"
    }:

        score -= 1

        reasons.append(
            "RSI5轉弱"
        )

    # MACD
    if mt in {
        "強勢向上",
        "溫和向上"
    }:

        score += 2

        reasons.append(
            "MACD DIF向上"
        )

    elif mt in {
        "略為向下",
        "明顯向下"
    }:

        score -= 2

        reasons.append(
            "MACD DIF轉弱"
        )

    # 20日
    if gain20 > 3:

        score += 1

    elif gain20 < -3:

        score -= 1

    # --------------------------------------------------------
    # 大盤環境
    # --------------------------------------------------------

    if score >= 5:

        status = "🟢 偏多"

        advice = (
            "可積極尋找強勢股，"
            "優先挑量價齊揚、"
            "站上均線且未過度乖離者。"
        )

    elif score >= 2:

        status = "🟡 震盪偏多"

        advice = (
            "可以做個股，"
            "但建議挑強勢股，"
            "不宜全面追高。"
        )

    elif score <= -5:

        status = "🔴 偏空"

        advice = (
            "大盤環境偏弱，"
            "建議降低追高，"
            "等待轉強訊號。"
        )

    else:

        status = "🟠 震盪"

        advice = (
            "大盤方向不明，"
            "適合個別選股，"
            "不宜因短線反彈全面追價。"
        )

    # --------------------------------------------------------
    # 追價風險
    # --------------------------------------------------------

    warnings_list = []

    if dev10 > 5:

        warnings_list.append(
            "指數高於MA10較多"
        )

    if dev20 > 8:

        warnings_list.append(
            "指數高於MA20較多"
        )

    if float(r5.iloc[-1]) >= 75:

        warnings_list.append(
            "RSI5偏熱"
        )

    if distance52 <= 2:

        warnings_list.append(
            "接近52週高"
        )

    if warnings_list:

        chase = "⚠️ 追價風險較高"

        chase_detail = (
            "、".join(
                warnings_list
            )
        )

    else:

        chase = "🟢 追價壓力尚可"

        chase_detail = (
            "目前未出現明顯過熱訊號"
        )

    return {

        "price": price,

        "gain": gain,

        "g20": gain20,

        "volume_ratio": volume_ratio,

        "volume_change": volume_change,

        "ma5": ma5,

        "ma10": ma10,

        "ma20": ma20,

        "ma60": ma60,

        "dev10": dev10,

        "dev20": dev20,

        "k": float(
            k.iloc[-1]
        ),

        "d": float(
            dline.iloc[-1]
        ),

        "kt": kt,

        "r5": float(
            r5.iloc[-1]
        ),

        "r10": float(
            r10.iloc[-1]
        ),

        "rt": rt,

        "r10t": r10t,

        "dif": float(
            dif.iloc[-1]
        ),

        "dea": float(
            dea.iloc[-1]
        ),

        "hist": float(
            hist.iloc[-1]
        ),

        "mt": mt,

        "s1": (
            ss[0]
            if len(ss) > 0
            else np.nan
        ),

        "s2": (
            ss[1]
            if len(ss) > 1
            else np.nan
        ),

        "s3": (
            ss[2]
            if len(ss) > 2
            else np.nan
        ),

        "r1": (
            rr[0]
            if len(rr) > 0
            else np.nan
        ),

        "r2": (
            rr[1]
            if len(rr) > 1
            else np.nan
        ),

        "r3": (
            rr[2]
            if len(rr) > 2
            else np.nan
        ),

        "h52": high52,

        "dist52": distance52,

        "score": score,

        "status": status,

        "advice": advice,

        "chase": chase,

        "chase_detail": chase_detail,

        "reasons": reasons

    }, None


# ============================================================
# 個股 Telegram 報告
# ============================================================

def stock_report(x):

    return f"""
<b>📊 Taiwan Stock Radar 6.1</b>
<b>#{x['stock']['code']}｜{x['stock']['name']}｜{x['stock']['market']}</b>

📅 {now():%Y/%m/%d %H:%M}

━━━━━━━━━━━━━━

💰 <b>現價：{fmt(x['price'])}</b>

📈 今日：{pct(x['gain'])}
📈 20日：{pct(x['g20'])}

<b>🔊 量能</b>

今日量：{x['today']:,} 張
5日均量：{x['avg5']:,} 張
量比：{fmt(x['vr'],2)}x
成交金額：{x['turn']/1e8:.2f} 億

<b>🟢 支撐</b>

S1：<b>{fmt(x['s1'])}</b>
S2：{fmt(x['s2'])}
S3：{fmt(x['s3'])}

距S1：{pct(x['sd'])}

<b>🔴 壓力</b>

R1：<b>{fmt(x['r1'])}</b>
R2：{fmt(x['r2'])}
R3：{fmt(x['r3'])}

距R1：{pct(x['rd'])}

<b>📐 均線</b>

MA5：{fmt(x['ma5'])}

MA10：{fmt(x['ma10'])}
乖離：{pct(x['dev10'])}

MA20：{fmt(x['ma20'])}
乖離：{pct(x['dev20'])}

MA60：{fmt(x['ma60'])}

<b>📊 技術指標</b>

KD 9K：
{icon(x['kt'])} {x['kt']}
K={fmt(x['k'])}
D={fmt(x['d'])}

RSI 5T：
{icon(x['rt'])} {x['rt']}
{fmt(x['r5'])}

RSI 10T：
{icon(x['r10t'])} {x['r10t']}
{fmt(x['r10'])}

MACD DIF：
{icon(x['mt'])} {x['mt']}
{fmt(x['dif'],3)}

{"🔥 三線共振" if x["res"] else "— 尚未形成完整三線共振"}

📌 52週高：
{fmt(x['h52'])}

📌 距52週高：
{pct(x['dist'])}

━━━━━━━━━━━━━━

⚠️ 技術分析僅供參考，
不代表買賣建議。
"""


# ============================================================
# 大盤 Telegram 報告
# ============================================================

def market_report(x):

    volume_text = (
        f"量比：{fmt(x['volume_ratio'],2)}x\n"
        f"較5日均量：{pct(x['volume_change'])}"
    )

    if pd.isna(
        x["volume_ratio"]
    ):

        volume_text = (
            "量比：—\n"
            "較5日均量：—\n"
            "※ Yahoo ^TWII 成交量資料不足，"
            "不影響大盤技術分析"
        )

    return f"""
<b>🇹🇼 6.1 台股大盤技術分析</b>

<b>加權指數｜TAIEX</b>

📅 {now():%Y/%m/%d %H:%M}

━━━━━━━━━━━━━━

💰 <b>目前指數：{fmt(x['price'])}</b>

📈 今日：
{pct(x['gain'])}

📈 20日：
{pct(x['g20'])}

<b>🔊 大盤量能</b>

{volume_text}

<b>📐 均線</b>

MA5：{fmt(x['ma5'])}

MA10：
{fmt(x['ma10'])}
乖離：{pct(x['dev10'])}

MA20：
{fmt(x['ma20'])}
乖離：{pct(x['dev20'])}

MA60：
{fmt(x['ma60'])}

<b>📊 技術指標</b>

KD 9K：
{icon(x['kt'])} {x['kt']}
K={fmt(x['k'])}
D={fmt(x['d'])}

RSI 5T：
{icon(x['rt'])} {x['rt']}
{fmt(x['r5'])}

RSI 10T：
{icon(x['r10t'])} {x['r10t']}
{fmt(x['r10'])}

MACD DIF：
{icon(x['mt'])} {x['mt']}
{fmt(x['dif'],2)}

<b>🟢 大盤支撐</b>

S1：<b>{fmt(x['s1'],0)}</b>
S2：{fmt(x['s2'],0)}
S3：{fmt(x['s3'],0)}

<b>🔴 大盤壓力</b>

R1：<b>{fmt(x['r1'],0)}</b>
R2：{fmt(x['r2'],0)}
R3：{fmt(x['r3'],0)}

📌 52週高：
{fmt(x['h52'],0)}

📌 距52週高：
{pct(x['dist52'])}

━━━━━━━━━━━━━━

<b>🎯 大盤環境：
{x['status']}</b>

評分：
{x['score']:+d} 分

💡 <b>操作參考</b>

{x['advice']}

<b>{x['chase']}</b>

{x['chase_detail']}

📝 主要判斷：

{"、".join(x['reasons'])}

━━━━━━━━━━━━━━

⚠️ 大盤分析僅供技術面參考，
不代表買賣建議。
"""


# ============================================================
# Help
# ============================================================

def help_text():

    return """
<b>📊 Taiwan Stock Radar 6.1</b>

━━━━━━━━━━━━━━

<b>📈 個股分析</b>

直接輸入：

<code>3563</code>

或：

<code>牧德</code>

也可以：

<code>/分析 3563</code>

<code>/分析 牧德</code>

━━━━━━━━━━━━━━

<b>🇹🇼 大盤分析</b>

直接輸入：

<code>大盤</code>

<code>台股大盤</code>

<code>加權</code>

<code>加權指數</code>

<code>TAIEX</code>

<code>TWII</code>

<code>^TWII</code>

也可以：

<code>/分析 大盤</code>

━━━━━━━━━━━━━━

<b>📊 分析內容</b>

現價
今日漲跌
20日漲跌

今日量
5日均量
量比

MA5
MA10
MA20
MA60

KD
RSI
MACD

支撐
壓力

52週高
距52週高

大盤多空環境

━━━━━━━━━━━━━━

<b>⚠️ 本 Bot 為技術分析工具，
不代表買賣建議。</b>
"""


# ============================================================
# Telegram 訊息處理
# ============================================================

def handle_update(u):

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
        "📨 收到訊息：",
        text,
        "chat_id=",
        chat_id
    )

    # --------------------------------------------------------
    # /start /help
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 指令解析
    # --------------------------------------------------------

    if text.startswith("/分析"):

        q = text[3:].strip()

    elif text.lower().startswith(
        "/analyze"
    ):

        q = text[8:].strip()

    elif text.startswith(
        "/分析大盤"
    ):

        q = "大盤"

    else:

        q = text.strip()

    q = q.replace(
        "\u3000",
        ""
    )

    log(
        "🔎 查詢內容：",
        repr(q)
    )

    # --------------------------------------------------------
    # 空白
    # --------------------------------------------------------

    if not q:

        send(
            chat_id,
            help_text()
        )

        return

    # ========================================================
    # ⭐⭐⭐ 大盤判斷必須優先
    # ========================================================

    if is_market_query(q):

        log(
            "🇹🇼 偵測到大盤查詢：",
            q
        )

        send(
            chat_id,
            "🔎 正在抓取 "
            "<b>台股大盤 TAIEX</b>"
            " 技術資料，請稍候..."
        )

        x, err = analyze_market()

        if err:

            send(
                chat_id,
                "⚠️ " + err
            )

            return

        send(
            chat_id,
            market_report(x)
        )

        log(
            "✅ 大盤分析完成"
        )

        return

    # ========================================================
    # 個股
    # ========================================================

    log(
        "📊 偵測為個股查詢：",
        q
    )

    send(
        chat_id,
        f"🔎 正在分析 "
        f"<b>{q}</b>"
        "，請稍候..."
    )

    stock, err = find_stock(q)

    if err:

        send(
            chat_id,
            "⚠️ " + err
        )

        return

    log(
        "🔎 找到股票：",
        stock
    )

    x, err = analyze_stock(
        stock
    )

    if err:

        send(
            chat_id,
            f"⚠️ "
            f"{stock['code']} "
            f"{stock['name']}\n"
            f"{err}"
        )

        return

    send(
        chat_id,
        stock_report(x)
    )

    log(
        "✅ 個股分析完成：",
        stock["code"],
        stock["name"]
    )


# ============================================================
# 主程式
# ============================================================

def main():

    log(
        "======================================"
    )

    log(
        "📊 Taiwan Stock Radar 6.1"
    )

    log(
        "📈 即時技術分析版"
    )

    log(
        "🇹🇼 上市 + 上櫃 + ^TWII"
    )

    log(
        "======================================"
    )

    # --------------------------------------------------------
    # Token
    # --------------------------------------------------------

    if not TOKEN:

        log(
            "❌ BOT TOKEN 未讀取"
        )

        log(
            "請檢查 GitHub Secret："
            "BACKTEST_TELEGRAM_BOT_TOKEN"
        )

        return

    # --------------------------------------------------------
    # Bot
    # --------------------------------------------------------

    me = telegram(
        "getMe"
    )

    log(
        "🤖 Bot：",
        me
    )

    # --------------------------------------------------------
    # Webhook
    # --------------------------------------------------------

    webhook = telegram(
        "getWebhookInfo"
    )

    if (
        webhook
        and
        webhook.get("url")
    ):

        log(
            "❌ Bot 目前有 webhook：",
            webhook.get("url")
        )

        log(
            "請先移除 webhook，"
            "才能使用 getUpdates。"
        )

        return

    # ========================================================
    # ⭐ Telegram offset
    #
    # 不要在這裡先呼叫 getUpdates 丟掉訊息。
    #
    # 從 offset = 0 開始，
    # 取得尚未確認的訊息。
    #
    # 每處理一則後：
    # offset = update_id + 1
    #
    # Telegram 官方規則就是這樣。
    # ========================================================

    offset = 0

    # GitHub Actions 每5分鐘執行一次
    # 每次最多等待約230秒

    end_time = (
        time.time()
        + 230
    )

    log(
        "🟢 開始等待 Telegram 指令"
    )

    while time.time() < end_time:

        remaining = max(
            1,
            min(
                20,
                int(
                    end_time
                    - time.time()
                )
            )
        )

        updates = telegram(
            "getUpdates",
            {
                "offset": offset,
                "timeout": remaining,
                "allowed_updates":
                    '["message"]'
            }
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
                    "❌ handle error:",
                    repr(e)
                )

            finally:

                # ------------------------------------------------
                # ⭐⭐⭐ 處理完才確認
                # ------------------------------------------------

                if update_id is not None:

                    offset = max(
                        offset,
                        int(update_id) + 1
                    )

                    log(
                        "✅ Telegram offset：",
                        offset
                    )

    log(
        "⏹️ 本次 Telegram 輪詢結束"
    )


# ============================================================
# Entry
# ============================================================

if __name__ == "__main__":

    main()
