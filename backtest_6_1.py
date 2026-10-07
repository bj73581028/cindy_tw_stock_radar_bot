import os
import time
import warnings
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings('ignore')

VERSION = '6.1-TECH-BOT'
TZ = ZoneInfo('Asia/Taipei')

TOKEN = os.getenv('BACKTEST_TELEGRAM_BOT_TOKEN', '')

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0'
})


# ============================================================
# Telegram
# ============================================================

def telegram(method, params=None, post=False):

    if not TOKEN:
        print('❌ BACKTEST_TELEGRAM_BOT_TOKEN 未讀取')
        return None

    url = f'https://api.telegram.org/bot{TOKEN}/{method}'

    try:

        if post:
            r = SESSION.post(
                url,
                json=params or {},
                timeout=30
            )
        else:
            r = SESSION.get(
                url,
                params=params or {},
                timeout=30
            )

        print(f'Telegram {method}: HTTP {r.status_code}')

        if not r.ok:
            print(r.text[:1000])
            return None

        j = r.json()

        if not j.get('ok'):
            print(j)
            return None

        return j.get('result')

    except Exception as e:

        print(f'Telegram {method} error:', e)

        return None


def send(chat_id, text):

    return telegram(
        'sendMessage',
        {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True,
        },
        post=True
    )


# ============================================================
# 台股清單
# ============================================================

def stock_list():

    out = []

    # TWSE
    try:

        j = SESSION.get(
            'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
            timeout=20
        ).json()

        for x in j:

            c = str(x.get('Code', '')).strip()
            n = str(x.get('Name', '')).strip()

            if c.isdigit() and n:

                out.append({
                    'code': c,
                    'name': n,
                    'market': 'TWSE',
                    'symbol': c + '.TW'
                })

        print('TWSE stocks:', len(out))

    except Exception as e:

        print('TWSE list error:', e)


    # TPEx
    try:

        j = SESSION.get(
            'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes',
            timeout=20
        ).json()

        for x in j:

            c = str(
                x.get(
                    'SecuritiesCompanyCode',
                    ''
                )
            ).strip()

            n = str(
                x.get(
                    'CompanyName',
                    ''
                )
            ).strip()

            if c.isdigit() and n:

                out.append({
                    'code': c,
                    'name': n,
                    'market': 'TPEx',
                    'symbol': c + '.TWO'
                })

        print(
            'TPEx stocks:',
            len(
                [
                    x for x in out
                    if x['market'] == 'TPEx'
                ]
            )
        )

    except Exception as e:

        print('TPEx list error:', e)


    d = {}

    for x in out:
        d[x['code']] = x

    return list(d.values())


# ============================================================
# 找股票
# ============================================================

def find_stock(q):

    q = q.strip()

    if q.startswith('/分析'):

        q = q[3:].strip()

    elif q.startswith('/analyze'):

        q = q[8:].strip()


    if not q:

        return None, '請輸入股票代號或名稱，例如：3563 或 牧德'


    # 代號
    if q.isdigit():

        candidates = [

            {
                'code': q,
                'name': q,
                'market': 'TWSE',
                'symbol': q + '.TW'
            },

            {
                'code': q,
                'name': q,
                'market': 'TPEx',
                'symbol': q + '.TWO'
            }

        ]

        for s in candidates:

            try:

                d = yf.Ticker(
                    s['symbol']
                ).history(
                    period='1mo',
                    interval='1d',
                    auto_adjust=False
                )

                if d is not None and len(d) >= 3:

                    try:

                        names = stock_list()

                        for item in names:

                            if item['code'] == q:

                                return item, None

                    except Exception:

                        pass

                    return s, None

            except Exception as e:

                print(
                    'Code lookup:',
                    s['symbol'],
                    e
                )

        return None, f'找不到「{q}」，請確認股票代號。'


    # 股票名稱
    ss = stock_list()

    for s in ss:

        if q == s['name']:

            return s, None


    m = [
        s for s in ss
        if q in s['name']
    ]

    if len(m) == 1:

        return m[0], None

    if m:

        return None, (
            '找到多檔符合：\n'
            +
            '\n'.join(
                f"{x['code']} {x['name']}"
                for x in m[:10]
            )
        )


    return None, (
        f'找不到「{q}」，'
        '請輸入正確台股代號或名稱。'
    )


