import os, time, warnings
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings('ignore')
VERSION='6.1-TECH-BOT'
TZ=ZoneInfo('Asia/Taipei')
TOKEN=os.getenv('BACKTEST_TELEGRAM_BOT_TOKEN','')
MARKET_SYMBOL='^TWII'
MARKET_KEYWORDS={'大盤','台股大盤','加權','加權指數','TAIEX','TWII','^TWII'}
SESSION=requests.Session(); SESSION.headers.update({'User-Agent':'Mozilla/5.0 TaiwanStockRadar/6.1'})

def now(): return datetime.now(TZ)
def log(*x): print(now().strftime('%Y-%m-%d %H:%M:%S'),*x,flush=True)
def fmt(x,d=2):
    try:return '-' if pd.isna(x) else f'{float(x):.{d}f}'
    except:return '-'
def pct(x):
    try:return '-' if pd.isna(x) else f'{float(x):+.2f}%'
    except:return '-'
def icon(t): return {'強勢向上':'🚀','溫和向上':'↗️','平穩':'➡️','略為向下':'↘️','明顯向下':'🔻','資料不足':'❔'}.get(t,'➡️')
def is_market_query(q): return str(q).strip() in MARKET_KEYWORDS or str(q).strip().upper() in {'TAIEX','TWII','^TWII'}

def telegram(method,params=None,post=False):
    if not TOKEN:return None
    try:
        u=f'https://api.telegram.org/bot{TOKEN}/{method}'
        r=SESSION.post(u,json=params or {},timeout=40) if post else SESSION.get(u,params=params or {},timeout=40)
        log('Telegram',method,'HTTP',r.status_code)
        if not r.ok:return None
        j=r.json(); return j.get('result') if j.get('ok') else None
    except Exception as e: log('Telegram error',repr(e)); return None

def send(cid,text): return telegram('sendMessage',{'chat_id':cid,'text':text,'parse_mode':'HTML','disable_web_page_preview':True},True)

def stock_list():
    out=[]
    try:
        r=SESSION.get('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',timeout=30); r.raise_for_status()
        for x in r.json():
            c=str(x.get('Code','')).strip(); n=str(x.get('Name','')).strip()
            if c.isdigit() and len(c)==4 and n and not c.startswith(('00','01','02','03')): out.append({'code':c,'name':n,'market':'TWSE','symbol':c+'.TW'})
        log('TWSE:',len(out))
    except Exception as e: log('TWSE list error',repr(e))
    twse_n=len(out)
    try:
        r=SESSION.get('https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes',timeout=30); r.raise_for_status()
        for x in r.json():
            c=str(x.get('SecuritiesCompanyCode','')).strip(); n=str(x.get('CompanyName','')).strip()
            if c.isdigit() and len(c)==4 and n and not c.startswith(('00','01','02','03')): out.append({'code':c,'name':n,'market':'TPEx','symbol':c+'.TWO'})
        log('TPEx:',len(out)-twse_n)
    except Exception as e: log('TPEx list error',repr(e))
    # 同一代號若上市櫃重複，保留兩個市場；查代號時會逐一驗證。
    seen=set(); clean=[]
    for x in out:
        k=(x['market'],x['code'])
        if k not in seen: seen.add(k); clean.append(x)
    return clean

def yf_history(symbol,period='1y'):
    try:
        d=yf.download(symbol,period=period,interval='1d',auto_adjust=False,actions=False,progress=False,threads=False)
        if d is None or d.empty:return None
        if isinstance(d.columns,pd.MultiIndex):
            # yfinance 不同版本的 MultiIndex 層級順序不同
            if symbol in d.columns.get_level_values(1): d=d.xs(symbol,axis=1,level=1)
            elif symbol in d.columns.get_level_values(0): d=d.xs(symbol,axis=1,level=0)
            else: d=d.droplevel(-1,axis=1)
        d.columns=[str(c).replace(' ','') for c in d.columns]
        need=['Open','High','Low','Close']
        if any(c not in d.columns for c in need): return None
        d.index=pd.to_datetime(d.index)
        try:
            if d.index.tz is not None:d.index=d.index.tz_localize(None)
        except:pass
        for c in need+(['Volume'] if 'Volume' in d.columns else []): d[c]=pd.to_numeric(d[c],errors='coerce')
        d=d.dropna(subset=need)
        return d if len(d)>=70 else None
    except Exception as e: log('History error',symbol,repr(e)); return None

