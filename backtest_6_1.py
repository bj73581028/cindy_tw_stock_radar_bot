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
SESSION.headers.update({'User-Agent': 'Mozilla/5.0'})

MARKET_SYMBOL='^TWII'
MARKET_KEYWORDS={'大盤','台股大盤','加權','加權指數','TAIEX','TWII','^TWII'}

def is_market_query(q):
    q=str(q).strip()
    return q in MARKET_KEYWORDS or q.upper() in {'TAIEX','TWII','^TWII'}


def telegram(method, params=None, post=False):
    if not TOKEN:
        print('❌ BACKTEST_TELEGRAM_BOT_TOKEN 未讀取')
        return None
    url = f'https://api.telegram.org/bot{TOKEN}/{method}'
    try:
        if post:
            r = SESSION.post(url, json=params or {}, timeout=30)
        else:
            r = SESSION.get(url, params=params or {}, timeout=30)
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
    return telegram('sendMessage', {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    }, post=True)


def stock_list():
    out = []
    try:
        j = SESSION.get('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL', timeout=20).json()
        for x in j:
            c = str(x.get('Code', '')).strip()
            n = str(x.get('Name', '')).strip()
            if c.isdigit() and n:
                out.append({'code': c, 'name': n, 'market': 'TWSE', 'symbol': c + '.TW'})
        print('TWSE stocks:', len(out))
    except Exception as e:
        print('TWSE list error:', e)

    try:
        j = SESSION.get('https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes', timeout=20).json()
        for x in j:
            c = str(x.get('SecuritiesCompanyCode', '')).strip()
            n = str(x.get('CompanyName', '')).strip()
            if c.isdigit() and n:
                out.append({'code': c, 'name': n, 'market': 'TPEx', 'symbol': c + '.TWO'})
        print('TPEx stocks:', len(out) - sum(1 for x in out if x['market'] == 'TPEx') + len([x for x in out if x['market'] == 'TPEx']))
    except Exception as e:
        print('TPEx list error:', e)

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

    if is_market_query(q):
        return {'code':'TWII','name':'加權指數','market':'TWSE','symbol':MARKET_SYMBOL}, None

    # 代號優先：直接嘗試 TWSE / TPEx，避免名單 API 偶發失敗時完全不能查
    if q.isdigit():
        candidates = [
            {'code': q, 'name': q, 'market': 'TWSE', 'symbol': q + '.TW'},
            {'code': q, 'name': q, 'market': 'TPEx', 'symbol': q + '.TWO'},
        ]
        for s in candidates:
            try:
                d = yf.Ticker(s['symbol']).history(period='1mo', interval='1d', auto_adjust=False)
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
                print('Code lookup:', s['symbol'], e)
        return None, f'找不到「{q}」，請確認股票代號。'

    ss = stock_list()
    for s in ss:
        if q == s['name']:
            return s, None
    m = [s for s in ss if q in s['name']]
    if len(m) == 1:
        return m[0], None
    if m:
        return None, '找到多檔符合：\n' + '\n'.join(f"{x['code']} {x['name']}" for x in m[:10])
    return None, f'找不到「{q}」，請輸入正確台股代號或名稱。'


def history(symbol):
    try:
        d = yf.Ticker(symbol).history(period='1y', interval='1d', auto_adjust=False)
        if d is None or d.empty:
            return None
        d = d.dropna(subset=['Open', 'High', 'Low', 'Close', 'Volume'])
        return d if len(d) >= 70 else None
    except Exception as e:
        print('History error:', symbol, e)
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
    for ma in [d.Close.rolling(10).mean().iloc[-1], d.Close.rolling(20).mean().iloc[-1], d.Close.rolling(60).mean().iloc[-1]]:
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
    for ma in [d.Close.rolling(10).mean().iloc[-1], d.Close.rolling(20).mean().iloc[-1], d.Close.rolling(60).mean().iloc[-1]]:
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


def direction_icon(t):
    return {'強勢向上':'🚀','溫和向上':'↗️','平穩':'➡️','略為向下':'↘️','明顯向下':'🔻','資料不足':'❔'}.get(t,'➡️')

