import pandas as pd
import datetime
import json
import os
import shutil

# ==========================================
# 0. 設定與路徑 (強制台灣時間)
# ==========================================
TZ_TW = datetime.timezone(datetime.timedelta(hours=8))
NOW = datetime.datetime.now(TZ_TW)
DATE_STR = NOW.strftime("%Y%m%d")
TITLE_DATE = NOW.strftime("%Y/%m/%d")

YYYY = NOW.strftime("%Y")
MM = NOW.strftime("%m")
BASE_DIR = "tw_stock_dashboard"
TARGET_DIR = os.path.join(BASE_DIR, YYYY, MM)

INDICES = ["^TWII", "^TWOII", "^VIXTWN", "^VIX", "^DJI", "^GSPC", "^SOX"]
COMMODITIES = ["GC=F", "SI=F", "HG=F", "HRC=F", "CL=F"] 
WATCHLIST = ["2330.TW", "2317.TW", "2454.TW", "2382.TW", "2881.TW", "2603.TW", "3661.TW"]
HIGH_PRICE_CODES = [
    "5274.TWO", "6669.TW", "3661.TW", "7769.TWO", "6515.TW", "2059.TW", "3008.TW", "3443.TW", "3653.TW", "6510.TWO",
    "6223.TWO", "3131.TWO", "3529.TWO", "2330.TW", "8299.TWO", "2383.TW", "2454.TW", "3665.TW", "6805.TW", "3017.TW",
    "3533.TW", "5269.TW", "6442.TW", "6781.TW", "2345.TW", "2308.TW", "6409.TW", "2404.TW", "7734.TWO", "1590.TW",
    "3324.TW", "8210.TW", "4749.TWO", "2360.TW", "7750.TWO", "5536.TWO", "3491.TWO", "1519.TW", "6944.TWO", "6739.TWO",
    "7751.TWO", "3293.TWO", "7805.TWO", "6640.TWO", "5289.TWO", "4583.TW", "2368.TW", "3081.TWO", "4966.TWO", "7728.TWO"
]

def style_table(df, table_id, period_col='Daily_Chg%', is_watchlist=False):
    if df.empty: return "<p style='color:#666'>無數據</p>"
    if 'Rank' not in df.columns:
        df = df.copy(); df.reset_index(drop=True, inplace=True)
        df.index += 1; df['Rank'] = df.index
    
    df['Code'] = df['Code'].astype(str).str.replace(r'\.TW.*|\.TWO.*', '', regex=True)

    col_map = {'Rank': '排名', 'Code': '代號', 'Name': '名稱', 'Close': '股價', 'Daily_Chg%': '日漲跌', 'Daily_Amount_B': '成交額(億)', 'Sector': '產業分類'}
    cols = ['Rank', 'Code', 'Name', 'Sector', 'Close', period_col, 'Daily_Amount_B']
    cols = [c for c in cols if c in df.columns]
    
    df_show = df[cols].rename(columns=col_map)
    display_chg_col = col_map.get(period_col, '日漲跌')

    def color_chg(val):
        try:
            val = float(val)
            color = '#ff5252' if val > 0 else '#4caf50' if val < 0 else '#ccc'
            return f'color: {color}; font-weight: bold;'
        except: return ''
    
    styler = df_show.style.format({'股價': "{:,.2f}", display_chg_col: "{:+.2f}%", '成交額(億)': "{:.2f}"}).map(color_chg, subset=[display_chg_col]).hide(axis='index')
    return styler.to_html(table_id=table_id, table_attributes='class="sortable"')

