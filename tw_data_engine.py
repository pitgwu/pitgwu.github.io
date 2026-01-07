import pandas as pd
import numpy as np
import requests
import json
import os
import datetime
import time
import random
import re
from io import StringIO
import yfinance as yf
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 0. 全域設定
# ==========================================
TZ_TW = datetime.timezone(datetime.timedelta(hours=8))
NOW = datetime.datetime.now(TZ_TW)
DATE_STR = NOW.strftime("%Y%m%d")

BASE_DIR = "tw_stock_dashboard"
TARGET_DIR = os.path.join(BASE_DIR, NOW.strftime("%Y"), NOW.strftime("%m"))
os.makedirs(TARGET_DIR, exist_ok=True)

print(f"📂 目標資料夾: {TARGET_DIR}")
print(f"📅 處理日期: {DATE_STR}")

# FinMind API
FINMIND_API = "https://api.finmindtrade.com/api/v4/data"

STD_COLS = ['Code', 'Name', 'Close', 'Daily_Chg%', 'Daily_Amount_B', 'Volume', 'Sector', 'Industry']

# ==========================================
# 1. 名單
# ==========================================
INDICES_CODES = {
    "^TWII": "加權指數", "^TWOII": "櫃買指數", 
    "^DJI": "道瓊工業", "^GSPC": "S&P 500", "^IXIC": "那斯達克", "^SOX": "費城半導體", "^VIX": "美股 VIX",
    "GC=F": "黃金", "SI=F": "白銀", "HG=F": "銅", "CL=F": "原油", "HRC=F": "熱軋鋼"
}

HIGH_PRICE_CODES = [
    "5274.TWO", "6669.TW", "3661.TW", "7769.TWO", "6515.TW", "2059.TW", "3008.TW", "3443.TW", "3653.TW", "6510.TWO",
    "6223.TWO", "3131.TWO", "3529.TWO", "2330.TW", "8299.TWO", "2383.TW", "2454.TW", "3665.TW", "6805.TW", "3017.TW",
    "3533.TW", "5269.TW", "6442.TW", "6781.TW", "2345.TW", "2308.TW", "6409.TW", "2404.TW", "7734.TWO", "1590.TW",
    "3324.TW", "8210.TW", "4749.TWO", "2360.TW", "7750.TWO", "5536.TWO", "3491.TWO", "1519.TW", "6944.TWO", "6739.TWO",
    "7751.TWO", "3293.TWO", "7805.TWO", "6640.TWO", "5289.TWO", "4583.TW", "2368.TW", "3081.TWO", "4966.TWO", "7728.TWO"
]

HP_SECTOR_MAP = {
    "2330.TW": "半導體業", "2317.TW": "電子代工", "2454.TW": "IC設計", "3008.TW": "光學鏡頭", 
    "5274.TWO": "伺服器IC", "3661.TW": "ASIC設計", "6669.TW": "AI伺服器", "2382.TW": "AI伺服器",
    "7769.TWO": "IC測試(興櫃)", "7750.TWO": "工具機(興櫃)", "6944.TWO": "廢水處理(興櫃)", 
    "7734.TWO": "封裝材料(興櫃)", "7751.TWO": "自動化(興櫃)", "6739.TWO": "半導體設備(興櫃)",
    "7805.TWO": "網通(興櫃)", "7728.TWO": "光電(興櫃)", "5289.TWO": "工控記憶體"
}

# ==========================================
# 2. 爬蟲工具
# ==========================================
def clean_number(x):
    if isinstance(x, str):
        x = re.sub(r'<[^>]+>|,|X|\+', '', x).strip()
        if x in ['--', '---', '']: return 0.0
        try: return float(x)
        except: return 0.0
    return x

def fetch_fear_and_greed():
    print("正在抓取 CNN Fear & Greed 指數 (雙重模式)...")
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
            result = {"score": int(latest['score']), "rating": rating}
            print(f"   ✅ [API] CNN 指數獲取成功: {result['score']}")
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
                    result = {"score": score, "rating": rating}
                    print(f"   ✅ [Web] CNN 指數獲取成功: {result['score']}")
        except: pass

    filepath = os.path.join(TARGET_DIR, f"sentiment_{DATE_STR}.json")
    if result:
        with open(filepath, "w", encoding="utf-8") as f: json.dump(result, f)
    else:
        print("   ❌ CNN 指數獲取失敗，使用預設值")
        with open(filepath, "w", encoding="utf-8") as f: json.dump({"score": 50, "rating": "Neutral"}, f)

