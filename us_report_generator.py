import pandas as pd
import datetime
import numpy as np
import json
import os
import shutil

# ==========================================
# 0. 設定與路徑
# ==========================================
# 系統時間
NOW_SYS = datetime.datetime.now()
DATE_STR = NOW_SYS.strftime("%Y%m%d")

# 定義時區
TZ_UTC = datetime.timezone.utc
TZ_TW = datetime.timezone(datetime.timedelta(hours=8))

# 計算美股日期 (US Eastern Time 約為 UTC-5)
now_utc = datetime.datetime.now(TZ_UTC)
us_date = now_utc - datetime.timedelta(hours=5)
US_DATE_STR = us_date.strftime("%Y/%m/%d")

YYYY = NOW_SYS.strftime("%Y")
MM = NOW_SYS.strftime("%m")

BASE_DIR = "us_stock_dashboard"
TARGET_DIR = os.path.join(BASE_DIR, YYYY, MM)

if not os.path.exists(TARGET_DIR):
    print(f"❌ 目錄不存在: {TARGET_DIR}，請先執行 us_data_engine.py")
    exit()

INDICES_TICKERS = ["^DJI", "^GSPC", "^IXIC", "^SOX", "^VIX"]
COMMODITY_TICKERS = ["GC=F", "SI=F", "HG=F", "HRC=F", "CL=F"]

# ✨ 完整 24 檔重點觀察股
WATCHLIST_TICKERS = [
    "NVDA", "MSFT", "AAPL", "AMZN", "GOOG", "META", "AVGO", "TSLA", 
    "TSM", "AMD", "MU", "QCOM", "TXN", "AMAT", "LRCX", "SMCI", 
    "ORCL", "CRWV", "PLTR", "LLY", "NFLX", "XOM", "BTC-USD", "COIN"
]

# ✨ TradingView 代號對照表 (美股專用)
TV_MAPPING = {
    # 指數
    "^DJI": "DJ-DJI",
    "^GSPC": "SP-SPX",
    "^IXIC": "TVC-IXIC",
    "^SOX": "PHLX-SOX",
    "^VIX": "CBOE-VIX",
    # 原物料 (期貨連續月)
    "GC=F": "COMEX-GC1!",    # 黃金
    "SI=F": "COMEX-SI1!",    # 白銀
    "HG=F": "COMEX-HG1!",    # 銅
    "HRC=F": "CME-HRC1!",    # 熱軋鋼
    "CL=F": "NYMEX-CL1!",    # 原油
    # 加密貨幣
    "BTC-USD": "CRYPTO-BTCUSD"
}

# ==========================================
# 1. 資料讀取函式
# ==========================================
def load_sentiment_data():
    filepath = os.path.join(TARGET_DIR, f"sentiment_{DATE_STR}.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f: return json.load(f)
    return {"score": 50, "rating": "N/A"}

def load_ai_data():
    filepath = os.path.join(TARGET_DIR, f"ai_report_{DATE_STR}.json")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f: return json.load(f)
    return []

# ==========================================
# 2. 熱力圖資料生成
# ==========================================
def generate_treemap_data(df):
    exclude = INDICES_TICKERS + ['BTC-USD']
    df_clean = df[~df['Code'].isin(exclude)].copy()
    
    for col in ['Daily_Amount_B', 'Daily_Chg%', 'RVOL']:
        df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0)
    
    if 'Sector' not in df_clean.columns: df_clean['Sector'] = 'Other'
    if 'Industry' not in df_clean.columns: df_clean['Industry'] = 'Other'
    df_clean['Sector'] = df_clean['Sector'].fillna('Other')
    df_clean['Industry'] = df_clean['Industry'].fillna('Other')

    df_top = df_clean[df_clean['Daily_Amount_B'] > 0].sort_values(by='Daily_Amount_B', ascending=False).head(100)
    
    data = []
    for sector, sector_group in df_top.groupby('Sector'):
        industry_children = []
        for industry, industry_group in sector_group.groupby('Industry'):
            stock_children = []
            for _, row in industry_group.iterrows():
                chg = row['Daily_Chg%']
                if chg >= 3.0:   color = "#006400"
                elif chg >= 1.0: color = "#228B22"
                elif chg >= 0.0: color = "#4CAF50"
                elif chg <= -3.0: color = "#8B0000"
                elif chg <= -1.0: color = "#CC0000"
                else:             color = "#F44336"
                if abs(chg) < 0.1: color = "#444444"

                stock_children.append({
                    "name": row['Code'],
                    "company": row['Name'],
                    "value": [float(row['Daily_Amount_B']), float(row['Daily_Chg%']), float(row['RVOL'])],
                    "itemStyle": {"color": color},
                    "label": {"show": True, "formatter": "{b}\n{c}%"} 
                })
            industry_children.append({
                "name": industry,
                "children": stock_children,
                "itemStyle": {"borderColor": "#555", "borderWidth": 1, "gapWidth": 1}
            })
        data.append({
            "name": sector,
            "children": industry_children,
            "itemStyle": {"borderColor": "#000", "borderWidth": 2, "gapWidth": 2}
        })
    return json.dumps(data)

