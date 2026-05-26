import os
import time
import requests
import pandas as pd
import sqlalchemy
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime, timedelta

# ===========================
# 1. 環境變數與連線設定
# ===========================
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")

if not SUPABASE_DB_URL:
    raise ValueError("❌ 未偵測到 SUPABASE_DB_URL")
if not FINMIND_TOKEN:
    print("⚠️ 未偵測到 FINMIND_TOKEN，將使用免費用戶額度 (可能會有 Rate Limit 限制)")

engine = sqlalchemy.create_engine(SUPABASE_DB_URL, poolclass=NullPool, connect_args={'connect_timeout': 30})

# ===========================
# 2. FinMind 抓取核心函式
# ===========================
def fetch_finmind_price(symbol_pure, start_date_str):
    """向 FinMind 請求特定股票的歷史股價"""
    url = "https://api.finmindtrade.com/api/v4/data"
    parameter = {
        "dataset": "TaiwanStockPrice",
        "data_id": symbol_pure,
        "start_date": start_date_str,
        "token": FINMIND_TOKEN,
    }
    
    try:
        r = requests.get(url, params=parameter, timeout=10)
        data = r.json()
        if data["status"] == 200 and data["data"]:
            df = pd.DataFrame(data["data"])
            # 欄位對齊我們資料庫的格式
            df = df.rename(columns={
                "max": "high",
                "min": "low",
                "Trading_Volume": "volume"
            })
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            return df[['date', 'open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        print(f"   [錯誤] 抓取 {symbol_pure} 失敗: {e}")
        
    return pd.DataFrame()

# ===========================
# 3. 補齊與寫入邏輯
# ===========================
def run_patch():
    print("🔍 [1/3] 開始掃描資料庫中報價落後的股票...")
    
    # 找出最近 30 天內有交易，但「最後更新日期」小於昨天的股票 (通常就是被 Yahoo 漏掉的)
    target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    check_sql = f"""
        SELECT symbol, MAX(date) as last_date
        FROM stock_prices
        GROUP BY symbol
        HAVING MAX(date) >= current_date - INTERVAL '30 days' 
           AND MAX(date) < '{target_date}'
    """
    
    with engine.connect() as conn:
        df_lag = pd.read_sql(text(check_sql), conn)
        
    if df_lag.empty:
        print("✅ 所有股票資料皆為最新，無須補齊！")
        return
        
    print(f"⚠️ 發現 {len(df_lag)} 檔股票資料落後，啟動 FinMind 救援機制...")
    
    all_records = []
    
    # 逐一呼叫 FinMind 補齊
    for index, row in df_lag.iterrows():
        symbol_db = row['symbol']
        last_date = row['last_date']
        
        # 切掉 .TW 或 .TWO 給 FinMind 用 (例如 3374.TWO -> 3374)
        symbol_pure = str(symbol_db).split('.')[0]
        
        # 從最後更新日的「隔天」開始抓
        start_fetch_date = (last_date + timedelta(days=1)).strftime('%Y-%m-%d')
        print(f"   -> 補齊 {symbol_db} (從 {start_fetch_date} 開始)...")
        
        df_new = fetch_finmind_price(symbol_pure, start_fetch_date)
        
        if not df_new.empty:
            # 加回資料庫原本的後綴，確保資料表格式一致
            df_new['symbol'] = symbol_db
            all_records.extend(df_new.to_dict(orient='records'))
            
        # 稍微暫停避免把 API 打掛
        time.sleep(0.1) 
        
    if not all_records:
        print("🤷‍♂️ FinMind 也沒有更新的資料了。")
        return
        
    # ===========================
    # 4. Upsert 寫回資料庫
    # ===========================
    print(f"📤 [3/3] 準備將 {len(all_records)} 筆救援資料寫入資料庫...")
    
    metadata = sqlalchemy.MetaData()
    target_table = sqlalchemy.Table('stock_prices', metadata, autoload_with=engine)
    
    with engine.begin() as conn:
        batch_size = 2000
        for i in range(0, len(all_records), batch_size):
            batch = all_records[i : i + batch_size]
            stmt = insert(target_table).values(batch)
            update_dict = {c.name: c for c in stmt.excluded if c.name not in ['date', 'symbol']}
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=['date', 'symbol'],
                set_=update_dict
            )
            conn.execute(upsert_stmt)
            
    print("✅ FinMind 補齊任務完美結束！請重新執行 etl_strongbuy.py 來更新戰情室。")

if __name__ == "__main__":
    run_patch()
