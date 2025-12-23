import requests
import pandas as pd
import os
import time
from datetime import datetime, timedelta

# --- 設定區 ---
OUT_DIR = "stock_train/data_txf_5m_daily"  # 資料夾名稱
os.makedirs(OUT_DIR, exist_ok=True)

# FinMind API 設定
FINMIND_KLINE_API = "https://api.finmindtrade.com/api/v4/kline"
TARGET_ID = "TX"  # 台指期代號
START_DATE = "2025-01-01" # 開始日期
# 結束日期設為今天 (避免抓取未來的空資料)
END_DATE = datetime.now().strftime("%Y-%m-%d") 

# 如果有 FinMind Token 請填入，沒有則填 None (大量抓取建議要有)
API_TOKEN = None 

def fetch_one_day_5m(date_str):
    """
    抓取指定「單日」的 5分K 資料
    """
    params = {
        "dataset": "TaiwanFuturesPrice",
        "data_id": TARGET_ID,
        "start_date": date_str,
        "end_date": date_str, # 起始與結束同一天
        "per": "5m",          # 指定週期 5分鐘
    }
    
    headers = {}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"

    try:
        r = requests.get(FINMIND_KLINE_API, params=params, headers=headers)
        data = r.json()
    except Exception as e:
        print(f"❌ {date_str} 請求失敗: {e}")
        return None

    # 檢查是否有資料 (假日或休市會回傳空list)
    if data.get("msg") != "success" or len(data.get("data", [])) == 0:
        return None

    df = pd.DataFrame(data["data"])
    
    # 欄位重新命名與整理
    rename_map = {
        "date": "datetime",
        "open": "open",
        "max": "high",
        "min": "low",
        "close": "close",
        "Trading_Volume": "volume"
    }
    df = df.rename(columns=rename_map)
    
    # 防呆：只留存在的欄位
    cols = ["datetime", "open", "high", "low", "close", "volume"]
    existing_cols = [c for c in cols if c in df.columns]
    df = df[existing_cols]
    
    return df

def main():
    print(f"🚀 開始抓取 {TARGET_ID} 日資料 ({START_DATE} ~ {END_DATE})...")
    
    # 產生日期範圍序列
    date_range = pd.date_range(start=START_DATE, end=END_DATE)
    
    count_saved = 0
    count_skipped = 0

    for dt in date_range:
        date_str = dt.strftime("%Y-%m-%d")
        
        # 簡單過濾：如果是週末(週六=5, 週日=6)，API通常沒資料，但如果有夜盤週六凌晨可能會有資料
        # 這裡我們還是都去問問 API 比較保險，反正沒資料會回傳 None
        
        df = fetch_one_day_5m(date_str)
        
        if df is None or df.empty:
            # 沒資料通常代表是假日或休市
            count_skipped += 1
            # 為了畫面乾淨，假日就不印出來了，或是可以印個 "." 代表跳過
            print(f".", end="", flush=True) 
        else:
            # 有資料 -> 存檔
            out_path = f"{OUT_DIR}/txf_5m_daily.csv"
            df.to_csv(out_path, index=False, encoding="utf-8-sig")
            count_saved += 1
            print(f"\n✔ 已儲存: {date_str} ({len(df)} 根K棒)")

        # 重要：FinMind 若無 Token 限制約每分鐘 60 次，這裡設定延遲
        time.sleep(1.0) 

    print("\n" + "-" * 30)
    print(f"🎉 全部完成！")
    print(f"📂 資料存放於: {OUT_DIR}/")
    print(f"📊 共儲存天數: {count_saved}")
    print(f"💤 跳過天數(假日/無資料): {count_skipped}")

if __name__ == "__main__":
    main()
