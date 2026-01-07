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
from google import genai
from google.genai import types

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
    # --- ✨ [新增] 原物料 (Commodities) ---
    "GC=F": {"Name": "Gold (黃金)", "Theme": "Commodity"},
    "SI=F": {"Name": "Silver (白銀)", "Theme": "Commodity"},
    "HG=F": {"Name": "Copper (銅)", "Theme": "Commodity"},
    "HRC=F": {"Name": "Steel (熱軋鋼)", "Theme": "Commodity"},
    "CL=F": {"Name": "Crude Oil (原油)", "Theme": "Commodity"}, # 順便送您原油，通常會一起看
    
    # --- 科技巨頭 ---
    "NVDA": {"Name": "NVIDIA", "Theme": "Technology"},
    "MSFT": {"Name": "Microsoft", "Theme": "Technology"},
    "AAPL": {"Name": "Apple", "Theme": "Technology"},
    "AMZN": {"Name": "Amazon", "Theme": "Consumer Cyclical"},
    "GOOG": {"Name": "Alphabet", "Theme": "Communication Services"},
    "META": {"Name": "Meta", "Theme": "Communication Services"},
    "TSLA": {"Name": "Tesla", "Theme": "Consumer Cyclical"},
    
    # --- 半導體與熱門股 ---
    "TSM": {"Name": "TSMC", "Theme": "Technology"},
    "AMD": {"Name": "AMD", "Theme": "Technology"},
    "AVGO": {"Name": "Broadcom", "Theme": "Technology"},
    "SMCI": {"Name": "Super Micro", "Theme": "Technology"},
    "COIN": {"Name": "Coinbase", "Theme": "Financial"},
}

# 初始化全域資訊字典
ALL_TICKER_INFO = STATIC_TICKERS.copy()

# ==========================================
# 2. 功能模組：抓取市場情緒 (Fear & Greed)
# ==========================================
def fetch_fear_and_greed():
    print("正在抓取 CNN Fear & Greed 指數...")
    
    # 偽裝成瀏覽器 Header
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://edition.cnn.com/"
    }
    
    result = None

    # 方法 A: 嘗試官方 API
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

    # 方法 B: 嘗試爬網頁 (Regex)
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
# 3. 功能模組：動態市場掃描 (Yahoo 爬蟲)
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
            # 使用 StringIO 避免 Pandas FutureWarning
            dfs = pd.read_html(StringIO(r.text))
            
            if len(dfs) > 0:
                df = dfs[0]
                symbols = df.iloc[:, 0].tolist()
                
                count = 0
                for sym in symbols:
                    sym = str(sym).split(" ")[0] # 去除註解
                    # 過濾掉包含 . 的權證或過長的代號
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
# 4. 功能模組：獲取個股新聞與分類
# ==========================================
def get_stock_profile(ticker_obj, symbol):
    """ 透過 yfinance API 獲取 Sector 與 Industry """
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


def calculate_technicals(closes):
    """ 計算技術指標：RSI, MA狀態 """
    try:
        if len(closes) < 15: return "資料不足", 50

        # 1. 計算 RSI (14)
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = round(rsi.iloc[-1], 1)

        # 2. 計算均線與乖離
        ma5 = closes.rolling(window=5).mean().iloc[-1]
        ma20 = closes.rolling(window=20).mean().iloc[-1]
        price = closes.iloc[-1]

        # 3. 生成描述字串
        trend = ""
        if price > ma5 and price > ma20: trend = "多頭排列 (站上5日/20日線)"
        elif price < ma5 and price < ma20: trend = "空頭排列 (跌破5日/20日線)"
        elif price > ma20: trend = "支撐有守 (站上20日線)"
        else: trend = "整理格局"

        tech_summary = f"RSI(14)={current_rsi}, {trend}, 5日乖離={(price/ma5-1)*100:.1f}%"
        return tech_summary, current_rsi
    except:
        return "技術面數據計算失敗", 50


def get_stock_news(symbol):
    """ 使用 yfinance 抓取該股票的最新新聞標題 """
    try:
        t = yf.Ticker(symbol)
        news_list = t.news
        headlines = []
        if news_list:
            for n in news_list[:5]: # 取前 5 則
                headlines.append(f"- {n.get('title', '')}")
        return "\n".join(headlines)
    except:
        return "No recent news found."

