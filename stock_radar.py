import os
import time
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

# ============================================================
# 台股飆股雷達 5.0
# ============================================================
#
# 功能：
# 1. 上市＋上櫃股票
# 2. 技術面
# 3. 成交量
# 4. 成交金額
# 5. 產業強度
# 6. 法人籌碼
# 7. 基本面
# 8. 防追高
# 9. S / A / B 分級
# 10. Telegram 推播
#
# ============================================================


# ============================================================
# Telegram
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN"
)

TELEGRAM_CHAT_ID = os.environ.get(
    "TELEGRAM_CHAT_ID"
)


# ============================================================
# 基本設定
# ============================================================

MIN_SCAN_SCORE = 50

TOP_STRONG = 5
TOP_WATCH = 10
TOP_ABNORMAL = 10

MIN_TURNOVER = 20_000_000


# ============================================================
# API
# ============================================================

TWSE_URL = (
    "https://openapi.twse.com.tw/"
    "v1/exchangeReport/STOCK_DAY_ALL"
)

TPEX_URL = (
    "https://www.tpex.org.tw/"
    "openapi/v1/tpex_mainboard_quotes"
)

TPEX_INSTITUTION_URL = (
    "https://www.tpex.org.tw/"
    "openapi/v1/tpex_3insti_daily_trading"
)


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:
        raise Exception(
            "找不到 TELEGRAM_BOT_TOKEN"
        )

    if not TELEGRAM_CHAT_ID:
        raise Exception(
            "找不到 TELEGRAM_CHAT_ID"
        )

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        },
        timeout=30
    )

    response.raise_for_status()


# ============================================================
# HTTP
# ============================================================

def get_json(url, timeout=30):

    headers = {
        "User-Agent":
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "Chrome/120 Safari/537.36"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=timeout
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# 取得上市股票
# ============================================================

def get_twse_stocks():

    print("📡 取得上市股票資料...")

    try:

        data = get_json(
            TWSE_URL
        )

        df = pd.DataFrame(data)

        if df.empty:
            return pd.DataFrame()

        print(
            f"✅ 上市股票：{len(df)} 檔"
        )

        return df

    except Exception as e:

        print(
            f"❌ 上市股票資料失敗：{e}"
        )

        return pd.DataFrame()


# ============================================================
# 取得上櫃股票
# ============================================================

def get_tpex_stocks():

    print("📡 取得上櫃股票資料...")

    try:

        data = get_json(
            TPEX_URL
        )

        df = pd.DataFrame(data)

        if df.empty:
            return pd.DataFrame()

        print(
            f"✅ 上櫃股票：{len(df)} 檔"
        )

        return df

    except Exception as e:

        print(
            f"❌ 上櫃股票資料失敗：{e}"
        )

        return pd.DataFrame()


# ============================================================
# 清理股票代號
# ============================================================

def clean_stock_id(value):

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    # 只接受4碼股票代號
    if (
        len(value) == 4
        and value.isdigit()
    ):
        return value

    return None


# ============================================================
# 建立股票池
# ============================================================

def build_stock_pool():

    twse = get_twse_stocks()

    tpex = get_tpex_stocks()

    stock_ids = set()

    # -------------------------
    # TWSE
    # -------------------------

    if not twse.empty:

        for col in [
            "Code",
            "股票代號",
            "證券代號"
        ]:

            if col in twse.columns:

                for value in twse[col]:

                    stock_id = (
                        clean_stock_id(
                            value
                        )
                    )

                    if stock_id:
                        stock_ids.add(
                            stock_id
                        )

                break

    # -------------------------
    # TPEX
    # -------------------------

    if not tpex.empty:

        for col in [
            "SecuritiesCompanyCode",
            "Code",
            "股票代號",
            "證券代號"
        ]:

            if col in tpex.columns:

                for value in tpex[col]:

                    stock_id = (
                        clean_stock_id(
                            value
                        )
                    )

                    if stock_id:
                        stock_ids.add(
                            stock_id
                        )

                break

    stock_ids = sorted(
        stock_ids
    )

    print(
        f"📊 全市場股票池："
        f"{len(stock_ids)} 檔"
    )

    return stock_ids


# ============================================================
# Yahoo 批次下載
# ============================================================

def download_all_stocks(
    stock_ids
):

    tickers = [
        f"{stock_id}.TW"
        for stock_id in stock_ids
    ]

    print(
        "📥 開始下載全市場歷史行情..."
    )

    try:

        data = yf.download(
            tickers=tickers,
            period="1y",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by="ticker"
        )

        if data is None or data.empty:

            print(
                "❌ Yahoo 沒有回傳資料"
            )

            return None

        print(
            "✅ 歷史行情下載完成"
        )

        return data

    except Exception as e:

        print(
            f"❌ Yahoo下載失敗：{e}"
        )

        return None


# ============================================================
# 取得個股 DataFrame
# ============================================================

def get_stock_dataframe(
    all_data,
    stock_id
):

    ticker = (
        f"{stock_id}.TW"
    )

    try:

        if (
            isinstance(
                all_data.columns,
                pd.MultiIndex
            )
        ):

            # group_by ticker
            if ticker in (
                all_data.columns
                .get_level_values(0)
            ):

                df = (
                    all_data[ticker]
                    .copy()
                )

            else:

                return None

        else:

            df = all_data.copy()

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume"
        ]

        for col in required:

            if col not in df.columns:

                return None

        df = df[required].copy()

        df = df.replace(
            [np.inf, -np.inf],
            np.nan
        )

        df = df.dropna()

        if len(df) < 60:

            return None

        return df

    except Exception:

        return None


