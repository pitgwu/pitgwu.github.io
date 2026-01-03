import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import os
import datetime
import time
from io import StringIO  # 新增: 用於消除 Pandas 警告

# ==========================================
# 0. 設定與目錄準備
# ==========================================
NOW = datetime.datetime.now()
YYYY = NOW.strftime("%Y")
MM = NOW.strftime("%m")
DATE_STR = NOW.strftime("%Y%m%d")

BASE_DIR = "us_stock_dashboard"
TARGET_DIR = os.path.join(BASE_DIR, YYYY, MM)

os.makedirs(TARGET_DIR, exist_ok=True)

print(f"📂 目標資料夾: {TARGET_DIR}")
print(f"📅 處理日期: {DATE_STR}")

# ==========================================
# 1. 靜態觀察名單 (核心權值股)
# ==========================================
STATIC_TICKERS = {
    # 指數
    "^DJI": {"Name": "Dow Jones", "Theme": "道瓊"},
    "^GSPC": {"Name": "S&P 500", "Theme": "標普"},
    "^IXIC": {"Name": "Nasdaq", "Theme": "那指"},
    "^SOX": {"Name": "PHLX Semi", "Theme": "費半"},
    "^VIX": {"Name": "VIX", "Theme": "恐慌"},
    "BTC-USD": {"Name": "Bitcoin", "Theme": "加密幣"},
    # 巨頭
    "NVDA": {"Name": "NVIDIA", "Theme": "AI"},
    "MSFT": {"Name": "Microsoft", "Theme": "軟體"},
    "AAPL": {"Name": "Apple", "Theme": "消費電"},
    "AMZN": {"Name": "Amazon", "Theme": "電商"},
    "GOOG": {"Name": "Alphabet", "Theme": "搜尋"},
    "META": {"Name": "Meta", "Theme": "社群"},
    "TSLA": {"Name": "Tesla", "Theme": "電動車"},
    "TSM": {"Name": "TSMC", "Theme": "晶圓"},
    "AMD": {"Name": "AMD", "Theme": "晶片"},
    "AVGO": {"Name": "Broadcom", "Theme": "網通"},
    "SMCI": {"Name": "Super Micro", "Theme": "伺服器"},
    "COIN": {"Name": "Coinbase", "Theme": "幣所"},
}

ALL_TICKER_INFO = STATIC_TICKERS.copy()

# ==========================================
# 2. 動態市場掃描 (Web Scraping)
# ==========================================
def get_market_screeners():
    print("🔍 正在爬取 Yahoo 網頁熱門榜 (Web Scraping)...")
    
    targets = [
        ("https://finance.yahoo.com/most-active", "🔥 交易熱門"),
        ("https://finance.yahoo.com/gainers", "🚀 漲幅排行")
    ]
    
    found_tickers = []
    
    # 偽裝瀏覽器 Header
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for url, tag in targets:
        try:
            print(f"   -> 正在讀取: {url} ...")
            r = requests.get(url, headers=headers, timeout=10)
            
            # 【修正點】使用 StringIO 包裝 HTML 字串，消除 FutureWarning
            dfs = pd.read_html(StringIO(r.text))
            
            if len(dfs) > 0:
                df = dfs[0]
                symbols = df.iloc[:, 0].tolist()
                
                count = 0
                for sym in symbols:
                    sym = str(sym).split(" ")[0]
                    if "." not in sym and len(sym) < 6:
                        found_tickers.append(sym)
                        if sym not in ALL_TICKER_INFO:
                            try:
                                name = df.iloc[count, 1]
                            except:
                                name = sym
                            ALL_TICKER_INFO[sym] = {"Name": name, "Theme": tag}
                        count += 1
                print(f"      抓到 {count} 檔")
            else:
                print(f"      ⚠️ 未在頁面中發現表格")

        except Exception as e:
            print(f"      ⚠️ 爬取失敗: {e}")

    # 保底清單
    if not found_tickers:
        print("⚠️ 爬蟲失敗，使用備用熱門清單")
        backup_list = ["PLTR", "SOFI", "MARA", "RIOT", "DKNG", "UBER", "HOOD", "OPEN", "LCID", "RIVN", "AMD", "F", "BAC", "T", "INTC"]
        for sym in backup_list:
            if sym not in ALL_TICKER_INFO:
                ALL_TICKER_INFO[sym] = {"Name": sym, "Theme": "備用熱門"}
        found_tickers = backup_list

    dynamic_list = list(set(found_tickers))
    print(f"✅ 掃描完成！共鎖定 {len(dynamic_list)} 檔活躍股票。")
    return dynamic_list

