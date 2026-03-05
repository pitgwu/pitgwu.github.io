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
# 0. 全域設定與目錄準備
# ==========================================
# ✨ [關鍵修正] 改用美股時間 (UTC-5) 作為檔案日期的基準
TZ_UTC = datetime.timezone.utc
now_utc = datetime.datetime.now(TZ_UTC)
us_date = now_utc - datetime.timedelta(hours=5)

DATE_STR = us_date.strftime("%Y%m%d")  # 例如: 20260211
YYYY = us_date.strftime("%Y")
MM = us_date.strftime("%m")

BASE_DIR = "us_stock_dashboard"
TARGET_DIR = os.path.join(BASE_DIR, YYYY, MM)

# 確保目錄存在
os.makedirs(TARGET_DIR, exist_ok=True)

print(f"📂 目標資料夾: {TARGET_DIR}")
print(f"📅 處理日期 (美股): {DATE_STR}")

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
    
    # --- Top Market Cap Giants ---
    "AAPL": {"Name": "Apple", "Theme": "Technology"},
    "NVDA": {"Name": "NVIDIA", "Theme": "Technology"},
    "MSFT": {"Name": "Microsoft", "Theme": "Technology"},
    "AMZN": {"Name": "Amazon", "Theme": "Consumer Cyclical"},
    "GOOG": {"Name": "Alphabet", "Theme": "Communication Services"},
    "META": {"Name": "Meta", "Theme": "Communication Services"},
    "TSLA": {"Name": "Tesla", "Theme": "Consumer Cyclical"},
    "BRK-B": {"Name": "Berkshire", "Theme": "Financial"},
    "AVGO": {"Name": "Broadcom", "Theme": "Technology"},
    "LLY":  {"Name": "Eli Lilly", "Theme": "Healthcare"},
    "WMT":  {"Name": "Walmart", "Theme": "Consumer Defensive"},
    "JPM":  {"Name": "JPMorgan", "Theme": "Financial"},
    "V":    {"Name": "Visa", "Theme": "Financial"},
    "XOM":  {"Name": "Exxon Mobil", "Theme": "Energy"},
    "UNH":  {"Name": "UnitedHealth", "Theme": "Healthcare"},
    "MA":   {"Name": "Mastercard", "Theme": "Financial"},
    "PG":   {"Name": "P&G", "Theme": "Consumer Defensive"},
    "COST": {"Name": "Costco", "Theme": "Consumer Defensive"},
    "JNJ":  {"Name": "J&J", "Theme": "Healthcare"},
    "HD":   {"Name": "Home Depot", "Theme": "Consumer Cyclical"},
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

ALL_TICKER_INFO = STATIC_TICKERS.copy()

