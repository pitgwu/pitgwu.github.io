import os
import requests
import pandas as pd
import yfinance as yf
import re
import sqlalchemy
import time
import random
import concurrent.futures
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
    """
    if df.empty: return
    
    records = df.to_dict(orient='records')
    metadata = sqlalchemy.MetaData()
    
    try:
        target_table = sqlalchemy.Table(table_name, metadata, autoload_with=engine)
    except sqlalchemy.exc.NoSuchTableError:
        df.to_sql(table_name, engine, if_exists='replace', index=False)
        ensure_primary_key(table_name, unique_cols)
        print(f"   ✨ 已建立新表 [{table_name}] 並寫入 {len(records)} 筆")
        return
    
    stmt = insert(target_table).values(records)
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
    print("\n🚀 [1/3] 更新股票代號與產業分類...")
    all_data = []
    configs = [("上市", 2, ".TW"), ("上櫃", 4, ".TWO"), ("興櫃", 5, ".TWO")]

    for market_name, mode, suffix in configs:
        print(f"   📡 正在抓取 {market_name} ...")
        url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}"
        
        html_text = fetch_market_data_with_retry(url)
        if not html_text: continue

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
                            except: pass
                            
                            if code.startswith('00'): industry = 'ETF'

                            all_data.append({'symbol': f"{code}{suffix}", 'name': name, 'industry': industry})
                            count += 1
                except Exception: continue
                
            print(f"      ✅ 取得 {count} 筆")
        except Exception as e:
            print(f"   ❌ {market_name} 解析失敗: {e}")
        time.sleep(random.uniform(2, 4))

    if all_data:
        df_info = pd.DataFrame(all_data).drop_duplicates(subset=['symbol'])
        upsert_to_supabase(df_info, 'stock_info', ['symbol'])
        return df_info['symbol'].tolist()
    return []

# ===========================
# 4. 模組 B: 日 K 股價 (yfinance 歷史批量)
# ===========================
def sync_daily_prices(symbols):
    print("\n🚀 [2/3] 下載歷史與最新股價 (yfinance)...")
    if not symbols: return

    try:
        chunk_size = 500
        total_inserted = 0

        for i in range(0, len(symbols), chunk_size):
            batch = symbols[i:i+chunk_size]
            print(f"   📡 下載進度 {i}/{len(symbols)}...", end="\r")

            data = yf.download(batch, period="5d", progress=False, threads=True, auto_adjust=False)

            if data.empty: continue

            if isinstance(data.columns, pd.MultiIndex):
                # 解決新舊版 yfinance Ticker 層級位置不同的 Bug
                if 'Ticker' in data.columns.names:
                    ticker_level = data.columns.names.index('Ticker')
                    data = data.stack(level=ticker_level).reset_index()
                else:
                    data = data.stack(level=1).reset_index()
                
                rename_map = {col: 'symbol' if str(col).lower() == 'ticker' else 'date' if str(col).lower() == 'date' else col for col in data.columns}
                data.rename(columns=rename_map, inplace=True)
            else:
                data = data.reset_index()
                data.rename(columns={col: 'date' for col in data.columns if str(col).lower() == 'date'}, inplace=True)
                if 'symbol' not in data.columns: data['symbol'] = batch[0]

            data.columns = [str(c).lower() for c in data.columns]
            req_cols = ['date', 'symbol', 'open', 'high', 'low', 'close', 'volume']
            if not set(req_cols).issubset(data.columns): continue

            df_upload = data[req_cols].copy()
            df_upload['date'] = pd.to_datetime(df_upload['date']).dt.strftime('%Y-%m-%d')
            df_upload.dropna(subset=['close'], inplace=True)
            df_upload.fillna(0, inplace=True)

            upsert_to_supabase(df_upload, 'stock_prices', ['date', 'symbol'])
            total_inserted += len(df_upload)

        print(f"\n   ✅ yfinance 股價更新完成 (共處理 {total_inserted} 筆數據)")
    except Exception as e:
        print(f"   ❌ yfinance 下載錯誤: {e}")

# ===========================
# 5. 模組 C: 台股官方 API 補齊防呆機制 (🔥 解決 5536* 漏抓的終極武器)
# ===========================
def patch_today_prices_via_twse(symbols):
    print("\n🚀 [3/3] 啟動台股防呆機制：補齊 yfinance 漏抓的今日精準報價...")
    if not symbols: return

    codes = []
    symbol_map = {}
    for sym in symbols:
        code = sym.split('.')[0]
        codes.append(code)
        symbol_map[code] = sym

    BATCH_SIZE = 70
    batches = [codes[i:i + BATCH_SIZE] for i in range(0, len(codes), BATCH_SIZE)]
    all_records = []
    
    def fetch_twse(batch):
        q = [f"tse_{c}.tw" for c in batch] + [f"otc_{c}.tw" for c in batch]
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={'|'.join(q)}"
        try:
            res = requests.get(url, timeout=5).json()
            return res.get('msgArray', [])
        except Exception:
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_twse, batch): batch for batch in batches}
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            for item in future.result():
                code = item.get('c')
                z = item.get('z')
                if not z or z == '-': continue # 排除沒開盤或無成交的股票
                
                try:
                    date_str = item.get('d') # '20260415'
                    if not date_str: continue
                    date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                    
                    price = float(str(z).replace(',', ''))
                    open_p = float(str(item.get('o')).replace(',', '')) if item.get('o') != '-' else price
                    high_p = float(str(item.get('h')).replace(',', '')) if item.get('h') != '-' else price
                    low_p = float(str(item.get('l')).replace(',', '')) if item.get('l') != '-' else price
                    vol = int(str(item.get('v')).replace(',', '')) if item.get('v') != '-' else 0
                    
                    db_symbol = symbol_map.get(code)
                    if db_symbol:
                        all_records.append({
                            'date': date_fmt,
                            'symbol': db_symbol,
                            'open': open_p,
                            'high': high_p,
                            'low': low_p,
                            'close': price,
                            'volume': vol * 1000  # 官方API回傳為「張」，需轉換為「股」
                        })
                except Exception: pass
            
            completed += 1
            print(f"   📡 防呆補齊進度 {completed}/{len(batches)}...", end="\r")

    if all_records:
        df_patch = pd.DataFrame(all_records)
        df_patch.drop_duplicates(subset=['date', 'symbol'], inplace=True)
        print(f"\n   💾 寫入官方精準校正報價: 共 {len(df_patch)} 筆")
        # 利用 Upsert 機制，把今日最新正確的價格強制覆寫上去
        upsert_to_supabase(df_patch, 'stock_prices', ['date', 'symbol'])
    else:
        print("\n   ⚠️ 無法取得今日校正報價")

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
    
    # 2. 下載歷史股價 (yfinance 大量且快速，但可能漏接)
    sync_daily_prices(symbols)
    
    # 3. 官方防呆補齊 (強制補齊今日最新報價)
    patch_today_prices_via_twse(symbols)
    
    print("\n🎉 基礎資料更新完成！")
