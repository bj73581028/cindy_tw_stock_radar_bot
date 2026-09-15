# -*- coding: utf-8 -*-
import os,time,requests,warnings
from datetime import datetime
import numpy as np
import pandas as pd
import yfinance as yf
warnings.filterwarnings('ignore')

BOT=os.getenv('TELEGRAM_BOT_TOKEN',''); CHAT=os.getenv('TELEGRAM_CHAT_ID','')
TWSE='https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL'
TPEX='https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes'
TOP_N=10; MIN_SCORE=55; BATCH=70

def num(x):
    try:
        s=str(x).replace(',','').replace('%','').strip()
        return np.nan if s in ('','-','--','nan','None') else float(s)
    except: return np.nan

def get(url):
    r=requests.get(url,headers={'User-Agent':'Mozilla/5.0'},timeout=30); r.raise_for_status(); return r.json()

def pick(r,ks):
    for k in ks:
        if k in r and r[k] not in ('',None,'-','--'): return r[k]
    return None

def pool():
    out={}
    for url,market,suffix in [(TWSE,'TWSE','.TW'),(TPEX,'TPEx','.TWO')]:
        try:
            data=get(url)
            for r in data if isinstance(data,list) else []:
                c=str(pick(r,['Code','SecuritiesCompanyCode','股票代號','證券代號']) or '').strip()
                n=str(pick(r,['Name','CompanyName','股票名稱','證券名稱']) or '').strip()
                if c.isdigit() and len(c)==4 and not c.startswith(('00','01','02','03')):
                    out[c]={'code':c,'name':n,'market':market,'suffix':suffix}
        except Exception as e: print(market,e)
    return pd.DataFrame(out.values())

def history(tickers):
    result={}
    for i in range(0,len(tickers),BATCH):
        batch=tickers[i:i+BATCH]
        try:
            x=yf.download(batch,period='1y',interval='1d',auto_adjust=False,progress=False,group_by='ticker',threads=True)
            for t in batch:
                try:
                    d=x[t].copy() if isinstance(x.columns,pd.MultiIndex) and t in x.columns.get_level_values(0) else pd.DataFrame()
                    if len(d): result[t]=d.dropna(subset=['Close','Volume'])
                except: pass
        except Exception as e: print('Yahoo:',e)
        time.sleep(.5)
    return result

def tech(d):
    if len(d)<65:return None
    c=d.Close.astype(float); h=d.High.astype(float); v=d.Volume.astype(float)
    p=float(c.iloc[-1]); prev=float(c.iloc[-2]);
    a5=v.iloc[-6:-1].mean(); a20=v.iloc[-21:-1].mean()
    if min(p,prev,a5,a20)<=0:return None
    ch=(p/prev-1)*100; v5=v.iloc[-1]/a5; v20=v.iloc[-1]/a20; turn=p*v.iloc[-1]
    ma5=c.rolling(5).mean(); ma20=c.rolling(20).mean(); ma60=c.rolling(60).mean()
    m20=float(ma20.iloc[-1]); h20=float(h.iloc[-21:-1].max()); h52=float(h.tail(252).max())
    g20=(p/float(c.iloc[-21])-1)*100; dist=(h52-p)/h52*100
    s=0; why=[]; warn=[]
    if v5>=3:s+=20;why.append('5日量3倍')
    elif v5>=2:s+=15;why.append('5日量2倍')
    elif v5>=1.5:s+=8;why.append('5日量1.5倍')
    if v20>=2:s+=8;why.append('20日量2倍')
    elif v20>=1.5:s+=5;why.append('20日量1.5倍')
    if 3<=ch<=7:s+=12;why.append('溫和強漲')
    elif 1<=ch<3:s+=5;why.append('溫和上漲')
    elif 7<ch<=9:s+=7;why.append('強勢上漲')
    elif ch>9:s-=15;warn.append('單日漲幅過大')
    elif ch<-3:s-=10;warn.append('今日下跌')
    if p>m20:s+=5;why.append('站上MA20')
    if ma5.iloc[-1]>m20:s+=5;why.append('MA5>MA20')
    if m20>float(ma20.iloc[-2]):s+=5;why.append('MA20上升')
    if m20>float(ma60.iloc[-1]):s+=4;why.append('MA20>MA60')
    if p>h20:s+=12;why.append('突破20日高')
    if dist<=10:s+=5;why.append('接近52週高')
    elif dist<=20:s+=3;why.append('距52週高20%內')
    if g20>35:s-=20;warn.append('20日漲幅>35%')
    elif g20>25:s-=10;warn.append('20日漲幅>25%')
    elif 10<=g20<=25:s+=5;why.append('20日趨勢健康')
    if turn>=40_000_000:s+=5;why.append('成交金額4,000萬')
    elif turn>=20_000_000:s+=3;why.append('成交金額2,000萬')
    trend='多頭趨勢' if p>m20 and ma5.iloc[-1]>m20 else ('等待站回MA20' if p<m20 else '震盪')
    return dict(price=p,change=ch,v5=v5,v20=v20,turn=turn,g20=g20,dist=dist,tech=s,why=why,warn=warn,trend=trend)

