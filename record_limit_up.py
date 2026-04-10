import twstock
import pandas as pd
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
            
            # 使用 PostgreSQL 的 ON CONFLICT 達成 UPSERT：
            # 如果 symbol 不存在就 INSERT；如果存在，且日期字串不包含今天，就把今天逗號串接上去
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
        
    # 產生 YYYYMM 格式 (例如 "202604")
    yymm_str = today_str.replace("-", "")[:6]
    menu_name = f"{yymm_str}漲停股清單"
    
    print(f"🔄 準備派發至戰情室群組: 「{menu_name}」 (使用者: {username})...")
    
    with engine.begin() as conn:
        # 1. 檢查群組是否存在，若無則建立
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

        # 2. 將漲停股寫入群組 (若重複則忽略 DO NOTHING)
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
    
    # 準備清單
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
                
                limit_up_list.append({
                    'Date': today_str,
                    'Code': code,
                    'Name': name,
                    'EntryPrice': price,
                    'PctChange': round(pct_change, 2),
                    'Note': '漲停'
                })
        except ValueError:
            continue

    duration = time.time() - start_time
    print(f"⏱️ 總耗時: {duration:.2f} 秒")
    print(f"🎯 掃描完成！共發現 {len(limit_up_list)} 檔漲停股。")
    
    if limit_up_list:
        # 1. 存入本地 CSV 備份
        df_new = pd.DataFrame(limit_up_list)
        if os.path.exists(filename):
            df_old = pd.read_csv(filename)
            df_old = df_old[df_old['Date'] != today_str]
            df_final = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_final = df_new
            
        df_final.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"📁 資料已備份至: {filename}")
        
        # 2. 更新 Supabase 漲停字串紀錄表
        update_limit_up_db(limit_up_list, today_str)
        
        # 3. 自動派發至戰情室 (使用者: pitg)
        update_watchlist_db(limit_up_list, today_str, username="pitg")
        
    else:
        print("⚠️ 今日無發現漲停股，無須更新資料庫。")

if __name__ == "__main__":
    scan_limit_up_stocks_fast()
