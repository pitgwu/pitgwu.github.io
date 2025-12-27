import pandas as pd
import yfinance as yf
import requests
import os
import io
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# ================= 設定區 =================
OUT_DIR = "stock_train/data_2025_yfinance"
# 確保目錄存在且乾淨
#if os.path.exists(OUT_DIR):
#    shutil.rmtree(OUT_DIR)
#os.makedirs(OUT_DIR, exist_ok=True)

SUFFIX_TWSE = ".TW"
SUFFIX_TPEX = ".TWO"
MAX_WORKERS = 4 # 稍微降低線程數以求穩定

def debug_yfinance_structure():
    """
    診斷函式：先抓一檔股票看看到底發生什麼事
    """
    print("🔍 正在進行單檔資料結構診斷 (2330.TW)...")
    try:
        # 故意不加 multi_level_index 參數，看看原始回傳長怎樣
        df = yf.download("2330.TW", start="2025-01-01", progress=False, auto_adjust=False)
        
        print(f"📥 下載狀況: {'空資料' if df.empty else '有資料'}")
        print(f"📋 原始欄位: {df.columns}")
        
        if not df.empty:
            # 測試是否為 MultiIndex
            if isinstance(df.columns, pd.MultiIndex):
                print("⚠️ 偵測到 MultiIndex (多層欄位)，將自動攤平。")
                df.columns = df.columns.get_level_values(0)
                print(f"📋 攤平後欄位: {df.columns}")
            
            print("✅ 診斷完成，準備開始批量下載...\n")
            return True
        else:
            print("❌ 診斷失敗：Yahoo 回傳空資料，可能是 IP 暫時被擋或參數錯誤。")
            return False
            
    except Exception as e:
        print(f"❌ 診斷發生錯誤: {e}")
        return False

def get_stock_list_from_official():
    print("正在從證交所/櫃買中心網頁爬取股票清單...")
    stock_list = []
    
    tasks = [
        ("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", SUFFIX_TWSE),
        ("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4", SUFFIX_TPEX)
    ]

    try:
        for url, suffix in tasks:
            res = requests.get(url)
            res.encoding = 'big5'
            dfs = pd.read_html(io.StringIO(res.text), header=0)
            if not dfs: continue
            df = dfs[0]
            
            if "CFICode" not in df.columns or "有價證券代號及名稱" not in df.columns: continue
            
            df_stocks = df[df["CFICode"] == "ESVUFR"].copy()
            
            for code_name in df_stocks["有價證券代號及名稱"]:
                raw_code = str(code_name).split()[0].strip()
                # 修正 SyntaxWarning: 使用 r'' 原始字串
                if re.match(r'^\d{4}$', raw_code):
                    stock_list.append(f"{raw_code}{suffix}")
                    
        print(f"✔ 成功取得股票清單，共 {len(stock_list)} 檔。")
        return stock_list

    except Exception as e:
        print(f"❌ 爬取清單失敗: {e}")
        return []

def get_market_calendar_yf():
    try:
        # 這裡加入 explicit 參數確保格式
        df = yf.download("2330.TW", start="2025-01-01", progress=False, auto_adjust=False)
        if df.empty: return None
        return pd.DatetimeIndex(df.index).sort_values()
    except Exception:
        return None

def fetch_and_process_one(ticker, market_calendar):
    try:
        # 核心修改：移除 multi_level_index=False (有些舊版 yfinance 不支援)
        # 改用手動判斷處理，相容性最高
        df = yf.download(ticker, start="2025-01-01", progress=False, auto_adjust=False)
        
        if df.empty: return None

        # 1. 處理 MultiIndex (關鍵修復)
        # 如果欄位是 ('Open', '2330.TW') 這種格式，強制只取第一層 'Open'
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 2. 欄位重新命名 (容錯處理：先轉小寫再比對)
        # 將所有欄位轉為小寫 (Open -> open, HIGH -> high)
        df.columns = [c.lower() for c in df.columns]
        
        # 檢查必要欄位
        cols = ["open", "high", "low", "close", "volume"]
        if not all(col in df.columns for col in cols):
            # 如果欄位不對，回傳 None (這就是之前失敗的原因)
            return None
            
        df = df[cols]

        # 3. 對齊與補值
        df = df.reindex(market_calendar)
        df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].ffill().bfill()
        df["volume"] = df["volume"].fillna(0)

        stock_id_only = ticker.replace(".TW", "").replace(".TWO", "")
        
        # 最終防呆檢查
        if not re.match(r'^\d{4}$', stock_id_only): return None

        out_path = f"{OUT_DIR}/{stock_id_only}.csv"
        df.reset_index().rename(columns={"index": "date"}).to_csv(
            out_path, index=False, date_format='%Y-%m-%d', encoding="utf-8-sig"
        )
        return stock_id_only

    except Exception:
        return None

def main():
    # 0. 先執行自我診斷
    if not debug_yfinance_structure():
        print("程式終止：無法取得基礎資料。")
        return

    all_tickers = get_stock_list_from_official()
    market_calendar = get_market_calendar_yf()
    
    if not all_tickers or market_calendar is None:
        return

    total_stocks = len(all_tickers)
    print(f"🚀 開始下載 {total_stocks} 檔股票...")

    success_count = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_and_process_one, ticker, market_calendar): ticker for ticker in all_tickers}
        
        with tqdm(total=total_stocks, desc="下載進度", unit="檔") as pbar:
            for future in as_completed(futures):
                if future.result():
                    success_count += 1
                pbar.update(1)

    print(f"\n✅ 全部完成！成功下載: {success_count} / {total_stocks}")
    print(f"檔案已儲存至: {OUT_DIR}")

if __name__ == "__main__":
    main()