# ============================================================
# 技術面
# ============================================================

def calculate_technical(
    df
):

    close = float(
        df["Close"].iloc[-1]
    )

    previous_close = float(
        df["Close"].iloc[-2]
    )

    volume = float(
        df["Volume"].iloc[-1]
    )

    if previous_close <= 0:

        return None

    change_pct = (
        close /
        previous_close -
        1
    ) * 100

    # -------------------------
    # Volume
    # -------------------------

    avg5 = float(
        df["Volume"]
        .iloc[-6:-1]
        .mean()
    )

    avg20 = float(
        df["Volume"]
        .iloc[-21:-1]
        .mean()
    )

    if avg5 <= 0:

        return None

    volume5 = (
        volume /
        avg5
    )

    volume20 = (
        volume /
        avg20
        if avg20 > 0
        else 0
    )

    # -------------------------
    # MA
    # -------------------------

    ma5 = (
        df["Close"]
        .rolling(5)
        .mean()
        .iloc[-1]
    )

    ma20 = (
        df["Close"]
        .rolling(20)
        .mean()
        .iloc[-1]
    )

    ma60 = (
        df["Close"]
        .rolling(60)
        .mean()
        .iloc[-1]
    )

    ma20_previous = (
        df["Close"]
        .rolling(20)
        .mean()
        .iloc[-2]
    )

    # -------------------------
    # Breakout
    # -------------------------

    high20 = (
        df["High"]
        .iloc[-21:-1]
        .max()
    )

    breakout20 = (
        close > high20
    )

    # -------------------------
    # 52週高
    # -------------------------

    high252 = (
        df["High"]
        .iloc[-252:]
        .max()
    )

    distance52 = (
        (high252 - close)
        / high252
        * 100
        if high252 > 0
        else 100
    )

    # -------------------------
    # 20日漲幅
    # -------------------------

    close20 = float(
        df["Close"].iloc[-21]
    )

    gain20 = (
        close /
        close20 -
        1
    ) * 100

    # -------------------------
    # 成交金額
    # -------------------------

    turnover = (
        close * volume
    )

    # -------------------------
    # 技術評分
    # -------------------------

    score = 0

    reasons = []

    # 5日量
    if volume5 >= 3:

        score += 20

        reasons.append(
            "5日量3倍以上"
        )

    elif volume5 >= 2:

        score += 15

        reasons.append(
            "5日量2倍以上"
        )

    elif volume5 >= 1.5:

        score += 8

        reasons.append(
            "5日量增"
        )

    # 20日量
    if volume20 >= 2:

        score += 8

        reasons.append(
            "20日量2倍以上"
        )

    elif volume20 >= 1.5:

        score += 5

        reasons.append(
            "20日量增"
        )

    # 漲幅
    if 3 <= change_pct <= 7:

        score += 12

        reasons.append(
            "強勢上漲"
        )

    elif 1 <= change_pct < 3:

        score += 5

        reasons.append(
            "溫和上漲"
        )

    elif 7 < change_pct <= 9:

        score += 7

        reasons.append(
            "高檔強勢"
        )

    elif change_pct > 9:

        score -= 15

        reasons.append(
            "漲幅過大"
        )

    # 突破
    if breakout20:

        score += 12

        reasons.append(
            "突破20日高"
        )

    # MA20
    if close > ma20:

        score += 5

        reasons.append(
            "站上MA20"
        )

    # MA5
    if ma5 > ma20:

        score += 5

        reasons.append(
            "MA5>MA20"
        )

    # MA20方向
    if ma20 > ma20_previous:

        score += 5

        reasons.append(
            "MA20上升"
        )

    # MA60
    if ma20 > ma60:

        score += 4

        reasons.append(
            "MA20>MA60"
        )

    # 52週高
    if distance52 <= 10:

        score += 5

        reasons.append(
            "接近52週高"
        )

    elif distance52 <= 20:

        score += 3

        reasons.append(
            "接近前高"
        )

    # 20日趨勢
    if 10 <= gain20 <= 25:

        score += 5

        reasons.append(
            "20日趨勢強"
        )

    elif gain20 > 25:

        score -= 10

        reasons.append(
            "20日漲幅偏大"
        )

    if gain20 > 35:

        score -= 10

        reasons.append(
            "20日漲幅過大"
        )

    # 成交金額
    if turnover >= 40_000_000:

        score += 5

        reasons.append(
            "成交金額達4,000萬"
        )

    elif turnover >= 20_000_000:

        score += 3

        reasons.append(
            "成交金額達2,000萬"
        )

    return {

        "close": close,

        "change_pct": change_pct,

        "volume5": volume5,

        "volume20": volume20,

        "turnover": turnover,

        "breakout20": breakout20,

        "distance52": distance52,

        "gain20": gain20,

        "ma5": ma5,

        "ma20": ma20,

        "ma60": ma60,

        "technical_score": score,

        "reasons": reasons
    }


