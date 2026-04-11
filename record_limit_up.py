import twstock
import pandas as pd
import numpy as np
import datetime
import os
import time
import requests
import concurrent.futures
import sqlalchemy
from sqlalchemy import text

# ===========================
# 1. 基本設定與資料庫連線
# ===========================
DATA_DIR = 'data'
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    raise ValueError("❌ 未偵測到 SUPABASE_DB_URL，請設定環境變數。")

engine = sqlalchemy.create_engine(SUPABASE_DB_URL)

# ===========================
# 2. 爬蟲工作函式
# ===========================
def fetch_batch_data(codes):
    """
    單一執行緒的工作函式：負責查詢一批股票
    採用「雙盲查詢」 (同時查 tse_ 與 otc_)
    """
    query_list = []
    for c in codes:
        query_list.append(f"tse_{c}.tw")
        query_list.append(f"otc_{c}.tw")
    
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={'|'.join(query_list)}"
    
    try:
        res = requests.get(url, timeout=3)
        res_json = res.json()
        
        result_list = []
        if 'msgArray' in res_json:
            for item in res_json['msgArray']:
                result_list.append(item)
        return result_list
    except Exception:
        return []

# ===========================
# 3. 資料庫更新函式 (漲停紀錄表)
# ===========================
def update_limit_up_db(limit_up_list, today_str):
    if not limit_up_list:
        return
        
    print(f"🔄 準備更新資料庫 `limit_up_records`...")
    with engine.begin() as conn:
        for item in limit_up_list:
            sym = item['Code']
            sql = text("""
                INSERT INTO limit_up_records (symbol, limit_up_dates)
                VALUES (:sym, :dt)
                ON CONFLICT (symbol) 
                DO UPDATE SET limit_up_dates = 
                    CASE 
                        WHEN limit_up_records.limit_up_dates LIKE '%' || :dt || '%' THEN limit_up_records.limit_up_dates
                        ELSE limit_up_records.limit_up_dates || ',' || :dt
                    END
            """)
            conn.execute(sql, {"sym": sym, "dt": today_str})
            
    print("✅ `limit_up_records` 漲停歷史紀錄表更新完成！")

# ===========================
# 4. 資料庫更新函式 (自選股戰情室)
# ===========================
def update_watchlist_db(limit_up_list, today_str, username="pitg"):
    if not limit_up_list:
        return
        
    yymm_str = today_str.replace("-", "")[:6]
    menu_name = f"{yymm_str}漲停股清單"
    
    print(f"🔄 準備派發至戰情室群組: 「{menu_name}」 (使用者: {username})...")
    
    with engine.begin() as conn:
        menu_id = conn.execute(
            text("SELECT id FROM watchlist_menus WHERE name = :mname AND username = :u"),
            {"mname": menu_name, "u": username}
        ).scalar()
        
        if not menu_id:
            menu_id = conn.execute(
                text("INSERT INTO watchlist_menus (name, username) VALUES (:mname, :u) RETURNING id"),
                {"mname": menu_name, "u": username}
            ).scalar()
            print(f"   🆕 發現新月份，已自動建立群組: {menu_name}")

        added_count = 0
        for item in limit_up_list:
            sym = item['Code']
            res = conn.execute(
                text("""
                    INSERT INTO watchlist_items (menu_id, symbol, added_date)
                    VALUES (:mid, :sym, :dt)
                    ON CONFLICT (menu_id, symbol) DO NOTHING
                    RETURNING 1
                """),
                {"mid": menu_id, "sym": sym, "dt": today_str}
            ).fetchone()
            
            if res:
                added_count += 1
                
    print(f"✅ 成功將 {added_count} 檔新的漲停股加入「{menu_name}」！(重複已自動忽略)")

