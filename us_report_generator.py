import pandas as pd
import datetime
import numpy as np
import json
import os

# ==========================================
# 0. 設定與路徑計算
# ==========================================
NOW = datetime.datetime.now()
YYYY = NOW.strftime("%Y")
MM = NOW.strftime("%m")
DATE_STR = NOW.strftime("%Y%m%d")

BASE_DIR = "us_stock_dashboard"
TARGET_DIR = os.path.join(BASE_DIR, YYYY, MM)

# 確保讀取檔案時目錄存在
if not os.path.exists(TARGET_DIR):
    print(f"❌ 目錄不存在: {TARGET_DIR}，請先執行 data_engine.py")
    exit()

# 重點觀察清單
WATCHLIST_TICKERS = [
    "NVDA", "MSFT", "AAPL", "AMZN", "GOOG", "META", 
    "AVGO", "TSLA", "TSM", "ORCL", "CRWD", 
    "BTC-USD", "COIN", "^VIX"
]

def load_sentiment_data():
    """ 讀取帶有日期的情緒指數檔案 """
    filename = f"sentiment_{DATE_STR}.json"
    filepath = os.path.join(TARGET_DIR, filename)
    
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"score": 50, "rating": "N/A", "timestamp": ""}

def generate_gauge_html(sentiment):
    """ 生成恐懼與貪婪指數 CSS """
    score = sentiment.get('score', 50)
    rating = sentiment.get('rating', 'Neutral').upper()
    deg = (score / 100 * 180) - 90
    
    color_map = {
        "EXTREME FEAR": "#FF5252",
        "FEAR": "#FF8A65",
        "NEUTRAL": "#ffd700",
        "GREED": "#66BB6A",
        "EXTREME GREED": "#2E7D32"
    }
    text_color = "#ccc"
    for key, val in color_map.items():
        if key in rating:
            text_color = val
            break

    html = f"""
    <div class="section gauge-container" style="text-align: center; position: relative; padding-bottom: 20px;">
        <h2 class="section-title" style="border-left: none; padding-left: 0;">⚡ 市場情緒儀表板 (Fear & Greed)</h2>
        <div class="gauge-wrapper">
            <div class="gauge-arch"></div>
            <div class="gauge-arch-mask"></div>
            <div class="gauge-needle" style="transform: rotate({deg}deg);"></div>
            <div class="gauge-center"></div>
        </div>
        <div class="gauge-score">
            <div style="font-size: 3rem; font-weight: bold; color: {text_color}; text-shadow: 0 0 10px rgba(0,0,0,0.5);">{score}</div>
            <div style="font-size: 1.2rem; color: #aaa; letter-spacing: 2px;">{rating}</div>
        </div>
        <div class="gauge-labels">
            <span style="left: 0; color: #FF5252;">極度恐慌</span>
            <span style="left: 50%; transform: translateX(-50%); color: #ffd700;">中立</span>
            <span style="right: 0; color: #2E7D32;">極度貪婪</span>
        </div>
    </div>
    """
    return html