# ============================================================
# 產業強度
# ============================================================
#
# 這裡採用「同批股票的20日漲幅排名」作為產業以外的
# 市場強度代理。
#
# 真正產業分類資料若官方欄位存在，後續會再併入。
# ============================================================

def calculate_market_strength(
    results
):

    if not results:

        return results

    gains = [
        x["gain20"]
        for x in results
        if x.get("gain20") is not None
    ]

    if not gains:

        return results

    percentile = np.percentile(
        gains,
        70
    )

    for item in results:

        gain20 = item["gain20"]

        if gain20 >= percentile:

            item["market_strength"] = 15

            item["strength_text"] = (
                "市場強勢Top30%"
            )

        else:

            item["market_strength"] = 0

            item["strength_text"] = (
                "市場強度一般"
            )

    return results


# ============================================================
# 法人資料
# ============================================================

def get_tpex_institution():

    try:

        data = get_json(
            TPEX_INSTITUTION_URL
        )

        df = pd.DataFrame(data)

        return df

    except Exception as e:

        print(
            f"⚠️ 上櫃法人資料取得失敗：{e}"
        )

        return pd.DataFrame()


# ============================================================
# 法人評分
# ============================================================

def calculate_institution_score(
    stock_id,
    institution_df
):

    if (
        institution_df is None
        or institution_df.empty
    ):

        return 0, "法人資料不足"

    # 嘗試尋找股票代號欄位
    code_col = None

    for col in [
        "SecuritiesCompanyCode",
        "Code",
        "證券代號",
        "股票代號"
    ]:

        if col in institution_df.columns:

            code_col = col

            break

    if code_col is None:

        return 0, "法人資料不足"

    rows = institution_df[
        institution_df[
            code_col
        ].astype(str)
        .str.strip()
        == str(stock_id)
    ]

    if rows.empty:

        return 0, "法人資料不足"

    # 嘗試找合計買賣超欄位
    possible_cols = [
        "TotalNetBuySell",
        "NetBuySell",
        "三大法人買賣超股數",
        "買賣超股數"
    ]

    value = None

    for col in possible_cols:

        if col in rows.columns:

            value = rows.iloc[0][col]

            break

    if value is None:

        return 0, "法人資料不足"

    try:

        value = float(
            str(value)
            .replace(",", "")
        )

    except Exception:

        return 0, "法人資料不足"

    if value > 0:

        return 10, "三大法人買超"

    elif value < 0:

        return 0, "三大法人賣超"

    return 3, "法人中性"