def generate_html_report():
    csv_path = os.path.join(TARGET_DIR, f"rank_all_{DATE_STR}.csv")
    if not os.path.exists(csv_path): print("❌ No CSV"); return

    try: df = pd.read_csv(csv_path, encoding='utf-8-sig')
    except: df = pd.read_csv(csv_path) 
    df.columns = df.columns.str.strip().str.replace('\ufeff', '')

    try:
        with open(os.path.join(TARGET_DIR, f"sentiment_{DATE_STR}.json"), "r") as f: sentiment = json.load(f)
    except: sentiment = {"score": 50, "rating": "N/A"}
    
    score = sentiment.get('score', 50)
    rating = sentiment.get('rating', 'Neutral').upper()
    deg = (score / 100 * 180) - 90
    color_map = { "EXTREME FEAR": "#FF5252", "FEAR": "#FF8A65", "NEUTRAL": "#ffd700", "GREED": "#66BB6A", "EXTREME GREED": "#2E7D32" }
    
    rating_color = "#ccc"
    for key, val in color_map.items():
        if key in rating: rating_color = val; break
    
    html_gauge = f"""
    <div class="section gauge-container" style="text-align: center; position: relative; padding-bottom: 20px;">
        <h2 class="section-title" style="border-left: none; padding-left: 0;">⚡ 市場情緒儀表板 (Fear & Greed)</h2>
        <div class="gauge-wrapper" style="width: 300px; height: 150px; margin: 0 auto; position: relative; overflow: hidden;">
            <div style="width: 300px; height: 150px; border-radius: 150px 150px 0 0; background: conic-gradient(from 180deg, #FF5252 0deg 36deg, #FF8A65 36deg 72deg, #ffd700 72deg 108deg, #66BB6A 108deg 144deg, #2E7D32 144deg 180deg);"></div>
            <div style="width: 240px; height: 120px; background: #161b22; border-radius: 120px 120px 0 0; position: absolute; bottom: 0; left: 30px;"></div>
            <div style="width: 4px; height: 130px; background: #fff; position: absolute; bottom: 0; left: 50%; margin-left: -2px; transform: rotate({deg}deg); transform-origin: bottom center; transition: transform 1s ease-out; z-index: 10; border-radius: 2px;"></div>
            <div style="width: 16px; height: 16px; background: #fff; border-radius: 50%; position: absolute; bottom: -8px; left: 50%; margin-left: -8px; z-index: 11;"></div>
        </div>
        <div style="margin-top: -30px;">
            <div style="font-size: 3.5rem; font-weight: 800; color: #fff; font-family: 'Arial', sans-serif;">{score}</div>
            <div style="font-size: 1.2rem; color: {rating_color}; letter-spacing: 2px; font-weight: bold;">{rating}</div>
        </div>
        <div style="width: 300px; margin: 10px auto 0; position: relative; height: 20px; font-size: 0.85rem; font-weight: bold; color: #888;">
            <span style="position: absolute; left: 0; color: #FF5252;">極度恐慌</span>
            <span style="position: absolute; left: 50%; transform: translateX(-50%); color: #ffd700;">中立</span>
            <span style="position: absolute; right: 0; color: #2E7D32;">極度貪婪</span>
        </div>
    </div>
    """

    df_high = df[df['Code'].isin(HIGH_PRICE_CODES)].sort_values('Close', ascending=False)
    miss = [c for c in HIGH_PRICE_CODES if c not in df_high['Code'].tolist()]
    if miss: df_high = pd.concat([df_high, pd.DataFrame([{'Code':c, 'Name':'N/A', 'Close':0, 'Daily_Chg%':0, 'Daily_Amount_B':0, 'Sector':'待補'} for c in miss])])
    
    html_indices = style_table(df[df['Code'].isin(INDICES)], "tbl_idx")
    html_comm = style_table(df[df['Code'].isin(COMMODITIES)], "tbl_comm")
    html_watch = style_table(df[df['Code'].isin(WATCHLIST)], "tbl_watch")
    html_high = style_table(df_high, "tbl_high")
    
    df_stocks = df[~df['Code'].str.contains(r'\^|=F')].copy()
    
    # ✨ 資金重心 (全寬)
    html_amt = style_table(df_stocks.sort_values('Daily_Amount_B', ascending=False).head(200), "tbl_amt")
    
    # ✨ 猛牛榜 (漲幅前200)
    html_bull = style_table(df_stocks.sort_values('Daily_Chg%', ascending=False).head(200), "tbl_bull")
    
    # ✨ 慘熊榜 (跌幅前200 - 升序)
    html_bear = style_table(df_stocks.sort_values('Daily_Chg%', ascending=True).head(200), "tbl_bear")

    html = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8"><title>台股戰情日報 {DATE_STR}</title>
    <style>
        body{{background:#0e1117;color:#ddd;font-family:'Segoe UI',sans-serif;padding:20px}} 
        header{{text-align:center;margin-bottom:30px;border-bottom:1px solid #333}}
        .section{{background:#161b22;padding:20px;margin-bottom:20px;border-radius:10px;box-shadow:0 4px 10px rgba(0,0,0,0.3)}}
        .section-title{{color:#ffd700;border-left:5px solid #ffd700;padding-left:10px}}
        table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid #333;text-align:left}}
        .row{{display:flex;gap:20px;flex-wrap:wrap}} .col{{flex:1;min-width:400px}}
    </style></head><body>
    <header><h1>台股戰情日報 <span style="font-size:0.6em;color:#aaa">({TITLE_DATE})</span></h1></header>
    {html_gauge}
    <div class="row"><div class="col"><div class="section"><h2 class="section-title">核心指數 & VIX</h2>{html_indices}</div></div>
    <div class="col"><div class="section"><h2 class="section-title">關鍵原物料</h2>{html_comm}</div></div></div>
    <div class="section"><h2 class="section-title">👀 台股權值重點觀察</h2>{html_watch}</div>
    <div class="section"><h2 class="section-title">🏆 50 檔高價股追蹤 (含興櫃)</h2>{html_high}</div>
    
    <div class="section"><h2 class="section-title">💰 資金重心 Top 200</h2>{html_amt}</div>
    
    <div class="row">
        <div class="col"><div class="section"><h2 class="section-title">🚀 強勢猛牛 Top 200 (漲幅)</h2>{html_bull}</div></div>
        <div class="col"><div class="section"><h2 class="section-title">🐻 弱勢慘熊 Top 200 (跌幅)</h2>{html_bear}</div></div>
    </div>
    </body></html>
    """
    
    filename_dated = f"market_dashboard_{DATE_STR}.html"
    path_dated = os.path.join(TARGET_DIR, filename_dated)
    with open(path_dated, "w", encoding="utf-8") as f: f.write(html)
    print(f"✅ 報表生成: {path_dated}")

    filename_current = "market_dashboard_current.html"
    path_current = os.path.join(BASE_DIR, filename_current)
    shutil.copy(path_dated, path_current)
    print(f"✅ 更新連結: {path_current}")

if __name__ == "__main__":
    generate_html_report()
