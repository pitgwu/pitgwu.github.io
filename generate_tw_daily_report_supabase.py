import pandas as pd
import yfinance as yf
import requests
import os
import urllib3
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from io import StringIO
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text  # ✨ 新增：用於連線 Supabase

# 修正 1: 直接使用匯入的 timezone 與 timedelta，不需要再加 datetime. 前綴
TZ_TW = timezone(timedelta(hours=8))
# 修正 2: datetime 已經是類別，直接呼叫 .now() 即可，不需要寫 datetime.datetime.now()
NOW = datetime.now(TZ_TW)
DATE_STR = NOW.strftime("%Y%m%d")

# 忽略期交所憑證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===========================
# 配置區
# ===========================
# ✨ 修改：設定 Supabase 連線字串
# 格式通常為: postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres
# 建議將此設定放在環境變數中，或者在此處直接填入
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

if not SUPABASE_DB_URL:
    raise RuntimeError("❌ SUPABASE_DB_URL 環境變數未設定")

# 輸出目錄設定
BASE_OUTPUT_DIR = "tw_stock_dashboard"

TOP_N = 100
LOOKBACK_DAYS = 365 

# 指數清單
INDICES_DICT = {
    "^TWII": "加權指數", 
    "^TWOII": "櫃買指數", 
    "^N225": "🇯🇵 日經 225", 
    "^KS11": "🇰🇷 韓國 KOSPI", 
    "000001.SS": "🇨🇳 上證指數"
}

CORE_WEIGHTS = ["2330.TW", "2317.TW", "2454.TW"]

# ===========================
# 1. 資料庫連線輔助
# ===========================
def get_db_engine():
    """建立並回傳資料庫引擎"""
    try:
        engine = create_engine(SUPABASE_DB_URL)
        return engine
    except Exception as e:
        print(f"❌ 資料庫連線設定錯誤: {e}")
        return None

# ===========================
# 2. 輔助函式
# ===========================
def get_yahoo_link(symbol, name):
    if symbol.startswith("^") or symbol.endswith(".SS") or symbol == "VIXTWN":
        return f'<a href="https://finance.yahoo.com/quote/{symbol}" target="_blank" class="stock-link">{name}<br><small>{symbol}</small></a>'
    
    display_name = name if name and str(name) != "nan" else symbol
    if len(str(display_name)) > 6: display_name = str(display_name)[:6] + ".."
        
    return f'<a href="https://tw.stock.yahoo.com/quote/{symbol}" target="_blank" class="stock-link">{display_name}<br><small>{symbol}</small></a>'

def format_number(val, is_price=False, is_idx=False):
    if pd.isna(val): return "-"
    if is_idx: return f"{val:,.2f}"
    if is_price: return f"{val:.2f}"
    return f"{int(val):,}"

def get_color_style(val):
    try:
        if val > 0: return 'class="t-up"'
        if val < 0: return 'class="t-down"'
    except: pass
    return ''

def format_display_date(date_str, period_type):
    weekdays = ['(一)', '(二)', '(三)', '(四)', '(五)', '(六)', '(日)']
    try:
        if period_type == 'D':
            dt = datetime.strptime(str(date_str), '%Y-%m-%d')
            return f"{dt.strftime('%Y-%m-%d')} {weekdays[dt.weekday()]}"
        elif period_type == 'W':
            if '/' in date_str:
                start, end = date_str.split('/')
                s_dt = datetime.strptime(start, '%Y-%m-%d')
                e_dt = datetime.strptime(end, '%Y-%m-%d')
                return f"{s_dt.strftime('%m/%d')} {weekdays[s_dt.weekday()]} ~ {e_dt.strftime('%m/%d')} {weekdays[e_dt.weekday()]}"
        elif period_type == 'M': return f"{date_str} 月報"
    except: return str(date_str)
    return str(date_str)