# ============================================================
# 歷史資料
# ============================================================

def history(symbol):

    try:

        d = yf.Ticker(
            symbol
        ).history(
            period='1y',
            interval='1d',
            auto_adjust=False
        )

        if d is None or d.empty:

            return None

        d = d.dropna(
            subset=[
                'Open',
                'High',
                'Low',
                'Close',
                'Volume'
            ]
        )

        return d if len(d) >= 70 else None

    except Exception as e:

        print(
            'History error:',
            symbol,
            e
        )

        return None


# ============================================================
# 大盤歷史資料
# ============================================================

def market_history():

    symbol = '^TWII'

    try:

        d = yf.Ticker(
            symbol
        ).history(
            period='1y',
            interval='1d',
            auto_adjust=False
        )

        if d is None or d.empty:

            print('❌ TWII 無資料')

            return None

        d = d.dropna(
            subset=[
                'Open',
                'High',
                'Low',
                'Close',
                'Volume'
            ]
        )

        if len(d) < 70:

            print(
                '❌ TWII 歷史資料不足：',
                len(d)
            )

            return None

        return d

    except Exception as e:

        print(
            'TWII history error:',
            e
        )

        return None


# ============================================================
# KD
# ============================================================

def kd(d):

    lo = d.Low.rolling(9).min()
    hi = d.High.rolling(9).max()

    rsv = (
        (d.Close - lo)
        /
        (hi - lo).replace(
            0,
            np.nan
        )
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

    g = delta.clip(
        lower=0
    )

    l = -delta.clip(
        upper=0
    )

    ag = g.ewm(
        alpha=1 / p,
        adjust=False
    ).mean()

    al = l.ewm(
        alpha=1 / p,
        adjust=False
    ).mean()

    return (
        100
        -
        100
        /
        (
            1
            +
            ag
            /
            al.replace(
                0,
                np.nan
            )
        )
    )


# ============================================================
# MACD
# ============================================================

def macd(c):

    dif = (
        c.ewm(
            span=12,
            adjust=False
        ).mean()
        -
        c.ewm(
            span=26,
            adjust=False
        ).mean()
    )

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

    s = s.dropna()

    if len(s) < 6:

        return '資料不足'

    a = float(s.iloc[-1])
    b = float(s.iloc[-6])

    diff = a - b


    if norm:

        if abs(b) < 0.01:

            return '平穩'

        x = diff / abs(b) * 100

        if x >= 8:

            return '強勢向上'

        if x >= 1:

            return '溫和向上'

        if x <= -8:

            return '明顯向下'

        if x <= -1:

            return '略為向下'

        return '平穩'


    if diff > .05:

        return '強勢向上'

    if diff > 0:

        return '溫和向上'

    if diff < -.05:

        return '明顯向下'

    if diff < 0:

        return '略為向下'

    return '平穩'


# ============================================================
# 支撐
# ============================================================

def supports(d, p):

    a = []

    lows = d.Low.tail(60)

    for i in range(
        2,
        len(lows) - 2
    ):

        v = lows.iloc[i]

        if (
            v <= lows.iloc[i-2:i].min()
            and
            v <= lows.iloc[i+1:i+3].min()
            and
            v < p
        ):

            a.append(
                float(v)
            )


    for ma in [

        d.Close.rolling(10).mean().iloc[-1],

        d.Close.rolling(20).mean().iloc[-1],

        d.Close.rolling(60).mean().iloc[-1]

    ]:

        if pd.notna(ma) and ma < p:

            a.append(
                float(ma)
            )


    for v in [

        d.Low.tail(20).min(),

        d.Low.tail(60).min()

    ]:

        if pd.notna(v) and v < p:

            a.append(
                float(v)
            )


    return sorted(
        set(
            round(x, 2)
            for x in a
        ),
        reverse=True
    )[:3]


# ============================================================
# 壓力
# ============================================================

def resistances(d, p):

    a = []

    highs = d.High.tail(60)

    for i in range(
        2,
        len(highs) - 2
    ):

        v = highs.iloc[i]

        if (
            v >= highs.iloc[i-2:i].max()
            and
            v >= highs.iloc[i+1:i+3].max()
            and
            v > p
        ):

            a.append(
                float(v)
            )


    for ma in [

        d.Close.rolling(10).mean().iloc[-1],

        d.Close.rolling(20).mean().iloc[-1],

        d.Close.rolling(60).mean().iloc[-1]

    ]:

        if pd.notna(ma) and ma > p:

            a.append(
                float(ma)
            )


    for v in [

        d.High.tail(20).max(),

        d.High.tail(60).max()

    ]:

        if pd.notna(v) and v > p:

            a.append(
                float(v)
            )


    return sorted(
        set(
            round(x, 2)
            for x in a
        )
    )[:3]


# ============================================================
# 格式
# ============================================================

def fmt(x, digits=2):

    try:

        if pd.isna(x):

            return '-'

        return f'{float(x):.{digits}f}'

    except Exception:

        return '-'


def pct(x):

    try:

        if pd.isna(x):

            return '-'

        return f'{float(x):+.2f}%'

    except Exception:

        return '-'


# ============================================================
# 個股分析
# ============================================================

def analyze(s):

    d = history(
        s['symbol']
    )

    if d is None:

        return None, (
            '目前無法取得歷史資料，'
            '可能是 Yahoo Finance 暫時無資料。'
        )


    c = d.Close.astype(float)

    v = d.Volume.astype(float)

    p = float(
        c.iloc[-1]
    )

    prev = float(
        c.iloc[-2]
    )

    gain = (
        p / prev - 1
    ) * 100


    avg5 = float(
        v.iloc[-6:-1].mean()
    )

    vr = (
        float(
            v.iloc[-1] / avg5
        )
        if avg5 > 0
        else np.nan
    )


    ma5 = float(
        c.rolling(5).mean().iloc[-1]
    )

    ma10 = float(
        c.rolling(10).mean().iloc[-1]
    )

    ma20 = float(
        c.rolling(20).mean().iloc[-1]
    )

    ma60 = float(
        c.rolling(60).mean().iloc[-1]
    )


    dev10 = (
        (p - ma10)
        / ma10
        * 100
        if ma10 > 0
        else np.nan
    )

    dev20 = (
        (p - ma20)
        / ma20
        * 100
        if ma20 > 0
        else np.nan
    )


    k, dline = kd(d)

    r5 = rsi(
        c,
        5
    )

    r10 = rsi(
        c,
        10
    )

    dif, dea, _ = macd(c)


    kt = trend(k)

    rt = trend(r5)

    r10t = trend(r10)

    mt = trend(
        dif,
        False
    )


    resonance = (
        kt in {
            '強勢向上',
            '溫和向上'
        }
        and
        rt in {
            '強勢向上',
            '溫和向上'
        }
        and
        mt in {
            '強勢向上',
            '溫和向上'
        }
    )


    ss = supports(
        d,
        p
    )

    rr = resistances(
        d,
        p
    )


    s1 = (
        ss[0]
        if ss
        else np.nan
    )

    r1 = (
        rr[0]
        if rr
        else np.nan
    )


    h52 = float(
        d.High.tail(252).max()
    )


    dist = (
        (h52 - p)
        / h52
        * 100
        if h52
        else np.nan
    )


    g20 = (
        (
            p
            /
            c.iloc[-21]
            - 1
        )
        * 100
        if len(c) >= 21
        else np.nan
    )


    return {

        'stock': s,

        'price': p,

        'gain': gain,

        'today': int(
            v.iloc[-1] / 1000
        ),

        'avg5': int(
            avg5 / 1000
        ),

        'vr': vr,

        'turn':
            p * float(
                v.iloc[-1]
            ),

        'ma5': ma5,

        'ma10': ma10,

        'ma20': ma20,

        'ma60': ma60,

        'dev10': dev10,

        'dev20': dev20,

        'k':
            float(
                k.iloc[-1]
            ),

        'd':
            float(
                dline.iloc[-1]
            ),

        'kt': kt,

        'r5':
            float(
                r5.iloc[-1]
            ),

        'r10':
            float(
                r10.iloc[-1]
            ),

        'rt': rt,

        'r10t': r10t,

        'dif':
            float(
                dif.iloc[-1]
            ),

        'dea':
            float(
                dea.iloc[-1]
            ),

        'mt': mt,

        'res':
            resonance,

        's1': s1,

        's2':
            ss[1]
            if len(ss) > 1
            else np.nan,

        's3':
            ss[2]
            if len(ss) > 2
            else np.nan,

        'r1': r1,

        'r2':
            rr[1]
            if len(rr) > 1
            else np.nan,

        'r3':
            rr[2]
            if len(rr) > 2
            else np.nan,

        'sd':
            (
                (p - s1)
                / p
                * 100
                if pd.notna(s1)
                else np.nan
            ),

        'rd':
            (
                (r1 - p)
                / p
                * 100
                if pd.notna(r1)
                else np.nan
            ),

        'h52': h52,

        'dist': dist,

        'g20': g20,

    }, None


# ============================================================
# 大盤分析
# ============================================================

def analyze_market():

    d = market_history()

    if d is None:

        return None, (
            '目前無法取得加權指數歷史資料，'
            '可能是 Yahoo Finance 暫時無資料。'
        )


    c = d.Close.astype(float)

    v = d.Volume.astype(float)

    p = float(
        c.iloc[-1]
    )

    prev = float(
        c.iloc[-2]
    )


    gain = (
        p / prev - 1
    ) * 100


    # ----------------------------
    # 成交量
    # ----------------------------

    avg5 = float(
        v.iloc[-6:-1].mean()
    )

    vr = (
        float(
            v.iloc[-1] / avg5
        )
        if avg5 > 0
        else np.nan
    )


    # ----------------------------
    # 均線
    # ----------------------------

    ma5 = float(
        c.rolling(5).mean().iloc[-1]
    )

    ma10 = float(
        c.rolling(10).mean().iloc[-1]
    )

    ma20 = float(
        c.rolling(20).mean().iloc[-1]
    )

    ma60 = float(
        c.rolling(60).mean().iloc[-1]
    )


    dev5 = (
        (p - ma5)
        / ma5
        * 100
    )

    dev10 = (
        (p - ma10)
        / ma10
        * 100
    )

    dev20 = (
        (p - ma20)
        / ma20
        * 100
    )

    dev60 = (
        (p - ma60)
        / ma60
        * 100
    )


    # ----------------------------
    # 技術指標
    # ----------------------------

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
        False
    )


    # ----------------------------
    # 三線共振
    # ----------------------------

    resonance = (
        kt in {
            '強勢向上',
            '溫和向上'
        }
        and
        rt in {
            '強勢向上',
            '溫和向上'
        }
        and
        mt in {
            '強勢向上',
            '溫和向上'
        }
    )


    # ----------------------------
    # 支撐壓力
    # ----------------------------

    ss = supports(
        d,
        p
    )

    rr = resistances(
        d,
        p
    )


    s1 = (
        ss[0]
        if len(ss) >= 1
        else np.nan
    )

    s2 = (
        ss[1]
        if len(ss) >= 2
        else np.nan
    )

    s3 = (
        ss[2]
        if len(ss) >= 3
        else np.nan
    )


    r1 = (
        rr[0]
        if len(rr) >= 1
        else np.nan
    )

    r2 = (
        rr[1]
        if len(rr) >= 2
        else np.nan
    )

    r3 = (
        rr[2]
        if len(rr) >= 3
        else np.nan
    )


    # ----------------------------
    # 52週高
    # ----------------------------

    h52 = float(
        d.High.tail(252).max()
    )

    dist52 = (
        (h52 - p)
        / h52
        * 100
    )


    # ----------------------------
    # 20日漲跌
    # ----------------------------

    g20 = (
        (
            p
            /
            c.iloc[-21]
            - 1
        )
        * 100
        if len(c) >= 21
        else np.nan
    )


    # ----------------------------
    # MA排列
    # ----------------------------

    ma_bull = (
        ma5 > ma10
        and
        ma10 > ma20
        and
        ma20 > ma60
    )


    # ----------------------------
    # 大盤趨勢判斷
    # ----------------------------

    bullish_score = 0

    bearish_score = 0


    if p > ma20:
        bullish_score += 1
    else:
        bearish_score += 1


    if p > ma60:
        bullish_score += 1
    else:
        bearish_score += 1


    if ma5 > ma10:
        bullish_score += 1
    else:
        bearish_score += 1


    if ma10 > ma20:
        bullish_score += 1
    else:
        bearish_score += 1


    if ma20 > ma60:
        bullish_score += 1
    else:
        bearish_score += 1


    if kt in {
        '強勢向上',
        '溫和向上'
    }:

        bullish_score += 1

    else:

        bearish_score += 1


    if rt in {
        '強勢向上',
        '溫和向上'
    }:

        bullish_score += 1

    else:

        bearish_score += 1


    if mt in {
        '強勢向上',
        '溫和向上'
    }:

        bullish_score += 1

    else:

        bearish_score += 1


    if bullish_score >= 6:

        market_trend = '🟢 多頭偏強'

    elif bullish_score >= 4:

        market_trend = '🟡 震盪偏多'

    elif bearish_score >= 6:

        market_trend = '🔴 空頭偏弱'

    else:

        market_trend = '🟠 震盪偏弱'


    # ----------------------------
    # 追價判斷
    # ----------------------------

    if (

        bullish_score >= 6
        and
        pd.notna(r1)
        and
        (r1 - p) / p * 100 >= 1.5
        and
        vr >= 1.0

    ):

        chase = (
            '🟢 環境偏多，可積極尋找強勢股'
        )

    elif (

        bullish_score >= 4
        and
        pd.notna(r1)
        and
        (r1 - p) / p * 100 >= 0.8

    ):

        chase = (
            '🟡 偏多但接近壓力，宜挑選個股'
        )

    elif (

        pd.notna(r1)
        and
        (r1 - p) / p * 100 < 0.8

    ):

        chase = (
            '⚠️ 接近壓力區，不宜盲目追高'
        )

    else:

        chase = (
            '🔴 大盤偏弱，追價宜保守'
        )


    return {

        'price': p,

        'gain': gain,

        'today':
            int(
                v.iloc[-1] / 1000
            ),

        'avg5':
            int(
                avg5 / 1000
            ),

        'vr': vr,

        'ma5': ma5,

        'ma10': ma10,

        'ma20': ma20,

        'ma60': ma60,

        'dev5': dev5,

        'dev10': dev10,

        'dev20': dev20,

        'dev60': dev60,

        'k':
            float(
                k.iloc[-1]
            ),

        'd':
            float(
                dline.iloc[-1]
            ),

        'kt': kt,

        'r5':
            float(
                r5.iloc[-1]
            ),

        'r10':
            float(
                r10.iloc[-1]
            ),

        'rt': rt,

        'r10t': r10t,

        'dif':
            float(
                dif.iloc[-1]
            ),

        'dea':
            float(
                dea.iloc[-1]
            ),

        'hist':
            float(
                hist.iloc[-1]
            ),

        'mt': mt,

        'res': resonance,

        's1': s1,

        's2': s2,

        's3': s3,

        'r1': r1,

        'r2': r2,

        'r3': r3,

        'h52': h52,

        'dist52': dist52,

        'g20': g20,

        'ma_bull':
            ma_bull,

        'bullish_score':
            bullish_score,

        'bearish_score':
            bearish_score,

        'market_trend':
            market_trend,

        'chase':
            chase,

    }, None


