import os
import warnings
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from flask import Flask, request, jsonify

warnings.filterwarnings('ignore')

VERSION = '6.1-TECH-BOT-WEBHOOK'
TZ = ZoneInfo('Asia/Taipei')
TOKEN = os.getenv('BACKTEST_TELEGRAM_BOT_TOKEN', '')
WEBHOOK_SECRET = os.getenv('TELEGRAM_WEBHOOK_SECRET', '')
PORT = int(os.getenv('PORT', '10000'))

SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0'})
app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=2)


def telegram(method, params=None, post=False):
    if not TOKEN:
        print('❌ BACKTEST_TELEGRAM_BOT_TOKEN 未讀取')
        return None
    url = f'https://api.telegram.org/bot{TOKEN}/{method}'
    try:
        if post:
            r = SESSION.post(url, json=params or {}, timeout=60)
        else:
            r = SESSION.get(url, params=params or {}, timeout=60)
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
        print(f'Telegram {method} error:', repr(e))
        return None


def send(chat_id, text):
    return telegram('sendMessage', {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    }, post=True)


def stock_list():
    out = []
    try:
        j = SESSION.get(
            'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
            timeout=20
        ).json()
        for x in j:
            c = str(x.get('Code', '')).strip()
            n = str(x.get('Name', '')).strip()
            if c.isdigit() and n:
                out.append({'code': c, 'name': n, 'market': 'TWSE', 'symbol': c + '.TW'})
        print('TWSE stocks:', len(out))
    except Exception as e:
        print('TWSE list error:', repr(e))

    try:
        j = SESSION.get(
            'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes',
            timeout=20
        ).json()
        for x in j:
            c = str(x.get('SecuritiesCompanyCode', '')).strip()
            n = str(x.get('CompanyName', '')).strip()
            if c.isdigit() and n:
                out.append({'code': c, 'name': n, 'market': 'TPEx', 'symbol': c + '.TWO'})
        print('TPEx stocks:', sum(1 for x in out if x['market'] == 'TPEx'))
    except Exception as e:
        print('TPEx list error:', repr(e))

    d = {}
    for x in out:
        d[x['code']] = x
    return list(d.values())