def fundamental(code,suffix):
    r={'eps':np.nan,'roe':np.nan,'rev':np.nan,'fscore':0,'industry':''}
    try:
        info=yf.Ticker(code+suffix).info
        eps=num(info.get('trailingEps')); roe=num(info.get('returnOnEquity')); rev=num(info.get('revenueGrowth'))
        if not np.isnan(eps):r['eps']=eps
        if not np.isnan(roe):
            r['roe']=roe*100 if abs(roe)<2 else roe
        if not np.isnan(rev):r['rev']=rev*100 if abs(rev)<2 else rev
        r['industry']=str(info.get('industry') or '')
        if not np.isnan(r['roe']) and r['roe']>=10:r['fscore']+=5
        if not np.isnan(eps) and eps>0:r['fscore']+=5
        if not np.isnan(r['rev']):r['fscore']+=5 if r['rev']>=20 else (3 if r['rev']>=10 else (1 if r['rev']>0 else 0))
    except Exception as e: print(code,'fundamental',e)
    return r

def telegram(text):
    if not BOT or not CHAT: raise RuntimeError('Telegram secrets missing')
    u=f'https://api.telegram.org/bot{BOT}/sendMessage'
    requests.post(u,json={'chat_id':CHAT,'text':text,'disable_web_page_preview':True},timeout=20).raise_for_status()

def main():
    p=pool(); print('股票池',len(p));
    tickers=[r.code+r.suffix for r in p.itertuples()]
    hs=history(tickers); rows=[]
    for r in p.itertuples():
        t=r.code+r.suffix; d=hs.get(t)
        if d is None:continue
        z=tech(d)
        if z and z['tech']>=30: rows.append(dict(code=r.code,name=r.name,market=r.market,suffix=r.suffix,**z))
    rows=sorted(rows,key=lambda x:x['tech'],reverse=True)[:150]
    for x in rows:
        x.update(fundamental(x['code'],x['suffix'])); time.sleep(.12)
    # 產業強度：以候選股產業的平均20日漲幅排名；無產業資料不加分
    df=pd.DataFrame(rows)
    if not df.empty:
        valid=df[df.industry.astype(str).str.len()>0]
        perf=valid.groupby('industry').g20.mean().sort_values(ascending=False) if not valid.empty else pd.Series(dtype=float)
        n=len(perf)
        for x in rows:
            if x['industry'] in perf.index:
                rank=list(perf.index).index(x['industry'])+1
                x['iscore']=15 if rank/n<=.30 else (8 if rank/n<=.50 else 3)
            else:x['iscore']=0
    for x in rows:
        # 法人資料：本版不使用不穩定的第三方/FinMind；避免虛構法人分數
        x['iscore']=x.get('iscore',0); x['instscore']=0
        x['final']=min(100,x['tech']+x['iscore']+x['fscore'])
    rows=sorted(rows,key=lambda x:(x['final'],x['v5'],x['turn']),reverse=True)
    chosen=[x for x in rows if x['final']>=MIN_SCORE][:TOP_N]
    msg=[f'🚨 台股飆股雷達 5.0\n📅 {datetime.now():%Y/%m/%d %H:%M}\n🔎 掃描：{len(p)} 檔\n🎯 技術候選：{len(rows)} 檔\n🏆 入選：{len(chosen)} 檔\n']
    if not chosen:msg.append('⚠️ 今日沒有達到55分的個股\n➡️ 不強行追價')
    for i,x in enumerate(chosen,1):
        grade='S' if x['final']>=80 else ('A' if x['final']>=70 else ('B' if x['final']>=60 else 'C'))
        msg.append(f"{'🔥' if grade=='S' else '🟢' if grade=='A' else '🟡'} 第{i}名｜{x['code']} {x['name']}\n⭐️ {x['final']:.0f}分｜{grade}級\n💰 股價 {x['price']:.2f}｜📈 {x['change']:+.2f}%\n🔥 5日量 {x['v5']:.1f}倍｜20日量 {x['v20']:.1f}倍\n💵 成交金額 {x['turn']/1e8:.2f}億\n🏭 產業：{x['industry'] or '資料不足'}\n📌 {'、'.join(x['why'][:7])}\n➡️ {x['trend']}"+(f"\n⚠️ {'、'.join(x['warn'])}" if x['warn'] else '')+'\n')
    telegram('\n'.join(msg)); print('\n'.join(msg))
if __name__=='__main__':main()