def get_tw_vix_from_taifex():
    print("🔍 正在從期交所抓取台指 VIX...")
    url = "https://www.taifex.com.tw/cht/7/vixMinNew"
    headers = { "User-Agent": "Mozilla/5.0", "Accept-Language": "zh-TW" }
    for i in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=15, verify=False)
            dfs = pd.read_html(StringIO(r.text))
            for df in dfs:
                if len(df) > 0:
                    try:
                        v = float(df.iloc[-1].iat[-1])
                        if 5 < v < 100: 
                            print(f"   ✅ 台指 VIX: {v}")
                            return v
                    except: continue
        except: time.sleep(1)
    return None

# ==========================================
# 3. FinMind 逐檔點名
# ==========================================
def fetch_finmind_individual(stock_id_raw):
    stock_id = stock_id_raw.split('.')[0]
    end_date = NOW
    start_date = end_date - datetime.timedelta(days=7)
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d")
    }
    try:
        r = requests.get(FINMIND_API, params=params, timeout=5)
        data = r.json()
        if data.get('msg') == 'success' and data.get('data'):
            df = pd.DataFrame(data['data'])
            latest = df.iloc[-1]
            close = float(latest.get('close', 0))
            vol = float(latest.get('Trading_Volume', 0))
            amt = float(latest.get('Trading_Money', 0)) 
            if amt == 0 and close > 0 and vol > 0: amt = close * vol # 補算
            spread = float(latest.get('spread', 0))
            prev = close - spread
            pct = (spread / prev * 100) if prev > 0 else 0.0
            return {
                "Code": stock_id_raw, "Close": close, "Daily_Chg%": pct,
                "Daily_Amount_B": amt / 100000000, "Volume": vol, "Sector": "一般"
            }
    except: pass
    return None

def fetch_finmind_batch_targets(target_list):
    print(f"   🚀 [FinMind] 啟動逐檔點名 ({len(target_list)} 檔)...")
    results = []
    name_map = {}
    try:
        r = requests.get(FINMIND_API, params={"dataset": "TaiwanStockInfo"}, timeout=10)
        if r.status_code == 200:
            infos = r.json().get('data', [])
            for i in infos: name_map[i['stock_id']] = i.get('stock_name', '')
    except: pass

    count = 0
    for code in target_list:
        if code in INDICES_CODES: continue
        data = fetch_finmind_individual(code)
        if data:
            pure_id = code.split('.')[0]
            data['Name'] = name_map.get(pure_id, code)
            if code in HP_SECTOR_MAP: data['Sector'] = HP_SECTOR_MAP[code]
            results.append(data)
            count += 1
            if count % 10 == 0: print(f"      進度: {count}...")
        time.sleep(0.05)
    return pd.DataFrame(results)

# ==========================================
# 4. Yahoo API
# ==========================================
def call_yahoo_api(url):
    headers = { "User-Agent": "Mozilla/5.0", "Referer": "https://tw.stock.yahoo.com/" }
    try:
        time.sleep(random.uniform(0.6, 1.2))
        r = requests.get(url, headers=headers, timeout=10)
        return r.json() if r.status_code == 200 else None
    except: return None

def fetch_yahoo_rankings(rank_type, limit=200):
    print(f"   [Yahoo] 抓取 {rank_type} 排行榜...")
    results = []
    for ex in ['TAI', 'TWO']:
        url = f"https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.rank;exchange={ex};rankCategory={rank_type};limit={limit}"
        data = call_yahoo_api(url)
        if data and 'list' in data:
            for item in data['list']:
                p = float(item.get('price', 0) or 0)
                vol = float(item.get('volume', 0) or 0)
                if vol == 0: vol = float(item.get('volumeK', 0) or 0) * 1000
                amt = float(item.get('turnoverM', 0) or 0) / 100 
                if amt == 0 and p > 0 and vol > 0: amt = (p * vol) / 100_000_000

                results.append({
                    "Code": item.get('symbol', ''), "Name": item.get('name', ''), "Close": p,
                    "Daily_Chg%": float(item.get('changePercent', 0) or 0),
                    "Daily_Amount_B": amt, "Volume": vol,
                    "Sector": item.get('sectorName', '其他')
                })
    return pd.DataFrame(results)