def find_stock(q):
    q = q.strip()
    if q.startswith('/分析'):
        q = q[3:].strip()
    elif q.startswith('/analyze'):
        q = q[8:].strip()

    if not q:
        return None, '請輸入股票代號或名稱，例如：3563 或 牧德'

    if q.isdigit():
        candidates = [
            {'code': q, 'name': q, 'market': 'TWSE', 'symbol': q + '.TW'},
            {'code': q, 'name': q, 'market': 'TPEx', 'symbol': q + '.TWO'},
        ]
        for s in candidates:
            try:
                d = yf.Ticker(s['symbol']).history(
                    period='1mo', interval='1d', auto_adjust=False
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
                print('Code lookup:', s['symbol'], repr(e))
        return None, f'找不到「{q}」，請確認股票代號。'

    ss = stock_list()
    for s in ss:
        if q == s['name']:
            return s, None
    m = [s for s in ss if q in s['name']]
    if len(m) == 1:
        return m[0], None
    if m:
        return None, '找到多檔符合：\n' + '\n'.join(
            f"{x['code']} {x['name']}" for x in m[:10]
        )
    return None, f'找不到「{q}」，請輸入正確台股代號或名稱。'


def history(symbol):
    try:
        d = yf.Ticker(symbol).history(
            period='1y', interval='1d', auto_adjust=False
        )
        if d is None or d.empty:
            return None
        d = d.dropna(subset=['Open', 'High', 'Low', 'Close', 'Volume'])
        return d if len(d) >= 70 else None
    except Exception as e:
        print('History error:', symbol, repr(e))
        return None


def kd(d):
    lo = d.Low.rolling(9).min()
    hi = d.High.rolling(9).max()
    rsv = (d.Close - lo) / (hi - lo).replace(0, np.nan) * 100
    k = rsv.ewm(alpha=1/3, adjust=False).mean()
    dline = k.ewm(alpha=1/3, adjust=False).mean()
    return k, dline


def rsi(c, p):
    delta = c.diff()
    g = delta.clip(lower=0)
    l = -delta.clip(upper=0)
    ag = g.ewm(alpha=1/p, adjust=False).mean()
    al = l.ewm(alpha=1/p, adjust=False).mean()
    return 100 - 100 / (1 + ag / al.replace(0, np.nan))


def macd(c):
    dif = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    dea = dif.ewm(span=9, adjust=False).mean()
    return dif, dea, dif - dea


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
        if x >= 8: return '強勢向上'
        if x >= 1: return '溫和向上'
        if x <= -8: return '明顯向下'
        if x <= -1: return '略為向下'
        return '平穩'
    if diff > .05: return '強勢向上'
    if diff > 0: return '溫和向上'
    if diff < -.05: return '明顯向下'
    if diff < 0: return '略為向下'
    return '平穩'


def supports(d, p):
    a = []
    lows = d.Low.tail(60)
    for i in range(2, len(lows) - 2):
        v = lows.iloc[i]
        if v <= lows.iloc[i-2:i].min() and v <= lows.iloc[i+1:i+3].min() and v < p:
            a.append(float(v))
    for ma in [
        d.Close.rolling(10).mean().iloc[-1],
        d.Close.rolling(20).mean().iloc[-1],
        d.Close.rolling(60).mean().iloc[-1],
    ]:
        if pd.notna(ma) and ma < p:
            a.append(float(ma))
    for v in [d.Low.tail(20).min(), d.Low.tail(60).min()]:
        if pd.notna(v) and v < p:
            a.append(float(v))
    return sorted(set(round(x, 2) for x in a), reverse=True)[:3]


def resistances(d, p):
    a = []
    highs = d.High.tail(60)
    for i in range(2, len(highs) - 2):
        v = highs.iloc[i]
        if v >= highs.iloc[i-2:i].max() and v >= highs.iloc[i+1:i+3].max() and v > p:
            a.append(float(v))
    for ma in [
        d.Close.rolling(10).mean().iloc[-1],
        d.Close.rolling(20).mean().iloc[-1],
        d.Close.rolling(60).mean().iloc[-1],
    ]:
        if pd.notna(ma) and ma > p:
            a.append(float(ma))
    for v in [d.High.tail(20).max(), d.High.tail(60).max()]:
        if pd.notna(v) and v > p:
            a.append(float(v))
    return sorted(set(round(x, 2) for x in a))[:3]


def fmt(x, digits=2):
    try:
        return '-' if pd.isna(x) else f'{float(x):.{digits}f}'
    except Exception:
        return '-'


def pct(x):
    try:
        return '-' if pd.isna(x) else f'{float(x):+.2f}%'
    except Exception:
        return '-'


def analyze(s):
    d = history(s['symbol'])
    if d is None:
        return None, '目前無法取得歷史資料，可能是 Yahoo Finance 暫時無資料。'

    c = d.Close.astype(float)
    v = d.Volume.astype(float)
    p = float(c.iloc[-1])
    prev = float(c.iloc[-2])
    gain = (p / prev - 1) * 100

    # 6.1 的量能定義：今日量 ÷ 前 5 個完整交易日平均量
    avg5 = float(v.iloc[-6:-1].mean())
    vr = float(v.iloc[-1] / avg5) if avg5 > 0 else np.nan

    ma5 = float(c.rolling(5).mean().iloc[-1])
    ma10 = float(c.rolling(10).mean().iloc[-1])
    ma20 = float(c.rolling(20).mean().iloc[-1])
    ma60 = float(c.rolling(60).mean().iloc[-1])
    dev10 = (p - ma10) / ma10 * 100 if ma10 > 0 else np.nan
    dev20 = (p - ma20) / ma20 * 100 if ma20 > 0 else np.nan

    k, dline = kd(d)
    r5 = rsi(c, 5)
    r10 = rsi(c, 10)
    dif, dea, _ = macd(c)

    kt = trend(k)
    rt = trend(r5)
    r10t = trend(r10)
    mt = trend(dif, False)
    resonance = (
        kt in {'強勢向上', '溫和向上'}
        and rt in {'強勢向上', '溫和向上'}
        and mt in {'強勢向上', '溫和向上'}
    )

    ss = supports(d, p)
    rr = resistances(d, p)
    s1 = ss[0] if ss else np.nan
    r1 = rr[0] if rr else np.nan
    h52 = float(d.High.tail(252).max())
    dist = (h52 - p) / h52 * 100 if h52 else np.nan
    g20 = (p / c.iloc[-21] - 1) * 100 if len(c) >= 21 else np.nan

    return {
        'stock': s,
        'price': p,
        'gain': gain,
        'today': int(v.iloc[-1] / 1000),
        'avg5': int(avg5 / 1000),
        'vr': vr,
        'turn': p * float(v.iloc[-1]),
        'ma5': ma5,
        'ma10': ma10,
        'ma20': ma20,
        'ma60': ma60,
        'dev10': dev10,
        'dev20': dev20,
        'k': float(k.iloc[-1]),
        'd': float(dline.iloc[-1]),
        'kt': kt,
        'r5': float(r5.iloc[-1]),
        'r10': float(r10.iloc[-1]),
        'rt': rt,
        'r10t': r10t,
        'dif': float(dif.iloc[-1]),
        'dea': float(dea.iloc[-1]),
        'mt': mt,
        'res': resonance,
        's1': s1,
        's2': ss[1] if len(ss) > 1 else np.nan,
        's3': ss[2] if len(ss) > 2 else np.nan,
        'r1': r1,
        'r2': rr[1] if len(rr) > 1 else np.nan,
        'r3': rr[2] if len(rr) > 2 else np.nan,
        'sd': (p - s1) / p * 100 if pd.notna(s1) else np.nan,
        'rd': (r1 - p) / p * 100 if pd.notna(r1) else np.nan,
        'h52': h52,
        'dist': dist,
        'g20': g20,
    }, None


def report(x):
    sym = {
        '強勢向上': '🚀',
        '溫和向上': '↗️',
        '平穩': '➡️',
        '略為向下': '↘️',
        '明顯向下': '🔻',
        '資料不足': '❔'
    }
    return f'''<b>📊 6.1 個股技術分析</b>\n<b>#{x["stock"]["code"]}｜{x["stock"]["name"]}</b>\n📅 {datetime.now(TZ):%Y/%m/%d %H:%M}\n━━━━━━━━━━━━━━\n💰 <b>現價：{fmt(x["price"])}</b>\n📈 今日：{pct(x["gain"])}｜20日：{pct(x["g20"])}\n\n<b>🔊 量能</b>\n今日量：{x["today"]:,} 張\n5日均量：{x["avg5"]:,} 張\n量比：{fmt(x["vr"],1)}x\n成交金額：{x["turn"]/1e8:.2f} 億\n\n<b>🟢 支撐</b>\nS1：<b>{fmt(x["s1"])}</b>\nS2：{fmt(x["s2"])}\nS3：{fmt(x["s3"])}\n距S1：{pct(x["sd"])}\n\n<b>🔴 壓力</b>\nR1：<b>{fmt(x["r1"])}</b>\nR2：{fmt(x["r2"])}\nR3：{fmt(x["r3"])}\n距R1：{pct(x["rd"])}\n\n<b>📐 均線</b>\nMA5：{fmt(x["ma5"])}\nMA10：{fmt(x["ma10"])}（乖離 {pct(x["dev10"])}）\nMA20：{fmt(x["ma20"])}（乖離 {pct(x["dev20"])}）\nMA60：{fmt(x["ma60"])}\n\n<b>📊 技術指標</b>\nKD 9K：{sym.get(x["kt"],"➡️")} {x["kt"]} K={fmt(x["k"])} D={fmt(x["d"])}\nRSI 5T：{sym.get(x["rt"],"➡️")} {x["rt"]} {fmt(x["r5"])}\nRSI 10T：{sym.get(x["r10t"],"➡️")} {x["r10t"]} {fmt(x["r10"])}\nMACD DIF：{sym.get(x["mt"],"➡️")} {x["mt"]} {fmt(x["dif"],3)}\n{"🔥 三線共振" if x["res"] else "— 尚未形成完整三線共振"}\n\n📌 52週高：{fmt(x["h52"])}\n📌 距52週高：{pct(x["dist"])}\n\n💡 技術分析僅供參考，不代表買賣建議。'''


def help_text():
    return '''<b>📊 台股 6.1 個股技術分析 Bot</b>\n\n直接輸入股票代號或名稱：\n<code>3563</code>\n<code>牧德</code>\n\n也可以：\n<code>/分析 3563</code>\n<code>/分析 牧德</code>\n\n平常不會主動推播，只有你輸入查詢才會回覆。\n\n會回傳：現價、支撐、壓力、量能、MA10/20、KD、RSI、MACD。'''


def process_message(cid, text):
    print('📨 收到查詢：', text, 'chat_id=', cid)
    q = text[3:].strip() if text.startswith('/分析') else (
        text[8:].strip() if text.startswith('/analyze') else text
    )

    if text.startswith('/start') or text.startswith('/help'):
        send(cid, help_text())
        return

    if not q:
        send(cid, help_text())
        return

    send(cid, f'🔎 正在分析 <b>{q}</b>，請稍候...')
    stock, err = find_stock(q)
    if err:
        send(cid, '⚠️ ' + err)
        return

    print('🔎 分析：', stock)
    x, err = analyze(stock)
    if err:
        send(cid, f'⚠️ {stock["code"]} {stock["name"]}\n{err}')
        return

    send(cid, report(x))
    print('✅ 分析完成：', stock['code'], stock['name'])


@app.get('/')
def home():
    return 'Taiwan Stock Radar 6.1 Technical Bot is running.', 200


@app.get('/health')
def health():
    return jsonify({'ok': True, 'version': VERSION}), 200


@app.post('/telegram/webhook')
def telegram_webhook():
    if WEBHOOK_SECRET:
        supplied = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
        if supplied != WEBHOOK_SECRET:
            return jsonify({'ok': False}), 403

    update = request.get_json(silent=True) or {}
    m = update.get('message', {})
    cid = m.get('chat', {}).get('id')
    text = str(m.get('text', '')).strip()

    if cid and text:
        # 立即回 200，避免 Telegram 因分析 Yahoo/TWSE 資料較慢而重送 webhook。
        executor.submit(process_message, cid, text)

    return jsonify({'ok': True}), 200


def configure_webhook():
    if not TOKEN:
        print('❌ BOT TOKEN 未設定')
        return False

    base = os.getenv('RENDER_EXTERNAL_URL', '').rstrip('/')
    if not base:
        print('⚠️ 找不到 RENDER_EXTERNAL_URL；請手動設定 WEBHOOK_BASE_URL')
        base = os.getenv('WEBHOOK_BASE_URL', '').rstrip('/')

    if not base:
        print('❌ 沒有 Webhook URL，無法設定 Telegram webhook')
        return False

    url = base + '/telegram/webhook'
    params = {
        'url': url,
        'allowed_updates': ['message'],
    }
    if WEBHOOK_SECRET:
        params['secret_token'] = WEBHOOK_SECRET

    result = telegram('setWebhook', params, post=True)
    if result is not None:
        print('✅ Webhook 已設定：', url)
        return True
    print('❌ Webhook 設定失敗')
    return False


if __name__ == '__main__':
    print('======================================')
    print('📊 Taiwan Stock Radar 6.1 Technical Bot')
    print('📡 Telegram Webhook / 被動查詢模式')
    print('======================================')
    configure_webhook()
    app.run(host='0.0.0.0', port=PORT)
