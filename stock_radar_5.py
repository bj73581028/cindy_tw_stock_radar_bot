import os, time, math, requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN','')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID','')

TWSE_BASE='https://openapi.twse.com.tw/v1'
TPEx_BASE='https://www.tpex.org.tw/openapi/v1'
UA={'User-Agent':'Mozilla/5.0'}

# ---------- helpers ----------
def get_json(url, timeout=30):
    r=requests.get(url,headers=UA,timeout=timeout)
    r.raise_for_status()
    return r.json()

def num(x):
    try:
        if x is None or x=='-' or x=='': return np.nan
        return float(str(x).replace(',','').replace('%',''))
    except: return np.nan

def clean_code(x):
    s=str(x).strip()
    return s.zfill(4) if s.isdigit() else s

def send_tg(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError('缺少 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID')
    url=f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    r=requests.post(url,data={'chat_id':TELEGRAM_CHAT_ID,'text':text},timeout=30)
    r.raise_for_status()

# ---------- universe: TWSE + TPEx ----------
def get_universe():
    rows=[]
    try:
        data=get_json(f'{TWSE_BASE}/exchangeReport/STOCK_DAY_ALL')
        for x in data:
            code=clean_code(x.get('Code',''))
            name=x.get('Name','')
            if code and code[0].isdigit() and not code.startswith(('00','01','02','03')):
                rows.append({'code':code,'name':name,'market':'TWSE','symbol':code+'.TW'})
    except Exception as e:
        print('TWSE universe error:',e)
    try:
        data=get_json(f'{TPEx_BASE}/tpex_mainboard_quotes')
        for x in data:
            code=clean_code(x.get('SecuritiesCompanyCode') or x.get('SecuritiesCompanyCode') or x.get('代號') or x.get('股票代號',''))
            name=x.get('CompanyName') or x.get('名稱') or x.get('公司名稱','')
            if code and code[0].isdigit() and not code.startswith(('00','01','02','03')):
                rows.append({'code':code,'name':name,'market':'TPEX','symbol':code+'.TWO'})
    except Exception as e:
        print('TPEx universe error:',e)
    df=pd.DataFrame(rows).drop_duplicates('code')
    return df

# ---------- institutional data ----------
def get_twse_inst():
    # TWSE T86: foreign investment, investment trust, dealer and total net buy/sell
    out={}
    try:
        data=get_json(f'{TWSE_BASE}/fund/T86')
        for x in data:
            code=clean_code(x.get('證券代號') or x.get('Code',''))
            if not code: continue
            # columns are official T86 labels; tolerate English aliases
            foreign=num(x.get('外陸資買賣超股數(不含外資自營商)') or x.get('Foreign_Investment_Net'))
            trust=num(x.get('投信買賣超股數') or x.get('Investment_Trust_Net'))
            dealer=num(x.get('自營商買賣超股數') or x.get('Dealer_Net'))
            total=num(x.get('三大法人買賣超股數') or x.get('Total_Net'))
            out[code]={'foreign':foreign,'trust':trust,'dealer':dealer,'total':total}
    except Exception as e: print('TWSE inst error:',e)
    return out

def get_tpex_inst():
    out={}
    urls=[f'{TPEx_BASE}/tpex_3insti_daily_trading',f'{TPEx_BASE}/tpex_3insti_trading']
    for url in urls:
        try:
            data=get_json(url)
            if not data: continue
            for x in data:
                code=clean_code(x.get('SecuritiesCompanyCode') or x.get('SecuritiesCompanyCode') or x.get('代號') or x.get('股票代號',''))
                if not code: continue
                foreign=num(x.get('ForeignInvestmentNetBuySell') or x.get('Foreign_Net') or x.get('外資及陸資買賣超股數'))
                trust=num(x.get('InvestmentTrustNetBuySell') or x.get('Trust_Net') or x.get('投信買賣超股數'))
                dealer=num(x.get('DealerNetBuySell') or x.get('Dealer_Net') or x.get('自營商買賣超股數'))
                total=num(x.get('TotalNetBuySell') or x.get('Total_Net') or x.get('三大法人買賣超股數'))
                if code not in out: out[code]={'foreign':foreign,'trust':trust,'dealer':dealer,'total':total}
                else:
                    for k,v in [('foreign',foreign),('trust',trust),('dealer',dealer),('total',total)]:
                        if not np.isnan(v): out[code][k]=v
            if out: break
        except Exception as e: print('TPEx inst error:',e)
    return out

# ---------- fundamentals ----------
def get_fundamentals(symbol):
    try:
        info=yf.Ticker(symbol).get_info()
        return {
            'eps':num(info.get('trailingEps')),
            'roe':num(info.get('returnOnEquity'))*100 if info.get('returnOnEquity') is not None else np.nan,
            'rev_growth':num(info.get('revenueGrowth'))*100 if info.get('revenueGrowth') is not None else np.nan,
            'industry':info.get('industry') or info.get('sector') or '其他'
        }
    except Exception as e:
        print('fundamental error',symbol,e)
        return {'eps':np.nan,'roe':np.nan,'rev_growth':np.nan,'industry':'其他'}

# ---------- scoring ----------
def technical_score(h):
    if len(h)<65: return None
    c=h['Close'].astype(float); v=h['Volume'].astype(float)
    last=float(c.iloc[-1]); prev=float(c.iloc[-2]) if len(c)>1 else last
    ma5=c.rolling(5).mean(); ma20=c.rolling(20).mean(); ma60=c.rolling(60).mean()
    avg5=v.rolling(5).mean().iloc[-1]; avg20=v.rolling(20).mean().iloc[-1]
    vol5=float(v.iloc[-1]/avg5) if avg5 else 0; vol20=float(v.iloc[-1]/avg20) if avg20 else 0
    pct=(last/prev-1)*100
    turnover=last*float(v.iloc[-1])
    high20=float(c.iloc[-21:-1].max()); high52=float(c.tail(252).max())
    gain20=(last/float(c.iloc[-21])-1)*100 if len(c)>=22 else 0
    score=0; reasons=[]
    if vol5>=3: score+=20; reasons.append('5日量3倍以上')
    elif vol5>=2: score+=15; reasons.append('5日量2倍以上')
    elif vol5>=1.5: score+=8; reasons.append('5日量1.5倍以上')
    if vol20>=2: score+=8; reasons.append('20日量2倍以上')
    elif vol20>=1.5: score+=5; reasons.append('20日量1.5倍以上')
    if 3<=pct<=7: score+=12; reasons.append('溫和強勢上漲')
    elif 1<=pct<3: score+=5; reasons.append('小幅上漲')
    elif 7<pct<=9: score+=7; reasons.append('強勢上漲')
    elif pct>9: score-=15; reasons.append('單日漲幅過大')
    elif pct<-3: score-=10; reasons.append('單日轉弱')
    if last>high20: score+=12; reasons.append('突破20日高')
    if last>float(ma20.iloc[-1]): score+=5; reasons.append('站上MA20')
    if float(ma5.iloc[-1])>float(ma20.iloc[-1]): score+=5; reasons.append('MA5>MA20')
    if float(ma20.iloc[-1])>float(ma20.iloc[-6]): score+=5; reasons.append('MA20上升')
    if float(ma20.iloc[-1])>float(ma60.iloc[-1]): score+=4; reasons.append('MA20>MA60')
    dist=(high52-last)/high52*100 if high52 else 100
    if dist<=10: score+=5; reasons.append('接近52週高')
    elif dist<=20: score+=3; reasons.append('距52週高20%內')
    if 10<=gain20<=25: score+=5; reasons.append('20日漲幅健康')
    elif gain20>25: score-=10; reasons.append('20日漲幅偏大')
    if gain20>35: score-=10; reasons.append('短線過熱')
    if turnover>=40_000_000: score+=5; reasons.append('成交金額達4,000萬')
    elif turnover>=20_000_000: score+=3; reasons.append('成交金額達2,000萬')
    return {'tech':max(0,score),'price':last,'pct':pct,'vol5':vol5,'vol20':vol20,'turnover':turnover,'gain20':gain20,'reasons':reasons}

def main():
    universe=get_universe(); print('Universe:',len(universe))
    if universe.empty: raise RuntimeError('無法取得股票清單')
    symbols=universe['symbol'].tolist(); hist={}
    for i in range(0,len(symbols),70):
        batch=symbols[i:i+70]
        try:
            data=yf.download(batch,period='1y',group_by='ticker',auto_adjust=False,progress=False,threads=True)
            for s in batch:
                try:
                    h=data[s] if len(batch)>1 and s in data.columns.get_level_values(0) else data
                    if isinstance(h.columns,pd.MultiIndex): h=h.droplevel(0,axis=1)
                    h=h.dropna(subset=['Close','Volume'])
                    if len(h)>=65: hist[s]=h
                except: pass
        except Exception as e: print('download error',e)
        time.sleep(1)
    results=[]
    for _,u in universe.iterrows():
        s=u['symbol']; h=hist.get(s)
        if h is None: continue
        t=technical_score(h)
        if not t or t['tech']<20: continue
        results.append({**u.to_dict(),**t})
    df=pd.DataFrame(results)
    if df.empty: raise RuntimeError('今日無技術面候選')
    # Fundamentals on top technical candidates only, to control runtime.
    df=df.sort_values('tech',ascending=False).head(160).copy()
    inst={**get_twse_inst(),**get_tpex_inst()}
    funds=[]
    for _,r in df.iterrows():
        f=get_fundamentals(r['symbol']); funds.append(f); time.sleep(0.05)
    fdf=pd.DataFrame(funds,index=df.index); df=pd.concat([df,fdf],axis=1)
    # Industry strength: average 20-day gain by industry among screened universe.
    ind=df.groupby('industry')['gain20'].mean()
    rank=ind.rank(pct=True)
    df['industry_score']=df['industry'].map(lambda x:15 if rank.get(x,0)>=0.70 else (8 if rank.get(x,0)>=0.50 else 3))
    df['industry_reason']=df['industry_score'].map({15:'產業強度Top30%',8:'產業強度Top50%',3:'一般產業強度'})
    # Institutional score: 5d unavailable from single-day public endpoint, so use latest-day signal robustly.
    def inst_score(code):
        x=inst.get(code,{})
        vals=[x.get('foreign',np.nan),x.get('trust',np.nan),x.get('dealer',np.nan)]
        pos=sum(1 for v in vals if not np.isnan(v) and v>0)
        total=x.get('total',np.nan)
        sc=0
        if pos>=3: sc=15
        elif pos==2: sc=10
        elif pos==1: sc=6
        if not np.isnan(total) and total>0: sc=min(15,sc+3)
        return sc
    df['inst_score']=df['code'].map(inst_score)
    df['fund_score']=0
    df.loc[df['rev_growth']>=20,'fund_score']+=5
    df.loc[(df['rev_growth']>=10)&(df['rev_growth']<20),'fund_score']+=3
    df.loc[df['eps']>0,'fund_score']+=5
    df.loc[df['roe']>=10,'fund_score']+=5
    # Keep fundamental bucket capped at 15; institutional 15, industry 15, liquidity/technical as actual points.
    df['fund_score']=df['fund_score'].clip(upper=15)
    df['score']=(df['tech']+df['industry_score']+df['inst_score']+df['fund_score']).clip(upper=100)
    def grade(x): return 'S' if x>=80 else ('A' if x>=70 else ('B' if x>=60 else 'C'))
    df['grade']=df['score'].map(grade)
    df=df.sort_values(['score','tech'],ascending=False).head(10)
    now=datetime.now().strftime('%Y/%m/%d %H:%M')
    lines=[f'🚨 台股飆股雷達 5.0｜完整市場版',f'📅 {now}',f'🔎 掃描：{len(universe)} 檔｜候選：{len(results)} 檔', '']
    for i,(_,r) in enumerate(df.iterrows(),1):
        lines += [f"🏆 第{i}名｜{r['code']} {r['name']}｜{r['market']}",f"⭐️ {int(r['score'])}分｜{r['grade']}級",f"💰 股價 {r['price']:.2f}｜📈 {r['pct']:+.2f}%",f"🔥 5日量 {r['vol5']:.1f}倍｜20日量 {r['vol20']:.1f}倍",f"💵 成交金額 {r['turnover']/1e8:.2f}億",f"🏭 {r['industry']}｜{r['industry_reason']}",f"🏦 法人評分 {int(r['inst_score'])}/15｜基本面 {int(r['fund_score'])}/15",'📌 '+'、'.join(r['reasons'][:8]),'']
    if df.empty: lines.append('今日沒有達到最低技術分數的股票。')
    send_tg('\n'.join(lines))
    print('\n'.join(lines))

if __name__=='__main__': main()