# ===========================
# 5. 主程式
# ===========================
def scan_limit_up_stocks_fast():
    start_time = time.time()
    today_str = str(datetime.date.today())
    print(f"🚀 [自動化工作流] 開始掃描今日 ({today_str}) 漲停板...")

    current_month = datetime.datetime.now().strftime('%Y_%m')
    filename = os.path.join(DATA_DIR, f'limit_up_{current_month}.csv')
    
    target_codes = [code for code, info in twstock.codes.items() if info.type == '股票' and len(code) == 4]
    if '3135' not in target_codes: target_codes.append('3135')

    BATCH_SIZE = 70
    batches = [target_codes[i:i + BATCH_SIZE] for i in range(0, len(target_codes), BATCH_SIZE)]
    
    raw_results = []
    print(f"⚡ 啟動多執行緒掃描: 共 {len(batches)} 批次，目標 {len(target_codes)} 檔...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_batch_data, batch): batch for batch in batches}
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            raw_results.extend(future.result())
            completed += 1
            print(f"   處理進度: {completed}/{len(batches)} 批...", end='\r')

    print(f"\n✅ 網路請求完成，開始解析數據...")

    # 🔥 1. 建立全市場最新價格字典 (用來更新舊股票)
    price_map = {}
    for item in raw_results:
        c = item.get('c')
        z = item.get('z')
        if c and z and z != '-':
            try:
                price_map[c] = float(z)
            except ValueError:
                pass

    limit_up_list = []
    seen_codes = set()

    for item in raw_results:
        code = item.get('c')
        if not code or code in seen_codes: continue
        if 'z' not in item or 'y' not in item: continue
        if item['z'] == '-' or item['y'] == '-': continue
        
        try:
            price = float(item['z'])
            prev_close = float(item['y'])
            pct_change = ((price - prev_close) / prev_close) * 100
            
            is_high = False
            if 'h' in item and item['h'] != '-':
                if price == float(item['h']):
                    is_high = True
            
            if pct_change >= 9.4 and is_high:
                seen_codes.add(code)
                name = item.get('n', code)
                
                # 加入新增的欄位：最新價、報酬率、持有天數
                limit_up_list.append({
                    'Date': today_str,
                    'Code': code,
                    'Name': name,
                    'EntryPrice': price,
                    'LatestPrice': price,
                    'ReturnPct': 0.0,
                    'HoldDays': 1,
                    'Note': '漲停'
                })
        except ValueError:
            continue

    duration = time.time() - start_time
    print(f"⏱️ 總耗時: {duration:.2f} 秒")
    print(f"🎯 掃描完成！共發現 {len(limit_up_list)} 檔漲停股。")

    df_final = pd.DataFrame()

    # 🔥 2. 更新 CSV 歷史紀錄的「最新價」與「報酬率」！
    if os.path.exists(filename):
        print(f"🔄 正在更新歷史紀錄的最新價與報酬率 ({filename})...")
        # 確保讀取時 Code 是字串，避免 0050 被轉成 50
        df_old = pd.read_csv(filename, dtype={'Code': str})
        
        # 濾掉今天可能已經重複跑過的資料
        df_old = df_old[df_old['Date'] != today_str].copy()
        
        if not df_old.empty:
            # 確保舊檔案擁有所有計算欄位
            for col in ['LatestPrice', 'ReturnPct', 'HoldDays']:
                if col not in df_old.columns:
                    df_old[col] = 0.0
            
            # 逐列更新報價
            for idx, row in df_old.iterrows():
                code_str = str(row['Code']).zfill(4)
                entry_price = float(row['EntryPrice'])
                date_str = str(row['Date'])
                
                # 更新最新價與累積報酬率
                if code_str in price_map:
                    latest_p = price_map[code_str]
                    df_old.at[idx, 'LatestPrice'] = latest_p
                    if entry_price > 0:
                        df_old.at[idx, 'ReturnPct'] = round(((latest_p - entry_price) / entry_price) * 100, 2)
                
                # 計算持有天數 (日曆天)
                try:
                    days_diff = (pd.to_datetime(today_str) - pd.to_datetime(date_str)).days + 1
                    df_old.at[idx, 'HoldDays'] = max(1, days_diff)
                except Exception:
                    df_old.at[idx, 'HoldDays'] = 1
                    
        df_final = df_old

    # 3. 將今日新漲停股接在最後面
    if limit_up_list:
        df_new = pd.DataFrame(limit_up_list)
        if not df_final.empty:
            df_final = pd.concat([df_final, df_new], ignore_index=True)
        else:
            df_final = df_new

    # 4. 存檔與派發
    if not df_final.empty:
        df_final.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"📁 CSV 本地端報表已更新至: {filename}")
        
    if limit_up_list:
        update_limit_up_db(limit_up_list, today_str)
        update_watchlist_db(limit_up_list, today_str, username="pitg")
    else:
        print("⚠️ 今日無發現漲停股，無須派發至戰情室與資料庫。")

if __name__ == "__main__":
    scan_limit_up_stocks_fast()