# ===========================
# 3. 資料抓取 (VIX)
# ===========================
def fetch_tw_vix_taifex():
    """
    🔥 VIX 三重保險版 (Supabase 整合版)
    """
    print("   🔍 嘗試抓取台指 VIX...")
    
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.taifex.com.tw/cht/index",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
    session.headers.update(headers)

    # --- Plan A: 期交所歷史資料 ---
    try:
        session.get("https://www.taifex.com.tw/cht/index", timeout=5, verify=False)
        url_hist = "https://www.taifex.com.tw/cht/2/vixData"
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        payload = {'queryStartDate': start_date.strftime('%Y/%m/%d'), 'queryEndDate': end_date.strftime('%Y/%m/%d')}
        
        session.headers.update({"Referer": "https://www.taifex.com.tw/cht/2/vixData"})
        res = session.post(url_hist, data=payload, timeout=10, verify=False)
        res.encoding = 'utf-8'
        
        dfs = pd.read_html(StringIO(res.text))
        for df in dfs:
            if "日期" in str(df.columns) and "收盤價" in str(df.columns):
                df = df.sort_values(by=df.columns[0])
                latest = df.iloc[-1]
                price = float(latest['收盤價'])
                pct = 0.0
                if len(df) >= 2:
                    prev = float(df.iloc[-2]['收盤價'])
                    if prev > 0: pct = ((price - prev) / prev) * 100
                print(f"      [DEBUG] Plan A (期交所歷史) 成功: {price}")
                return price, pct
    except: pass

    # --- Plan B: 期交所即時看板 ---
    try:
        url_real = "https://www.taifex.com.tw/cht/7/vixMinNew"
        res = session.get(url_real, timeout=10, verify=False)
        res.encoding = 'utf-8'
        dfs = pd.read_html(StringIO(res.text))
        for df in dfs:
            if "指數" in str(df.columns) or "成交指數" in str(df.columns):
                row = df.iloc[-1]
                price = 0.0
                for c in ['成交指數', '指數']:
                    if c in row: 
                        price = float(row[c]); break
                if price > 0:
                    print(f"      [DEBUG] Plan B (期交所即時) 成功: {price}")
                    return price, 0.0
    except: pass

    # --- Plan C: HiStock ---
    try:
        print("      [DEBUG] 切換至 Plan C (HiStock)...")
        url_hi = "https://histock.tw/index/VIX"
        res = requests.get(url_hi, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        dfs = pd.read_html(StringIO(res.text))
        for df in dfs:
            if "指數" in df.columns and "漲跌" in df.columns:
                row = df.iloc[0]
                price = float(row['指數'])
                raw_pct = str(row.get('幅度', row.get('漲跌幅', 0)))
                pct = float(raw_pct.replace('%', '').replace('+', ''))
                print(f"      [DEBUG] Plan C (HiStock) 成功: {price} ({pct}%)")
                return price, pct
    except Exception as e:
        print(f"      [DEBUG] Plan C 失敗: {e}")

    print("      ⚠️ 放棄 VIX 抓取")
    return None, 0.0

def fetch_indices_data():
    print("🌍 正在更新亞股指數 & VIX...")
    data_list = []
    tickers = list(INDICES_DICT.keys())
    try:
        df = yf.download(tickers, period="5d", progress=False)
        if len(tickers) > 1: closes = df['Close']
        else: closes = pd.DataFrame({tickers[0]: df['Close']})

        for sym, name in INDICES_DICT.items():
            try:
                s = closes[sym].dropna()
                if s.empty: continue
                price = s.iloc[-1]
                prev = s.iloc[-2]
                pct = ((price - prev) / prev) * 100
                data_list.append({"symbol": sym, "name": name, "industry": "指數", "close": price, "change_pct": pct, "volume": 0})
            except: pass
    except: pass
    
    # 🔥 VIX
    vix_val, vix_pct = fetch_tw_vix_taifex()
    if vix_val:
        data_list.append({"symbol": "VIXTWN", "name": "台指 VIX", "industry": "避險", "close": vix_val, "change_pct": vix_pct, "volume": 0})

    return pd.DataFrame(data_list)

# ===========================
# 4. 資料庫讀取 (改為 Supabase/SQLAlchemy)
# ===========================
def load_db_data(period_type):
    engine = get_db_engine()
    if not engine: return None, "資料庫連線失敗"

    df = None
    latest_date_str = "Unknown"
    
    try:
        # 使用 context manager 自動管理連線
        with engine.connect() as conn:
            if period_type == 'D':
                # 取得最新日期
                res = conn.execute(text("SELECT MAX(date) FROM stock_prices")).fetchone()
                if res and res[0]:
                    latest_date_str = str(res[0])
                    print(f"   [DEBUG] 資料庫最新日期: {latest_date_str}")
                    
                    # 讀取當日股價
                    df = pd.read_sql(text(f"SELECT * FROM stock_prices WHERE date = '{latest_date_str}'"), conn)
                    
                    # 取得前一日日期以計算漲跌
                    res_prev = conn.execute(text(f"SELECT MAX(date) FROM stock_prices WHERE date < '{latest_date_str}'")).fetchone()
                    if res_prev and res_prev[0]:
                        prev_date = str(res_prev[0])
                        df_prev = pd.read_sql(text(f"SELECT symbol, close as prev_close FROM stock_prices WHERE date = '{prev_date}'"), conn)
                        df = df.merge(df_prev, on='symbol', how='left')
                        df['change_pct'] = ((df['close'] - df['prev_close']) / df['prev_close']) * 100
                    else:
                        df['change_pct'] = 0.0
            
            else:
                # 週線或月線
                table = 'stock_weekly_k' if period_type == 'W' else 'stock_monthly_k'
                try:
                    res = conn.execute(text(f"SELECT MAX(period) FROM {table}")).fetchone()
                    if res and res[0]:
                        latest_date_str = str(res[0])
                        df = pd.read_sql(text(f"SELECT * FROM {table} WHERE period = '{latest_date_str}'"), conn)
                        df['change_pct'] = ((df['close'] - df['open']) / df['open']) * 100
                except Exception as e:
                    print(f"   [DEBUG] 週/月資料讀取異常: {e}")

            if df is None or df.empty:
                print("   [DEBUG] 載入資料失敗 (df 為空)")
                return None, "無資料"

            # 讀取股票資訊 (名稱、產業)
            try:
                info_df = pd.read_sql(text("SELECT symbol, name, industry FROM stock_info"), conn)
                df = df.merge(info_df, on='symbol', how='left')
                df['name'] = df['name'].fillna(df['symbol'])
                df['industry'] = df['industry'].fillna('其他')
            except:
                # 備用方案：只讀取名稱表
                try:
                    names = pd.read_sql(text("SELECT symbol, name FROM stock_names"), conn)
                    name_map = dict(zip(names['symbol'], names['name']))
                    df['name'] = df['symbol'].map(name_map).fillna(df['symbol'])
                except:
                    df['name'] = df['symbol']
                df['industry'] = '其他'

            # 讀取法人買賣超 (僅日報需要)
            try:
                if period_type == 'D':
                    inst = pd.read_sql(text(f"SELECT symbol, foreign_net, trust_net, dealer_net FROM institutional_investors WHERE date = '{latest_date_str}'"), conn)
                elif period_type == 'W' and '/' in latest_date_str:
                    s, e = latest_date_str.split('/')
                    inst = pd.read_sql(text(f"SELECT symbol, SUM(foreign_net) as foreign_net, SUM(trust_net) as trust_net, SUM(dealer_net) as dealer_net FROM institutional_investors WHERE date BETWEEN '{s}' AND '{e}' GROUP BY symbol"), conn)
                elif period_type == 'M':
                    inst = pd.read_sql(text(f"SELECT symbol, SUM(foreign_net) as foreign_net, SUM(trust_net) as trust_net, SUM(dealer_net) as dealer_net FROM institutional_investors WHERE date LIKE '{latest_date_str}%' GROUP BY symbol"), conn)
                
                if not inst.empty:
                    df = df.merge(inst, on='symbol', how='left')
            except: pass

    except Exception as e:
        print(f"❌ 資料庫錯誤: {e}")
        return None, "資料庫錯誤"
    
    # 填補空值
    for c in ['change_pct', 'volume', 'foreign_net', 'trust_net', 'dealer_net']:
        if c in df.columns: df[c] = df[c].fillna(0)
    
    df['turnover_billion'] = (df['close'] * df['volume']) / 100000000
    
    return df, latest_date_str

# ===========================
# 5. 核心計算模組 & 圖表
# ===========================

# --- A. 市場廣度 (多空排列) ---
def calculate_market_breadth_html():
    print("📊 正在計算全市場多空排列 (Market Breadth)...")
    
    engine = get_db_engine()
    if not engine: return "<p>資料庫連線失敗</p>"

    start_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS + 120)).strftime("%Y-%m-%d")
    
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(f"SELECT date, symbol, close FROM stock_prices WHERE date >= '{start_date}'"), conn)
    except:
        return "<div class='error-msg'>資料讀取失敗</div>"

    if df.empty: return "<p>資料不足</p>"

    df['date'] = pd.to_datetime(df['date'])
    close_matrix = df.pivot(index='date', columns='symbol', values='close')
    
    ma5 = close_matrix.rolling(window=5).mean()
    ma10 = close_matrix.rolling(window=10).mean()
    ma20 = close_matrix.rolling(window=20).mean()
    ma60 = close_matrix.rolling(window=60).mean()

    short_bull = ((ma5 > ma10) & (ma10 > ma20)).sum(axis=1)
    short_bear = ((ma5 < ma10) & (ma10 < ma20)).sum(axis=1)
    long_bull = ((ma10 > ma20) & (ma20 > ma60)).sum(axis=1)
    long_bear = ((ma10 < ma20) & (ma20 < ma60)).sum(axis=1)
    
    total_stocks = close_matrix.count(axis=1).replace(0, 1)
    
    res = pd.DataFrame({
        'short_bull_pct': (short_bull / total_stocks) * 100,
        'short_bear_pct': (short_bear / total_stocks) * 100,
        'long_bull_pct': (long_bull / total_stocks) * 100,
        'long_bear_pct': (long_bear / total_stocks) * 100
    }).dropna()
    
    # 抓取大盤
    try:
        twii = yf.download("^TWII", start=start_date, progress=False)
        if not twii.empty:
            if isinstance(twii.columns, pd.MultiIndex):
                try: twii_close = twii.xs('Close', axis=1, level=0)
                except: twii_close = twii['Close']
            else: twii_close = twii['Close']
            
            if isinstance(twii_close, pd.DataFrame): twii_close = twii_close.iloc[:, 0]
            if twii_close.index.tz is not None: twii_close.index = twii_close.index.tz_localize(None)
            res = res.join(twii_close.rename("TWII"))
        else: res['TWII'] = 0
    except: res['TWII'] = 0
    
    res = res.dropna()

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08,
        row_heights=[0.4, 0.3, 0.3],
        subplot_titles=("<b>加權指數</b>", "<b>短線多空排列 (5>10>20)</b>", "<b>長線多空排列 (10>20>60)</b>")
    )

    fig.add_trace(go.Scatter(x=res.index, y=res['TWII'], mode='lines', name='加權指數', line=dict(color='#FFD700', width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=res.index, y=res['short_bull_pct'], mode='lines', name='短多(紅)', line=dict(color='#FF3333', width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=res.index, y=res['short_bear_pct'], mode='lines', name='短空(綠)', line=dict(color='#00CC66', width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=res.index, y=res['long_bull_pct'], mode='lines', name='長多(紅)', line=dict(color='#FF3333', width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=res.index, y=res['long_bear_pct'], mode='lines', name='長空(綠)', line=dict(color='#00CC66', width=1.5)), row=3, col=1)

    for r in [2, 3]:
        fig.add_hline(y=50, line_dash="dash", line_color="#555", opacity=0.8, row=r, col=1)

    fig.update_layout(
        template="plotly_dark", height=600, 
        margin=dict(l=50, r=30, t=50, b=40),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        legend=dict(orientation="h", y=1.05, x=0.5, xanchor="center", bgcolor="rgba(0,0,0,0)")
    )
    return fig.to_html(full_html=False, include_plotlyjs='cdn', config={'displayModeBar': False})

# --- B. 類股成交比重 ---
def generate_sector_turnover_html(df):
    if df is None or df.empty or 'industry' not in df.columns:
        return "<div class='card'>無產業數據</div>"

    print("📊 正在計算產業資金流向...")

    mask = (
        ~df['symbol'].str.startswith('00') & 
        (df['industry'] != '其他') & 
        (df['industry'].notna())
    )
    df_sec = df[mask].copy()
    df_sec['turnover'] = df_sec['close'] * df_sec['volume']
    
    sector_stats = df_sec.groupby('industry').agg(
        total_turnover=('turnover', 'sum'),
        avg_change=('change_pct', 'mean')
    ).reset_index()

    market_turnover = sector_stats['total_turnover'].sum()
    sector_stats['ratio'] = (sector_stats['total_turnover'] / market_turnover) * 100
    sector_stats = sector_stats.sort_values('ratio', ascending=False)
    
    # Pie Chart
    top_n = 15
    if len(sector_stats) > top_n:
        top_sec = sector_stats.head(top_n).copy()
        other_turnover = sector_stats.iloc[top_n:]['total_turnover'].sum()
        other_row = pd.DataFrame([{
            'industry': '其他產業', 
            'total_turnover': other_turnover, 
            'ratio': (other_turnover/market_turnover)*100,
            'avg_change': 0
        }])
        plot_df = pd.concat([top_sec, other_row], ignore_index=True)
    else:
        plot_df = sector_stats.copy()

    fig = go.Figure(data=[go.Pie(
        labels=plot_df['industry'], 
        values=plot_df['total_turnover'],
        hole=.4,
        textinfo='label+percent',
        insidetextorientation='radial',
        marker=dict(colors=px.colors.qualitative.Pastel)
    )])

    # 🔥 版面優化：放大圖表高度 (450)
    fig.update_layout(
        title_text="<b>各產業成交比重 (資金流向)</b>",
        template="plotly_dark",
        height=450,
        margin=dict(l=10, r=10, t=40, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        showlegend=False
    )
    pie_html = fig.to_html(full_html=False, include_plotlyjs=False, config={'displayModeBar': False})

    # Table
    table_html = f'''
    <div class="card">
        <h3>💰 類股資金成交比重</h3>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th width="10%">排名</th>
                        <th width="30%">類股</th>
                        <th width="20%">成交比重</th>
                        <th width="20%">平均漲跌</th>
                        <th width="20%">成交值(億)</th>
                    </tr>
                </thead>
                <tbody>
    '''
    
    for i, row in enumerate(sector_stats.itertuples(), 1):
        style = 'class="t-up"' if row.avg_change > 0 else ('class="t-down"' if row.avg_change < 0 else '')
        ratio_str = f"{row.ratio:.2f}%"
        change_str = f"{row.avg_change:+.2f}%"
        val_str = f"{row.total_turnover / 100000000:.2f}"
        rank_cls = str(i)
        if i == 1: rank_cls = "🥇"
        elif i == 2: rank_cls = "🥈"
        elif i == 3: rank_cls = "🥉"

        table_html += f'''
            <tr>
                <td>{rank_cls}</td>
                <td><span class="ind-badge">{row.industry}</span></td>
                <td><div class="bar-container"><div class="bar-fill" style="width:{min(row.ratio*2, 100)}%;"></div><span>{ratio_str}</span></div></td>
                <td {style}>{change_str}</td>
                <td>{val_str}</td>
            </tr>
        '''
    
    table_html += "</tbody></table></div></div>"

    # 🔥 佈局優化：使用 1fr 1fr
    return f"""
    <div class="grid-container" style="grid-template-columns: 1fr 1fr;">
        <div class="chart-container" style="display:flex; align-items:center; justify-content:center;">
            {pie_html}
        </div>
        {table_html}
    </div>
    """

def get_ranking_html(df, title, sort_col, ascend, value_fmt_func=None, limit=TOP_N, show_rank=True):
    if df is None or df.empty or sort_col not in df.columns: return ""
    df_sorted = df.sort_values(sort_col, ascending=ascend).head(limit).copy()
    
    html = f'''<div class="card"><h3>{title}</h3><div class="table-wrapper"><table><thead><tr>{'<th>排名</th>' if show_rank else ''}<th>名稱</th><th>產業</th><th>收盤</th><th>漲跌</th><th>成交量</th><th>數值</th></tr></thead><tbody>'''
    
    for i, row in enumerate(df_sorted.itertuples(), 1):
        sym = row.symbol
        name = getattr(row, 'name', sym)
        ind = getattr(row, 'industry', '')
        if not ind or pd.isna(ind): ind = ''
        
        close = row.close
        pct = row.change_pct
        vol = row.volume
        target_val = getattr(row, sort_col)
        
        link = get_yahoo_link(sym, name)
        is_idx = True if sym.startswith("^") or sym.endswith(".SS") or sym == "VIXTWN" else False
        
        close_str = format_number(close, is_price=True, is_idx=is_idx)
        pct_str = f"{pct:+.2f}%"
        vol_str = format_number(vol) if not is_idx else "-"
        target_str = str(target_val)
        if value_fmt_func:
            try: target_str = value_fmt_func(target_val)
            except: pass
        
        pct_style = get_color_style(pct)
        target_style = get_color_style(target_val) if sort_col in ['change_pct', 'foreign_net', 'trust_net', 'dealer_net'] else ""

        ind_html = f'<span class="ind-badge">{ind}</span>' if ind and not is_idx else ''

        html += f'''<tr>{'<td>' + str(i) + '</td>' if show_rank else ''}<td>{link}</td><td>{ind_html}</td><td>{close_str}</td><td {pct_style}>{pct_str}</td><td>{vol_str}</td><td {target_style}><strong>{target_str}</strong></td></tr>'''
    html += '</tbody></table></div></div>'
    return html

def generate_tab_content(period_type):
    df, raw_date_str = load_db_data(period_type)
    display_date = format_display_date(raw_date_str, period_type)
    
    if df is None: return f"<div class='error-msg'>{raw_date_str}</div>"
    
    html_parts = []
    
    # 1. 亞股指數
    df_indices = fetch_indices_data()
    if not df_indices.empty:
        html_parts.append(get_ranking_html(df_indices, "🌏 亞洲股市 & VIX", "symbol", True, lambda x: "", limit=10, show_rank=False))

    # 2. 權值觀察
    df_core = df[df['symbol'].isin(CORE_WEIGHTS)]
    df_no_etf = df[~df['symbol'].str.startswith('00')]
    df_top_val = df_no_etf.sort_values('turnover_billion', ascending=False).head(12)
    df_watch = pd.concat([df_core, df_top_val]).drop_duplicates(subset=['symbol'])
    html_parts.append(get_ranking_html(df_watch, "👀 權值觀察", "turnover_billion", False, lambda x: f"{x:.2f} 億", limit=15))

    # 3. 高價股
    html_parts.append(get_ranking_html(df, "👑 高價股", "close", False, lambda x: f"${x:,.0f}", limit=50))

    # 10 大表格
    min_vol = 500000 if period_type == 'D' else 100000
    df_active = df[df['volume'] > min_vol]
    if df_active.empty: df_active = df 

    html_parts.append(get_ranking_html(df_active, "🚀 強勢股", "change_pct", False, lambda x: f"{x:+.2f}%"))
    html_parts.append(get_ranking_html(df_active, "📉 弱勢股", "change_pct", True, lambda x: f"{x:+.2f}%"))
    html_parts.append(get_ranking_html(df, "🔥 熱門量", "volume", False, lambda x: f"{int(x/1000):,} 張"))
    html_parts.append(get_ranking_html(df, "💰 成交值", "turnover_billion", False, lambda x: f"{x:.2f} 億"))
    
    if 'foreign_net' in df.columns:
        html_parts.append(get_ranking_html(df, "✈️ 外資買超", "foreign_net", False, lambda x: f"{int(x/1000):,} 張"))
        html_parts.append(get_ranking_html(df, "💸 外資賣超", "foreign_net", True, lambda x: f"{int(x/1000):,} 張"))
        html_parts.append(get_ranking_html(df, "🏦 投信買超", "trust_net", False, lambda x: f"{int(x/1000):,} 張"))
        html_parts.append(get_ranking_html(df, "📉 投信賣超", "trust_net", True, lambda x: f"{int(x/1000):,} 張"))
        html_parts.append(get_ranking_html(df, "📊 自營買超", "dealer_net", False, lambda x: f"{int(x/1000):,} 張"))
        html_parts.append(get_ranking_html(df, "📉 自營賣超", "dealer_net", True, lambda x: f"{int(x/1000):,} 張"))

    sector_html = ""
    if period_type == 'D':
        sector_html = generate_sector_turnover_html(df)

    final_html = f"<h2>統計日期: {display_date}</h2>"
    
    if not df_indices.empty:
         # 亞股單獨一行
         final_html += f'<div class="grid-container" style="grid-template-columns: 1fr;">{html_parts[0]}</div>'
         html_parts = html_parts[1:]
    
    if sector_html:
        final_html += sector_html

    final_html += '<div class="grid-container">' + "".join(html_parts) + '</div>'
    return final_html

def main():
    print("🚀 正在生成台股戰情日報 (Supabase + VIX救援版)...")
    
    market_breadth_chart = calculate_market_breadth_html()
    
    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <title>台股戰情日報 {DATE_STR}</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            :root {{ --bg: #121212; --card: #1e1e1e; --text: #e0e0e0; --red: #ff5252; --green: #4caf50; --accent: #2196f3; --border: #333; }}
            body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; margin: 0; padding: 20px; }}
            h1 {{ text-align: center; color: var(--accent); letter-spacing: 1px; margin-bottom: 20px; }}
            
            .tabs {{ display: flex; justify-content: center; gap: 10px; margin-bottom: 20px; }}
            .tab-btn {{ background: #333; color: #aaa; border: none; padding: 10px 20px; border-radius: 20px; cursor: pointer; transition: 0.3s; }}
            .tab-btn.active {{ background: var(--accent); color: white; box-shadow: 0 0 10px rgba(33, 150, 243, 0.4); }}
            
            .tab-content {{ display: none; }}
            .tab-content.active {{ display: block; animation: fadeIn 0.5s; }}
            
            /* 固定為雙欄佈局 (1:1) */
            .grid-container {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-bottom: 20px; }}
            
            @media (max-width: 768px) {{
                .grid-container {{ grid-template-columns: 1fr !important; }}
            }}
            
            .card {{ background: var(--card); border-radius: 8px; border: 1px solid var(--border); overflow: hidden; display: flex; flex-direction: column; height: 500px; }}
            .card h3 {{ background: #2c2c2c; margin: 0; padding: 12px 15px; font-size: 1rem; color: var(--accent); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }}
            
            .table-wrapper {{ overflow-y: auto; flex-grow: 1; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
            
            th {{ position: sticky; top: 0; background: #252525; color: #888; padding: 8px; text-align: right; z-index: 1; white-space: nowrap; }}
            th:nth-child(1), th:nth-child(2), th:nth-child(3) {{ text-align: left; }}
            
            td {{ padding: 6px 8px; border-bottom: 1px solid #2a2a2a; text-align: right; color: #ddd; white-space: nowrap; }}
            td:nth-child(1), td:nth-child(2), td:nth-child(3) {{ text-align: left; }}
            
            .t-up {{ color: var(--red) !important; }}
            .t-down {{ color: var(--green) !important; }}
            .stock-link {{ color: var(--text); text-decoration: none; font-weight: bold; }}
            .stock-link small {{ color: #777; font-size: 0.75rem; display: block; }}
            
            .ind-badge {{ background: #334155; color: #94a3b8; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; display: inline-block; }}
            
            .bar-container {{ display: flex; align-items: center; gap: 8px; justify-content: flex-end; }}
            .bar-fill {{ height: 6px; background: var(--accent); border-radius: 3px; }}

            tr td:first-child {{ color: var(--accent); font-weight: bold; }}
            tr:nth-child(1) td:first-child {{ color: #ffd700; }}
            tr:nth-child(2) td:first-child {{ color: #c0c0c0; }}
            tr:nth-child(3) td:first-child {{ color: #cd7f32; }}
            
            .chart-container {{ background: var(--card); border-radius: 8px; border: 1px solid var(--border); padding: 10px; margin-bottom: 20px; }}
            
            ::-webkit-scrollbar {{ width: 6px; }}
            ::-webkit-scrollbar-thumb {{ background: #444; border-radius: 3px; }}
            @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
        </style>
    </head>
    <body>
        <h1>📈 台股戰情日報 ({DATE_STR})</h1>
        
        <div class="tabs">
            <button class="tab-btn active" onclick="openTab('daily')">今日戰報</button>
            <button class="tab-btn" onclick="openTab('weekly')">本週趨勢</button>
            <button class="tab-btn" onclick="openTab('monthly')">本月月報</button>
        </div>
        
        <div id="daily" class="tab-content active">
            <div class="chart-container">
                {market_breadth_chart}
            </div>
            {generate_tab_content('D')}
        </div>
        
        <div id="weekly" class="tab-content">{generate_tab_content('W')}</div>
        <div id="monthly" class="tab-content">{generate_tab_content('M')}</div>
        
        <script>
            function openTab(id) {{
                document.querySelectorAll('.tab-content').forEach(d => d.classList.remove('active'));
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.getElementById(id).classList.add('active');
                event.target.classList.add('active');
            }}
        </script>
    </body>
    </html>
    """
    
    # 輸出邏輯
    now = datetime.now()
    yyyy = now.strftime("%Y")
    mm = now.strftime("%m")
    yyyymmdd = now.strftime("%Y%m%d")
    
    # 1. 建立目錄
    archive_dir = os.path.join(BASE_OUTPUT_DIR, yyyy, mm)
    os.makedirs(archive_dir, exist_ok=True)
    
    # 2. 定義檔名
    archive_filename = f"tw_market_dashboard_{yyyymmdd}.html"
    archive_path = os.path.join(archive_dir, archive_filename)
    
    # 3. 寫入報表
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(html_template)
    
    print(f"✅ [歸檔] 報表已生成：{archive_path}")

    # 4. 更新 Current 捷徑
    current_path = os.path.join(BASE_OUTPUT_DIR, "tw_market_dashboard_current.html")
    rel_path = f"./{yyyy}/{mm}/{archive_filename}"
    
    redirect_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="0; url={rel_path}" />
        <title>Redirecting...</title>
    </head>
    <body>
        <p>正在載入今日最新報表... <a href="{rel_path}">點擊這裡</a></p>
    </body>
    </html>
    """
    
    with open(current_path, "w", encoding="utf-8") as f:
        f.write(redirect_html)
        
    print(f"✅ [捷徑] current 頁面已更新：{current_path} -> {rel_path}")

if __name__ == "__main__":
    main()