def stock_history(symbol):
    d=yf_history(symbol,'1y')
    if d is None:return None
    if 'Volume' not in d.columns:return None
    d['Volume']=d['Volume'].fillna(0)
    return d

def find_stock(q):
    q=str(q).strip()
    if q.startswith('/分析'):q=q[3:].strip()
    elif q.lower().startswith('/analyze'):q=q[8:].strip()
    if not q:return None,'請輸入股票代號或名稱，例如：3563 或 牧德'
    if is_market_query(q):return {'code':'TWII','name':'加權指數','market':'TWSE','symbol':MARKET_SYMBOL},None
    names=stock_list()
    if q.isdigit():
        cand=[x for x in names if x['code']==q]
        # API 名單找不到時仍直接嘗試 Yahoo
        if not cand:cand=[{'code':q,'name':q,'market':'TWSE','symbol':q+'.TW'},{'code':q,'name':q,'market':'TPEx','symbol':q+'.TWO'}]
        for s in cand:
            d=stock_history(s['symbol'])
            if d is not None:
                if s['name']==q:
                    for z in names:
                        if z['code']==q and z['symbol']==s['symbol']: return z,None
                return s,None
        return None,f'找不到「{q}」，請確認股票代號。'
    exact=[x for x in names if q==x['name']]
    if len(exact)==1:return exact[0],None
    m=[x for x in names if q in x['name']]
    if len(m)==1:return m[0],None
    if m:return None,'找到多檔符合：\n'+'\n'.join(f"{x['code']} {x['name']} ({x['market']})" for x in m[:10])
    return None,f'找不到「{q}」，請輸入正確台股代號或名稱。'

def kd(d):
    lo=d.Low.rolling(9).min(); hi=d.High.rolling(9).max(); rsv=(d.Close-lo)/(hi-lo).replace(0,np.nan)*100
    k=rsv.ewm(alpha=1/3,adjust=False).mean(); dl=k.ewm(alpha=1/3,adjust=False).mean(); return k,dl

def rsi(c,p):
    delta=c.diff(); g=delta.clip(lower=0); l=-delta.clip(upper=0); ag=g.ewm(alpha=1/p,adjust=False).mean(); al=l.ewm(alpha=1/p,adjust=False).mean(); return 100-100/(1+ag/al.replace(0,np.nan))

def macd(c):
    dif=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean(); dea=dif.ewm(span=9,adjust=False).mean(); return dif,dea,dif-dea

def trend(s,norm=True):
    s=s.dropna()
    if len(s)<6:return '資料不足'
    a=float(s.iloc[-1]); b=float(s.iloc[-6]); diff=a-b
    if norm:
        if abs(b)<0.01:return '平穩'
        z=diff/abs(b)*100
        if z>=8:return '強勢向上'
        if z>=1:return '溫和向上'
        if z<=-8:return '明顯向下'
        if z<=-1:return '略為向下'
        return '平穩'
    if diff>.05:return '強勢向上'
    if diff>0:return '溫和向上'
    if diff<-.05:return '明顯向下'
    if diff<0:return '略為向下'
    return '平穩'