# ============================================================
# 基本面
# ============================================================
#
# 使用 Yahoo 基本資料。
# 為避免一次查詢數百家公司造成 API 過慢，
# 只對技術分數較高的候選股查詢。
# ============================================================

def get_fundamental_score(
    stock_id
):

    ticker = (
        f"{stock_id}.TW"
    )

    try:

        info = yf.Ticker(
            ticker
        ).info

        score = 0

        reasons = []

        # -------------------------
        # ROE
        # -------------------------

        roe = info.get(
            "returnOnEquity"
        )

        if roe is not None:

            roe_pct = roe * 100

            if roe_pct >= 10:

                score += 5

                reasons.append(
                    "ROE>10%"
                )

            elif roe_pct >= 5:

                score += 2

        # -------------------------
        # EPS
        # -------------------------

        eps = info.get(
            "trailingEps"
        )

        if eps is not None:

            try:

                eps = float(eps)

                if eps > 0:

                    score += 5

                    reasons.append(
                        "EPS為正"
                    )

            except Exception:

                pass

        # -------------------------
        # 營收成長
        # -------------------------

        revenue_growth = info.get(
            "revenueGrowth"
        )

        if revenue_growth is not None:

            growth_pct = (
                revenue_growth * 100
            )

            if growth_pct >= 20:

                score += 5

                reasons.append(
                    "營收成長>20%"
                )

            elif growth_pct >= 10:

                score += 3

                reasons.append(
                    "營收成長>10%"
                )

            elif growth_pct > 0:

                score += 1

        return score, reasons

    except Exception:

        return 0, []


# ============================================================
# 防追高
# ============================================================

def chase_penalty(
    item
):

    penalty = 0

    warning = ""

    change = item[
        "change_pct"
    ]

    gain20 = item[
        "gain20"
    ]

    if change > 9:

        penalty -= 15

        warning = (
            "🔴 今日漲幅過大"
        )

    elif gain20 > 35:

        penalty -= 20

        warning = (
            "🔴 20日漲幅過大"
        )

    elif gain20 > 25:

        penalty -= 10

        warning = (
            "🟠 短線漲幅偏大"
        )

    return penalty, warning


# ============================================================
# 等級
# ============================================================

def get_grade(
    score
):

    if score >= 80:

        return "🟢 S級"

    if score >= 70:

        return "🟡 A級"

    if score >= 60:

        return "🟠 B級"

    return "⚪ 異動"


# ============================================================
# 主程式
# ============================================================