def generate_heatmap_script(treemap_data):
    return f"""
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <script>
        var chartDom = document.getElementById('heatmap-chart');
        var myChart = echarts.init(chartDom, 'dark');
        var rawData = {treemap_data};
        var option = {{
            backgroundColor: '#161b22',
            title: {{ text: '🔥 美股全市場熱力圖', left: 'center', top: 10, textStyle: {{ color: '#fff', fontSize: 20 }} }},
            tooltip: {{
                backgroundColor: 'rgba(50,50,50,0.95)',
                borderColor: '#777',
                textStyle: {{ color: '#fff' }},
                formatter: function (info) {{
                    var value = info.value;
                    if (Array.isArray(value) && value.length >= 3) {{
                        return [
                            '<div style="border-bottom: 1px solid #777; padding-bottom: 5px; margin-bottom: 5px;">',
                            '<span style="font-size:18px; font-weight:bold; color:#fff;">' + info.name + '</span>',
                            '<span style="font-size:13px; color:#ccc; margin-left:10px;">' + (info.data.company || "") + '</span>',
                            '</div>',
                            '成交額: <span style="color:#ffd700; font-weight:bold">$' + value[0].toFixed(2) + ' B</span>',
                            '漲跌幅: <span style="color:' + (value[1] > 0 ? '#4CAF50' : '#FF5252') + '; font-weight:bold">' + (value[1] > 0 ? '+' : '') + value[1].toFixed(2) + '%</span>',
                            'RVOL: <span style="color:#fff">' + value[2].toFixed(2) + 'x</span>'
                        ].join('<br>');
                    }} else {{ return '<div style="font-weight:bold; font-size:16px;">' + info.name + '</div>'; }}
                }}
            }},
            series: [
                {{
                    name: 'US Market',
                    type: 'treemap',
                    roam: false,
                    nodeClick: 'zoomToNode',
                    width: '95%', height: '85%', top: 60, bottom: 20,
                    visualDimension: 0, 
                    breadcrumb: {{ show: true, height: 30, itemStyle: {{ textStyle: {{ lineHeight: 30 }} }} }},
                    label: {{
                        show: true,
                        formatter: function(params) {{
                            var arr = params.value;
                            if (!Array.isArray(arr)) return params.name;
                            if (arr[0] < 0.5) return params.name; 
                            return params.name + '\\n' + (arr[1] > 0 ? '+' : '') + arr[1].toFixed(2) + '%';
                        }},
                        fontSize: 13, fontWeight: 'bold', color: '#fff'
                    }},
                    levels: [
                        {{ itemStyle: {{ borderColor: '#000', borderWidth: 0, gapWidth: 1 }} }},
                        {{ itemStyle: {{ borderColor: '#000', borderWidth: 3, gapWidth: 3 }}, upperLabel: {{ show: true, height: 30, color: '#eee', backgroundColor: '#222', fontWeight: 'bold' }} }},
                        {{ itemStyle: {{ borderColor: '#444', borderWidth: 1, gapWidth: 1 }}, upperLabel: {{ show: true, height: 20, backgroundColor: 'rgba(0,0,0,0.3)', color: '#ccc', fontSize: 11 }} }},
                        {{ itemStyle: {{ borderColor: '#222', borderWidth: 1, gapWidth: 0 }}, label: {{ position: 'inside' }} }}
                    ],
                    data: rawData
                }}
            ]
        }};
        option && myChart.setOption(option);
        window.addEventListener('resize', function() {{ myChart.resize(); }});
    </script>
    """

