import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import os
import datetime

# ==========================================
# 0. 設定與目錄準備
# ==========================================
# 取得今日日期與路徑資訊
NOW = datetime.datetime.now()
YYYY = NOW.strftime("%Y")
MM = NOW.strftime("%m")
DATE_STR = NOW.strftime("%Y%m%d")

# 定義根目錄與目標目錄: us_stock_dashboard/2026/01
BASE_DIR = "us_stock_dashboard"
TARGET_DIR = os.path.join(BASE_DIR, YYYY, MM)

# 確保目錄存在
os.makedirs(TARGET_DIR, exist_ok=True)

print(f"📂 目標資料夾: {TARGET_DIR}")
print(f"📅 處理日期: {DATE_STR}")

# ==========================================
# 1. 股票基本資料設定
# ==========================================
TICKER_INFO = {
    # --- 科技巨頭 ---
    "NVDA": {"Name": "NVIDIA", "Theme": "AI 龍頭"},
    "MSFT": {"Name": "Microsoft", "Theme": "軟體/雲端"},
    "AAPL": {"Name": "Apple", "Theme": "消費電子"},
    "AMZN": {"Name": "Amazon", "Theme": "電商/AWS"},
    "GOOG": {"Name": "Alphabet", "Theme": "搜尋引擎"},
    "META": {"Name": "Meta", "Theme": "社群/廣告"},
    "TSLA": {"Name": "Tesla", "Theme": "電動車"},
    
    # --- 半導體 ---
    "TSM":  {"Name": "TSMC", "Theme": "晶圓代工"},
    "AVGO": {"Name": "Broadcom", "Theme": "網通/ASIC"},
    "AMD":  {"Name": "AMD", "Theme": "CPU/GPU"},
    "INTC": {"Name": "Intel", "Theme": "半導體"},
    "MU":   {"Name": "Micron", "Theme": "記憶體"},
    "QCOM": {"Name": "Qualcomm", "Theme": "手機晶片"},
    "TXN":  {"Name": "Texas Inst", "Theme": "類比IC"},
    "AMAT": {"Name": "Applied Mat", "Theme": "設備"},
    "LRCX": {"Name": "Lam Research", "Theme": "設備"},
    "SMCI": {"Name": "Super Micro", "Theme": "伺服器"},
    
    # --- 軟體/資安/金融 ---
    "ORCL": {"Name": "Oracle", "Theme": "資料庫"},
    "ADBE": {"Name": "Adobe", "Theme": "創意軟體"},
    "CRM":  {"Name": "Salesforce", "Theme": "CRM"},
    "CRWD": {"Name": "CrowdStrike", "Theme": "資安"},
    "PLTR": {"Name": "Palantir", "Theme": "大數據/AI"},
    "PANW": {"Name": "Palo Alto", "Theme": "資安"},
    "JPM":  {"Name": "JPMorgan", "Theme": "銀行龍頭"},
    "V":    {"Name": "Visa", "Theme": "支付"},
    "MA":   {"Name": "Mastercard", "Theme": "支付"},
    "PYPL": {"Name": "PayPal", "Theme": "支付"},
    "COIN": {"Name": "Coinbase", "Theme": "加密交易所"},
    "MSTR": {"Name": "MicroStrategy", "Theme": "比特幣持倉"},

    # --- 傳統/消費/其他 ---
    "WMT":  {"Name": "Walmart", "Theme": "零售龍頭"},
    "COST": {"Name": "Costco", "Theme": "量販"},
    "LLY":  {"Name": "Eli Lilly", "Theme": "減肥藥"},
    "JNJ":  {"Name": "J&J", "Theme": "醫療保健"},
    "NFLX": {"Name": "Netflix", "Theme": "串流"},
    "DIS":  {"Name": "Disney", "Theme": "娛樂"},
    "XOM":  {"Name": "Exxon Mobil", "Theme": "石油"},
    
    # --- 指數 ---
    "BTC-USD": {"Name": "Bitcoin", "Theme": "加密貨幣"},
    "^VIX":    {"Name": "VIX Index", "Theme": "恐慌指數"}
}