def main():

    print("=" * 70)

    print(
        "🚀 台股飆股雷達 5.0"
    )

    print("=" * 70)

    # -------------------------
    # 1. 股票池
    # -------------------------

    stock_ids = (
        build_stock_pool()
    )

    if not stock_ids:

        raise Exception(
            "無法取得股票池"
        )

    # -------------------------
    # 2. 歷史行情
    # -------------------------

    all_data = (
        download_all_stocks(
            stock_ids
        )
    )

    if all_data is None:

        raise Exception(
            "無法取得歷史行情"
        )

    # -------------------------
    # 3. 技術面
    # -------------------------

    results = []

    total = len(
        stock_ids
    )

    for index, stock_id in enumerate(
        stock_ids,
        1
    ):

        print(
            f"[{index}/{total}] "
            f"{stock_id}"
        )

        df = (
            get_stock_dataframe(
                all_data,
                stock_id
            )
        )

        if df is None:

            continue

        tech = (
            calculate_technical(
                df
            )
        )

        if tech is None:

            continue

        # 成交金額低於2000萬
        # 不列為主要候選
        if tech["turnover"] < MIN_TURNOVER:

            continue

        # 技術面至少30分
        if tech[
            "technical_score"
        ] < 30:

            continue

        result = {

            "stock_id": stock_id,

            **tech

        }

        results.append(
            result
        )

    print(
        f"🎯 技術面候選："
        f"{len(results)} 檔"
    )

    # -------------------------
    # 4. 市場強度
    # -------------------------

    results = (
        calculate_market_strength(
            results
        )
    )

    # -------------------------
    # 5. 法人資料
    # -------------------------

    institution_df = (
        get_tpex_institution()
    )

    # -------------------------
    # 6. 基本面
    # -------------------------

    # 只處理技術面排名較前者
    results.sort(
        key=lambda x:
        x["technical_score"],
        reverse=True
    )

    candidates = results[:100]

    final_results = []

    for item in candidates:

        stock_id = item[
            "stock_id"
        ]

        # 法人
        inst_score, inst_text = (
            calculate_institution_score(
                stock_id,
                institution_df
            )
        )

        # 基本面
        fund_score, fund_reasons = (
            get_fundamental_score(
                stock_id
            )
        )

        # 防追高
        penalty, warning = (
            chase_penalty(
                item
            )
        )

        final_score = (

            item["technical_score"]

            + item.get(
                "market_strength",
                0
            )

            + inst_score

            + fund_score

            + penalty
        )

        item[
            "institution_score"
        ] = inst_score

        item[
            "institution_text"
        ] = inst_text

        item[
            "fundamental_score"
        ] = fund_score

        item[
            "fundamental_reasons"
        ] = fund_reasons

        item[
            "penalty"
        ] = penalty

        item[
            "warning"
        ] = warning

        item[
            "final_score"
        ] = final_score

        item[
            "grade"
        ] = get_grade(
            final_score
        )

        final_results.append(
            item
        )

    # -------------------------
    # 7. 排名
    # -------------------------

    final_results.sort(

        key=lambda x: (

            x["final_score"],

            x["volume5"],

            x["change_pct"]

        ),

        reverse=True
    )

    # -------------------------
    # 8. Telegram
    # -------------------------

    today = datetime.now()

    strong = [
        x
        for x in final_results
        if x["final_score"] >= 80
    ]

    watch = [
        x
        for x in final_results
        if 70 <= x["final_score"] < 80
    ]

    abnormal = [
        x
        for x in final_results
        if 60 <= x["final_score"] < 70
    ]

    lines = []

    lines.append(
        "🚨 台股飆股雷達 5.0"
    )

    lines.append(
        f"📅 {today.strftime('%Y/%m/%d %H:%M')}"
    )

    lines.append(
        f"🔎 全市場股票池："
        f"{len(stock_ids)} 檔"
    )

    lines.append(
        f"🎯 技術面候選："
        f"{len(results)} 檔"
    )

    lines.append("")

    # -------------------------
    # S級
    # -------------------------

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    lines.append(
        "🟢 S級｜80分以上"
    )

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    if not strong:

        lines.append(
            "今日沒有S級股票"
        )

    else:

        for rank, item in enumerate(
            strong[:TOP_STRONG],
            1
        ):

            lines.extend(
                format_stock(
                    rank,
                    item
                )
            )

    # -------------------------
    # A級
    # -------------------------

    lines.append("")

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    lines.append(
        "🟡 A級｜70～79分"
    )

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    if not watch:

        lines.append(
            "今日沒有A級股票"
        )

    else:

        for rank, item in enumerate(
            watch[:TOP_WATCH],
            1
        ):

            lines.extend(
                format_stock(
                    rank,
                    item
                )
            )

    # -------------------------
    # B級
    # -------------------------

    lines.append("")

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    lines.append(
        "🟠 B級｜60～69分"
    )

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    if not abnormal:

        lines.append(
            "今日沒有B級股票"
        )

    else:

        for rank, item in enumerate(
            abnormal[:TOP_ABNORMAL],
            1
        ):

            lines.extend(
                format_stock(
                    rank,
                    item
                )
            )

    # -------------------------
    # 結尾
    # -------------------------

    lines.append("")

    lines.append(
        "━━━━━━━━━━━━━━"
    )

    lines.append(
        "📌 5.0核心："
    )

    lines.append(
        "量能＋技術＋市場強度＋"
        "法人＋基本面＋防追高"
    )

    lines.append("")

    lines.append(
        "⚠️ 僅供研究參考，"
        "不代表買進建議。"
    )

    message = "\n".join(
        lines
    )

    print(
        "\n" + message
    )

    send_telegram(
        message
    )

    print(
        "\n✅ Telegram 發送成功"
    )


