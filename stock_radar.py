import os
import requests
import pandas as pd
from datetime import datetime, timedelta

# =========================
# 基本設定
# =========================
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

API_URL = "https://api.finmindtrade.com/api/v4/data"

# =========================
# 取得 FinMind 資料
# =========================
def get_finmind(dataset, start_date, end_date=None):

    params = {
        "dataset": dataset,
        "start_date": start_date,
        "token": FINMIND_TOKEN,
    }

    if end_date:
        params["end_date"] = end_date

    response = requests.get(API_URL, params=params, timeout=60)
    response.raise_for_status()

    result = response.json()

    if result.get("status") != 200:
        raise Exception(result)

    return pd.DataFrame(result.get("data", []))


# =========================
# Telegram
# =========================
def send_telegram(message):

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }

    response = requests.post(url, data=data, timeout=30)
    response.raise_for_status()


# =========================
# 主程式
# =========================
def main():

    today = datetime.now()

    # 抓最近約 2 個月資料
    start_date = (today - timedelta(days=70)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    print("開始取得台股資料...")

    # 股票基本資料
    stock_info = get_finmind(
        "TaiwanStockInfo",
        start_date,
        end_date
    )

    if stock_info.empty:
        raise Exception("無法取得 TaiwanStockInfo")

    print(f"取得股票資料：{len(stock_info)} 筆")

    # 取得股票代碼
    if "stock_id" not in stock_info.columns:
        raise Exception("TaiwanStockInfo 缺少 stock_id 欄位")

    stock_ids = stock_info["stock_id"].dropna().astype(str).unique()

    # 排除 ETF、權證等非一般股票
    stock_ids = [
        x for x in stock_ids
        if x.isdigit() and len(x) == 4
    ]

    print(f"準備分析股票：{len(stock_ids)} 檔")

    # =========================
    # 取得每日股價
    # =========================
    price = get_finmind(
        "TaiwanStockPrice",
        start_date,
        end_date
    )

    if price.empty:
        raise Exception("無法取得 TaiwanStockPrice")

    price["stock_id"] = price["stock_id"].astype(str)
    price["date"] = pd.to_datetime(price["date"])

    # 只保留一般 4 碼股票
    price = price[
        price["stock_id"].isin(stock_ids)
    ].copy()

    # =========================
    # 開始計算飆股分數
    # =========================
    results = []

    for stock_id, df in price.groupby("stock_id"):

        df = df.sort_values("date").copy()

        if len(df) < 30:
            continue

        latest = df.iloc[-1]

        close = float(latest["close"])
        volume = float(latest["Trading_Volume"])

        # 5日、20日均量
        avg5 = df["Trading_Volume"].iloc[-6:-1].mean()
        avg20 = df["Trading_Volume"].iloc[-21:-1].mean()

        if avg5 <= 0 or avg20 <= 0:
            continue

        volume_ratio_5 = volume / avg5
        volume_ratio_20 = volume / avg20

        # 漲跌幅
        prev_close = float(df.iloc[-2]["close"])

        if prev_close <= 0:
            continue

        change_pct = (close / prev_close - 1) * 100

        # MA
        ma5 = df["close"].rolling(5).mean().iloc[-1]
        ma20 = df["close"].rolling(20).mean().iloc[-1]

        ma20_prev = df["close"].rolling(20).mean().iloc[-2]

        # 20日最高
        high20 = df["close"].iloc[-21:-1].max()

        breakout20 = close > high20

        # 52週高點
        high252 = df["close"].iloc[-252:].max()

        distance_from_high = (high252 - close) / high252 * 100

        # 20日漲幅
        price_20_days_ago = df["close"].iloc[-21]

        gain20 = (close / price_20_days_ago - 1) * 100

        # =========================
        # 計分
        # =========================
        score = 0
        reasons = []

        # 成交量
        if volume_ratio_5 >= 2:
            score += 15
            reasons.append("5日量爆2倍")
        elif volume_ratio_5 >= 1.5:
            score += 8
            reasons.append("5日量增")

        if volume_ratio_20 >= 1.5:
            score += 5
            reasons.append("20日量增")

        # 漲幅
        if 3 <= change_pct <= 9:
            score += 10
            reasons.append("強勢上漲")

        elif change_pct > 9:
            score -= 15
            reasons.append("漲幅過大")

        # 突破
        if breakout20:
            score += 10
            reasons.append("突破20日高")

        # 均線
        if close > ma20:
            score += 5

        if ma5 > ma20:
            score += 5
            reasons.append("MA5>MA20")

        if ma20 > ma20_prev:
            score += 5
            reasons.append("MA20上升")

        # 接近52週高點
        if distance_from_high <= 15:
            score += 5

        # 避免已經漲太多
        if gain20 > 25:
            score -= 10
            reasons.append("20日漲幅過大")

        # 只留下有一定分數的股票
        if score < 50:
            continue

        results.append({
            "stock_id": stock_id,
            "close": close,
            "change_pct": change_pct,
            "volume_ratio_5": volume_ratio_5,
            "volume_ratio_20": volume_ratio_20,
            "score": score,
            "breakout20": breakout20,
            "gain20": gain20,
            "reasons": reasons
        })

    if not results:
        message = (
            "🚨 飆股雷達 3.0\n\n"
            "今日沒有符合目前條件的股票。\n"
            "建議等待下一個交易日。"
        )

        send_telegram(message)
        return

    result_df = pd.DataFrame(results)

    result_df = result_df.sort_values(
        ["score", "volume_ratio_5"],
        ascending=False
    )

    # =========================
    # Telegram 訊息
    # =========================
    message_lines = []

    message_lines.append(
        f"🚨 飆股雷達 3.0｜{today.strftime('%Y/%m/%d')}"
    )

    message_lines.append(
        f"📊 今日掃描：{len(stock_ids)} 檔"
    )

    message_lines.append("")

    top10 = result_df.head(10)

    for rank, (_, row) in enumerate(top10.iterrows(), 1):

        stock_id = row["stock_id"]

        info = stock_info[
            stock_info["stock_id"].astype(str) == stock_id
        ]

        if not info.empty:
            stock_name = str(info.iloc[0].get("stock_name", ""))
        else:
            stock_name = ""

        message_lines.append(
            f"{rank}. {stock_name} {stock_id}"
        )

        message_lines.append(
            f"⭐ {int(row['score'])}分｜"
            f"📈 {row['change_pct']:+.2f}%｜"
            f"🔥 5日量 {row['volume_ratio_5']:.1f}倍"
        )

        if row["breakout20"]:
            message_lines.append("🚀 突破20日高點")

        if row["reasons"]:
            message_lines.append(
                "📌 " + "、".join(row["reasons"])
            )

        # 操作提醒
        if row["change_pct"] >= 8:
            status = "🔴 避免追高"
        elif row["breakout20"]:
            status = "🟡 突破後觀察"
        else:
            status = "🟢 等待拉回"

        message_lines.append(
            f"➡️ 狀態：{status}"
        )

        message_lines.append("")

    message_lines.append(
        "⚠️ 雷達僅供選股參考，不代表買進建議。"
    )

    message = "\n".join(message_lines)

    send_telegram(message)

    print(message)


if __name__ == "__main__":
    main()