def supports(d,p):
    a=[]; lows=d.Low.tail(60)
    for i in range(2,len(lows)-2):
        v=lows.iloc[i]
        if v<=lows.iloc[i-2:i].min() and v<=lows.iloc[i+1:i+3].min() and v<p:a.append(float(v))
    for ma in [d.Close.rolling(10).mean().iloc[-1],d.Close.rolling(20).mean().iloc[-1],d.Close.rolling(60).mean().iloc[-1]]:
        if pd.notna(ma) and ma<p:a.append(float(ma))
    for v in [d.Low.tail(20).min(),d.Low.tail(60).min()]:
        if pd.notna(v) and v<p:a.append(float(v))
    return sorted(set(round(x,2) for x in a),reverse=True)[:3]

def resistances(d,p):
    a=[]; highs=d.High.tail(60)
    for i in range(2,len(highs)-2):
        v=highs.iloc[i]
        if v>=highs.iloc[i-2:i].max() and v>=highs.iloc[i+1:i+3].max() and v>p:a.append(float(v))
    for ma in [d.Close.rolling(10).mean().iloc[-1],d.Close.rolling(20).mean().iloc[-1],d.Close.rolling(60).mean().iloc[-1]]:
        if pd.notna(ma) and ma>p:a.append(float(ma))
    for v in [d.High.tail(20).max(),d.High.tail(60).max()]:
        if pd.notna(v) and v>p:a.append(float(v))
    return sorted(set(round(x,2) for x in a))[:3]

def analyze_stock(s):
    d=stock_history(s['symbol'])
    if d is None:return None,'目前無法取得歷史資料，可能是 Yahoo Finance 暫時無資料。'
    c=d.Close.astype(float); v=d.Volume.astype(float); p=float(c.iloc[-1]); prev=float(c.iloc[-2]); gain=(p/prev-1)*100
    avg5=float(v.iloc[-6:-1].mean()); vr=float(v.iloc[-1]/avg5) if avg5>0 else np.nan
    ma5=float(c.rolling(5).mean().iloc[-1]); ma10=float(c.rolling(10).mean().iloc[-1]); ma20=float(c.rolling(20).mean().iloc[-1]); ma60=float(c.rolling(60).mean().iloc[-1])
    dev10=(p-ma10)/ma10*100; dev20=(p-ma20)/ma20*100; k,dl=kd(d); r5=rsi(c,5); r10=rsi(c,10); dif,dea,_=macd(c)
    kt=trend(k); rt=trend(r5); r10t=trend(r10); mt=trend(dif,False); res=kt in {'強勢向上','溫和向上'} and rt in {'強勢向上','溫和向上'} and mt in {'強勢向上','溫和向上'}
    ss=supports(d,p); rr=resistances(d,p); h52=float(d.High.tail(252).max()); dist=(h52-p)/h52*100; g20=(p/c.iloc[-21]-1)*100 if len(c)>=21 else np.nan
    return {'stock':s,'price':p,'gain':gain,'today':int(v.iloc[-1]/1000),'avg5':int(avg5/1000),'vr':vr,'turn':p*float(v.iloc[-1]),'ma5':ma5,'ma10':ma10,'ma20':ma20,'ma60':ma60,'dev10':dev10,'dev20':dev20,'k':float(k.iloc[-1]),'d':float(dl.iloc[-1]),'kt':kt,'r5':float(r5.iloc[-1]),'r10':float(r10.iloc[-1]),'rt':rt,'r10t':r10t,'dif':float(dif.iloc[-1]),'dea':float(dea.iloc[-1]),'mt':mt,'res':res,'s1':ss[0] if ss else np.nan,'s2':ss[1] if len(ss)>1 else np.nan,'s3':ss[2] if len(ss)>2 else np.nan,'r1':rr[0] if rr else np.nan,'r2':rr[1] if len(rr)>1 else np.nan,'r3':rr[2] if len(rr)>2 else np.nan,'sd':(p-ss[0])/p*100 if ss else np.nan,'rd':(rr[0]-p)/p*100 if rr else np.nan,'h52':h52,'dist':dist,'g20':g20},None

