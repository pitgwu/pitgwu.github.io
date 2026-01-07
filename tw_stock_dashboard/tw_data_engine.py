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

# 關閉 SSL 警告 (針對期交所)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 0. 全域設定
# ==========================================
NOW = datetime.datetime.now()
YYYY = NOW.strftime("%Y")
MM = NOW.strftime("%m")
DATE_STR = NOW.strftime("%Y%m%d")

BASE_DIR = "tw_stock_dashboard"
TARGET_DIR = os.path.join(BASE_DIR, YYYY, MM)
os.makedirs(TARGET_DIR, exist_ok=True)

print(f"📂 目標資料夾: {TARGET_DIR}")
print(f"📅 處理日期: {DATE_STR}")

# ==========================================
# 1. 名單與設定
# ==========================================
INDICES_CODES = {
    "^TWII": "加權指數", "^TWOII": "櫃買指數", 
    "^DJI": "道瓊工業", "^GSPC": "S&P 500", "^IXIC": "那斯達克", "^SOX": "費城半導體", "^VIX": "美股 VIX",
    "GC=F": "黃金", "SI=F": "白銀", "HG=F": "銅", "CL=F": "原油"
}

HIGH_PRICE_CODES = [
    "5274.TWO", "6669.TW", "3661.TW", "7769.TWO", "6515.TW", "2059.TW", "3008.TW", "3443.TW", "3653.TW", "6510.TWO",
    "6223.TWO", "3131.TWO", "3529.TWO", "2330.TW", "8299.TWO", "2383.TW", "2454.TW", "3665.TW", "6805.TW", "3017.TW",
    "3533.TW", "5269.TW", "6442.TW", "6781.TW", "2345.TW", "2308.TW", "6409.TW", "2404.TW", "7734.TWO", "1590.TW",
    "3324.TW", "8210.TW", "4749.TWO", "2360.TW", "7750.TWO", "5536.TWO", "3491.TWO", "1519.TW", "6944.TWO", "6739.TWO",
    "7751.TWO", "3293.TWO", "7805.TWO", "6640.TWO", "5289.TWO", "4583.TW", "2368.TW", "3081.TWO", "4966.TWO", "7728.TWO"
]

# 擴充產業對照 (當 Yahoo API 失效時使用)
HP_SECTOR_MAP = {
    "2330.TW": "半導體", "2317.TW": "電子代工", "2454.TW": "IC設計", "3008.TW": "光學鏡頭", 
    "5274.TWO": "伺服器管理IC", "3661.TW": "ASIC", "6669.TW": "AI伺服器", "2382.TW": "AI伺服器",
    "2059.TW": "滑軌", "3443.TW": "IC設計", "3653.TW": "散熱", "6510.TWO": "測試介面",
    "6223.TWO": "探針卡", "3131.TWO": "半導體設備", "3529.TWO": "矽智財", "8299.TWO": "NAND控制",
    "2383.TW": "銅箔基板", "3665.TW": "連接器", "6805.TW": "軸承", "3017.TW": "散熱",
    "3533.TW": "連接器", "5269.TW": "IC設計", "6442.TW": "光通訊", "6781.TW": "電池模組",
    "2345.TW": "網通", "2308.TW": "電源供應", "6409.TW": "不斷電系統", "2404.TW": "無塵室工程",
    "3324.TW": "散熱", "8210.TW": "機殼", "2360.TW": "檢測設備", "1519.TW": "重電",
    "3293.TWO": "遊戲", "2368.TW": "PCB", "3081.TWO": "光通訊", "4966.TWO": "IC設計"
}

# ==========================================
# 2. 爬蟲功能
# ==========================================
def fetch_fear_and_greed():
    print("正在抓取 CNN Fear & Greed 指數...")
    try:
        r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if r.status_code == 200:
            data = r.json()['fear_and_greed']
            with open(os.path.join(TARGET_DIR, f"sentiment_{DATE_STR}.json"), "w") as f:
                json.dump({"score": int(data['score']), "rating": data['rating']}, f)
    except: pass