# ==========================================
# 5. 功能模組：Gemini AI 分析 (新版 SDK) - 修正版
# ==========================================
def generate_ai_analysis(df_daily):
    """ 挑選 Top 10 飆股並呼叫 Gemini 2.0 Flash-Lite 進行分析 """
    print("\n🤖 正在啟動 Google Gemini AI 分析模組 (Ver 2.0 Lite)...")
    
    if not GOOGLE_API_KEY:
        print("⚠️ 跳過 AI 分析 (缺少 API Key)")
        return

    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
    except Exception as e:
        print(f"⚠️ Gemini Client 初始化失敗: {e}")
        return

    try:
        # 1. 挑選名單 (Top 10)
        df_liquid = df_daily.sort_values(by='Daily_Amount_B', ascending=False).head(50)
        top_gainers = df_liquid.sort_values(by='Daily_Chg%', ascending=False).head(10)
        
        if top_gainers.empty:
            return

        ai_data = []

        for i, (_, row) in enumerate(top_gainers.iterrows()):
            symbol = row['Code']
            name = row['Name']
            chg = row['Daily_Chg%']
            sector = row['Sector']
            
            print(f"   -> [{i+1}/10] 分析: {symbol} ({chg}%) | 聯網搜尋中...")
            
            # --- 技術指標 ---
            try:
                hist = yf.download(symbol, period="1mo", progress=False, auto_adjust=False)
                if not hist.empty:
                    if isinstance(hist.columns, pd.MultiIndex):
                        close_series = hist['Close'][symbol]
                    else:
                        close_series = hist['Close']
                    tech_str, rsi_val = calculate_technicals(close_series)
                else:
                    tech_str, rsi_val = "無技術數據", 50
            except:
                tech_str, rsi_val = "數據讀取錯誤", 50

            # --- Prompt ---
            prompt = f"""
            你是一位專業的華爾街美股分析師。請分析美股 {symbol} ({name})。
            今日漲幅：{chg}%
            所屬板塊：{sector}
            技術面數據：{tech_str}
            
            請利用 Google Search 搜尋該公司「今日最新財經新聞」、「最近一週重大公告」以及「台灣供應鏈關係」。
            
            請回傳一個【純 JSON 字串】，不要包含 Markdown (```json ... ```) 標記。
            JSON 格式如下：
            {{
                "position": "一句話精準描述它賣什麼產品、市佔率或關鍵地位 (30字內)",
                "catalyst": "上漲具體原因。是財報優於預期(給數字)？分析師升評？還是發布新產品？ (40字內)",
                "momentum": "結合技術面數據 ({tech_str}) 與搜尋結果的動能判斷 (30字內)",
                "taiwan_link": "列出 2-3 檔受惠的台灣供應鏈名稱與代號，並用括號說明關係"
            }}
            """

            try:
                # ✨ [救援] 改用 Lite 版本，避開已耗盡的配額
                response = client.models.generate_content(
                    model='gemini-2.0-flash-lite-preview-02-05', 
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        # 關閉 JSON Mode 以支援 Google Search Tool
                        tools=[types.Tool(google_search=types.GoogleSearch())]
                    )
                )
                
                # 手動清理 JSON 字串
                raw_text = response.text
                clean_text = raw_text.replace("```json", "").replace("```", "").strip()
                
                analysis = json.loads(clean_text)
                
                ai_data.append({
                    "symbol": symbol,
                    "name": name,
                    "chg": chg,
                    "analysis": analysis
                })
                print(f"      ✅ 分析完成 (RSI: {rsi_val})")
                
                # 聯網搜尋耗時，休息 10 秒
                time.sleep(10)
                
            except Exception as e:
                # 捕捉 429 錯誤 (Resource Exhausted)
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    print(f"      ❌ 配額耗盡，停止後續分析。")
                    break # 直接跳出迴圈，不再嘗試下一檔
                
                print(f"      ⚠️ Gemini 分析失敗: {e}")
                # Fallback
                ai_data.append({
                    "symbol": symbol, "name": name, "chg": chg,
                    "analysis": {
                        "position": "資料讀取中...", "catalyst": "AI 連線逾時，請參閱新聞",
                        "momentum": f"技術面：{tech_str}", "taiwan_link": "暫無法查詢"
                    }
                })
                time.sleep(15)

        # 存檔
        out_path = os.path.join(TARGET_DIR, f"ai_report_{DATE_STR}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(ai_data, f, ensure_ascii=False, indent=4)
        print(f"✅ AI 分析報告已生成: {out_path}")

    except Exception as e:
        print(f"❌ AI 模組執行錯誤: {e}")

# ==========================================
# 6. 主程式：數據下載與處理
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
        df = pd.DataFrame(results)
        df['Sector'] = df.fillna('Other')['Sector']
        df['Industry'] = df.fillna('Other')['Industry']
        
        # 儲存 CSV
        for fname in [f"rank_daily_{DATE_STR}.csv", f"rank_weekly_{DATE_STR}.csv", f"rank_monthly_{DATE_STR}.csv"]:
            csv_path = os.path.join(TARGET_DIR, fname)
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        # 【執行 Gemini AI 分析】
        # 只傳入日排行數據
        # generate_ai_analysis(df)
        
        print(f"\n✅ 數據更新完成！所有檔案已歸檔至: {TARGET_DIR}")
    else:
        print("❌ 嚴重錯誤：未抓取到任何有效數據")

if __name__ == "__main__":
    fetch_and_process_data()
