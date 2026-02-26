import os
import requests
import pandas as pd
import yfinance as yf
import re
import sqlalchemy
import time
import random
from io import StringIO
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert

# ===========================
# 1. 全域配置與連線
# ===========================
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

if not SUPABASE_DB_URL:
    raise RuntimeError("❌ 請設定環境變數 SUPABASE_DB_URL")

# 加上 pool_pre_ping 防止連線中斷
engine = create_engine(SUPABASE_DB_URL, pool_pre_ping=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ===========================
# 2. 通用工具函式
# ===========================
def ensure_primary_key(table_name, unique_cols):
    """確保資料表有 Primary Key，以便執行 Upsert"""
    try:
        with engine.begin() as conn:
            pk_str = ", ".join([f'"{c}"' for c in unique_cols])
            conn.execute(text(f'ALTER TABLE "{table_name}" ADD PRIMARY KEY ({pk_str});'))
    except Exception:
        pass

def upsert_to_supabase(df, table_name, unique_cols):
    """
    使用 PostgreSQL 的 INSERT ON CONFLICT DO UPDATE (Upsert)
    這是最安全的寫入方式，不會誤刪資料。
    """
    if df.empty: return
    
    records = df.to_dict(orient='records')
    metadata = sqlalchemy.MetaData()
    
    try:
        target_table = sqlalchemy.Table(table_name, metadata, autoload_with=engine)
    except sqlalchemy.exc.NoSuchTableError:
        # 表格不存在，直接建立
        df.to_sql(table_name, engine, if_exists='replace', index=False)
        ensure_primary_key(table_name, unique_cols)
        print(f"   ✨ 已建立新表 [{table_name}] 並寫入 {len(records)} 筆")
        return
    
    # 建立 Upsert 語句
    stmt = insert(target_table).values(records)
    # 定義衝突時更新的欄位 (排除 Primary Key)
    update_dict = {c.name: c for c in stmt.excluded if c.name not in unique_cols}
    
    if update_dict:
        on_conflict_stmt = stmt.on_conflict_do_update(index_elements=unique_cols, set_=update_dict)
    else:
        on_conflict_stmt = stmt.on_conflict_do_nothing(index_elements=unique_cols)

    try:
        with engine.begin() as conn:
            conn.execute(on_conflict_stmt)
    except sqlalchemy.exc.ProgrammingError as e:
        if "there is no unique or exclusion constraint" in str(e):
            print(f"   ⚠️ [{table_name}] 缺少 Primary Key，嘗試修復...")
            ensure_primary_key(table_name, unique_cols)
            with engine.begin() as conn:
                conn.execute(on_conflict_stmt)
        else:
            raise e
            
    print(f"   ✅ [{table_name}] Upsert 成功: {len(records)} 筆")

# ===========================
# 3. 模組 A: 股票清單
# ===========================
def fetch_market_data_with_retry(url, retries=3):
    for i in range(retries):
        try:
            res = requests.get(url, headers=HEADERS, timeout=45)
            if res.status_code == 200:
                res.encoding = 'cp950'
                return res.text
        except Exception as e:
            print(f"      ⚠️ 連線失敗 ({i+1}/{retries}): {e}")
            time.sleep(random.uniform(3, 5))
    return None

def sync_stock_info():
    print("\n🚀 [1/2] 更新股票代號與產業分類...")
    all_data = []
    configs = [("上市", 2, ".TW"), ("上櫃", 4, ".TWO"), ("興櫃", 5, ".TWO")]

    for market_name, mode, suffix in configs:
        print(f"   📡 正在抓取 {market_name} ...")
        url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}"
        
        html_text = fetch_market_data_with_retry(url)
        if not html_text:
            print(f"   ❌ {market_name} 下載失敗")
            continue

        try:
            dfs = pd.read_html(StringIO(html_text), header=0)
            if not dfs: continue
            df = dfs[0]
            
            count = 0
            
            for _, row in df.iterrows():
                try:
                    raw_str = str(row.iloc[0]).strip()
                    parts = re.split(r'[\s\u3000]+', raw_str, maxsplit=1)
                    
                    if len(parts) >= 2:
                        code = parts[0].strip()
                        name = parts[1].strip()
                        
                        if re.match(r'^\d{4,6}$', code): 
                            industry = '其他'
                            try:
                                if len(row) > 4:
                                    ind_val = str(row.iloc[4]).strip()
                                    if ind_val and ind_val.lower() != 'nan':
                                        industry = ind_val
                            except:
                                pass
                            
                            if code.startswith('00'):
                                industry = 'ETF'

                            all_data.append({
                                'symbol': f"{code}{suffix}",
                                'name': name,
                                'industry': industry
                            })
                            count += 1
                except Exception:
                    continue
                
            print(f"      ✅ 取得 {count} 筆")
            
        except Exception as e:
            print(f"   ❌ {market_name} 解析失敗: {e}")
        
        time.sleep(random.uniform(2, 4))

    if len(all_data) < 1000:
        print(f"\n🛑 [危險] 抓取數量過少 ({len(all_data)} 筆)，跳過更新。")
        try:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT symbol FROM stock_info"))
                return [r[0] for r in res]
        except: 
            return []

    if all_data:
        df_info = pd.DataFrame(all_data).drop_duplicates(subset=['symbol'])
        print(f"   💾 寫入資料庫: 共 {len(df_info)} 筆...")
        upsert_to_supabase(df_info, 'stock_info', ['symbol'])
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE INDEX IF NOT EXISTS idx_stock_info_symbol ON stock_info (symbol)"))
        except: pass
        print(f"   ✅ stock_info 更新完成")
        return df_info['symbol'].tolist()
    else:
        return []

# ===========================
# 4. 模組 B: 日 K 股價 (盤中防呆版)
# ===========================
def sync_daily_prices(symbols):
    print("\n🚀 [2/2] 下載最新股價 (yfinance)...")
    if not symbols:
        print("   ⚠️ 無股票代號，略過更新")
        return

    try:
        chunk_size = 500
        total_inserted = 0

        # 強制抓取最近 5 天，確保涵蓋跨時區的「今天」
        for i in range(0, len(symbols), chunk_size):
            batch = symbols[i:i+chunk_size]
            print(f"   📡 下載進度 {i}/{len(symbols)}...", end="\r")

            data = yf.download(batch, period="5d", progress=False, threads=True, auto_adjust=False)

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

            # 🔥 關鍵：只剔除沒有收盤價的廢資料，若成交量為空則補 0，不整筆刪除
            df_upload.dropna(subset=['close'], inplace=True)
            df_upload.fillna(0, inplace=True)

            # Upsert 寫入 (相同日期與代號自動覆蓋最新盤中報價)
            upsert_to_supabase(df_upload, 'stock_prices', ['date', 'symbol'])

            total_inserted += len(df_upload)

        print(f"\n   ✅ 股價更新完成 (共處理 {total_inserted} 筆數據)")

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

    # 1. 更新股票清單
    symbols = sync_stock_info()
    
    # 🔥 剛剛被漏掉的最關鍵一行：
    # 2. 下載股價
    sync_daily_prices(symbols)
    
    print("\n🎉 基礎資料更新完成！")