def analyze(s):
    d = history(s['symbol'])
    if d is None:
        return None, '目前無法取得歷史資料，可能是 Yahoo Finance 暫時無資料。'

    c = d.Close.astype(float)
    v = d.Volume.astype(float)
    p = float(c.iloc[-1])
    prev = float(c.iloc[-2])
    gain = (p / prev - 1) * 100
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
    resonance = kt in {'強勢向上', '溫和向上'} and rt in {'強勢向上', '溫和向上'} and mt in {'強勢向上', '溫和向上'}

    ss = supports(d, p)
    rr = resistances(d, p)
    s1 = ss[0] if ss else np.nan
    r1 = rr[0] if rr else np.nan
    h52 = float(d.High.tail(252).max())
    dist = (h52 - p) / h52 * 100 if h52 else np.nan
    g20 = (p / c.iloc[-21] - 1) * 100 if len(c) >= 21 else np.nan

    return {
        'stock': s, 'price': p, 'gain': gain,
        'today': int(v.iloc[-1] / 1000), 'avg5': int(avg5 / 1000), 'vr': vr,
        'turn': p * float(v.iloc[-1]),
        'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60,
        'dev10': dev10, 'dev20': dev20,
        'k': float(k.iloc[-1]), 'd': float(dline.iloc[-1]), 'kt': kt,
        'r5': float(r5.iloc[-1]), 'r10': float(r10.iloc[-1]), 'rt': rt, 'r10t': r10t,
        'dif': float(dif.iloc[-1]), 'dea': float(dea.iloc[-1]), 'mt': mt,
        'res': resonance,
        's1': s1, 's2': ss[1] if len(ss) > 1 else np.nan, 's3': ss[2] if len(ss) > 2 else np.nan,
        'r1': r1, 'r2': rr[1] if len(rr) > 1 else np.nan, 'r3': rr[2] if len(rr) > 2 else np.nan,
        'sd': (p - s1) / p * 100 if pd.notna(s1) else np.nan,
        'rd': (r1 - p) / p * 100 if pd.notna(r1) else np.nan,
        'h52': h52, 'dist': dist, 'g20': g20,
    }, None


def report(x):
    sym = {'強勢向上':'🚀','溫和向上':'↗️','平穩':'➡️','略為向下':'↘️','明顯向下':'🔻','資料不足':'❔'}
    return f'''<b>📊 6.1 個股技術分析</b>\n<b>#{x["stock"]["code"]}｜{x["stock"]["name"]}</b>\n📅 {datetime.now(TZ):%Y/%m/%d %H:%M}\n━━━━━━━━━━━━━━\n💰 <b>現價：{fmt(x["price"])}</b>\n📈 今日：{pct(x["gain"])}｜20日：{pct(x["g20"])}\n\n<b>🔊 量能</b>\n今日量：{x["today"]:,} 張\n5日均量：{x["avg5"]:,} 張\n量比：{fmt(x["vr"],1)}x\n成交金額：{x["turn"]/1e8:.2f} 億\n\n<b>🟢 支撐</b>\nS1：<b>{fmt(x["s1"])}</b>\nS2：{fmt(x["s2"])}\nS3：{fmt(x["s3"])}\n距S1：{pct(x["sd"])}\n\n<b>🔴 壓力</b>\nR1：<b>{fmt(x["r1"])}</b>\nR2：{fmt(x["r2"])}\nR3：{fmt(x["r3"])}\n距R1：{pct(x["rd"])}\n\n<b>📐 均線</b>\nMA5：{fmt(x["ma5"])}\nMA10：{fmt(x["ma10"])}（乖離 {pct(x["dev10"])}）\nMA20：{fmt(x["ma20"])}（乖離 {pct(x["dev20"])}）\nMA60：{fmt(x["ma60"])}\n\n<b>📊 技術指標</b>\nKD 9K：{sym.get(x["kt"],"➡️")} {x["kt"]} K={fmt(x["k"])} D={fmt(x["d"])}\nRSI 5T：{sym.get(x["rt"],"➡️")} {x["rt"]} {fmt(x["r5"])}\nRSI 10T：{sym.get(x["r10t"],"➡️")} {x["r10t"]} {fmt(x["r10"])}\nMACD DIF：{sym.get(x["mt"],"➡️")} {x["mt"]} {fmt(x["dif"],3)}\n{"🔥 三線共振" if x["res"] else "— 尚未形成完整三線共振"}\n\n📌 52週高：{fmt(x["h52"])}\n📌 距52週高：{pct(x["dist"])}\n\n💡 技術分析僅供參考，不代表買賣建議。'''