# ============================================================
# 個股報告
# ============================================================

def report(x):

    sym = {

        '強勢向上': '🚀',

        '溫和向上': '↗️',

        '平穩': '➡️',

        '略為向下': '↘️',

        '明顯向下': '🔻',

        '資料不足': '❔'

    }


    return f'''
<b>📊 6.1 個股技術分析</b>
<b>#{x["stock"]["code"]}｜{x["stock"]["name"]}</b>
📅 {datetime.now(TZ):%Y/%m/%d %H:%M}

━━━━━━━━━━━━━━

💰 <b>現價：{fmt(x["price"])}</b>

📈 今日：{pct(x["gain"])}
📈 20日：{pct(x["g20"])}

<b>🔊 量能</b>

今日量：{x["today"]:,} 張
5日均量：{x["avg5"]:,} 張
量比：{fmt(x["vr"],1)}x

<b>🟢 支撐</b>

S1：<b>{fmt(x["s1"])}</b>
S2：{fmt(x["s2"])}
S3：{fmt(x["s3"])}

<b>🔴 壓力</b>

R1：<b>{fmt(x["r1"])}</b>
R2：{fmt(x["r2"])}
R3：{fmt(x["r3"])}

<b>📐 均線</b>

MA5：{fmt(x["ma5"])}
MA10：{fmt(x["ma10"])}（乖離 {pct(x["dev10"])}）
MA20：{fmt(x["ma20"])}（乖離 {pct(x["dev20"])}）
MA60：{fmt(x["ma60"])}

<b>📊 技術指標</b>

KD 9K：
{sym.get(x["kt"],"➡️")} {x["kt"]}
K={fmt(x["k"])} D={fmt(x["d"])}

RSI 5T：
{sym.get(x["rt"],"➡️")} {x["rt"]} {fmt(x["r5"])}

RSI 10T：
{sym.get(x["r10t"],"➡️")} {x["r10t"]} {fmt(x["r10"])}

MACD DIF：
{sym.get(x["mt"],"➡️")} {x["mt"]} {fmt(x["dif"],3)}

{"🔥 三線共振" if x["res"] else "— 尚未形成完整三線共振"}

📌 52週高：{fmt(x["h52"])}
📌 距52週高：{pct(x["dist"])}

💡 技術分析僅供參考，不代表買賣建議。
'''