def analyze_market():
    d=yf_history(MARKET_SYMBOL,'1y')
    if d is None:return None,'目前無法取得加權指數歷史資料。'
    c=d.Close.astype(float); p=float(c.iloc[-1]); prev=float(c.iloc[-2]); gain=(p/prev-1)*100; g20=(p/c.iloc[-21]-1)*100
    ma5=float(c.rolling(5).mean().iloc[-1]); ma10=float(c.rolling(10).mean().iloc[-1]); ma20=float(c.rolling(20).mean().iloc[-1]); ma60=float(c.rolling(60).mean().iloc[-1])
    dev10=(p-ma10)/ma10*100; dev20=(p-ma20)/ma20*100; k,dl=kd(d); r5=rsi(c,5); r10=rsi(c,10); dif,dea,hist=macd(c); kt=trend(k); rt=trend(r5); r10t=trend(r10); mt=trend(dif,True)
    ss=supports(d,p); rr=resistances(d,p); h52=float(d.High.tail(252).max()); dist=(h52-p)/h52*100
    volratio=np.nan; volchange=np.nan
    if 'Volume' in d.columns:
        v=pd.to_numeric(d.Volume,errors='coerce').fillna(0); av=float(v.iloc[-6:-1].mean()); volratio=float(v.iloc[-1]/av) if av>0 else np.nan; volchange=(float(v.iloc[-1])/av-1)*100 if av>0 else np.nan
    score=0; reasons=[]
    if p>ma20:score+=2;reasons.append('指數站上MA20')
    else:score-=2;reasons.append('指數跌破MA20')
    ma20prev=float(c.rolling(20).mean().iloc[-6])
    if ma20>ma20prev:score+=2;reasons.append('MA20向上')
    else:score-=2;reasons.append('MA20向下')
    if kt in {'強勢向上','溫和向上'}:score+=1;reasons.append('KD偏多')
    elif kt in {'略為向下','明顯向下'}:score-=1;reasons.append('KD轉弱')
    if rt in {'強勢向上','溫和向上'}:score+=1;reasons.append('RSI5偏多')
    elif rt in {'略為向下','明顯向下'}:score-=1;reasons.append('RSI5轉弱')
    if mt in {'強勢向上','溫和向上'}:score+=2;reasons.append('MACD DIF向上')
    elif mt in {'略為向下','明顯向下'}:score-=2;reasons.append('MACD DIF轉弱')
    if g20>3:score+=1
    elif g20<-3:score-=1
    status='🟢 偏多' if score>=5 else '🟡 震盪偏多' if score>=2 else '🔴 偏空' if score<=-5 else '🟠 震盪'
    advice='可積極尋找強勢股，優先挑量價齊揚、站上均線且未過度乖離者。' if score>=5 else '可以做個股，但建議挑強勢股，不宜全面追高。' if score>=2 else '大盤環境偏弱，建議降低追高，等待轉強訊號。' if score<=-5 else '大盤方向不明，適合個別選股，不宜因短線反彈全面追價。'
    warns=[]
    if dev10>5:warns.append('高於MA10較多')
    if dev20>8:warns.append('高於MA20較多')
    if float(r5.iloc[-1])>=75:warns.append('RSI5偏熱')
    if dist<=2:warns.append('接近52週高')
    return {'price':p,'gain':gain,'g20':g20,'volume_ratio':volratio,'volume_change':volchange,'ma5':ma5,'ma10':ma10,'ma20':ma20,'ma60':ma60,'dev10':dev10,'dev20':dev20,'k':float(k.iloc[-1]),'d':float(dl.iloc[-1]),'kt':kt,'r5':float(r5.iloc[-1]),'r10':float(r10.iloc[-1]),'rt':rt,'r10t':r10t,'dif':float(dif.iloc[-1]),'dea':float(dea.iloc[-1]),'hist':float(hist.iloc[-1]),'mt':mt,'s1':ss[0] if ss else np.nan,'s2':ss[1] if len(ss)>1 else np.nan,'s3':ss[2] if len(ss)>2 else np.nan,'r1':rr[0] if rr else np.nan,'r2':rr[1] if len(rr)>1 else np.nan,'r3':rr[2] if len(rr)>2 else np.nan,'h52':h52,'dist52':dist,'score':score,'status':status,'advice':advice,'chase':'⚠️ 追價風險較高' if warns else '🟢 追價壓力尚可','chase_detail':'、'.join(warns) if warns else '目前未出現明顯過熱訊號','reasons':reasons},None