# ==========================================
# 3. HTML 生成函式
# ==========================================
def generate_ai_section_html(ai_data):
    if not ai_data: return ""
    cards_html = ""
    for item in ai_data:
        analysis = item.get('analysis', {})
        color = "#4CAF50" if item['chg'] > 0 else "#FF5252"
        cards_html += f"""
        <div class="ai-card">
            <div class="ai-header" style="border-left: 4px solid {color};">
                <span class="ai-symbol">{item['symbol']}</span>
                <span class="ai-name">{item['name']}</span>
                <span class="ai-chg" style="color: {color}">{item['chg']:+.2f}%</span>
            </div>
            <div class="ai-body">
                <p><strong>🏭 產業地位：</strong>{analysis.get('position', 'N/A')}</p>
                <p><strong>🚀 上漲利多：</strong>{analysis.get('catalyst', 'N/A')}</p>
                <p><strong>⚡ 動能分析：</strong>{analysis.get('momentum', 'N/A')}</p>
                <p><strong>🔗 台股連動：</strong><span style="color: #ffd700;">{analysis.get('taiwan_link', 'N/A')}</span></p>
            </div>
        </div>
        """
    return f"""
    <div class="section">
        <h2 class="section-title" style="border-left: none; padding-left: 0;">🤖 Gemini AI 焦點股解讀 (Top 10)</h2>
        <div class="ai-container">{cards_html}</div>
    </div>
    """

