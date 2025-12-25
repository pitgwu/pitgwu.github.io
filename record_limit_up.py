import twstock
import pandas as pd
import datetime
import os
import time
import requests
import concurrent.futures

# 設定存檔目錄
DATA_DIR = 'data'
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def fetch_batch_data(codes):
    """
    單一執行緒的工作函式：負責查詢一批股票
    採用「雙盲查詢」 (同時查 tse_ 與 otc_)
    """
    query_list = []
    for c in codes:
        query_list.append(f"tse_{c}.tw")
        query_list.append(f"otc_{c}.tw")
    
    # 組合 API URL
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={'|'.join(query_list)}"
    
    try:
        # 設定 timeout，避免卡住
        res = requests.get(url, timeout=3)
        res_json = res.json()
        
        result_list = []
        if 'msgArray' in res_json:
            for item in res_json['msgArray']:
                # 這裡只回傳原始資料，過濾邏輯交給主程式
                result_list.append(item)
        return result_list
    except Exception:
        # 網路超時或錯誤直接回傳空list，不讓程式崩潰
        return []

def scan_limit_up_stocks_fast():
    start_time = time.time()
    today_str = str(datetime.date.today())
    print(f"🚀 [程式 A - V4 極速版] 開始掃描今日 ({today_str}) 漲停板...")

    current_month = datetime.datetime.now().strftime('%Y_%m')
    filename = os.path.join(DATA_DIR, f'limit_up_{current_month}.csv')
    
    # 1. 準備清單 (含手動補強)
    target_codes = []
    for code, info in twstock.codes.items():
        if info.type == '股票' and len(code) == 4:
            target_codes.append(code)
    
    # 補強漏網之魚
    if '3135' not in target_codes:
        target_codes.append('3135')

    total_stocks = len(target_codes)
    
    # 2. 設定批次參數
    # 雙盲查詢 URL 較長，建議一批 60-80 檔，這裡設 70
    BATCH_SIZE = 70
    # 將清單切分成多個小批次
    batches = [target_codes[i:i + BATCH_SIZE] for i in range(0, len(target_codes), BATCH_SIZE)]
    
    raw_results = []
    print(f"⚡ 啟動多執行緒掃描: 共 {len(batches)} 批次，目標 {total_stocks} 檔...")

    # 3. 多執行緒平行處理
    # max_workers=10 代表同時發送 10 個請求，速度極快
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        # 提交任務
        futures = {executor.submit(fetch_batch_data, batch): batch for batch in batches}
        
        completed = 0
        for future in concurrent.futures.as_completed(futures):
            data = future.result()
            raw_results.extend(data)
            
            completed += 1
            # 顯示進度條 (因為並發很快，這行會跳很快)
            print(f"   處理進度: {completed}/{len(batches)} 批...", end='\r')

    print(f"\n✅ 網路請求完成，開始解析數據...")

    # 4. 解析數據與篩選 (在本地端處理，速度極快)
    limit_up_list = []
    
    # 用 set 避免雙盲查詢可能造成的極少數重複 (雖然 API 通常會濾掉)
    seen_codes = set()

    for item in raw_results:
        code = item.get('c')
        if not code or code in seen_codes: continue
        
        # 檢查必要欄位
        if 'z' not in item or 'y' not in item: continue
        if item['z'] == '-' or item['y'] == '-': continue
        
        try:
            price = float(item['z'])
            prev_close = float(item['y'])
            
            # 計算漲幅
            pct_change = ((price - prev_close) / prev_close) * 100
            
            # 漲停判斷 (漲幅 > 9.4% 且 現價 == 最高價)
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

    # 5. 存檔
    duration = time.time() - start_time
    print(f"⏱️ 總耗時: {duration:.2f} 秒")
    print(f"✅ 掃描完成！共發現 {len(limit_up_list)} 檔漲停股。")
    
    if limit_up_list:
        df_new = pd.DataFrame(limit_up_list)
        
        if os.path.exists(filename):
            df_old = pd.read_csv(filename)
            df_old = df_old[df_old['Date'] != today_str]
            df_final = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_final = df_new
            
        df_final.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"📁 資料已存入: {filename}")
        print(df_new[['Code', 'Name', 'EntryPrice', 'PctChange']].to_string(index=False))
    else:
        print("⚠️ 今日無發現漲停股。")

if __name__ == "__main__":
    scan_limit_up_stocks_fast()