# ============================================================
# Telegram 個股格式
# ============================================================

def format_stock(
    rank,
    item
):

    stock_id = item[
        "stock_id"
    ]

    score = item[
        "final_score"
    ]

    close = item[
        "close"
    ]

    change = item[
        "change_pct"
    ]

    volume5 = item[
        "volume5"
    ]

    turnover = (
        item["turnover"]
        / 100_000_000
    )

    reasons = list(
        item.get(
            "reasons",
            []
        )
    )

    reasons.extend(
        item.get(
            "fundamental_reasons",
            []
        )
    )

    lines = []

    lines.append(
        f"🏆 {rank}. {stock_id}｜"
        f"{item['grade']}｜{score}分"
    )

    lines.append(
        f"💰 股價 {close:.2f}"
        f"｜📈 {change:+.2f}%"
    )

    lines.append(
        f"🔥 5日量 "
        f"{volume5:.1f}倍"
        f"｜💵 成交 "
        f"{turnover:.2f}億"
    )

    lines.append(
        f"🏭 {item.get('strength_text', '市場強度一般')}"
    )

    lines.append(
        f"💼 {item.get('institution_text', '法人資料不足')}"
    )

    if reasons:

        # 避免訊息過長
        unique_reasons = list(
            dict.fromkeys(
                reasons
            )
        )

        lines.append(
            "📌 "
            + "、".join(
                unique_reasons[:8]
            )
        )

    if item.get(
        "warning"
    ):

        lines.append(
            f"⚠️ {item['warning']}"
        )

    else:

        if (
            item["breakout20"]
            and item["volume5"] >= 2
        ):

            lines.append(
                "➡️ 🟢 爆量突破，值得觀察"
            )

        elif (
            item["ma5"] >
            item["ma20"]
            and item["ma20"] >
            item["ma60"]
        ):

            lines.append(
                "➡️ 🟢 多頭排列"
            )

        else:

            lines.append(
                "➡️ 🟡 持續觀察"
            )

    lines.append("")

    return lines


# ============================================================
# 執行
# ============================================================

if __name__ == "__main__":

    main()