def get_tw_vix_from_taifex():
    print("🔍 正在從期交所抓取台指 VIX (強化版)...")
    url = "https://www.taifex.com.tw/cht/7/vixMinNew"
    # 使用更像真人的 Header 並且接受中文編碼
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    for i in range(3):
        try:
            # verify=False 忽略 SSL 憑證問題
            r = requests.get(url, headers=headers, timeout=15, verify=False)
            r.encoding = 'utf-8'
            dfs = pd.read_html(StringIO(r.text))
            if dfs:
                df = dfs[0]
                # 倒序檢查最後一筆有效數值
                for idx in range(len(df)-1, -1, -1):
                    try:
                        # 嘗試取得最後一個欄位 (通常是指數)
                        val = df.iloc[idx].iat[-1]
                        v = float(val)
                        if 5 < v < 100: 
                            print(f"   ✅ 台指 VIX: {v}")
                            return v
                    except: continue
                break
        except Exception as e:
            # print(f"VIX retry {i}: {e}")
            time.sleep(1)
    
    print("   ⚠️ VIX 抓取失敗")
    return None

# --- Plan A: Yahoo API ---
def call_yahoo_api(url):
    # 隨機 User-Agent
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ]
    headers = { "User-Agent": random.choice(uas), "Referer": "https://tw.stock.yahoo.com/" }
    try:
        time.sleep(random.uniform(0.8, 2.0)) # 增加延遲，降低被鎖機率
        r = requests.get(url, headers=headers, timeout=10)
        return r.json() if r.status_code == 200 else None
    except: return None

def fetch_yahoo_rankings(rank_type, limit=250):
    print(f"   [Yahoo] 抓取 {rank_type} ...")
    results = []
    for ex in ['TAI', 'TWO']:
        url = f"https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.rank;exchange={ex};rankCategory={rank_type};limit={limit}"
        data = call_yahoo_api(url)
        if data and 'list' in data:
            for item in data['list']:
                p = float(item.get('price', 0) or 0)
                vol_k = float(item.get('volumeK', 0) or 0) * 1000
                amt = float(item.get('turnoverM', 0) or 0) / 100
                if amt == 0 and p > 0: amt = (vol_k * p) / 100_000_000
                
                results.append({
                    "Code": item.get('symbol', ''), "Name": item.get('name', ''), "Close": p,
                    "Daily_Chg%": float(item.get('changePercent', 0) or 0),
                    "Daily_Amount_B": amt, "Volume": vol_k,
                    "Sector": item.get('sectorName', '其他')
                })
    return pd.DataFrame(results)

def fetch_yahoo_quotes(symbols):
    if not symbols: return pd.DataFrame()
    results = []
    print(f"   [Yahoo] 補抓 {len(symbols)} 檔關注股...")
    
    batch_size = 20
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        url = f"https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.quote;symbols={','.join(batch)}"
        data = call_yahoo_api(url)
        if data and 'list' in data:
            for item in data['list']:
                sym = item.get('symbol', '')
                p = float(item.get('price', 0) or 0)
                sector = "市場指數" if "^" in sym else item.get('sectorName', '其他')
                name = INDICES_CODES.get(sym, item.get('name', sym))
                
                vol = float(item.get('volume', 0) or 0) * 1000
                amt = float(item.get('turnoverM', 0) or 0) / 100
                if amt == 0 and p > 0: amt = (vol * p) / 100_000_000

                results.append({
                    "Code": sym, "Name": name, "Close": p, 
                    "Daily_Chg%": float(item.get('changePercent', 0) or 0),
                    "Daily_Amount_B": amt, "Volume": vol, "Sector": sector
                })
    return pd.DataFrame(results)

# --- Plan B: 官方報表 (TWSE/TPEX/Emerging) ---
def clean_number(x):
    if isinstance(x, str):
        x = re.sub(r'<[^>]+>|,|X|\+', '', x).strip()
        if x in ['--', '---', '']: return 0.0
        try: return float(x)
        except: return 0.0
    return x