def style_dataframe(df, table_id, period_type, is_watchlist=False):
    if df.empty: return "<p style='color:#666'>無數據</p>"

    col_map = {
        'Rank': '排名',
        'Code': '代號', 'Name': '公司名稱', 'Theme': '題材', 'Close': '收盤價',
        'Daily_Chg%': '每日漲跌幅', 'Daily_Amount_B': '成交額(B)',
        'Weekly_Chg%': '週漲跌幅', 'Weekly_Amount_B': '週成交額(B)',
        'Monthly_Chg%': '月漲跌幅', 'Monthly_Amount_B': '月成交額(B)'
    }

    if period_type == 'Daily':
        bar_col, chg_col = 'Daily_Amount_B', 'Daily_Chg%'
    elif period_type == 'Weekly':
        bar_col, chg_col = 'Weekly_Amount_B', 'Weekly_Chg%'
    else:
        bar_col, chg_col = 'Monthly_Amount_B', 'Monthly_Chg%'

    cols_to_use = ['Rank', 'Code', 'Name', 'Theme', 'Close', chg_col, bar_col]
    cols_to_use = [c for c in cols_to_use if c in df.columns]
    
    df_show = df[cols_to_use].rename(columns=col_map).copy()
    display_chg_col = col_map.get(chg_col, '漲跌幅')
    display_amt_col = col_map.get(bar_col, '成交額')

    def color_change(val):
        if isinstance(val, str):
            try: val = float(val.strip('%'))
            except: val = 0
        if pd.isna(val): return 'color: #888;'
        color = '#4CAF50' if val > 0 else '#FF5252' if val < 0 else '#888'
        return f'color: {color}; font-weight: bold;'

    styler = df_show.style.format({
        '收盤價': "${:,.2f}", 
        display_chg_col: lambda x: "0.00%" if pd.isna(x) else "{:+.2f}%".format(x),
        display_amt_col: lambda x: "N/A" if (pd.isna(x) or x == 0) else "${:.2f} B".format(x),
    })
    styler = styler.map(color_change, subset=[display_chg_col])
    try: styler = styler.bar(subset=[display_amt_col], color='#333333', vmin=0)
    except: pass
    styler = styler.hide(axis="index")

    if is_watchlist:
        styler = styler.set_properties(**{'font-size': '1.05em', 'border-bottom': '1px solid #444'})

    html = styler.to_html(table_id=table_id)
    html = html.replace('<table id="', '<table class="sortable" id="')
    return html

def add_rank_column(df):
    df = df.copy()
    df.reset_index(drop=True, inplace=True)
    df['Rank'] = df.index + 1
    return df

def generate_section_html(df, period_name, title_prefix):
    df_clean = df[~df['Code'].isin(['BTC-USD', '^VIX'])].copy()
    
    if period_name == 'Daily':
        col_amt, col_chg = 'Daily_Amount_B', 'Daily_Chg%'
    elif period_name == 'Weekly':
        col_amt, col_chg = 'Weekly_Amount_B', 'Weekly_Chg%'
    else:
        col_amt, col_chg = 'Monthly_Amount_B', 'Monthly_Chg%'

    df_clean[col_amt] = pd.to_numeric(df_clean[col_amt], errors='coerce').fillna(0)
    df_clean[col_chg] = pd.to_numeric(df_clean[col_chg], errors='coerce').fillna(0)

    # Top 50 排行
    df_amt = df_clean.sort_values(by=col_amt, ascending=False).head(50)
    df_amt = add_rank_column(df_amt)
    html_amt = style_dataframe(df_amt, f"tbl_{period_name}_amt", period_name)

    df_bull = df_clean.sort_values(by=col_chg, ascending=False).head(50)
    df_bull = add_rank_column(df_bull)
    html_bull = style_dataframe(df_bull, f"tbl_{period_name}_bull", period_name)

    df_bear = df_clean.sort_values(by=col_chg, ascending=True).head(50)
    df_bear = add_rank_column(df_bear)
    html_bear = style_dataframe(df_bear, f"tbl_{period_name}_bear", period_name)

    return f"""
    <div class="section">
        <h2 class="section-title">{title_prefix}</h2>
        <h3>💰 資金重心 Top 50</h3>
        {html_amt}
        <div class="row">
            <div class="col">
                <h3>🚀 猛牛榜 Top 50</h3>
                {html_bull}
            </div>
            <div class="col">
                <h3>🐻 慘熊榜 Top 50</h3>
                {html_bear}
            </div>
        </div>
    </div>
    """