def stock_report(x):
    return f'''<b>📊 6.1 個股技術分析</b>\n<b>#{x['stock']['code']}｜{x['stock']['name']}｜{x['stock']['market']}</b>\n📅 {now():%Y/%m/%d %H:%M}\n━━━━━━━━━━━━━━\n💰 <b>現價：{fmt(x['price'])}</b>\n📈 今日：{pct(x['gain'])}｜20日：{pct(x['g20'])}\n\n<b>🔊 量能</b>\n今日量：{x['today']:,} 張\n5日均量：{x['avg5']:,} 張\n量比：{fmt(x['vr'],2)}x\n成交金額：{x['turn']/1e8:.2f} 億\n\n<b>🟢 支撐</b>\nS1：<b>{fmt(x['s1'])}</b>\nS2：{fmt(x['s2'])}\nS3：{fmt(x['s3'])}\n距S1：{pct(x['sd'])}\n\n<b>🔴 壓力</b>\nR1：<b>{fmt(x['r1'])}</b>\nR2：{fmt(x['r2'])}\nR3：{fmt(x['r3'])}\n距R1：{pct(x['rd'])}\n\n<b>📐 均線</b>\nMA5：{fmt(x['ma5'])}\nMA10：{fmt(x['ma10'])}（乖離 {pct(x['dev10'])}）\nMA20：{fmt(x['ma20'])}（乖離 {pct(x['dev20'])}）\nMA60：{fmt(x['ma60'])}\n\n<b>📊 技術指標</b>\nKD 9K：{icon(x['kt'])} {x['kt']} K={fmt(x['k'])} D={fmt(x['d'])}\nRSI 5T：{icon(x['rt'])} {x['rt']} {fmt(x['r5'])}\nRSI 10T：{icon(x['r10t'])} {x['r10t']} {fmt(x['r10'])}\nMACD DIF：{icon(x['mt'])} {x['mt']} {fmt(x['dif'],3)}\n{'🔥 三線共振' if x['res'] else '— 尚未形成完整三線共振'}\n\n📌 52週高：{fmt(x['h52'])}\n📌 距52週高：{pct(x['dist'])}\n\n⚠️ 技術分析僅供參考，不代表買賣建議。'''

def market_report(x):
    return f'''<b>🇹🇼 6.1 台股大盤技術分析</b>\n<b>加權指數｜TAIEX</b>\n📅 {now():%Y/%m/%d %H:%M}\n━━━━━━━━━━━━━━\n💰 <b>目前指數：{fmt(x['price'])}</b>\n📈 今日：{pct(x['gain'])}｜20日：{pct(x['g20'])}\n\n<b>🔊 大盤量能</b>\n量比：{fmt(x['volume_ratio'],2)}x\n較5日均量：{pct(x['volume_change'])}\n\n<b>📐 均線</b>\nMA5：{fmt(x['ma5'])}\nMA10：{fmt(x['ma10'])}（乖離 {pct(x['dev10'])}）\nMA20：{fmt(x['ma20'])}（乖離 {pct(x['dev20'])}）\nMA60：{fmt(x['ma60'])}\n\n<b>📊 技術指標</b>\nKD 9K：{icon(x['kt'])} {x['kt']} K={fmt(x['k'])} D={fmt(x['d'])}\nRSI 5T：{icon(x['rt'])} {x['rt']} {fmt(x['r5'])}\nRSI 10T：{icon(x['r10t'])} {x['r10t']} {fmt(x['r10'])}\nMACD DIF：{icon(x['mt'])} {x['mt']} {fmt(x['dif'],2)}\n\n<b>🟢 大盤支撐</b>\nS1：<b>{fmt(x['s1'],0)}</b>\nS2：{fmt(x['s2'],0)}\nS3：{fmt(x['s3'],0)}\n\n<b>🔴 大盤壓力</b>\nR1：<b>{fmt(x['r1'],0)}</b>\nR2：{fmt(x['r2'],0)}\nR3：{fmt(x['r3'],0)}\n\n📌 52週高：{fmt(x['h52'],0)}\n📌 距52週高：{pct(x['dist52'])}\n\n━━━━━━━━━━━━━━\n<b>🎯 大盤環境：{x['status']}</b>\n評分：{x['score']:+d} 分\n\n💡 <b>操作參考</b>\n{x['advice']}\n\n<b>{x['chase']}</b>\n{x['chase_detail']}\n\n📝 主要判斷：{'、'.join(x['reasons'])}\n\n⚠️ 大盤分析僅供技術面參考，不代表買賣建議。'''

