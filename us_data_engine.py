import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import os
import datetime
import time
import re
from io import StringIO

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
# 1. 靜態觀察名單 (核心權值股 & 指數)
# ==========================================
# 這些是無論有無上榜，我們都想持續監控的標的
STATIC_TICKERS = {
    # 指數
    "^DJI": {"Name": "Dow Jones", "Theme": "Index"},
    "^GSPC": {"Name": "S&P 500", "Theme": "Index"},
    "^IXIC": {"Name": "Nasdaq", "Theme": "Index"},
    "^SOX": {"Name": "PHLX Semi", "Theme": "Index"},
    "^VIX": {"Name": "VIX", "Theme": "Index"},
    "BTC-USD": {"Name": "Bitcoin", "Theme": "Crypto"},
    
    # 科技巨頭
    "NVDA": {"Name": "NVIDIA", "Theme": "Technology"},
    "MSFT": {"Name": "Microsoft", "Theme": "Technology"},
    "AAPL": {"Name": "Apple", "Theme": "Technology"},
    "AMZN": {"Name": "Amazon", "Theme": "Consumer Cyclical"},
    "GOOG": {"Name": "Alphabet", "Theme": "Communication Services"},
    "META": {"Name": "Meta", "Theme": "Communication Services"},
    "TSLA": {"Name": "Tesla", "Theme": "Consumer Cyclical"},
    
    # 半導體與熱門股
    "TSM": {"Name": "TSMC", "Theme": "Technology"},
    "AMD": {"Name": "AMD", "Theme": "Technology"},
    "AVGO": {"Name": "Broadcom", "Theme": "Technology"},
    "SMCI": {"Name": "Super Micro", "Theme": "Technology"},
    "COIN": {"Name": "Coinbase", "Theme": "Financial"},
}

# 初始化全域資訊字典
ALL_TICKER_INFO = STATIC_TICKERS.copy()

