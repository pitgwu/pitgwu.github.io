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
# ✨ 引入 Google 官方最新 SDK
#from google import genai
#from google.genai import types

# ==========================================
# 0. 全域設定與目錄準備
# ==========================================
NOW = datetime.datetime.now()
YYYY = NOW.strftime("%Y")
MM = NOW.strftime("%m")
DATE_STR = NOW.strftime("%Y%m%d")

BASE_DIR = "us_stock_dashboard"
TARGET_DIR = os.path.join(BASE_DIR, YYYY, MM)

# 確保目錄存在
os.makedirs(TARGET_DIR, exist_ok=True)

print(f"📂 目標資料夾: {TARGET_DIR}")
print(f"📅 處理日期: {DATE_STR}")

# 取得 API Key (建議設定在環境變數)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# ==========================================
# 1. 靜態觀察名單 (核心權值股 & 指數)
# ==========================================
STATIC_TICKERS = {
    # --- 指數 ---
    "^DJI": {"Name": "Dow Jones", "Theme": "Index"},
    "^GSPC": {"Name": "S&P 500", "Theme": "Index"},
    "^IXIC": {"Name": "Nasdaq", "Theme": "Index"},
    "^SOX": {"Name": "PHLX Semi", "Theme": "Index"},
    "^VIX": {"Name": "VIX", "Theme": "Index"},
    "BTC-USD": {"Name": "Bitcoin", "Theme": "Crypto"},
    
    # --- 原物料 ---
    "GC=F": {"Name": "Gold (黃金)", "Theme": "Commodity"},
    "SI=F": {"Name": "Silver (白銀)", "Theme": "Commodity"},
    "HG=F": {"Name": "Copper (銅)", "Theme": "Commodity"},
    "HRC=F": {"Name": "Steel (熱軋鋼)", "Theme": "Commodity"},
    "CL=F": {"Name": "Crude Oil (原油)", "Theme": "Commodity"},
    
    # --- ✨ Top Market Cap Giants (補齊市值前20大) ---
    "AAPL": {"Name": "Apple", "Theme": "Technology"},
    "NVDA": {"Name": "NVIDIA", "Theme": "Technology"},
    "MSFT": {"Name": "Microsoft", "Theme": "Technology"},
    "AMZN": {"Name": "Amazon", "Theme": "Consumer Cyclical"},
    "GOOG": {"Name": "Alphabet", "Theme": "Communication Services"},
    "META": {"Name": "Meta", "Theme": "Communication Services"},
    "TSLA": {"Name": "Tesla", "Theme": "Consumer Cyclical"},
    "BRK-B": {"Name": "Berkshire", "Theme": "Financial"}, # 波克夏
    "AVGO": {"Name": "Broadcom", "Theme": "Technology"},
    "LLY":  {"Name": "Eli Lilly", "Theme": "Healthcare"},
    "WMT":  {"Name": "Walmart", "Theme": "Consumer Defensive"},
    "JPM":  {"Name": "JPMorgan", "Theme": "Financial"},
    "V":    {"Name": "Visa", "Theme": "Financial"},
    "XOM":  {"Name": "Exxon Mobil", "Theme": "Energy"},
    "UNH":  {"Name": "UnitedHealth", "Theme": "Healthcare"}, # 聯合健康
    "MA":   {"Name": "Mastercard", "Theme": "Financial"},
    "PG":   {"Name": "P&G", "Theme": "Consumer Defensive"}, # 寶僑
    "COST": {"Name": "Costco", "Theme": "Consumer Defensive"},
    "JNJ":  {"Name": "J&J", "Theme": "Healthcare"},
    "HD":   {"Name": "Home Depot", "Theme": "Consumer Cyclical"}, # 家得寶
    "ABBV": {"Name": "AbbVie", "Theme": "Healthcare"},
    "BAC":  {"Name": "Bank of America", "Theme": "Financial"},
    "KO":   {"Name": "Coca-Cola", "Theme": "Consumer Defensive"},
    
    # --- 熱門與半導體 ---
    "TSM": {"Name": "TSMC", "Theme": "Technology"},
    "AMD": {"Name": "AMD", "Theme": "Technology"},
    "SMCI": {"Name": "Super Micro", "Theme": "Technology"},
    "COIN": {"Name": "Coinbase", "Theme": "Financial"},
    "INTC": {"Name": "Intel", "Theme": "Semiconductors"},
    "MU":   {"Name": "Micron", "Theme": "Memory"},
    "QCOM": {"Name": "Qualcomm", "Theme": "Mobile Chipsets"},
    "TXN":  {"Name": "Texas Inst", "Theme": "Analog IC"},
    "AMAT": {"Name": "Applied Mat", "Theme": "Semiconductor Equipment"},
    "LRCX": {"Name": "Lam Research", "Theme": "Semiconductor Equipment"},
    
    # --- Software / Others ---
    "ORCL": {"Name": "Oracle", "Theme": "Database"},
    "CRWV": {"Name": "CoreWeave", "Theme": "Cloud Computing"},
    "ADBE": {"Name": "Adobe", "Theme": "Creative Software"},
    "CRM":  {"Name": "Salesforce", "Theme": "CRM"},
    "PLTR": {"Name": "Palantir", "Theme": "Big Data / AI"},
    "NFLX": {"Name": "Netflix", "Theme": "Streaming"},
    "DIS":  {"Name": "Disney", "Theme": "Entertainment"},
    "MSTR": {"Name": "MicroStrategy", "Theme": "Bitcoin Holdings"},
}

