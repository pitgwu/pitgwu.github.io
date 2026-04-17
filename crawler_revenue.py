import os
import requests
import pandas as pd
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime
import time

# ===========================
# 1. 全域配置與連線
# ===========================
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    raise RuntimeError("❌ 請設定環境變數 SUPABASE_DB_URL")

engine = create_engine(SUPABASE_DB_URL, pool_pre_ping=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

# ===========================
# 2. 自動修正資料表架構與寫入
# ===========================
def ensure_table_schema():
    """確保 monthly_revenue 擁有 symbol 欄位"""
    with engine.begin() as conn:
        try:
            conn.execute(text('ALTER TABLE monthly_revenue ADD COLUMN IF NOT EXISTS symbol TEXT;'))
        except Exception:
            pass

def upsert_revenue_data(df):
    """安全寫入資料 (Upsert)"""
    if df.empty: return
    
    table_name = 'monthly_revenue'
    unique_cols = ['report_month', 'stock_id']
    records = df.to_dict(orient='records')
    metadata = sqlalchemy.MetaData()
    
    try:
        target_table = sqlalchemy.Table(table_name, metadata, autoload_with=engine)
    except sqlalchemy.exc.NoSuchTableError:
        df.to_sql(table_name, engine, if_exists='replace', index=False)
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE {table_name} ADD PRIMARY KEY (report_month, stock_id);'))
        print(f"   ✨ 已建立新表 [{table_name}] 並寫入 {len(records)} 筆")
        return
    
    stmt = insert(target_table).values(records)
    update_dict = {c.name: c for c in stmt.excluded if c.name not in unique_cols}
    on_conflict_stmt = stmt.on_conflict_do_update(index_elements=unique_cols, set_=update_dict)

    with engine.begin() as conn:
        conn.execute(on_conflict_stmt)
    print(f"   ✅ 成功寫入/更新 {len(records)} 筆營收資料！")

def clean_num(val):
    """清理 JSON 中的數字（確保轉為浮點數）"""
    if pd.isna(val) or str(val).strip() in ['', '-', '無']: return 0.0
    try:
        return float(str(val).replace(',', '').strip())
    except Exception:
        return 0.0

# ===========================
# 3. 爬蟲核心 (官方 OpenAPI 純 JSON 高速版)
# ===========================
def fetch_openapi_revenue():
    print(f"🚀 啟動證交所 OpenAPI 營收下載引擎...")
    
    # 官方 Open API 網址 (回傳純 JSON)
    endpoints = {
        '上市': ('https://openapi.twse.com.tw/v1/opendata/t187ap05_L', '.TW'),
        '上櫃': ('https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O', '.TWO'),
        '興櫃': ('https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_R', '.TWO')
    }
    
    all_data = []

    for market_name, (url, suffix) in endpoints.items():
        print(f"   📡 正在請求 {market_name} 最新營收資料...")
        
        try:
            res = requests.get(url, headers=HEADERS, timeout=20)
            
            if res.status_code != 200:
                print(f"      ⚠️ {market_name} API 請求失敗 (狀態碼: {res.status_code})")
                continue
                
            data = res.json()
            if not data:
                print(f"      ⚠️ {market_name} 回傳空資料。")
                continue
                
            print(f"      ✅ 取得 {len(data)} 筆 {market_name} 原始資料，開始解析...")
            
            for row in data:
                try:
                    # 從資料庫自動解析出所屬月份 (如 '11303' -> 2024-03-01)
                    ym_str = str(row.get('資料年月', '')).strip()
                    if not ym_str or len(ym_str) < 4: continue
                    
                    roc_year = int(ym_str[:-2])
                    month = int(ym_str[-2:])
                    report_date_str = f"{roc_year + 1911}-{month:02d}-01"
                    
                    stock_id = int(row['公司代號'])
                    
                    all_data.append({
                        'report_month': report_date_str,
                        'stock_id': stock_id,
                        'symbol': f"{stock_id}{suffix}",  # 🔥 完美串接戰情室的代號
                        'market_type': market_name,
                        'stock_name': str(row.get('公司名稱', '')).strip().replace('*', ''),
                        
                        # 從 JSON 欄位中精準取值
                        'rev_current': clean_num(row.get('營業收入-當月營收')),
                        'rev_last_month': clean_num(row.get('營業收入-上月營收')),
                        'rev_last_year': clean_num(row.get('營業收入-去年當月營收')),
                        'mom_pct': clean_num(row.get('營業收入-上月比較增減(%)')),
                        'yoy_pct': clean_num(row.get('營業收入-去年同月增減(%)')),
                        'rev_accumulated': clean_num(row.get('累計營業收入-當月累計營收')),
                        'rev_accumulated_last_year': clean_num(row.get('累計營業收入-去年累計營收')),
                        'yoy_accumulated_pct': clean_num(row.get('累計營業收入-前期比較增減(%)')),
                        'remark': str(row.get('備註', ''))
                    })
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"      ❌ {market_name} 解析過程發生錯誤: {e}")
            
        # 避免 API 阻擋，短暫休息
        time.sleep(2)

    return pd.DataFrame(all_data)

# ===========================
# 4. 主程式
# ===========================
if __name__ == "__main__":
    ensure_table_schema()
    
    # OpenAPI 自動提供最新一期營收，直接抓取即可
    df_revenue = fetch_openapi_revenue()
    
    if not df_revenue.empty:
        # 印出抓到的資料月份概況
        latest_month = df_revenue['report_month'].max()
        print(f"\n📈 本次抓取的最新營收月份為：{latest_month}")
        
        upsert_revenue_data(df_revenue)
    else:
        print("⚠️ 網路連線異常或 API 暫時無回應，未取得任何資料。")