# ============================================================
# 大盤報告
# ============================================================

def market_report(x):

    sym = {

        '強勢向上': '🚀',

        '溫和向上': '↗️',

        '平穩': '➡️',

        '略為向下': '↘️',

        '明顯向下': '🔻',

        '資料不足': '❔'

    }


    return f'''
<b>📊 Taiwan Stock Radar 6.1｜大盤分析</b>

<b>🇹🇼 加權指數 TAIEX</b>

📅 {datetime.now(TZ):%Y/%m/%d %H:%M}

━━━━━━━━━━━━━━

💰 <b>目前指數：{fmt(x["price"])}</b>

📈 今日漲跌：{pct(x["gain"])}
📈 20日漲跌：{pct(x["g20"])}

━━━━━━━━━━━━━━

<b>🔊 大盤量能</b>

今日量：約 {x["today"]:,} 張
5日均量：約 {x["avg5"]:,} 張
量能比：約 {fmt(x["vr"],2)}x

━━━━━━━━━━━━━━

<b>📐 均線結構</b>

MA5：{fmt(x["ma5"])}
MA10：{fmt(x["ma10"])}
MA20：{fmt(x["ma20"])}
MA60：{fmt(x["ma60"])}

MA5乖離：{pct(x["dev5"])}
MA10乖離：{pct(x["dev10"])}
MA20乖離：{pct(x["dev20"])}
MA60乖離：{pct(x["dev60"])}

{"🟢 MA多頭排列" if x["ma_bull"] else "⚠️ MA尚未形成完整多頭排列"}

━━━━━━━━━━━━━━

<b>📊 技術指標</b>

KD 9K：
{sym.get(x["kt"],"➡️")} {x["kt"]}
K={fmt(x["k"])} D={fmt(x["d"])}

RSI 5T：
{sym.get(x["rt"],"➡️")} {x["rt"]} {fmt(x["r5"])}

RSI 10T：
{sym.get(x["r10t"],"➡️")} {x["r10t"]} {fmt(x["r10"])}

MACD DIF：
{sym.get(x["mt"],"➡️")} {x["mt"]} {fmt(x["dif"],3)}

{"🔥 大盤三線共振" if x["res"] else "— 尚未形成完整三線共振"}

━━━━━━━━━━━━━━

<b>🟢 大盤支撐</b>

S1：<b>{fmt(x["s1"])}</b>
S2：{fmt(x["s2"])}
S3：{fmt(x["s3"])}

━━━━━━━━━━━━━━

<b>🔴 大盤壓力</b>

R1：<b>{fmt(x["r1"])}</b>
R2：{fmt(x["r2"])}
R3：{fmt(x["r3"])}

━━━━━━━━━━━━━━

<b>📌 52週高點</b>

52週高：{fmt(x["h52"])}
距離52週高：{pct(x["dist52"])}

━━━━━━━━━━━━━━

<b>🎯 大盤環境判斷</b>

{x["market_trend"]}

多頭分數：
{x["bullish_score"]} / 8

空頭分數：
{x["bearish_score"]} / 8

━━━━━━━━━━━━━━

<b>🚦 追價參考</b>

{x["chase"]}

━━━━━━━━━━━━━━

💡 本分析為技術面量化判斷，
僅供投資研究參考，不代表買賣建議。
'''