# ==========================================
# 2. 功能函式：抓取恐懼與貪婪指數
# ==========================================
def fetch_fear_and_greed():
    print("正在抓取 CNN Fear & Greed 指數...")
    
    # 偽裝 Header
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    result = None

    # 方法 A: 嘗試 API
    try:
        url_api = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        resp = requests.get(url_api, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            latest = data['fear_and_greed']
            rating = latest['rating'].capitalize() if latest['rating'] else "Neutral"
            result = {"score": int(latest['score']), "rating": rating, "timestamp": latest['timestamp']}
            print(f"✅ [API] CNN 指數獲取成功: {result['score']}")
    except: pass

    # 方法 B: 嘗試爬網頁 (備案)
    if result is None:
        try:
            url_web = "https://edition.cnn.com/markets/fear-and-greed"
            resp = requests.get(url_web, headers=headers, timeout=10)
            if resp.status_code == 200:
                match_score = re.search(r'"score":([\d\.]+)', resp.text)
                match_rating = re.search(r'"rating":"([a-zA-Z\s]+)"', resp.text)
                if match_score:
                    score = int(float(match_score.group(1)))
                    rating = match_rating.group(1).capitalize() if match_rating else "Neutral"
                    result = {"score": score, "rating": rating, "timestamp": datetime.datetime.now().isoformat()}
                    print(f"✅ [Web] CNN 指數獲取成功: {result['score']}")
        except: pass

    # 存檔
    filepath = os.path.join(TARGET_DIR, f"sentiment_{DATE_STR}.json")
    if result:
        with open(filepath, "w", encoding="utf-8") as f: json.dump(result, f, indent=4)
    else:
        print("❌ CNN 指數獲取失敗，使用預設值")
        with open(filepath, "w", encoding="utf-8") as f: json.dump({"score": 50, "rating": "N/A", "timestamp": ""}, f)

# ==========================================
# 3. 功能函式：動態市場掃描 (Web Scraping)
# ==========================================
def get_market_screeners():
    """ 爬取 Yahoo Finance 網頁抓取當日最熱門與漲幅最大股票 """
    print("🔍 正在爬取 Yahoo 網頁熱門榜...")
    
    targets = [
        ("https://finance.yahoo.com/most-active", "Most Active"),
        ("https://finance.yahoo.com/gainers", "Top Gainers")
    ]
    
    found_tickers = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    for url, tag in targets:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            # 使用 StringIO 避免 Pandas 警告
            dfs = pd.read_html(StringIO(r.text))
            
            if len(dfs) > 0:
                df = dfs[0]
                symbols = df.iloc[:, 0].tolist()
                
                count = 0
                for sym in symbols:
                    sym = str(sym).split(" ")[0] # 處理註解
                    # 過濾權證或不尋常的代號
                    if "." not in sym and len(sym) < 6:
                        found_tickers.append(sym)
                        # 如果不在靜態名單中，暫時標記，稍後會抓詳細 Sector
                        if sym not in ALL_TICKER_INFO:
                            ALL_TICKER_INFO[sym] = {"Name": sym, "Theme": "Unknown"}
                        count += 1
                print(f"   -> {tag}: 抓到 {count} 檔")
        except Exception as e:
            print(f"   ⚠️ 爬取失敗 {url}: {e}")

    # 保底機制：如果爬蟲全掛，使用備用清單
    if not found_tickers:
        print("⚠️ 警告：爬蟲未抓到數據，使用備用熱門清單")
        backup = ["PLTR", "SOFI", "MARA", "RIOT", "DKNG", "UBER", "HOOD", "OPEN", "LCID", "RIVN", "AMD", "F", "BAC"]
        for sym in backup:
            if sym not in ALL_TICKER_INFO: ALL_TICKER_INFO[sym] = {"Name": sym, "Theme": "Backup"}
        found_tickers = backup

    return list(set(found_tickers))

# ==========================================
# 4. 功能函式：獲取 Sector 與 Industry
# ==========================================
def get_stock_profile(ticker_obj, symbol):
    """ 透過 yfinance API 獲取詳細分類 """
    try:
        # 特殊處理
        if symbol == "BTC-USD": return "Crypto", "Cryptocurrency"
        if symbol.startswith("^"): return "Index", "Market Index"
        
        info = ticker_obj.info
        sector = info.get('sector', 'Other')
        industry = info.get('industry', 'Other')
        return sector, industry
    except:
        return "Other", "Other"

# ==========================================
# 5. 主程式：下載與處理數據
# ==========================================
def fetch_and_process_data():
    # 1. 抓情緒
    fetch_fear_and_greed()
    
    # 2. 抓動態清單
    dynamic_tickers = get_market_screeners()
    
    # 3. 合併清單
    static_list = list(STATIC_TICKERS.keys())
    final_tickers = list(set(static_list + dynamic_tickers))
    
    print(f"🚀 準備下載 {len(final_tickers)} 檔數據並分析產業結構...")
    
    results = []
    
    # 分批設定 (避免 Timeout)
    BATCH_SIZE = 8
    chunks = [final_tickers[i:i + BATCH_SIZE] for i in range(0, len(final_tickers), BATCH_SIZE)]
    
    for i, chunk in enumerate(chunks):
        max_retries = 5
        success = False
        data = pd.DataFrame()

        # 重試迴圈
        for attempt in range(max_retries):
            try:
                print(f"⏳ 下載批次 {i+1}/{len(chunks)}: {chunk[:3]}...")
                # threads=False 是避免大量連線被阻擋的關鍵
                data = yf.download(chunk, period="3mo", progress=False, auto_adjust=False, threads=False)
                if not data.empty:
                    success = True
                    break
            except: 
                time.sleep(2)
            time.sleep(2) # 失敗後等待

        if not success or data.empty:
            print(f"❌ 批次 {i+1} 失敗，跳過")
            continue
        
        # 處理該批次數據
        for ticker in chunk:
            try:
                # 處理 yfinance 回傳格式 (單檔 vs 多檔)
                if len(chunk) == 1 or isinstance(data.columns, pd.Index) and not isinstance(data.columns, pd.MultiIndex):
                    closes = data['Close']; volumes = data['Volume']
                else:
                    try: 
                        closes = data['Close'][ticker].dropna()
                        volumes = data['Volume'][ticker].dropna()
                    except: continue

                if closes.empty: continue
                current_price = closes.iloc[-1]
                
                # 過濾股價低於 $1 的水餃股
                if current_price < 1.0: continue

                current_vol = 0 if volumes.empty else volumes.iloc[-1]
                
                # 計算 RVOL (相對成交量)
                rvol = 0
                if len(volumes) >= 6:
                    avg_vol_5d = volumes.iloc[-6:-1].mean()
                    rvol = (current_vol / avg_vol_5d) if avg_vol_5d > 0 else 0

                # 計算漲跌幅
                def calc_chg(s, shift):
                    if len(s) > shift:
                        prev = s.iloc[-(shift + 1)]
                        return ((s.iloc[-1] - prev) / prev) * 100 if prev != 0 else 0
                    return 0
                
                daily_chg = calc_chg(closes, 1)
                amount_b = (current_price * current_vol) / 1_000_000_000
                
                # --- 【關鍵】獲取 Sector & Industry ---
                t_obj = yf.Ticker(ticker)
                sector, industry = get_stock_profile(t_obj, ticker)
                
                # 取得名稱 (優先使用我們清單中的，若無則用代號)
                name = ALL_TICKER_INFO.get(ticker, {}).get('Name', ticker)

                results.append({
                    "Code": ticker,
                    "Name": name,
                    "Sector": sector,     # 第一層分類
                    "Industry": industry, # 第二層分類
                    "Close": round(current_price, 2),
                    "Volume": current_vol,
                    "RVOL": round(rvol, 2),
                    "Daily_Chg%": round(daily_chg, 2),
                    "Weekly_Chg%": round(calc_chg(closes, 5), 2),
                    "Monthly_Chg%": round(calc_chg(closes, 21), 2),
                    "Daily_Amount_B": round(amount_b, 2),
                    "Weekly_Amount_B": round(amount_b, 2), # 這裡簡化，用當日量代表
                    "Monthly_Amount_B": round(amount_b, 2)
                })

            except Exception as e: continue
        
        # 批次間休息
        time.sleep(1)

    # 存檔
    if results:
        df_result = pd.DataFrame(results)
        # 填補空缺
        df_result['Sector'] = df_result['Sector'].fillna('Other')
        df_result['Industry'] = df_result['Industry'].fillna('Other')
        
        for fname in [f"rank_daily_{DATE_STR}.csv", f"rank_weekly_{DATE_STR}.csv", f"rank_monthly_{DATE_STR}.csv"]:
            df_result.to_csv(os.path.join(TARGET_DIR, fname), index=False, encoding='utf-8-sig')
        print(f"\n✅ 數據更新完成！已包含 Sector 與 Industry 資訊。")
    else:
        print("❌ 嚴重錯誤：未抓取到任何有效數據")

if __name__ == "__main__":
    fetch_and_process_data()