def generate_gauge_html(sentiment):
    score = sentiment.get('score', 50)
    rating = sentiment.get('rating', 'Neutral').upper()
    deg = (score / 100 * 180) - 90
    color_map = { "EXTREME FEAR": "#FF5252", "FEAR": "#FF8A65", "NEUTRAL": "#ffd700", "GREED": "#66BB6A", "EXTREME GREED": "#2E7D32" }
    text_color = "#ccc"
    for key, val in color_map.items():
        if key in rating: text_color = val; break

    return f"""
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

def style_dataframe(df, table_id, period_type, is_watchlist=False, sort_by_rvol=False, sort_by_mkt_cap=False):
    if df.empty: return "<p style='color:#666'>無數據</p>"
    col_map = {
        'Rank': '排名', 'Code': '代號', 'Name': '公司名稱', 'Sector': '族群', 'Industry': '細分產業',
        'Close': '收盤價', 'RVOL': '相對量能', 'Market_Cap_B': '市值(B)',
        'Daily_Chg%': '漲跌幅', 'Daily_Amount_B': '成交額(B)', 'Volume': '成交量',
        'Weekly_Chg%': '漲跌幅', 'Weekly_Amount_B': '成交額(B)',
        'Monthly_Chg%': '漲跌幅', 'Monthly_Amount_B': '成交額(B)'
    }
    if period_type == 'Daily': bar_col, chg_col = 'Daily_Amount_B', 'Daily_Chg%'
    elif period_type == 'Weekly': bar_col, chg_col = 'Weekly_Amount_B', 'Weekly_Chg%'
    else: bar_col, chg_col = 'Monthly_Amount_B', 'Monthly_Chg%'

    base_cols = ['Rank', 'Code', 'Name', 'Industry', 'Close', chg_col]
    if sort_by_rvol: cols_to_use = base_cols + ['RVOL', bar_col]
    elif sort_by_mkt_cap: cols_to_use = base_cols + ['Market_Cap_B', bar_col]
    else: cols_to_use = base_cols + [bar_col, 'Volume']
    cols_to_use = [c for c in cols_to_use if c in df.columns]
    
    df_show = df[cols_to_use].rename(columns=col_map).copy()
    display_chg_col = col_map.get(chg_col)
    display_amt_col = col_map.get(bar_col)
    display_rvol_col = '相對量能' if sort_by_rvol else None
    display_mkt_cap_col = '市值(B)' if sort_by_mkt_cap else None

    # ✨ 生成 TradingView 超連結
    def make_tv_link(code):
        code_str = str(code)
        tv_symbol = code_str 
        if code_str in TV_MAPPING: tv_symbol = TV_MAPPING[code_str]
        return f'<a href="https://www.tradingview.com/symbols/{tv_symbol}/" target="_blank" style="color: #82cfff; text-decoration: none; font-weight: bold;">{code_str}</a>'

    df_show['代號'] = df_show['代號'].apply(make_tv_link)

    def color_change(val):
        if isinstance(val, str): val = float(val.strip('%'))
        if pd.isna(val): return 'color: #888;'
        color = '#4CAF50' if val > 0 else '#FF5252' if val < 0 else '#888'
        return f'color: {color}; font-weight: bold;'
    
    def color_rvol(val):
        if isinstance(val, (int, float)):
            if val >= 3.0: return 'color: #FF5252; font-weight: bold;'
            if val >= 2.0: return 'color: #FFD700; font-weight: bold;'
            if val >= 1.5: return 'color: #fff;'
        return 'color: #888;'

    format_dict = {'收盤價': "${:,.2f}"}
    if display_chg_col: format_dict[display_chg_col] = "{:+.2f}%"
    if display_amt_col: format_dict[display_amt_col] = "${:.2f} B"
    if display_rvol_col: format_dict[display_rvol_col] = "{:.2f}x"
    if display_mkt_cap_col: format_dict[display_mkt_cap_col] = "${:,.2f} B"

    styler = df_show.style.format(format_dict)
    if display_chg_col: styler = styler.map(color_change, subset=[display_chg_col])
    if display_rvol_col: styler = styler.map(color_rvol, subset=[display_rvol_col])
    if display_amt_col:
        try: styler = styler.bar(subset=[display_amt_col], color='#333333', vmin=0)
        except: pass
    styler = styler.hide(axis="index")
    if is_watchlist: styler = styler.set_properties(**{'font-size': '1.05em', 'border-bottom': '1px solid #444'})
    styler = styler.set_properties(subset=['細分產業'], **{'font-size': '0.8em', 'color': '#aaa'})

    html = styler.to_html(table_id=table_id)
    html = html.replace('<table id="', '<table class="sortable" id="')
    return html

def add_rank_column(df):
    df = df.copy().reset_index(drop=True)
    df['Rank'] = df.index + 1
    return df

def generate_section_html(df, period_name, title_prefix, is_active=False):
    exclude_list = ['BTC-USD'] + INDICES_TICKERS
    df_clean = df[~df['Code'].isin(exclude_list)].copy()
    
    if period_name == 'Daily': col_amt, col_chg = 'Daily_Amount_B', 'Daily_Chg%'
    elif period_name == 'Weekly': col_amt, col_chg = 'Weekly_Amount_B', 'Weekly_Chg%'
    else: col_amt, col_chg = 'Monthly_Amount_B', 'Monthly_Chg%'

    for col in [col_amt, col_chg, 'RVOL', 'Market_Cap_B']: 
        if col in df_clean.columns: df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0)

    df_amt = add_rank_column(df_clean.sort_values(by=col_amt, ascending=False).head(50))
    html_amt = style_dataframe(df_amt, f"tbl_{period_name}_amt", period_name)

    df_mkt = add_rank_column(df_clean.sort_values(by='Market_Cap_B', ascending=False).head(20))
    html_mkt = style_dataframe(df_mkt, f"tbl_{period_name}_mkt", period_name, sort_by_mkt_cap=True, is_watchlist=True)

    df_rvol = add_rank_column(df_clean[df_clean[col_amt] > 0.01].sort_values(by='RVOL', ascending=False).head(50))
    html_rvol = style_dataframe(df_rvol, f"tbl_{period_name}_rvol", period_name, sort_by_rvol=True)

    df_bull = add_rank_column(df_clean.sort_values(by=col_chg, ascending=False).head(50))
    html_bull = style_dataframe(df_bull, f"tbl_{period_name}_bull", period_name)

    df_bear = add_rank_column(df_clean.sort_values(by=col_chg, ascending=True).head(50))
    html_bear = style_dataframe(df_bear, f"tbl_{period_name}_bear", period_name)

    display_style = "block" if is_active else "none"
    return f"""
    <div id="tab-{period_name}" class="tab-content" style="display: {display_style};">
        <div class="section">
            <h2 class="section-title">{title_prefix}</h2>
            
            <div class="section" style="border: 2px solid #9c27b0; background: #0d1319; margin-bottom: 20px;">
                <h3 style="color: #ba68c8; margin-top:0;">🏆 美股市值排行 Top 20 (Market Cap Giants)</h3>
                {html_mkt}
            </div>

            <div class="row">
                <div class="col">
                    <h3>💰 資金重心 Top 50 (Turnover)</h3>
                    {html_amt}
                </div>
                <div class="col">
                    <h3>🔥 真實熱門 Top 50 (High RVOL)</h3>
                    <p style="color:#aaa; font-size:0.85em; margin-bottom:5px;">*篩選: 成交額>0.01B 且 爆發量能最大</p>
                    {html_rvol}
                </div>
            </div>
            <div class="row">
                <div class="col"><h3>🚀 猛牛榜 Top 50</h3>{html_bull}</div>
                <div class="col"><h3>🐻 慘熊榜 Top 50</h3>{html_bear}</div>
            </div>
        </div>
    </div>
    """

def generate_indices_html(df):
    mask = df['Code'].isin(INDICES_TICKERS)
    df_idx = df[mask].copy()
    df_idx['Code'] = pd.Categorical(df_idx['Code'], categories=INDICES_TICKERS, ordered=True)
    df_idx = df_idx.sort_values('Code')
    return f"""
    <div class="section" style="border: 2px solid #a3b18a; background: #0d1319;">
        <h2 class="section-title" style="border-left: none; padding-left: 0; color: #a3b18a;">📉 市場核心指數 (Major Indices)</h2>
        {style_dataframe(df_idx, "tbl_indices", "Daily", is_watchlist=True)}
    </div>
    """

def generate_commodities_html(df):
    mask = df['Code'].isin(COMMODITY_TICKERS)
    df_cmd = df[mask].copy()
    df_cmd['Code'] = pd.Categorical(df_cmd['Code'], categories=COMMODITY_TICKERS, ordered=True)
    df_cmd = df_cmd.sort_values('Code')
    return f"""
    <div class="section" style="border: 2px solid #e67e22; background: #0d1319;">
        <h2 class="section-title" style="border-left: none; padding-left: 0; color: #e67e22;">🧱 關鍵原物料 (Commodities)</h2>
        {style_dataframe(df_cmd, "tbl_commodities", "Daily", is_watchlist=True)}
    </div>
    """

def generate_watchlist_html(df):
    mask = df['Code'].isin(WATCHLIST_TICKERS)
    df_watch = df[mask].copy()
    df_watch['Code'] = pd.Categorical(df_watch['Code'], categories=WATCHLIST_TICKERS, ordered=True)
    df_watch = df_watch.sort_values('Code')
    df_watch = add_rank_column(df_watch)
    return f"""
    <div class="section" style="border: 2px solid #4db8ff; background: #0d1319;">
        <h2 class="section-title" style="border-left: none; padding-left: 0; color: #4db8ff;">👀 美股重點觀察股 (Key Watchlist)</h2>
        {style_dataframe(df_watch, "tbl_watchlist", "Daily", is_watchlist=True)}
    </div>
    """

def create_current_link(path):
    with open(os.path.join(BASE_DIR, "market_dashboard_current.html"), "w", encoding="utf-8") as f:
        f.write(f'<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0; url={path}" /></head></html>')

def generate_html_report():
    sentiment = load_sentiment_data()
    ai_data = load_ai_data()
    
    # 更新時間 (UTC+8)
    now_tw = datetime.datetime.now(TZ_TW)
    now_str = now_tw.strftime("%Y-%m-%d %H:%M:%S")

    try:
        df_daily = pd.read_csv(os.path.join(TARGET_DIR, f"rank_daily_{DATE_STR}.csv"))
        for col in ['Sector', 'Industry']:
            if col not in df_daily.columns: df_daily[col] = 'Other'
            df_daily[col] = df_daily[col].fillna('Other')
            
        try: df_weekly = pd.read_csv(os.path.join(TARGET_DIR, f"rank_weekly_{DATE_STR}.csv"))
        except: df_weekly = pd.DataFrame()
        try: df_monthly = pd.read_csv(os.path.join(TARGET_DIR, f"rank_monthly_{DATE_STR}.csv"))
        except: df_monthly = pd.DataFrame()
    except Exception as e:
        print(f"❌ 讀取 CSV 失敗: {e}"); return

    # 生成各組件
    html_gauge = generate_gauge_html(sentiment)
    html_ai = generate_ai_section_html(ai_data)
    treemap_json = generate_treemap_data(df_daily)
    html_heatmap_script = generate_heatmap_script(treemap_json)
    html_heatmap_div = '<div class="section" style="padding: 0;"><div id="heatmap-chart" style="width: 100%; height: 600px;"></div></div>'
    
    html_indices = generate_indices_html(df_daily)
    html_commodities = generate_commodities_html(df_daily)
    html_watchlist = generate_watchlist_html(df_daily)
    
    html_daily = generate_section_html(df_daily, 'Daily', '📅 當日戰況', True)
    html_weekly = generate_section_html(df_weekly, 'Weekly', '🗓️ 本週戰況', False)
    html_monthly = generate_section_html(df_monthly, 'Monthly', '📊 本月戰況', False)

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>美股戰情室 ({DATE_STR})</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; background-color: #0e1117; color: #e0e0e0; padding: 20px; margin: 0; }}
            header {{ text-align: center; margin-bottom: 30px; border-bottom: 1px solid #333; padding-bottom: 20px; }}
            h1 {{ color: #4db8ff; margin: 0; }}
            .timestamp {{ color: #888; font-size: 0.9em; }}
            .section {{ margin-bottom: 40px; background: #161b22; padding: 25px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); }}
            .section-title {{ color: #ffd700; border-left: 5px solid #ffd700; padding-left: 10px; }}
            .row {{ display: flex; gap: 20px; flex-wrap: wrap; margin-top: 20px; }}
            .col {{ flex: 1; min-width: 350px; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
            th {{ background-color: #21262d; color: #f0f6fc; padding: 12px 8px; text-align: left; position: sticky; top: 0; }}
            td {{ padding: 10px 8px; border-bottom: 1px solid #30363d; color: #c9d1d9; }}
            td:nth-child(1) {{ color: #888; width: 40px; text-align: center; }}
            td:nth-child(2) {{ font-weight: bold; color: #fff; }}
            
            /* AI Card CSS */
            .ai-container {{ display: flex; gap: 20px; flex-wrap: wrap; }}
            .ai-card {{ 
                flex: 1; min-width: 300px; 
                background: #21262d; border-radius: 8px; padding: 15px; 
                border: 1px solid #30363d; box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            }}
            .ai-header {{ display: flex; align-items: center; gap: 10px; padding-left: 10px; margin-bottom: 15px; background: #161b22; padding: 10px; border-radius: 4px; }}
            .ai-symbol {{ font-size: 1.4em; font-weight: bold; color: #fff; }}
            .ai-name {{ font-size: 0.9em; color: #aaa; flex-grow: 1; }}
            .ai-chg {{ font-weight: bold; font-size: 1.1em; }}
            .ai-body p {{ margin: 8px 0; font-size: 0.95em; line-height: 1.5; color: #d0d0d0; display: flex; }}
            .ai-body strong {{ color: #a5d6ff; display: inline-block; min-width: 110px; white-space: nowrap; }}

            .tab-container {{ display: flex; justify-content: center; gap: 10px; margin-bottom: 20px; }}
            .tab-button {{ background: #21262d; color: #c9d1d9; border: 1px solid #30363d; padding: 10px 24px; cursor: pointer; border-radius: 6px; }}
            .tab-button.active {{ background: #1f6feb; color: #fff; border-color: #1f6feb; }}
            .tab-content {{ animation: fadeIn 0.3s; }}
            @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
            
            /* Gauge CSS (維持不變) */
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
            <h1>美股資金流向戰情日報 <span style="font-size: 0.6em; color: #aaa;">(美股收盤: {US_DATE_STR})</span></h1>
            <div class="timestamp">更新時間: {now_str} (UTC+8)</div>
        </header>
        
        {html_gauge}
        {html_ai}
        {html_heatmap_div}
        
        <div class="row">
            <div class="col">{html_indices}</div>
            <div class="col">{html_commodities}</div>
        </div>
        
        {html_watchlist}
        
        <div class="tab-container">
            <button class="tab-button active" onclick="openTab('Daily')">📅 當日戰況</button>
            <button class="tab-button" onclick="openTab('Weekly')">🗓️ 本週戰況</button>
            <button class="tab-button" onclick="openTab('Monthly')">📊 本月戰況</button>
        </div>
        {html_daily} {html_weekly} {html_monthly}
        
        {html_heatmap_script}
        
        <script>
            function openTab(name) {{
                var contents = document.getElementsByClassName("tab-content");
                for(var i=0; i<contents.length; i++) contents[i].style.display = "none";
                var btns = document.getElementsByClassName("tab-button");
                for(var i=0; i<btns.length; i++) btns[i].classList.remove("active");
                document.getElementById("tab-"+name).style.display = "block";
                event.currentTarget.classList.add("active");
            }}
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
    
    out_path = os.path.join(TARGET_DIR, f"market_dashboard_{DATE_STR}.html")
    with open(out_path, "w", encoding="utf-8") as f: f.write(full_html)
    print(f"✅ 報表生成: {out_path}")
    create_current_link(f"{YYYY}/{MM}/market_dashboard_{DATE_STR}.html")

if __name__ == "__main__":
    generate_html_report()