# 初始化全域資訊字典
ALL_TICKER_INFO = STATIC_TICKERS.copy()

# ==========================================
# 2. 功能模組：抓取市場情緒 (Fear & Greed)
# ==========================================
def fetch_fear_and_greed():
    print("正在抓取 CNN Fear & Greed 指數...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://edition.cnn.com/"
    }
    
    result = None

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

    filepath = os.path.join(TARGET_DIR, f"sentiment_{DATE_STR}.json")
    if result:
        with open(filepath, "w", encoding="utf-8") as f: json.dump(result, f, indent=4)
    else:
        print("❌ CNN 指數獲取失敗，使用預設值")
        with open(filepath, "w", encoding="utf-8") as f: json.dump({"score": 50, "rating": "N/A", "timestamp": ""}, f)

# ==========================================
# 3. 功能模組：動態市場掃描 (Yahoo 爬蟲)
# ==========================================
def get_market_screeners():
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
                            ALL_TICKER_INFO[sym] = {"Name": sym, "Theme": "Unknown"}
                        count += 1
                print(f"   -> {tag}: 抓到 {count} 檔")
        except Exception as e:
            print(f"   ⚠️ 爬取失敗 {url}: {e}")

    if not found_tickers:
        print("⚠️ 警告：爬蟲未抓到數據，使用備用熱門清單")
        backup = ["PLTR", "SOFI", "MARA", "RIOT", "DKNG", "UBER", "HOOD", "OPEN", "LCID", "RIVN", "AMD", "F", "BAC"]
        for sym in backup:
            if sym not in ALL_TICKER_INFO: ALL_TICKER_INFO[sym] = {"Name": sym, "Theme": "Backup"}
        found_tickers = backup

    return list(set(found_tickers))

# ==========================================
# 4. 功能模組：獲取個股新聞與分類
# ==========================================
def get_stock_profile(ticker_obj, symbol):
    """ 透過 yfinance API 獲取 Sector, Industry 與 Market Cap """
    try:
        if symbol == "BTC-USD": return "Crypto", "Cryptocurrency", 0
        if symbol.startswith("^") or "=F" in symbol: return "Index", "Market Index", 0
        
        info = ticker_obj.info
        sector = info.get('sector', 'Other')
        industry = info.get('industry', 'Other')
        # ✨ 抓取市值
        mkt_cap = info.get('marketCap', 0)
        
        return sector, industry, mkt_cap
    except:
        return "Other", "Other", 0