def help_text():
    return '''<b>📊 Taiwan Stock Radar 6.1</b>\n\n<b>個股：</b>直接輸入 <code>3563</code> 或 <code>牧德</code>\n<code>/分析 3563</code>\n\n<b>大盤：</b>輸入 <code>大盤</code>、<code>加權</code>、<code>TAIEX</code>、<code>TWII</code>\n\n會分析現價、漲跌、今日量、5日均量、量比、MA5/10/20/60、KD、RSI、MACD、支撐、壓力、52週高及大盤環境。'''

def handle_update(u):
    m=u.get('message',{}); cid=m.get('chat',{}).get('id'); text=str(m.get('text','')).strip()
    if not cid or not text:return
    log('📨 收到訊息：',text,'chat_id=',cid)
    if text.startswith('/start') or text.startswith('/help'):send(cid,help_text());return
    if text.startswith('/分析'):q=text[3:].strip()
    elif text.lower().startswith('/analyze'):q=text[8:].strip()
    else:q=text
    if not q:send(cid,help_text());return
    if is_market_query(q):
        send(cid,'🔎 正在抓取 <b>^TWII 加權指數</b>，請稍候...'); x,e=analyze_market(); send(cid,'⚠️ '+e if e else market_report(x)); return
    send(cid,f'🔎 正在分析 <b>{q}</b>，請稍候...'); s,e=find_stock(q)
    if e:send(cid,'⚠️ '+e);return
    x,e=analyze_stock(s); send(cid,'⚠️ '+e if e else stock_report(x))

def main():
    log('======================================'); log('📊 Taiwan Stock Radar 6.1 Technical Bot'); log('上市 + 上櫃 + ^TWII'); log('======================================')
    if not TOKEN:log('❌ BOT TOKEN 未讀取：BACKTEST_TELEGRAM_BOT_TOKEN');return
    me=telegram('getMe'); log('🤖 Bot:',me)
    wh=telegram('getWebhookInfo')
    if wh and wh.get('url'):log('❌ Bot 有 webhook：',wh.get('url'));return
    # 不主動丟掉舊訊息；取得目前 pending updates 後逐一處理並確認 offset。
    updates=telegram('getUpdates',{'timeout':1,'allowed_updates':'["message"]'}) or []
    offset=0
    if updates: offset=min(int(x.get('update_id',0)) for x in updates)
    end=time.time()+230
    while time.time()<end:
        remaining=max(1,min(20,int(end-time.time())))
        updates=telegram('getUpdates',{'offset':offset,'timeout':remaining,'allowed_updates':'["message"]'}) or []
        for u in updates:
            uid=u.get('update_id')
            if uid is not None:offset=int(uid)+1
            try:handle_update(u)
            except Exception as e:log('❌ handle error',repr(e))
    log('⏹️ 本次輪詢結束')

if __name__=='__main__':main()