def fetch_official_market(date_dt):
    print(f"   🚑 [救援模式] 下載 {date_dt.strftime('%Y-%m-%d')} 官方報表...")
    date_str = date_dt.strftime("%Y%m%d")
    roc_year = date_dt.year - 1911
    date_roc = f"{roc_year}/{date_dt.month:02d}/{date_dt.day:02d}"
    
    dfs = []
    # 上市
    try:
        r = requests.get(f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={date_str}&type=ALLBUT0999&response=json", timeout=10)
        data = r.json()
        if data['stat'] == 'OK':
            tbl = next((t['data'] for t in data.get('tables', []) if '收盤價' in t['fields']), [])
            if tbl:
                d = pd.DataFrame(tbl).iloc[:, [0, 1, 2, 8, 9, 10]]
                d.columns = ['Code', 'Name', 'Volume', 'Close', 'Sign', 'ChgVal']
                d['Code'] = d['Code'].astype(str) + ".TW"
                dfs.append(d)
    except: pass
    # 上櫃
    try:
        r = requests.get(f"https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&d={date_roc}&s=0,asc,0&o=json", timeout=10)
        data = r.json()
        if 'aaData' in data:
            d = pd.DataFrame(data['aaData']).iloc[:, [0, 1, 8, 2, 3]]
            d.columns = ['Code', 'Name', 'Volume', 'Close', 'ChgVal']
            d['Code'] = d['Code'].astype(str) + ".TWO"
            d['Sign'] = ''
            dfs.append(d)
    except: pass
    # 興櫃
    try:
        r = requests.get(f"https://www.tpex.org.tw/web/emergingstock/historical/daily/EMDaily_result.php?l=zh-tw&d={date_roc}&s=0,asc,0&o=json", timeout=10)
        data = r.json()
        if 'aaData' in data:
            d = pd.DataFrame(data['aaData']).iloc[:, [0, 1, 9, 6, 7]]
            d.columns = ['Code', 'Name', 'Volume', 'Close', 'ChgVal']
            d['Code'] = d['Code'].astype(str) + ".TWO"
            d['Sign'] = ''
            dfs.append(d)
    except: pass

    if not dfs: return None
    
    df_all = pd.concat(dfs, ignore_index=True)
    
    for c in ['Volume', 'Close', 'ChgVal']: df_all[c] = df_all[c].apply(clean_number)
    
    def parse_chg(row):
        v = row['ChgVal']
        s = str(row.get('Sign', ''))
        return -abs(v) if '-' in s or 'green' in s else abs(v)
    
    df_all['ChgAmt'] = df_all.apply(parse_chg, axis=1)
    df_all['Prev'] = df_all['Close'] - df_all['ChgAmt']
    
    def calc_pct(row):
        if row['Prev'] > 0: return (row['ChgAmt'] / row['Prev']) * 100
        return 0.0

    df_all['Daily_Chg%'] = df_all.apply(calc_pct, axis=1)
    df_all['Daily_Amount_B'] = (df_all['Volume'] * df_all['Close']) / 100_000_000
    
    # 補上產業 (使用靜態 Map)
    df_all['Sector'] = '一般'
    for code, sector in HP_SECTOR_MAP.items():
        df_all.loc[df_all['Code'] == code, 'Sector'] = sector
    
    # 標記高價股 (如果不在 Map 裡但也許是興櫃高價)
    df_all.loc[df_all['Code'].isin(HIGH_PRICE_CODES) & (df_all['Sector']=='一般'), 'Sector'] = '高價股'
    
    return df_all[['Code', 'Name', 'Close', 'Daily_Chg%', 'Daily_Amount_B', 'Volume', 'Sector']]

def generate_ai_analysis_placeholder():
    print("\n🚧 [Mark] AI 分析暫停...")
    with open(os.path.join(TARGET_DIR, f"ai_report_{DATE_STR}.json"), "w", encoding="utf-8") as f: json.dump([], f)

# ==========================================
# 4. 主流程
# ==========================================
def fetch_and_process_data():
    fetch_fear_and_greed()
    tw_vix = get_tw_vix_from_taifex()
    
    print("🚀 啟動 V15.0 混合數據引擎...")
    
    # 1. 嘗試 Yahoo API (A計畫)
    df_yahoo = pd.DataFrame()
    try:
        t200 = fetch_yahoo_rankings('turnover', 250)
        c200 = fetch_yahoo_rankings('changeUp', 250)
        targets = list(set(HIGH_PRICE_CODES + list(INDICES_CODES.keys())))
        quotes = fetch_yahoo_quotes(targets)
        df_yahoo = pd.concat([t200, c200, quotes], ignore_index=True)
    except: pass

    df_final = df_yahoo
    
    # 2. 若 Yahoo 失敗，啟動官方救援 (B計畫)
    if df_final.empty or len(df_final) < 50:
        print("❌ Yahoo API 資料不足，切換至官方報表救援...")
        
        d = NOW
        if NOW.hour < 14: d -= datetime.timedelta(days=1)
        
        df_official = None
        for _ in range(5):
            df_official = fetch_official_market(d)
            if df_official is not None and not df_official.empty:
                print(f"   ✅ 官方報表獲取成功: {d.strftime('%Y-%m-%d')}")
                break
            d -= datetime.timedelta(days=1)
            
        if df_official is not None:
            # ✨ [關鍵修正] 使用 yfinance 補抓國際指數 (繞過 Yahoo API 限制)
            print("   🌍 透過 yfinance 補充國際指數 (繞道模式)...")
            try:
                # yfinance 套件使用不同的存取機制，通常較耐封鎖
                yf_tickers = list(INDICES_CODES.keys())
                # 排除 VIXTWN, 它是台股
                yf_tickers = [t for t in yf_tickers if t != "^VIXTWN"]
                
                yf_data = yf.download(yf_tickers, period="5d", progress=False)
                
                idx_rows = []
                for t in yf_tickers:
                    try:
                        # 處理 MultiIndex 或 SingleIndex
                        if len(yf_tickers) > 1: c = yf_data['Close'][t]
                        else: c = yf_data['Close']
                        
                        c = c.dropna()
                        if not c.empty:
                            p = c.iloc[-1]; prev = c.iloc[-2]
                            chg = ((p-prev)/prev)*100
                            name = INDICES_CODES.get(t, t)
                            sector = "市場指數" if "^" in t else "大宗商品"
                            
                            idx_rows.append({
                                "Code": t, "Name": name, "Close": round(p, 2), 
                                "Daily_Chg%": round(chg, 2), "Daily_Amount_B": 0, 
                                "Volume": 0, "Sector": sector
                            })
                    except: continue
                
                if idx_rows:
                    df_official = pd.concat([df_official, pd.DataFrame(idx_rows)], ignore_index=True)
            except Exception as e: print(f"   ⚠️ yfinance 補抓失敗: {e}")
            
            df_final = df_official

    # 3. 補充 VIX
    if tw_vix:
        vix_row = {"Code": "^VIXTWN", "Name": "台指 VIX", "Sector": "波動率", "Close": tw_vix, "Daily_Chg%": 0, "Daily_Amount_B": 0, "Volume": 0}
        df_final = pd.concat([df_final, pd.DataFrame([vix_row])], ignore_index=True)

    # 4. 存檔
    if df_final.empty:
        # 萬一真的全掛，建立空表防止 crash
        STD_COLUMNS = ['Code', 'Name', 'Close', 'Daily_Chg%', 'Daily_Amount_B', 'Volume', 'Sector', 'Industry']
        df_final = pd.DataFrame(columns=STD_COLUMNS)

    df_final['Industry'] = df_final.get('Sector', '其他')
    df_final['Vol_Increase'] = False
    for c in ['RVOL', 'Weekly_Chg%', 'Monthly_Chg%']: df_final[c] = 0
    
    # 漲停美化
    def beautify_limit_up(pct):
        try:
            p = float(pct)
            if p >= 9.90: return 10.00
            if p <= -9.90: return -10.00
            return p
        except: return 0.0
    
    if 'Daily_Chg%' in df_final.columns:
        df_final['Daily_Chg%'] = df_final['Daily_Chg%'].apply(beautify_limit_up)

    csv_path = os.path.join(TARGET_DIR, f"rank_all_{DATE_STR}.csv")
    df_final.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    generate_ai_analysis_placeholder()
    print(f"✅ 數據更新完成: {csv_path} (總筆數: {len(df_final)})")

if __name__ == "__main__":
    fetch_and_process_data()