# ==========================================
# 5. 主程式：數據下載與處理
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
    
    # 分批設定
    BATCH_SIZE = 8
    chunks = [final_tickers[i:i + BATCH_SIZE] for i in range(0, len(final_tickers), BATCH_SIZE)]
    
    for i, chunk in enumerate(chunks):
        max_retries = 3 # 降為3次加速
        success = False
        data = pd.DataFrame()

        for attempt in range(max_retries):
            try:
                print(f"⏳ 下載批次 {i+1}/{len(chunks)}: {chunk[:3]}...")
                data = yf.download(chunk, period="3mo", progress=False, auto_adjust=False, threads=False)
                if not data.empty:
                    success = True
                    break
            except: 
                time.sleep(1)
            time.sleep(1)

        if not success or data.empty:
            print(f"❌ 批次 {i+1} 失敗，跳過")
            continue
        
        for ticker in chunk:
            try:
                if len(chunk) == 1 or isinstance(data.columns, pd.Index) and not isinstance(data.columns, pd.MultiIndex):
                    closes = data['Close']; volumes = data['Volume']
                else:
                    try: 
                        closes = data['Close'][ticker].dropna()
                        volumes = data['Volume'][ticker].dropna()
                    except: continue

                if closes.empty: continue
                current_price = closes.iloc[-1]
                if current_price < 1.0: continue # 過濾水餃股

                current_vol = 0 if volumes.empty else volumes.iloc[-1]
                
                # RVOL
                rvol = 0
                if len(volumes) >= 6:
                    avg_vol_5d = volumes.iloc[-6:-1].mean()
                    rvol = (current_vol / avg_vol_5d) if avg_vol_5d > 0 else 0

                # 漲跌幅
                def calc_chg(s, shift):
                    if len(s) > shift:
                        prev = s.iloc[-(shift + 1)]
                        return ((s.iloc[-1] - prev) / prev) * 100 if prev != 0 else 0
                    return 0
                
                daily_chg = calc_chg(closes, 1)
                amount_b = (current_price * current_vol) / 1_000_000_000
                
                # --- 【關鍵】獲取 Sector, Industry & Market Cap ---
                t_obj = yf.Ticker(ticker)
                sector, industry, mkt_cap_raw = get_stock_profile(t_obj, ticker)
                
                # 市值轉 B (Billions)
                mkt_cap_b = mkt_cap_raw / 1_000_000_000 if mkt_cap_raw else 0
                
                name = ALL_TICKER_INFO.get(ticker, {}).get('Name', ticker)

                results.append({
                    "Code": ticker,
                    "Name": name,
                    "Sector": sector,
                    "Industry": industry,
                    "Close": round(current_price, 2),
                    "Volume": current_vol,
                    "RVOL": round(rvol, 2),
                    "Daily_Chg%": round(daily_chg, 2),
                    "Weekly_Chg%": round(calc_chg(closes, 5), 2),
                    "Monthly_Chg%": round(calc_chg(closes, 21), 2),
                    "Daily_Amount_B": round(amount_b, 2),
                    "Weekly_Amount_B": round(amount_b, 2),
                    "Monthly_Amount_B": round(amount_b, 2),
                    "Market_Cap_B": round(mkt_cap_b, 2) # ✨ 新增市值欄位
                })

            except Exception as e: continue
        
        time.sleep(1)

    if results:
        df = pd.DataFrame(results)
        df['Sector'] = df.fillna('Other')['Sector']
        df['Industry'] = df.fillna('Other')['Industry']
        
        for fname in [f"rank_daily_{DATE_STR}.csv", f"rank_weekly_{DATE_STR}.csv", f"rank_monthly_{DATE_STR}.csv"]:
            csv_path = os.path.join(TARGET_DIR, fname)
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        print(f"\n✅ 數據更新完成！所有檔案已歸檔至: {TARGET_DIR}")
    else:
        print("❌ 嚴重錯誤：未抓取到任何有效數據")

if __name__ == "__main__":
    fetch_and_process_data()