def fetch_fear_and_greed():
    print("正在抓取 CNN Fear & Greed 指數...")
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            latest = data['fear_and_greed']
            result = {"score": int(latest['score']), "rating": latest['rating'], "timestamp": latest['timestamp']}
            filepath = os.path.join(TARGET_DIR, f"sentiment_{DATE_STR}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=4)
            print(f"✅ CNN 指數已存檔")
            return
    except: pass
    
    filepath = os.path.join(TARGET_DIR, f"sentiment_{DATE_STR}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({"score": 50, "rating": "Neutral", "timestamp": ""}, f)

def fetch_and_process_data():
    fetch_fear_and_greed()
    
    dynamic_tickers = get_market_screeners()
    static_list = list(STATIC_TICKERS.keys())
    final_tickers = list(set(static_list + dynamic_tickers))
    
    print(f"🚀 準備下載 {len(final_tickers)} 檔標的數據...")
    
    results = []
    BATCH_SIZE = 8
    chunks = [final_tickers[i:i + BATCH_SIZE] for i in range(0, len(final_tickers), BATCH_SIZE)]
    
    for i, chunk in enumerate(chunks):
        max_retries = 5
        success = False
        data = pd.DataFrame()

        for attempt in range(max_retries):
            try:
                print(f"⏳ 下載批次 {i+1}/{len(chunks)} (嘗試 {attempt+1}/{max_retries}): {chunk[:3]}...")
                data = yf.download(chunk, period="3mo", progress=False, auto_adjust=False, threads=False)
                if not data.empty:
                    success = True
                    break
            except Exception as e:
                print(f"   ⚠️ 錯誤: {e}")
            time.sleep(5)

        if not success or data.empty:
            print(f"❌ 批次 {i+1} 最終失敗，跳過。")
            continue
        
        for ticker in chunk:
            try:
                if len(chunk) == 1 or isinstance(data.columns, pd.Index) and not isinstance(data.columns, pd.MultiIndex):
                    closes = data['Close']
                    volumes = data['Volume']
                else:
                    try:
                        closes = data['Close'][ticker].dropna()
                        volumes = data['Volume'][ticker].dropna()
                    except KeyError: continue

                if closes.empty: continue
                
                current_price = closes.iloc[-1]
                
                # 【新增】過濾掉股價 < 1 美元的水餃股 (Penny Stocks)
                if current_price < 1.0:
                    continue

                current_vol = 0 if volumes.empty else volumes.iloc[-1]
                
                if len(volumes) >= 6:
                    avg_vol_5d = volumes.iloc[-6:-1].mean()
                    rvol = (current_vol / avg_vol_5d) if avg_vol_5d > 0 else 0
                else:
                    rvol = 0

                def calc_chg(series, shift):
                    if len(series) > shift:
                        last = series.iloc[-1]
                        prev = series.iloc[-(shift + 1)]
                        return ((last - prev) / prev) * 100 if prev != 0 else 0
                    return 0

                def calc_vol_chg(series, shift):
                    if len(series) > shift:
                        last = series.iloc[-1]
                        prev = series.iloc[-(shift + 1)]
                        return ((last - prev) / prev) * 100 if prev != 0 else 0
                    return 0

                daily_chg = calc_chg(closes, 1)
                weekly_chg = calc_chg(closes, 5)
                monthly_chg = calc_chg(closes, 21)
                
                daily_vol_chg = calc_vol_chg(volumes, 1)
                weekly_vol_chg = calc_vol_chg(volumes, 5)
                monthly_vol_chg = calc_vol_chg(volumes, 21)
                
                amount_b = (current_price * current_vol) / 1_000_000_000
                info = ALL_TICKER_INFO.get(ticker, {"Name": ticker, "Theme": "Scan"})

                results.append({
                    "Code": ticker,
                    "Name": info.get('Name', ticker),
                    "Theme": info.get('Theme', 'Scan'),
                    "Close": round(current_price, 2),
                    "Volume": current_vol,
                    "RVOL": round(rvol, 2),
                    "Daily_Chg%": round(daily_chg, 2),
                    "Weekly_Chg%": round(weekly_chg, 2),
                    "Monthly_Chg%": round(monthly_chg, 2),
                    "Daily_Vol_Chg%": round(daily_vol_chg, 2),
                    "Weekly_Vol_Chg%": round(weekly_vol_chg, 2),
                    "Monthly_Vol_Chg%": round(monthly_vol_chg, 2),
                    "Daily_Amount_B": round(amount_b, 2),
                    "Weekly_Amount_B": round(amount_b, 2),
                    "Monthly_Amount_B": round(amount_b, 2)
                })

            except Exception: continue
        
        time.sleep(1)

    if not results:
        print("❌ 嚴重警告：無數據！")
    else:
        df_result = pd.DataFrame(results)
        for fname in [f"rank_daily_{DATE_STR}.csv", f"rank_weekly_{DATE_STR}.csv", f"rank_monthly_{DATE_STR}.csv"]:
            df_result.to_csv(os.path.join(TARGET_DIR, fname), index=False, encoding='utf-8-sig')
            
        print(f"\n✅ 數據更新完成！共處理 {len(df_result)} 檔股票。")

if __name__ == "__main__":
    fetch_and_process_data()
