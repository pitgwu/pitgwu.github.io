import os
import requests
import pandas as pd
import sqlalchemy
import time
import random
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert

# ===========================
# 1. 配置與連線
# ===========================
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

if not SUPABASE_DB_URL:
    raise RuntimeError("❌ 請設定環境變數 SUPABASE_DB_URL")

engine = create_engine(SUPABASE_DB_URL)

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
        print(f"   ✨ 表格 {table_name} 不存在，初次建立中...")
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
    print(f"   ✅ [{table_name}] 成功寫入/更新 {len(records)} 筆資料")

def clean_number(x):
    if isinstance(x, (int, float)): return x
    try:
        val_str = str(x).replace(',', '').strip()
        if val_str == '' or val_str == '--': return 0
        return int(float(val_str))
    except: return 0

# ===========================
# 3. 核心功能模組 (法人)
# ===========================

# --- A. 抓取上市法人 (精確版) ---
def fetch_twse_institutional(date_str):
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALL&response=json"
    try:
        res = requests.get(url, timeout=15)
        try: data = res.json()
        except: return pd.DataFrame()
        
        if data.get('stat') != 'OK':
            return pd.DataFrame()
        
        cols = data['fields']
        df = pd.DataFrame(data['data'], columns=cols)
        rename_map = {}
        
        # 精確對映邏輯
        for col in cols:
            if '外陸資' in col and '買賣超' in col: rename_map[col] = 'foreign_net'
            elif '投信' in col and '買賣超' in col: rename_map[col] = 'trust_net'
            elif '自營商' in col and '買賣超' in col:
                if '自行' not in col and '避險' not in col and '外資' not in col:
                    rename_map[col] = 'dealer_net'
            elif '證券代號' in col: rename_map[col] = 'symbol'
            elif '證券名稱' in col: rename_map[col] = 'name'

        required = ['symbol', 'name', 'foreign_net', 'trust_net', 'dealer_net']
        if not all(k in rename_map.values() for k in required):
            return pd.DataFrame()

        df = df.rename(columns=rename_map)
        df = df.loc[:, ~df.columns.duplicated()] 
        df = df[required]
        df['symbol'] = df['symbol'].apply(lambda x: f"{x}.TW")
        return df
    except Exception as e:
        print(f"   ❌ 上市抓取例外: {e}")
        return pd.DataFrame()

# --- B. 抓取上櫃法人 ---
def fetch_tpex_institutional(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y%m%d")
        minguo_date = f"{dt.year-1911}/{dt.month:02d}/{dt.day:02d}"
    except: return pd.DataFrame()
    
    url = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={minguo_date}"
    try:
        res = requests.get(url, timeout=15)
        try: data = res.json()
        except: return pd.DataFrame()

        if not data.get('aaData'): return pd.DataFrame()
        
        df = pd.DataFrame(data['aaData'])
        if df.shape[1] > 10:
            df = df.iloc[:, [0, 1, 2, 5, 8]] 
            df.columns = ['symbol', 'name', 'foreign_net', 'trust_net', 'dealer_net']
            df['symbol'] = df['symbol'].apply(lambda x: f"{x}.TWO")
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"   ❌ 上櫃抓取例外: {e}")
        return pd.DataFrame()

# --- C. 整合執行 ---
def sync_institutional():
    print("\n🚀 [Daily] 下載三大法人買賣超...")
    today = datetime.now()
    if today.weekday() >= 5:
        print("   😴 今天是週末，跳過法人資料")
        return

    date_compact = today.strftime("%Y%m%d")
    date_dash = today.strftime("%Y-%m-%d")
    
    # 1. 抓上市
    df_tw = fetch_twse_institutional(date_compact)
    # 2. 抓上櫃
    df_two = fetch_tpex_institutional(date_compact)
    
    # 3. 合併
    df_all = pd.concat([df_tw, df_two], ignore_index=True)
    
    if df_all.empty:
        print(f"   ⚠️ 無資料 (可能是平日休市、API 尚未更新或欄位對應失敗)")
        return

    # 4. 清洗數據
    for c in ['foreign_net', 'trust_net', 'dealer_net']:
        df_all[c] = df_all[c].map(clean_number)
    
    df_all['date'] = date_dash
    
    # 5. 寫入 Supabase
    upsert_to_supabase(df_all, 'institutional_investors', ['date', 'symbol'])

# ===========================
# 主程式
# ===========================
if __name__ == "__main__":
    print("="*60)
    print(f"📊 每日籌碼更新 (Daily Analytics)")
    print(f"⏰ 時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    sync_institutional()

    print("\n🎉 法人籌碼更新完畢！")