# ============================================================
# Help
# ============================================================

def help_text():

    return '''
<b>📊 Taiwan Stock Radar 6.1</b>

<b>📈 個股分析</b>

直接輸入：

<code>3563</code>
<code>牧德</code>

或：

<code>/分析 3563</code>
<code>/分析 牧德</code>

━━━━━━━━━━━━━━

<b>🇹🇼 大盤分析</b>

直接輸入：

<code>大盤</code>

或：

<code>TWII</code>
<code>TAIEX</code>

也可以：

<code>/分析 大盤</code>
<code>/分析 TWII</code>

━━━━━━━━━━━━━━

大盤會分析：

• 加權指數
• 今日漲跌
• 20日漲跌
• MA5 / MA10 / MA20 / MA60
• KD 9K
• RSI 5T
• RSI 10T
• MACD DIF
• 大盤量能
• 支撐位
• 壓力位
• 52週高點
• 大盤多空環境
• 追價參考
'''


# ============================================================
# Telegram 指令
# ============================================================

def handle_update(u):

    m = u.get(
        'message',
        {}
    )

    chat = m.get(
        'chat',
        {}
    )

    cid = chat.get(
        'id'
    )

    text = str(
        m.get(
            'text',
            ''
        )
    ).strip()


    if not cid or not text:

        return


    print(
        '📨 收到訊息：',
        text,
        'chat_id=',
        cid
    )


    # ----------------------------
    # Help
    # ----------------------------

    if (
        text.startswith('/start')
        or
        text.startswith('/help')
    ):

        send(
            cid,
            help_text()
        )

        return


    # ----------------------------
    # 移除指令
    # ----------------------------

    q = (

        text[3:].strip()

        if text.startswith('/分析')

        else

        text[8:].strip()

        if text.startswith('/analyze')

        else

        text

    )


    if not q:

        send(
            cid,
            help_text()
        )

        return


    # ========================================================
    # ⭐ 大盤模式
    # ========================================================

    market_words = {

        '大盤',

        '台股大盤',

        '加權',

        '加權指數',

        'TAIEX',

        'TaiEX',

        'TWII',

        'twii',

        '^TWII'

    }


    if q in market_words:

        send(
            cid,
            '🇹🇼 正在分析加權指數，請稍候...'
        )


        print(
            '📊 執行大盤分析'
        )


        x, err = analyze_market()


        if err:

            send(
                cid,
                '⚠️ ' + err
            )

            return


        send(
            cid,
            market_report(x)
        )


        print(
            '✅ 大盤分析完成'
        )

        return


    # ========================================================
    # 個股模式
    # ========================================================

    send(
        cid,
        f'🔎 正在分析 <b>{q}</b>，請稍候...'
    )


    stock, err = find_stock(
        q
    )


    if err:

        send(
            cid,
            '⚠️ ' + err
        )

        return


    print(
        '🔎 分析：',
        stock
    )


    x, err = analyze(
        stock
    )


    if err:

        send(
            cid,
            f'''
⚠️ {stock["code"]} {stock["name"]}

{err}
'''
        )

        return


    send(
        cid,
        report(x)
    )


    print(
        '✅ 分析完成：',
        stock['code'],
        stock['name']
    )