def analyze_market():
    d=history(MARKET_SYMBOL)
    if d is None: return None,'目前無法取得加權指數歷史資料，可能是 Yahoo Finance 暫時無資料。'
    c=d.Close.astype(float); v=d.Volume.astype(float); p=float(c.iloc[-1]); prev=float(c.iloc[-2])
    gain=(p/prev-1)*100; g20=(p/c.iloc[-21]-1)*100 if len(c)>=21 else np.nan
    ma5=float(c.rolling(5).mean().iloc[-1]); ma10=float(c.rolling(10).mean().iloc[-1]); ma20=float(c.rolling(20).mean().iloc[-1]); ma60=float(c.rolling(60).mean().iloc[-1])
    dev10=(p-ma10)/ma10*100; dev20=(p-ma20)/ma20*100
    avg5=float(v.iloc[-6:-1].mean()); vr=float(v.iloc[-1]/avg5) if avg5>0 else np.nan; vc=(float(v.iloc[-1])/avg5-1)*100 if avg5>0 else np.nan
    k,dline=kd(d); r5=rsi(c,5); r10=rsi(c,10); dif,dea,hist=macd(c)
    kt=trend(k); rt=trend(r5); r10t=trend(r10); mt=trend(dif,True)
    ss=supports(d,p); rr=resistances(d,p); h52=float(d.High.tail(252).max()); dist52=(h52-p)/h52*100 if h52 else np.nan
    score=0; reasons=[]
    if p>ma20: score+=2; reasons.append('指數站上MA20')
    else: score-=2; reasons.append('指數跌破MA20')
    ma20prev=float(c.rolling(20).mean().iloc[-6])
    if ma20>ma20prev: score+=2; reasons.append('MA20向上')
    else: score-=2; reasons.append('MA20向下')
    if kt in {'強勢向上','溫和向上'}: score+=1; reasons.append('KD偏多')
    elif kt in {'略為向下','明顯向下'}: score-=1; reasons.append('KD轉弱')
    if rt in {'強勢向上','溫和向上'}: score+=1; reasons.append('RSI5偏多')
    elif rt in {'略為向下','明顯向下'}: score-=1; reasons.append('RSI5轉弱')
    if mt in {'強勢向上','溫和向上'}: score+=2; reasons.append('MACD DIF向上')
    elif mt in {'略為向下','明顯向下'}: score-=2; reasons.append('MACD DIF轉弱')
    if pd.notna(g20):
        if g20>3: score+=1
        elif g20<-3: score-=1
    if score>=5: status='🟢 偏多'; advice='可積極尋找強勢股，優先挑量價齊揚、站上均線且未過度乖離者。'
    elif score>=2: status='🟡 震盪偏多'; advice='可以做個股，但建議挑強勢股，不宜全面追高。'
    elif score<=-5: status='🔴 偏空'; advice='大盤環境偏弱，建議降低追高，等待轉強訊號。'
    else: status='🟠 震盪'; advice='大盤方向不明，適合個別選股，不宜因短線反彈全面追價。'
    warns=[]
    if dev10>5: warns.append('指數高於MA10較多')
    if dev20>8: warns.append('指數高於MA20較多')
    if float(r5.iloc[-1])>=75: warns.append('RSI5偏熱')
    if dist52<=2: warns.append('接近52週高')
    chase='⚠️ 追價風險較高' if warns else '🟢 追價壓力尚可'; chase_detail='、'.join(warns) if warns else '目前未出現明顯過熱訊號'
    return {'price':p,'gain':gain,'g20':g20,'volume_ratio':vr,'volume_change':vc,'ma5':ma5,'ma10':ma10,'ma20':ma20,'ma60':ma60,'dev10':dev10,'dev20':dev20,'k':float(k.iloc[-1]),'d':float(dline.iloc[-1]),'kt':kt,'r5':float(r5.iloc[-1]),'r10':float(r10.iloc[-1]),'rt':rt,'r10t':r10t,'dif':float(dif.iloc[-1]),'dea':float(dea.iloc[-1]),'hist':float(hist.iloc[-1]),'mt':mt,'s1':ss[0] if ss else np.nan,'s2':ss[1] if len(ss)>1 else np.nan,'s3':ss[2] if len(ss)>2 else np.nan,'r1':rr[0] if rr else np.nan,'r2':rr[1] if len(rr)>1 else np.nan,'r3':rr[2] if len(rr)>2 else np.nan,'h52':h52,'dist52':dist52,'score':score,'status':status,'advice':advice,'chase':chase,'chase_detail':chase_detail,'reasons':reasons},None


def market_report(x):
    return f'''<b>🇹🇼 6.1 台股大盤技術分析</b>
<b>加權指數｜TAIEX</b>
📅 {datetime.now(TZ):%Y/%m/%d %H:%M}
━━━━━━━━━━━━━━
💰 <b>目前指數：{fmt(x["price"])}</b>
📈 今日：{pct(x["gain"])}｜20日：{pct(x["g20"])}

<b>🔊 大盤量能</b>
量比：{fmt(x["volume_ratio"],2)}x
較5日均量：{pct(x["volume_change"])}

<b>📐 均線</b>
MA5：{fmt(x["ma5"])}
MA10：{fmt(x["ma10"])}（乖離 {pct(x["dev10"])}）
MA20：{fmt(x["ma20"])}（乖離 {pct(x["dev20"])}）
MA60：{fmt(x["ma60"])}

<b>📊 技術指標</b>
KD 9K：{direction_icon(x["kt"])} {x["kt"]} K={fmt(x["k"])} D={fmt(x["d"])}
RSI 5T：{direction_icon(x["rt"])} {x["rt"]} {fmt(x["r5"])}
RSI 10T：{direction_icon(x["r10t"])} {x["r10t"]} {fmt(x["r10"])}
MACD DIF：{direction_icon(x["mt"])} {x["mt"]} {fmt(x["dif"],2)}

<b>🟢 大盤支撐</b>
S1：<b>{fmt(x["s1"],0)}</b>
S2：{fmt(x["s2"],0)}
S3：{fmt(x["s3"],0)}

<b>🔴 大盤壓力</b>
R1：<b>{fmt(x["r1"],0)}</b>
R2：{fmt(x["r2"],0)}
R3：{fmt(x["r3"],0)}

📌 52週高：{fmt(x["h52"],0)}
📌 距52週高：{pct(x["dist52"])}

━━━━━━━━━━━━━━
<b>🎯 大盤環境：{x["status"]}</b>
評分：{x["score"]:+d} 分

💡 <b>操作參考</b>
{x["advice"]}

<b>{x["chase"]}</b>
{x["chase_detail"]}

📝 主要判斷：{"、".join(x["reasons"])}

⚠️ 大盤分析僅供技術面參考，不代表買賣建議。'''


