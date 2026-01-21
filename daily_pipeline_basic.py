import os
import requests
import pandas as pd
import yfinance as yf
import re
import sqlalchemy
from io import StringIO
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert

# ===========================
# 1. 全域配置與連線
# ===========================
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

if not SUPABASE_DB_URL:
    raise RuntimeError("❌ 請設定環境變數 SUPABASE_DB_URL")

engine = create_engine(SUPABASE_DB_URL)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ===========================
# 2. 通用工具函式
# ===========================
def ensure_primary_key(table_name, unique_cols):
    try:
        with engine.begin() as conn:
            pk_str = ", ".join([f'"{c}"' for c in unique_cols])
            conn.execute(text(f'ALTER TABLE "{table_name}" ADD PRIMARY KEY ({pk_str});'))
    except Exception:
        pass

def upsert_to_supabase(df, table_name, unique_cols):
    if df.empty: return
    records = df.to_dict(orient='records')
    metadata = sqlalchemy.MetaData()
    try:
        target_table = sqlalchemy.Table(table_name, metadata, autoload_with=engine)
    except sqlalchemy.exc.NoSuchTableError:
        df.to_sql(table_name, engine, if_exists='replace', index=False)
        ensure_primary_key(table_name, unique_cols)
        return

    stmt = insert(target_table).values(records)
    update_dict = {c.name: c for c in stmt.excluded if c.name not in unique_cols}
    on_conflict_stmt = stmt.on_conflict_do_update(index_elements=unique_cols, set_=update_dict) if update_dict else stmt.on_conflict_do_nothing(index_elements=unique_cols)

    try:
        with engine.begin() as conn:
            conn.execute(on_conflict_stmt)
    except sqlalchemy.exc.ProgrammingError as e:
        if "there is no unique or exclusion constraint" in str(e):
            ensure_primary_key(table_name, unique_cols)
            with engine.begin() as conn:
                conn.execute(on_conflict_stmt)
        else:
            raise e
    print(f"   ✅ [{table_name}] 更新 {len(records)} 筆")

def simple_upsert(df, table_name, chunk_size=1000):
    if df.empty: return
    if 'date' in df.columns:
        target_dates = df['date'].unique()
        date_list = "', '".join([str(d) for d in target_dates])
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {table_name} WHERE date IN ('{date_list}')"))
    df.to_sql(table_name, engine, if_exists='append', index=False, chunksize=chunk_size, method='multi')
    print(f"   ✅ [{table_name}] 寫入 {len(df)} 筆")

# ===========================
# 3. 核心功能
# ===========================
def sync_stock_info():
    print("\n🚀 [1/2] 更新股票代號與產業分類...")
    all_data = []
    configs = [("上市", 2, ".TW"), ("上櫃", 4, ".TWO"), ("興櫃", 5, ".TWO")]

    for market_name, mode, suffix in configs:
        url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=30)
            res.encoding = 'cp950'
            dfs = pd.read_html(StringIO(res.text), header=0)
            if not dfs: continue
            df = dfs[0]
            for _, row in df.iterrows():
                try:
                    raw_str = str(row.iloc[0]).strip()
                    industry = str(row.iloc[4]).strip()
                    parts = re.split(r'[\s\u3000]+', raw_str, maxsplit=1)
                    if len(parts) >= 2:
                        code = parts[0].strip()
                        name = parts[1].strip()
                        if re.match(r'^\d{4}$', code):
                            if industry == 'nan' or not industry: industry = '其他'
                            all_data.append({'symbol': f"{code}{suffix}", 'name': name, 'industry': industry})
                except: continue
        except Exception as e:
            print(f"   ❌ {market_name} 下載失敗: {e}")

    if all_data:
        df_info = pd.DataFrame(all_data).drop_duplicates(subset=['symbol'])
        df_info.to_sql('stock_info', engine, if_exists='replace', index=False)
        ensure_primary_key('stock_info', ['symbol'])
        with engine.begin() as conn:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_stock_info_symbol ON stock_info (symbol)"))
        print(f"   ✅ 已更新 {len(df_info)} 檔股票資訊")
        return df_info['symbol'].tolist()
    else:
        return []

def sync_daily_prices(symbols):
    print("\n🚀 [2/2] 下載最新股價 (yfinance)...")
    if not symbols: return
    try:
        chunk_size = 500
        total_inserted = 0
        for i in range(0, len(symbols), chunk_size):
            batch = symbols[i:i+chunk_size]
            print(f"   📡 下載進度 {i}/{len(symbols)}...", end="\r")
            data = yf.download(batch, period="2d", progress=False, threads=True, auto_adjust=False)
            if data.empty: continue
            
            if isinstance(data.columns, pd.MultiIndex):
                data = data.stack(level=1).reset_index()
                data.rename(columns={'Ticker': 'symbol', 'Date': 'date'}, inplace=True)
            else:
                data = data.reset_index()
            
            data.columns = [str(c).lower() for c in data.columns]
            req_cols = ['date', 'symbol', 'open', 'high', 'low', 'close', 'volume']
            if not set(req_cols).issubset(data.columns): continue

            df_upload = data[req_cols].copy()
            df_upload['date'] = pd.to_datetime(df_upload['date']).dt.strftime('%Y-%m-%d')
            df_upload.dropna(inplace=True)
            simple_upsert(df_upload, 'stock_prices')
            total_inserted += len(df_upload)
        print(f"\n   ✅ 股價更新完成 (共更新 {total_inserted} 筆)")
    except Exception as e:
        print(f"   ❌ 股價下載錯誤: {e}")

# ===========================
# 主程式
# ===========================
if __name__ == "__main__":
    print("="*60)
    print(f"📅 基礎資料更新 (Basic Pipeline)")
    print(f"⏰ 時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    symbols = sync_stock_info()
    
    if not symbols:
        try:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT symbol FROM stock_info"))
                symbols = [r[0] for r in res]
        except:
            print("❌ 無法取得股票代號，程式終止")
            exit(1)

    sync_daily_prices(symbols)
    print("\n🎉 基礎資料更新完成！")
