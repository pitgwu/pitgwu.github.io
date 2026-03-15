import os
import json
import io
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ===========================
# 1. Google Drive 搜尋與下載模組
# ===========================
def download_excel_from_drive(folder_id, target_filename):
    print(f"🔍 正在 Google Drive 資料夾中尋找檔案: {target_filename} ...")
    
    creds_json_str = os.environ.get("GDRIVE_SERVICE_ACCOUNT")
    if not creds_json_str:
        raise ValueError("❌ 找不到 GDRIVE_SERVICE_ACCOUNT 環境變數，請確認 GitHub Secrets 設定。")

    creds_dict = json.loads(creds_json_str)
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    credentials = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    service = build('drive', 'v3', credentials=credentials)

    query = f"'{folder_id}' in parents and name = '{target_filename}' and trashed = false"
    
    results = service.files().list(q=query, spaces='drive', fields='files(id, name, mimeType)').execute()
    items = results.get('files', [])

    if not items:
        raise FileNotFoundError(f"❌ 在資料夾 (ID:{folder_id}) 中找不到名為 '{target_filename}' 的檔案！")
    
    file_id = items[0]['id']
    mime_type = items[0]['mimeType']
    print(f"   ✅ 找到檔案！(File ID: {file_id})，準備下載...")

    if mime_type == 'application/vnd.google-apps.spreadsheet':
        request = service.files().export_media(
            fileId=file_id, 
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    else:
        request = service.files().get_media(fileId=file_id)
    
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print(f"   下載進度: {int(status.progress() * 100)}%")
        
    fh.seek(0)
    print("✅ 檔案下載完成！")
    return fh

# ===========================
# 2. 報表生成模組
# ===========================
def generate_html_report(file_stream, output_file):
    print("正在為你讀取 Excel 資料...")
    
    df = pd.read_excel(file_stream, skiprows=5, header=None, engine='openpyxl')

    # 智慧判斷：如果 Excel 匯出的是 11 欄就直接套用，如果是 9 欄就由 Python 自動計算
    if len(df.columns) == 11:
        df.columns = [
            "股票代號", "股票名稱", "收盤價", 
            "外資買賣超（張）", "外資買賣超（金額）", "外資成本", 
            "投信買賣超（張）", "投信買賣超（金額）", "投信持股比率(%)", "投信成本", "投信浮盈"
        ]
    elif len(df.columns) == 9:
        print("   💡 偵測到原本的 9 欄格式，自動為您計算買賣超（金額）...")
        df.columns = [
            "股票代號", "股票名稱", "收盤價", 
            "外資買賣超（張）", "外資成本", "投信買賣超（張）", 
            "投信持股比率(%)", "投信成本", "投信浮盈"
        ]
        
        df['收盤價'] = pd.to_numeric(df['收盤價'], errors='coerce')
        df['外資買賣超（張）'] = pd.to_numeric(df['外資買賣超（張）'], errors='coerce')
        df['投信買賣超（張）'] = pd.to_numeric(df['投信買賣超（張）'], errors='coerce')
        
        外資金額 = df['外資買賣超（張）'] * df['收盤價'] * 1000
        投信金額 = df['投信買賣超（張）'] * df['收盤價'] * 1000
        
        df.insert(4, "外資買賣超（金額）", 外資金額)
        df.insert(7, "投信買賣超（金額）", 投信金額)
    else:
        print(f"   ⚠️ 警告：欄位數量為 {len(df.columns)}，與預期不符，可能會有錯位風險。")

    print("正在幫「買賣超」欄位微調成整數格式，並加上千分位逗號...")
    for col in df.columns:
        if '買賣超' in str(col):
            df[col] = pd.to_numeric(df[col], errors='coerce')
            df[col] = df[col].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else x)

    df = df.fillna('-')

    html_table = df.to_html(classes='table table-hover table-striped custom-table', index=False, border=0)

    print("正在套用更聰明的「最適欄寬」與「紅綠上色」版型...")
    
    tz_taiwan = timezone(timedelta(hours=8))
    now_str = datetime.now(tz_taiwan).strftime("%Y-%m-%d %H:%M")
    
    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-Hant">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>法人成本與籌碼追蹤表 - {now_str}</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdn.datatables.net/1.13.4/css/dataTables.bootstrap5.min.css" rel="stylesheet">
        <style>
            body {{
                background-color: #f4f7f6;
                padding: 20px;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }}
            .table-container {{
                background-color: #ffffff;
                border-radius: 10px;
                padding: 25px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.05);
            }}
            .custom-table th {{
                white-space: normal; 
                vertical-align: middle;
                text-align: center;
                min-width: 90px; 
                background-color: #2c3e50 !important;
                color: #ffffff !important;
            }}
            .custom-table td {{
                white-space: nowrap;
                vertical-align: middle;
                text-align: right; 
            }}
            .custom-table td:nth-child(1), .custom-table td:nth-child(2) {{
                text-align: left;
            }}
        </style>
    </head>
    <body>
        <div class="container-fluid table-container">
            <h3 class="mb-4" style="color: #2c3e50; font-weight: bold;">
                📊 法人成本與籌碼追蹤表 
                <small style="font-size: 0.6em; color: #7f8c8d; margin-left: 10px;">更新時間: {now_str}</small>
            </h3>
            <div class="table-responsive">
                {html_table}
            </div>
        </div>

        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <script src="https://cdn.datatables.net/1.13.4/js/jquery.dataTables.min.js"></script>
        <script src="https://cdn.datatables.net/1.13.4/js/dataTables.bootstrap5.min.js"></script>
        <script>
            $(document).ready(function() {{
                $('.custom-table').DataTable({{
                    "language": {{
                        "url": "https://cdn.datatables.net/plug-ins/1.13.4/i18n/zh-HANT.json"
                    }},
                    "autoWidth": false,     
                    "scrollX": true,        
                    "pageLength": 50,       
                    "order": [],
                    // 🔥 網頁渲染時的動態上色邏輯
                    "createdRow": function(row, data, dataIndex) {{
                        // 目標欄位的索引 (由左至右從 0 開始算)
                        // 3: 外資(張), 4: 外資(金額), 6: 投信(張), 7: 投信(金額), 10: 投信浮盈
                        let targetCols = [3, 4, 6, 7, 10];
                        
                        targetCols.forEach(function(colIdx) {{
                            let cell = $('td', row).eq(colIdx);
                            let text = cell.text().trim();
                            
                            // 略過空值或無效符號
                            if (text !== '-' && text !== '') {{
                                // 把千分位逗號拔掉，轉成純數字判斷
                                let num = parseFloat(text.replace(/,/g, ''));
                                
                                if (num > 0) {{
                                    // 台股紅 (買超/獲利)
                                    cell.css({{
                                        'color': '#e74c3c',
                                        'font-weight': 'bold'
                                    }});
                                }} else if (num < 0) {{
                                    // 台股綠 (賣超/虧損)
                                    cell.css({{
                                        'color': '#2ecc71',
                                        'font-weight': 'bold'
                                    }});
                                }}
                            }}
                        }});
                    }}
                }});
            }});
        </script>
    </body>
    </html>
    """

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_template)
        
    print(f"搞定囉！🎉 網頁已存為：{output_file} (台灣時間標記: {now_str})")

# ===========================
# 3. 主程式執行區
# ===========================
if __name__ == "__main__":
    GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID")
    if not GDRIVE_FOLDER_ID:
        raise ValueError("❌ 找不到 GDRIVE_FOLDER_ID 環境變數，請確認 GitHub Secrets 與 YAML 設定。")
    
    TARGET_FILENAME = "給andy的報表.xlsx"
    output_html = 'snowbaby/法人成本.html'    
    
    try:
        file_stream = download_excel_from_drive(GDRIVE_FOLDER_ID, TARGET_FILENAME)
        generate_html_report(file_stream, output_html)
        
    except Exception as e:
        print(f"❌ 執行失敗: {e}")