def help_text():
    return '''<b>📊 台股 6.1 技術分析 Bot</b>

<b>🔎 個股分析</b>
直接輸入：
<code>3563</code>
<code>牧德</code>

或：
<code>/分析 3563</code>
<code>/分析 牧德</code>

<b>🇹🇼 大盤分析</b>
直接輸入：
<code>大盤</code>
<code>台股大盤</code>
<code>加權</code>
<code>加權指數</code>
<code>TAIEX</code>
<code>TWII</code>

或：
<code>/分析 大盤</code>
<code>/分析 TWII</code>

會回傳：支撐、壓力、量能、均線、KD、RSI、MACD，以及大盤多空環境。'''


def handle_update(u):
    m=u.get('message',{}); chat=m.get('chat',{}); cid=chat.get('id'); text=str(m.get('text','')).strip()
    if not cid or not text: return
    print('📨 收到訊息：',text,'chat_id=',cid)
    if text.startswith('/start') or text.startswith('/help'):
        send(cid,help_text()); return
    if text.startswith('/分析'): q=text[3:].strip()
    elif text.startswith('/analyze'): q=text[8:].strip()
    else: q=text
    if not q:
        send(cid,help_text()); return
    if is_market_query(q):
        send(cid,'🔎 正在分析 <b>台股大盤</b>，請稍候...')
        x,err=analyze_market()
        if err: send(cid,'⚠️ '+err); return
        send(cid,market_report(x)); print('✅ 大盤分析完成'); return
    send(cid,f'🔎 正在分析 <b>{q}</b>，請稍候...')
    stock,err=find_stock(q)
    if err: send(cid,'⚠️ '+err); return
    print('🔎 分析：',stock)
    x,err=analyze(stock)
    if err:
        send(cid,f'⚠️ {stock["code"]} {stock["name"]}\n{err}'); return
    send(cid,report(x)); print('✅ 個股分析完成：',stock['code'],stock['name'])


def main():
    print('======================================')
    print('📊 Taiwan Stock Radar 6.1 Technical Bot')
    print('======================================')

    if not TOKEN:
        print('❌ BOT TOKEN 未讀取，請檢查 GitHub Secret：BACKTEST_TELEGRAM_BOT_TOKEN')
        return

    me = telegram('getMe')
    print('🤖 Bot：', me)
    webhook = telegram('getWebhookInfo')
    if webhook and webhook.get('url'):
        print('❌ 目前 Bot 有 webhook：', webhook.get('url'))
        print('請移除 webhook 後才能使用 getUpdates。')
        return

    # 先取得目前 offset，避免把很久以前的舊訊息一次全部重跑
    updates = telegram('getUpdates', {'timeout': 1, 'allowed_updates': '["message"]'})
    offset = 0
    if updates:
        offset = max(u.get('update_id', 0) for u in updates) + 1
        print('ℹ️ 忽略舊訊息，起始 offset =', offset)

    # 每次 Actions 執行約 4 分鐘持續輪詢，配合每 5 分鐘排程
    end_at = time.time() + 240
    print('🟢 開始持續等待 Telegram 指令（約 4 分鐘）')

    while time.time() < end_at:
        remaining = max(1, min(30, int(end_at - time.time())))
        updates = telegram('getUpdates', {
            'offset': offset,
            'timeout': remaining,
            'allowed_updates': '["message"]'
        })
        if not updates:
            continue
        for u in updates:
            uid = u.get('update_id')
            if uid is not None:
                offset = max(offset, uid + 1)
            try:
                handle_update(u)
            except Exception as e:
                print('❌ 處理訊息錯誤：', repr(e))

    print('⏹️ 本次輪詢結束')


if __name__ == '__main__':
    main()
