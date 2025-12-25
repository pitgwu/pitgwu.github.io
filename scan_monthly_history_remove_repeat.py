import pandas as pd
import twstock
import os
import datetime
import time
import webbrowser

# 設定資料來源目錄
DATA_DIR = 'data'
# 設定報表輸出目錄
REPORT_DIR = 'performance'

def generate_report():
    # 1. 取得當前年月 (例如: 2025_12)
    current_month = datetime.datetime.now().strftime('%Y_%m')
    
    # 讀取對應月份的 CSV
    filename = os.path.join(DATA_DIR, f'limit_up_{current_month}.csv')
    
    if not os.path.exists(filename):
        print(f"❌ 找不到檔案: {filename}，請先執行掃描程式。")
        return

    print(f"📖 正在讀取 {filename} 並計算績效...")
    try:
        df = pd.read_csv(filename, dtype={'Code': str})
    except pd.errors.EmptyDataError:
        print("⚠️ CSV 檔案是空的，尚未有資料。")
        return
    
    if df.empty:
        print("⚠️ 無資料可分析。")
        return

    # --- 去除重複邏輯 (只留最早進場的那一次) ---
    df = df.sort_values(by='Date', ascending=True)
    df = df.drop_duplicates(subset=['Code'], keep='first')

    # 2. 抓取最新股價
    unique_codes = df['Code'].unique().tolist()
    realtime_data = {}
    
    batch_size = 50
    for i in range(0, len(unique_codes), batch_size):
        batch = unique_codes[i:i+batch_size]
        try:
            data = twstock.realtime.get(batch)
            if data:
                realtime_data.update(data)
        except Exception as e:
            print(f"抓取資料部分失敗: {e}")
        time.sleep(0.8)

    # 3. 計算績效
    report_data = []
    
    for index, row in df.iterrows():
        code = row['Code']
        entry_price = float(row['EntryPrice'])
        entry_date = row['Date']
        
        current_price = entry_price 
        
        if code in realtime_data and realtime_data[code]['success']:
            rt = realtime_data[code]['realtime']
            if rt['latest_trade_price'] != '-':
                current_price = float(rt['latest_trade_price'])
            elif rt['open'] != '-':
                 current_price = float(rt['open'])
        
        roi = ((current_price - entry_price) / entry_price) * 100
        
        d1 = datetime.datetime.strptime(entry_date, "%Y-%m-%d").date()
        d2 = datetime.date.today()
        days_held = (d2 - d1).days
        
        report_data.append({
            '日期': entry_date,
            '代號': code,
            '名稱': row['Name'],
            '進場價': entry_price,
            '最新價': current_price,
            '累積報酬率(%)': round(roi, 2),
            '持有天數': days_held
        })

    # 4. 產生 HTML 報表
    df_report = pd.DataFrame(report_data)
    
    if not df_report.empty:
        df_report = df_report.sort_values(by='累積報酬率(%)', ascending=False)
    
    html_template = """
    <html>
    <head>
        <title>每日漲停股績效追蹤</title>
        <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/css/bootstrap.min.css">
        <style>
            body {{ padding: 20px; font-family: "Microsoft JhengHei", sans-serif; }}
            .positive {{ color: #d9534f; font-weight: bold; }}
            .negative {{ color: #5cb85c; font-weight: bold; }}
            h1 {{ margin-bottom: 20px; }}
            .summary-box {{ background: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📈 漲停股戰隊績效追蹤 ({month})</h1>
            <div class="summary-box">
                <strong>統計概況 (已去重)：</strong><br>
                總追蹤檔數：{total_count} 檔<br>
                平均報酬率：<span class="{avg_class}">{avg_roi}%</span><br>
                勝率 (>0%)：{win_rate}%
            </div>
            {table}
            <p class="text-muted text-right">報表生成時間: {gen_time}</p>
        </div>
    </body>
    </html>
    """
    
    def color_roi(val):
        color = '#d9534f' if val > 0 else '#5cb85c' if val < 0 else 'black'
        return f'color: {color}; font-weight: bold;'

    table_html = df_report.style.map(color_roi, subset=['累積報酬率(%)']).to_html(classes='table table-striped table-hover', index=False)
    
    if len(df_report) > 0:
        avg_roi = df_report['累積報酬率(%)'].mean()
        win_count = len(df_report[df_report['累積報酬率(%)'] > 0])
        win_rate = round((win_count / len(df_report)) * 100, 1)
        avg_class = "positive" if avg_roi > 0 else "negative"
    else:
        avg_roi = 0
        win_rate = 0
        avg_class = "text-dark"
    
    final_html = html_template.format(
        month=current_month,
        total_count=len(df_report),
        avg_roi=round(avg_roi, 2),
        avg_class=avg_class,
        win_rate=win_rate,
        table=table_html,
        gen_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )
    
    # 檢查並建立目錄
    if not os.path.exists(REPORT_DIR):
        print(f"📂 建立報表目錄: {REPORT_DIR}")
        os.makedirs(REPORT_DIR)

    # --- [修改點] 檔名加入年月 ---
    output_filename = f'performance_report_{current_month}.html'
    output_file = os.path.join(REPORT_DIR, output_filename)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(final_html)
        
    print(f"\n✅ 報表已生成：{output_file}")
    
    # 自動開啟
    abs_path = os.path.abspath(output_file)
    print(f"👉 請手動開啟: {abs_path}")
    try:
        webbrowser.open(f'file://{abs_path}')
    except:
        pass

if __name__ == "__main__":
    generate_report()
