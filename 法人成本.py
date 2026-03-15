import os
import json
import io
import pandas as pd
import numpy as np
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ===========================
# 1. Google Drive 搜尋與下載模組
# ===========================
def download_excel_from_drive(folder_id, target_filename):
    print(f"🔍 正在 Google Drive 資料夾中尋找檔案: {target_filename} ...")
    
    # 從環境變數讀取金鑰
    creds_json_str = os.environ.get("GDRIVE_SERVICE_ACCOUNT")
    if not creds_json_str:
        raise ValueError("❌ 找不到 GDRIVE_SERVICE_ACCOUNT 環境變數，請確認 GitHub Secrets 設定。")

    creds_dict = json.loads(creds_json_str)
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    credentials = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    service = build('drive', 'v3', credentials=credentials)

    # 步驟 A: 透過 Folder ID 與檔名進行搜尋
    query = f"'{folder_id}' in parents and name = '{target_filename}' and trashed = false"
    
    results = service.files().list(q=query, spaces='drive', fields='files(id, name, mimeType)').execute()
    items = results.get('files', [])

    if not items:
        raise FileNotFoundError(f"❌ 在資料夾 (ID:{folder_id}) 中找不到名為 '{target_filename}' 的檔案！")
    
    # 取得搜尋結果的第一個檔案的 ID
    file_id = items[0]['id']
    mime_type = items[0]['mimeType']
    print(f"   ✅ 找到檔案！(File ID: {file_id})，準備下載...")

    # 步驟 B: 下載檔案
    # 判斷是否為 Google 原生試算表
    if mime_type == 'application/vnd.google-apps.spreadsheet':
        request = service.files().export_media(
            fileId=file_id, 
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    else:
        # 一般上傳的 .xlsx 實體檔案
        request = service.files().get_media(fileId=file_id)
    
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print(f"   下載進度: {int(status.progress() * 100)}%")
        
    fh.seek(0) # 將指標移回檔案開頭，準備給 pandas 讀取
    print("✅ 檔案下載完成！")
    return fh

# ===========================
# 2. 報表生成模組
# ===========================
def generate_html_report(file_stream, output_file):
    print("正在為你讀取 Excel 資料...")
    
    # 從第 6 列（header=5）開始讀取標題，加上 engine='openpyxl' 確保能讀記憶體中的 xlsx
    df = pd.read_excel(file_stream, header=5, engine='openpyxl')

    print("正在幫「買賣超」欄位微調成整數格式，並加上千分位逗號...")
    # 針對所有欄位進行檢查
    for col in df.columns:
        if '外資買賣超' in str(col) or '投信買賣超' in str(col):
            df[col] = pd.to_numeric(df[col], errors='coerce')
            df[col] = df[col].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else x)

    df = df.fillna('-')

    html_table = df.to_html(classes='table table-hover table-striped custom-table', index=False, border=0)

    print("正在套用更聰明的「最適欄寬」版型...")
    
    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-Hant">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>法人成本與籌碼追蹤表</title>
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
            <h3 class="mb-4" style="color: #2c3e50; font-weight: bold;">📊 法人成本與籌碼追蹤表</h3>
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
                    "order": []             
                }});
            }});
        </script>
    </body>
    </html>
    """

    # 自動建立資料夾（如果 snowbaby 資料夾不存在會自動產生）
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_template)
        
    print(f"搞定囉！🎉 網頁已存為：{output_file}")

# ===========================
# 3. 主程式執行區
# ===========================
if __name__ == "__main__":
    # ⚠️ 1. 請在這裡填入您的 Google Drive「資料夾 ID」
    GDRIVE_FOLDER_ID = "請在這裡填入您的資料夾_ID" 
    
    # ⚠️ 2. 指定您要尋找的檔名
    TARGET_FILENAME = "給andy的報表.xlsx"
    
    # 🔥 輸出檔名已修正
    output_html = 'snowbaby/法人成本.html'    
    
    try:
        # 1. 搜尋資料夾並下載檔案到記憶體
        file_stream = download_excel_from_drive(GDRIVE_FOLDER_ID, TARGET_FILENAME)
        
        # 2. 將記憶體中的檔案交給報表生成函數處理
        generate_html_report(file_stream, output_html)
        
    except Exception as e:
        print(f"❌ 執行失敗: {e}")