def generate_watchlist_html(df):
    mask = df['Code'].isin(WATCHLIST_TICKERS)
    df_watch = df[mask].copy()
    df_watch['Code'] = pd.Categorical(df_watch['Code'], categories=WATCHLIST_TICKERS, ordered=True)
    df_watch = df_watch.sort_values('Code')
    df_watch = add_rank_column(df_watch)
    html_table = style_dataframe(df_watch, "tbl_watchlist", "Daily", is_watchlist=True)
    return f"""
    <div class="section" style="border: 2px solid #4db8ff; background: #0d1319;">
        <h2 class="section-title" style="color: #4db8ff; border-left-color: #4db8ff;">👀 美股重點觀察股 (Key Watchlist)</h2>
        <p style="color:#aaa; margin-bottom:15px;">關注科技巨頭、BTC 與市場領頭羊的表現</p>
        {html_table}
    </div>
    """

def create_current_link(latest_html_rel_path):
    """ 
    生成 us_stock_dashboard/market_dashboard_current.html 
    使用 HTML Redirect 跳轉到最新的日期報表
    """
    current_file_path = os.path.join(BASE_DIR, "market_dashboard_current.html")
    
    # 注意：這裡的路徑要改成相對路徑，讓網頁瀏覽器能讀懂
    # 例如：2026/01/market_dashboard_20260102.html
    redirect_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv="refresh" content="0; url={latest_html_rel_path}" />
        <title>Redirecting to latest report...</title>
    </head>
    <body>
        <p>正在跳轉至最新報表: <a href="{latest_html_rel_path}">{latest_html_rel_path}</a></p>
    </body>
    </html>
    """
    with open(current_file_path, "w", encoding="utf-8") as f:
        f.write(redirect_html)
    print(f"🔗 最新連結已建立: {current_file_path} -> {latest_html_rel_path}")

def generate_html_report():
    sentiment_data = load_sentiment_data()
    
    # 讀取帶有日期的 CSV
    try:
        daily_path = os.path.join(TARGET_DIR, f"rank_daily_{DATE_STR}.csv")
        weekly_path = os.path.join(TARGET_DIR, f"rank_weekly_{DATE_STR}.csv")
        monthly_path = os.path.join(TARGET_DIR, f"rank_monthly_{DATE_STR}.csv")
        
        df_daily = pd.read_csv(daily_path)
        try: df_weekly = pd.read_csv(weekly_path)
        except: df_weekly = pd.DataFrame()
        try: df_monthly = pd.read_csv(monthly_path)
        except: df_monthly = pd.DataFrame()
    except FileNotFoundError:
        print(f"❌ 找不到 CSV: {daily_path}，請先執行 data_engine.py")
        return

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_gauge = generate_gauge_html(sentiment_data)
    html_watchlist = generate_watchlist_html(df_daily)
    html_daily = generate_section_html(df_daily, 'Daily', '📅 當日戰況')
    html_weekly = generate_section_html(df_weekly, 'Weekly', '🗓️ 本週戰況') if not df_weekly.empty else ""
    html_monthly = generate_section_html(df_monthly, 'Monthly', '📊 本月戰況') if not df_monthly.empty else ""

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>美股戰情室 ({DATE_STR})</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Microsoft JhengHei', 'Segoe UI', sans-serif; background-color: #0e1117; color: #e0e0e0; padding: 20px; margin: 0; }}
            header {{ text-align: center; margin-bottom: 30px; border-bottom: 1px solid #333; padding-bottom: 20px; }}
            h1 {{ color: #4db8ff; margin: 0; font-size: 2em; letter-spacing: 2px; }}
            .timestamp {{ color: #888; font-size: 0.9em; margin-top: 5px; }}
            .section {{ margin-bottom: 40px; background: #161b22; padding: 25px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }}
            .section-title {{ color: #ffd700; border-left: 5px solid #ffd700; padding-left: 10px; margin-top: 0; }}
            h3 {{ color: #bbb; margin-top: 20px; font-size: 1.1em; }}
            .row {{ display: flex; gap: 20px; flex-wrap: wrap; margin-top: 20px; }}
            .col {{ flex: 1; min-width: 350px; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-bottom: 10px; }}
            th {{ background-color: #21262d; color: #f0f6fc; padding: 12px 8px; text-align: left; cursor: pointer; position: sticky; top: 0; }}
            th:hover {{ background-color: #30363d; }}
            td {{ padding: 10px 8px; border-bottom: 1px solid #30363d; color: #c9d1d9; }}
            tr:hover {{ background-color: #21262d; }}
            td:nth-child(1), th:nth-child(1) {{ color: #888; text-align: center; width: 50px; font-weight: normal; }}
            td:nth-child(2) {{ font-weight: bold; color: #fff; }}
            td:nth-child(4) {{ color: #8b949e; font-size: 0.85em; }}

            /* === 儀表板 CSS === */
            .gauge-wrapper {{ width: 300px; height: 150px; margin: 0 auto; position: relative; overflow: hidden; }}
            .gauge-arch {{ width: 300px; height: 150px; border-radius: 150px 150px 0 0; background: conic-gradient(from 180deg, #FF5252 0deg 36deg, #FF8A65 36deg 72deg, #ffd700 72deg 108deg, #66BB6A 108deg 144deg, #2E7D32 144deg 180deg); }}
            .gauge-arch-mask {{ width: 240px; height: 120px; background: #161b22; border-radius: 120px 120px 0 0; position: absolute; bottom: 0; left: 30px; }}
            .gauge-needle {{ width: 4px; height: 130px; background: #fff; position: absolute; bottom: 0; left: 50%; margin-left: -2px; transform-origin: bottom center; transition: transform 1s ease-out; z-index: 10; border-radius: 2px; }}
            .gauge-center {{ width: 16px; height: 16px; background: #fff; border-radius: 50%; position: absolute; bottom: -8px; left: 50%; margin-left: -8px; z-index: 11; }}
            .gauge-labels {{ width: 300px; margin: 10px auto 0; position: relative; height: 20px; font-size: 0.85rem; font-weight: bold; }}
            .gauge-labels span {{ position: absolute; bottom: 0; }}
        </style>
    </head>
    <body>
        <header>
            <h1>美股資金流向戰情日報</h1>
            <div class="timestamp">更新時間: {now_str} (UTC+8) | 檔案日期: {DATE_STR}</div>
        </header>
        {html_gauge}
        {html_watchlist}
        {html_daily}
        {html_weekly}
        {html_monthly}
        <script>
            document.querySelectorAll('th').forEach(th => {{
                th.addEventListener('click', (() => {{
                    const table = th.closest('table');
                    const tbody = table.querySelector('tbody');
                    Array.from(tbody.querySelectorAll('tr'))
                        .sort(comparer(Array.from(th.parentNode.children).indexOf(th), this.asc = !this.asc))
                        .forEach(tr => tbody.appendChild(tr) );
                }}));
            }});
            const getCellValue = (tr, idx) => tr.children[idx].innerText || tr.children[idx].textContent;
            const comparer = (idx, asc) => (a, b) => {{
                const v1 = getCellValue(asc ? a : b, idx);
                const v2 = getCellValue(asc ? b : a, idx);
                const num1 = parseFloat(v1.replace(/[^0-9.-]/g, ''));
                const num2 = parseFloat(v2.replace(/[^0-9.-]/g, ''));
                if (!isNaN(num1) && !isNaN(num2)) return num1 - num2;
                return v1.toString().localeCompare(v2);
            }};
        </script>
    </body>
    </html>
    """

    # 生成帶日期的 HTML
    output_filename = f"market_dashboard_{DATE_STR}.html"
    output_path = os.path.join(TARGET_DIR, output_filename)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"✅ 戰情日報生成完畢: {output_path}")

    # 生成連結 (Redirect)
    # 相對路徑: YYYY/MM/market_dashboard_YYYYMMDD.html
    rel_path = f"{YYYY}/{MM}/{output_filename}"
    create_current_link(rel_path)

if __name__ == "__main__":
    generate_html_report()
