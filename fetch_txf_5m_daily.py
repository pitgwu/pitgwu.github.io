import yfinance as yf
import pandas as pd
import os
from datetime import datetime
import pytz

# --- 設定區 ---
OUT_DIR = "stock_train/data_txf_5m_daily"
os.makedirs(OUT_DIR, exist_ok=True)

# 標的：加權指數
SYMBOL = "^TWII" 

def fetch_today_5m():
    # 取得台灣今天的日期字串 (例如: 2025-12-22)
    tw_tz = pytz.timezone("Asia/Taipei")
    today_date = datetime.now(tw_tz).date()
    today_str = today_date.strftime("%Y-%m-%d")

    print(f"🚀 正在檢查 {SYMBOL} 今日 ({today_str}) 的 5分K 資料...")

    try:
        # 下載最近 1 天的資料
        # valid_ranges: 1d, 5d, 1mo... 
        df = yf.download(
            tickers=SYMBOL, 
            period="1d",      # 只抓最近一天
            interval="5m",    # 5分鐘頻率
            progress=False, 
            auto_adjust=False, 
            multi_level_index=False
        )
        
        if df.empty:
            print(f"⚠ 無資料回傳 (可能尚未開盤或今日休市)。")
            return

        # --- 欄位清洗 (處理 yfinance 的格式問題) ---
        # 1. 如果是 MultiIndex，只取第一層
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # 2. 處理時區 -> 轉為台灣時間
        if df.index.tz is not None:
            df.index = df.index.tz_convert("Asia/Taipei")
        else:
            df.index = df.index.tz_localize("UTC").tz_convert("Asia/Taipei")

        # 3. 重置索引
        df = df.reset_index()
        
        # 4. 欄位轉小寫並改名
        df.columns = [str(c).lower() for c in df.columns]
        df = df.rename(columns={"date": "datetime"})
        
        # 5. 只留需要的欄位
        req_cols = ["datetime", "open", "high", "low", "close", "volume"]
        final_cols = [c for c in req_cols if c in df.columns]
        df = df[final_cols]

        # --- 嚴格篩選：確保資料屬於「今天」 ---
        # 雖然 period='1d'，但如果早上8點跑，Yahoo 可能回傳昨天的資料
        # 所以這裡要再過濾一次
        df["date_check"] = df["datetime"].dt.date
        df_today = df[df["date_check"] == today_date].copy()
        
        # 移除輔助欄位
        df_today = df_today.drop(columns=["date_check"])

        if df_today.empty:
            print(f"⚠ 下載成功，但資料日期不是今天 ({today_str})。可能是昨日資料或尚未開盤。")
            # 如果你想看它是哪一天的，可以打開下面這行：
            # print(f"   (抓到的資料日期是: {df['datetime'].dt.date.iloc[0]})")
            return

        # --- 存檔 ---
        out_path = f"{OUT_DIR}/txf_5m_daily.csv"
        df_today.to_csv(out_path, index=False, encoding="utf-8-sig")
        
        print(f"✔ 成功儲存今日資料！")
        print(f"📂 檔案路徑: {out_path}")
        print(f"📊 資料筆數: {len(df_today)} 根K棒")
        print(f"🕒 最後一筆時間: {df_today.iloc[-1]['datetime']}")

    except Exception as e:
        print(f"❌ 發生錯誤: {e}")

if __name__ == "__main__":
    fetch_today_5m()