ALL_TICKERS = list(TICKER_INFO.keys())

def fetch_fear_and_greed():
    """ 抓取 CNN 恐懼與貪婪指數 """
    print("正在抓取 CNN Fear & Greed 指數...")
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            latest_data = data['fear_and_greed']
            score = int(latest_data['score'])
            rating = latest_data['rating']
            timestamp = latest_data['timestamp']
            
            result = {
                "score": score,
                "rating": rating,
                "timestamp": timestamp
            }
            
            # 存檔路徑：加上日期後綴，並存入目標資料夾
            filename = f"sentiment_{DATE_STR}.json"
            filepath = os.path.join(TARGET_DIR, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=4)
            
            print(f"✅ CNN 指數已存檔: {filepath}")
            return result
        else:
            print(f"⚠️ CNN API 回傳錯誤: {response.status_code}")
            return None
    except Exception as e:
        print(f"⚠️ CNN 指數抓取失敗: {e}")
        # 失敗時的預設檔案
        default_data = {"score": 50, "rating": "Neutral (Data N/A)", "timestamp": ""}
        filename = f"sentiment_{DATE_STR}.json"
        filepath = os.path.join(TARGET_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(default_data, f)
        return None

def fetch_and_process_data():
    fetch_fear_and_greed()
    
    print(f"正在下載 {len(ALL_TICKERS)} 檔標的數據 (範圍: 3個月)...")
    
    try:
        data = yf.download(ALL_TICKERS, period="3mo", progress=False, auto_adjust=False)
        
        results = []

        for ticker in ALL_TICKERS:
            try:
                closes = data['Close'][ticker].dropna()
                try:
                    volumes = data['Volume'][ticker].dropna()
                except KeyError:
                    volumes = pd.Series()

                if closes.empty: continue
                
                current_price = closes.iloc[-1]
                current_vol = 0 if volumes.empty else volumes.iloc[-1]
                
                def calc_dynamic_change(series, shift_count):
                    if len(series) > shift_count:
                        last_val = series.iloc[-1]
                        prev_val = series.iloc[-(shift_count + 1)]
                        if prev_val == 0: return 0.0
                        return ((last_val - prev_val) / prev_val) * 100
                    return 0.0

                daily_chg = calc_dynamic_change(closes, 1)
                weekly_chg = calc_dynamic_change(closes, 5)
                monthly_chg = calc_dynamic_change(closes, 21)
                amount_b = (current_price * current_vol) / 1_000_000_000
                info = TICKER_INFO.get(ticker, {"Name": ticker, "Theme": "N/A"})

                results.append({
                    "Code": ticker,
                    "Name": info['Name'],
                    "Theme": info['Theme'],
                    "Close": round(current_price, 2),
                    "Volume": current_vol,
                    "Daily_Chg%": round(daily_chg, 2),
                    "Daily_Amount_B": round(amount_b, 2),
                    "Weekly_Chg%": round(weekly_chg, 2),
                    "Weekly_Amount_B": round(amount_b, 2),
                    "Monthly_Chg%": round(monthly_chg, 2),
                    "Monthly_Amount_B": round(amount_b, 2)
                })

            except Exception as e:
                continue

        df_result = pd.DataFrame(results)
        
        # 定義輸出的三個 CSV 檔名 (含日期)
        csv_files = [
            f"rank_daily_{DATE_STR}.csv",
            f"rank_weekly_{DATE_STR}.csv",
            f"rank_monthly_{DATE_STR}.csv"
        ]
        
        for fname in csv_files:
            filepath = os.path.join(TARGET_DIR, fname)
            df_result.to_csv(filepath, index=False, encoding='utf-8-sig')
            print(f"已儲存: {filepath}")

        print(f"\n✅ 數據更新完成！所有檔案已歸檔至: {TARGET_DIR}")
        
    except Exception as e:
        print(f"下載流程錯誤: {e}")

if __name__ == "__main__":
    fetch_and_process_data()