# ==========================================
# 2. 功能模組：抓取市場情緒 (修復版)
# ==========================================
def fetch_fear_and_greed():
    print("🔍 正在抓取 CNN Fear & Greed 指數...")
    
    # 🌟 關鍵修正：加入完整的瀏覽器偽裝與 Referer，突破 CNN 的防爬蟲機制
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://edition.cnn.com/",
        "Accept": "application/json, text/plain, */*"
    }
    
    result = None
    
    # 策略 1: 嘗試呼叫 CNN Dataviz API
    try:
        url_api = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        resp = requests.get(url_api, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            latest = data.get('fear_and_greed', {})
            if 'score' in latest and 'rating' in latest:
                result = {
                    "score": int(latest['score']), 
                    "rating": latest['rating'].capitalize(), 
                    "timestamp": latest.get('timestamp', datetime.datetime.now().isoformat())
                }
                print(f"✅ 成功從 API 取得情緒指數: {result['score']} ({result['rating']})")
        else:
            print(f"⚠️ API 阻擋請求 (狀態碼: {resp.status_code})")
    except Exception as e:
        print(f"⚠️ API 請求錯誤: {e}")

    # 策略 2: 若 API 失敗，啟動網頁爬蟲備用方案
    if result is None:
        print("🔄 改用網頁爬蟲模式尋找數值...")
        try:
            url_web = "https://edition.cnn.com/markets/fear-and-greed"
            resp = requests.get(url_web, headers=headers, timeout=10)
            if resp.status_code == 200:
                # 使用 Regex 尋找藏在網頁原始碼裡的 JSON 數據
                match_score = re.search(r'"score":\s*([0-9.]+)', resp.text)
                match_rating = re.search(r'"rating":\s*"([^"]+)"', resp.text)
                
                if match_score and match_rating:
                    result = {
                        "score": int(float(match_score.group(1))), 
                        "rating": match_rating.group(1).capitalize(), 
                        "timestamp": datetime.datetime.now().isoformat()
                    }
                    print(f"✅ 成功從網頁原始碼取得情緒指數: {result['score']} ({result['rating']})")
        except Exception as e:
            print(f"⚠️ 網頁爬蟲失敗: {e}")

    # 防呆機制：如果都失敗，給予預設值避免報表生成報錯
    if result is None:
        print("❌ 無法取得情緒指數，寫入預設值 (Neutral: 50)")
        result = {"score": 50, "rating": "Neutral", "timestamp": datetime.datetime.now().isoformat()}

    # 寫入 JSON
    filepath = os.path.join(TARGET_DIR, f"sentiment_{DATE_STR}.json")
    with open(filepath, "w", encoding="utf-8") as f: 
        json.dump(result, f, indent=4)

# ==========================================
# 3. 功能模組：Yahoo 爬蟲
# ==========================================
def get_market_screeners():
    print("🔍 正在爬取 Yahoo 網頁熱門榜...")
    targets = [("https://finance.yahoo.com/most-active", "Most Active"), ("https://finance.yahoo.com/gainers", "Top Gainers")]
    found_tickers = []
    headers = {"User-Agent": "Mozilla/5.0"}

    for url, tag in targets:
        try:
            r = requests.get(url, headers=headers, timeout=10)
            dfs = pd.read_html(StringIO(r.text))
            if len(dfs) > 0:
                df = dfs[0]; symbols = df.iloc[:, 0].tolist()
                for sym in symbols:
                    sym = str(sym).split(" ")[0]
                    if "." not in sym and len(sym) < 6:
                        found_tickers.append(sym)
                        if sym not in ALL_TICKER_INFO: ALL_TICKER_INFO[sym] = {"Name": sym, "Theme": "Unknown"}
        except: pass

    if not found_tickers:
        found_tickers = ["PLTR", "SOFI", "MARA", "RIOT", "DKNG", "UBER", "HOOD", "OPEN", "LCID", "RIVN", "AMD", "F", "BAC"]
        for sym in found_tickers: 
            if sym not in ALL_TICKER_INFO: ALL_TICKER_INFO[sym] = {"Name": sym, "Theme": "Backup"}
    return list(set(found_tickers))

def get_stock_profile(ticker_obj, symbol):
    try:
        if symbol == "BTC-USD": return "Crypto", "Cryptocurrency", 0
        if symbol.startswith("^") or "=F" in symbol: return "Index", "Market Index", 0
        info = ticker_obj.info
        return info.get('sector', 'Other'), info.get('industry', 'Other'), info.get('marketCap', 0)
    except: return "Other", "Other", 0

# ==========================================
# 4. 主程式
# ==========================================
def fetch_and_process_data():
    fetch_fear_and_greed()
    dynamic_tickers = get_market_screeners()
    final_tickers = list(set(list(STATIC_TICKERS.keys()) + dynamic_tickers))
    
    print(f"🚀 準備下載 {len(final_tickers)} 檔數據...")
    
    results = []
    BATCH_SIZE = 8
    chunks = [final_tickers[i:i + BATCH_SIZE] for i in range(0, len(final_tickers), BATCH_SIZE)]
    
    for i, chunk in enumerate(chunks):
        data = pd.DataFrame()
        for attempt in range(3):
            try:
                print(f"⏳ 下載批次 {i+1}/{len(chunks)}: {chunk[:3]}...")
                data = yf.download(chunk, period="3mo", progress=False, auto_adjust=False, threads=False)
                if not data.empty: break
            except: time.sleep(1)
            time.sleep(1)

        if data.empty: continue
        
        for ticker in chunk:
            try:
                if len(chunk) == 1: closes, volumes = data['Close'], data['Volume']
                else: 
                    try: closes, volumes = data['Close'][ticker].dropna(), data['Volume'][ticker].dropna()
                    except: continue

                if closes.empty: continue
                current_price = closes.iloc[-1]
                if current_price < 1.0: continue

                current_vol = 0 if volumes.empty else volumes.iloc[-1]
                rvol = 0
                if len(volumes) >= 6:
                    avg_vol_5d = volumes.iloc[-6:-1].mean()
                    rvol = (current_vol / avg_vol_5d) if avg_vol_5d > 0 else 0

                def calc_chg(s, shift):
                    if len(s) > shift:
                        prev = s.iloc[-(shift + 1)]
                        return ((s.iloc[-1] - prev) / prev) * 100 if prev != 0 else 0
                    return 0
                
                daily_chg = calc_chg(closes, 1)
                amount_b = (current_price * current_vol) / 1_000_000_000
                
                t_obj = yf.Ticker(ticker)
                sector, industry, mkt_cap_raw = get_stock_profile(t_obj, ticker)
                mkt_cap_b = mkt_cap_raw / 1_000_000_000 if mkt_cap_raw else 0
                name = ALL_TICKER_INFO.get(ticker, {}).get('Name', ticker)

                results.append({
                    "Code": ticker, "Name": name, "Sector": sector, "Industry": industry,
                    "Close": round(current_price, 2), "Volume": current_vol, "RVOL": round(rvol, 2),
                    "Daily_Chg%": round(daily_chg, 2), "Weekly_Chg%": round(calc_chg(closes, 5), 2), "Monthly_Chg%": round(calc_chg(closes, 21), 2),
                    "Daily_Amount_B": round(amount_b, 2), "Weekly_Amount_B": round(amount_b, 2), "Monthly_Amount_B": round(amount_b, 2),
                    "Market_Cap_B": round(mkt_cap_b, 2)
                })
            except: continue
        time.sleep(1)

    if results:
        df = pd.DataFrame(results)
        df['Sector'] = df.fillna('Other')['Sector']
        df['Industry'] = df.fillna('Other')['Industry']
        
        # ✨ 存檔時使用 DATE_STR (美股日期)
        for fname in [f"rank_daily_{DATE_STR}.csv", f"rank_weekly_{DATE_STR}.csv", f"rank_monthly_{DATE_STR}.csv"]:
            csv_path = os.path.join(TARGET_DIR, fname)
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        print(f"\n✅ 數據更新完成: {TARGET_DIR}/rank_daily_{DATE_STR}.csv")
    else:
        print("❌ 嚴重錯誤：未抓取到任何有效數據")

if __name__ == "__main__":
    fetch_and_process_data()