# ============================================================
# Main
# ============================================================

def main():

    print(
        '======================================'
    )

    print(
        '📊 Taiwan Stock Radar 6.1 Technical Bot'
    )

    print(
        '======================================'
    )


    if not TOKEN:

        print(
            '❌ BOT TOKEN 未讀取，'
            '請檢查 GitHub Secret：'
            'BACKTEST_TELEGRAM_BOT_TOKEN'
        )

        return


    me = telegram(
        'getMe'
    )

    print(
        '🤖 Bot：',
        me
    )


    webhook = telegram(
        'getWebhookInfo'
    )


    if webhook and webhook.get('url'):

        print(
            '❌ 目前 Bot 有 webhook：',
            webhook.get('url')
        )

        print(
            '請移除 webhook 後才能使用 getUpdates。'
        )

        return


    # ========================================================
    # 取得目前 Offset
    # ========================================================

    updates = telegram(
        'getUpdates',
        {
            'timeout': 1,
            'allowed_updates':
                '["message"]'
        }
    )


    offset = 0


    if updates:

        offset = (
            max(
                u.get(
                    'update_id',
                    0
                )
                for u in updates
            )
            + 1
        )

        print(
            'ℹ️ 忽略舊訊息，'
            '起始 offset =',
            offset
        )


    # ========================================================
    # 持續等待 Telegram
    # ========================================================

    end_at = (
        time.time()
        +
        240
    )


    print(
        '🟢 開始持續等待 Telegram 指令（約 4 分鐘）'
    )


    while time.time() < end_at:

        remaining = max(
            1,
            min(
                30,
                int(
                    end_at
                    -
                    time.time()
                )
            )
        )


        updates = telegram(
            'getUpdates',
            {
                'offset':
                    offset,

                'timeout':
                    remaining,

                'allowed_updates':
                    '["message"]'
            }
        )


        if not updates:

            continue


        for u in updates:

            uid = u.get(
                'update_id'
            )


            if uid is not None:

                offset = max(
                    offset,
                    uid + 1
                )


            try:

                handle_update(
                    u
                )

            except Exception as e:

                print(
                    '❌ 處理訊息錯誤：',
                    repr(e)
                )


    print(
        '⏹️ 本次輪詢結束'
    )


# ============================================================
# 執行
# ============================================================

if __name__ == '__main__':

    main()