def fetch_yfinance_indices():
    print("   🌍 [yfinance] 補充國際指數與原物料...")
    results = []
    idx_list = [k for k in INDICES_CODES.keys() if k != "^VIXTWN"]
    try:
        data = yf.download(idx_list, period="5d", progress=False)
        for code in idx_list:
            try:
                c = data['Close'][code] if len(idx_list)>1 else data['Close']
                c = c.dropna()
                if not c.empty:
                    p = c.iloc[-1]; prev = c.iloc[-2]
                    results.append({
                        "Code": code, "Name": INDICES_CODES[code], "Close": p,
                        "Daily_Chg%": ((p-prev)/prev)*100, "Daily_Amount_B": 0, "Volume": 0, "Sector": "指數/原物料"
                    })
            except: continue
    except: pass
    return pd.DataFrame(results)

def fetch_yahoo_quotes(symbols):
    if not symbols: return pd.DataFrame()
    results = []
    batch_size = 20
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        url = f"https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.quote;symbols={','.join(batch)}"
        data = call_yahoo_api(url)
        if data and 'list' in data:
            for item in data['list']:
                sym = item.get('symbol', '')
                sector = "市場指數" if "^" in sym else item.get('sectorName', '一般')
                results.append({ "Code": sym, "Sector": sector })
    return pd.DataFrame(results)

# ==========================================
# 5. 主流程
# ==========================================
def fetch_and_process_data():
    fetch_fear_and_greed()
    tw_vix = get_tw_vix_from_taifex()
    
    print("🚀 啟動 V31.0 數據引擎 (含跌幅排行)...")
    
    # 1. 高價股
    df_targets = fetch_finmind_batch_targets(HIGH_PRICE_CODES)
    
    # 2. 排行榜 (Turnover + Gainers + Losers)
    df_rank_t = fetch_yahoo_rankings('turnover', 200)
    df_rank_bull = fetch_yahoo_rankings('changeUp', 200)
    df_rank_bear = fetch_yahoo_rankings('changeDown', 200) # ✨ 新增：抓取跌幅排行
    
    # 3. 指數 & 原物料
    df_indices = fetch_yfinance_indices()
    
    # 4. 合併
    df_final = pd.concat([df_targets, df_rank_t, df_rank_bull, df_rank_bear, df_indices], ignore_index=True)
    
    if tw_vix:
        vix_row = {"Code": "^VIXTWN", "Name": "台指 VIX", "Sector": "波動率", "Close": tw_vix, "Daily_Chg%": 0, "Daily_Amount_B": 0, "Volume": 0}
        df_final = pd.concat([df_final, pd.DataFrame([vix_row])], ignore_index=True)

    if df_final.empty:
        df_final = pd.DataFrame(columns=STD_COLS)
    else:
        df_final = df_final.drop_duplicates(subset=['Code'], keep='first')

    # 產業補強
    if not df_final.empty:
        for code, sec in HP_SECTOR_MAP.items():
            df_final.loc[df_final['Code'] == code, 'Sector'] = sec
        
        targets = df_final[
            (df_final['Sector'].isin(['一般', '其他', '化學工業', '電機機械'])) & 
            (df_final['Daily_Amount_B'] > 0.5)
        ]['Code'].tolist()
        
        if targets:
            print(f"      優化產業分類 ({len(targets[:100])} 檔)...")
            sector_df = fetch_yahoo_quotes(targets[:100])
            if not sector_df.empty:
                s_map = sector_df.set_index('Code')['Sector'].to_dict()
                df_final['Sector'] = df_final['Code'].map(s_map).fillna(df_final['Sector'])

    df_final['Industry'] = df_final.get('Sector', '其他')
    for c in ['RVOL', 'Weekly_Chg%', 'Monthly_Chg%', 'Vol_Increase']: 
        if c not in df_final.columns: df_final[c] = 0
    
    def beautify(pct):
        try: return 10.0 if float(pct) >= 9.9 else (-10.0 if float(pct) <= -9.9 else float(pct))
        except: return 0.0
    
    if 'Daily_Chg%' in df_final.columns: df_final['Daily_Chg%'] = df_final['Daily_Chg%'].apply(beautify)

    csv_path = os.path.join(TARGET_DIR, f"rank_all_{DATE_STR}.csv")
    df_final.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    with open(os.path.join(TARGET_DIR, f"ai_report_{DATE_STR}.json"), "w", encoding="utf-8") as f: json.dump([], f)
    print(f"✅ 數據更新完成: {csv_path}")

if __name__ == "__main__":
    fetch_and_process_data()
