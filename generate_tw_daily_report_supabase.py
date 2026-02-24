import pandas as pd
import yfinance as yf
import requests
import os
import urllib3
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from io import StringIO
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

# 忽略期交所憑證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===========================
# 配置區
# ===========================
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

if not SUPABASE_DB_URL:
    raise RuntimeError("❌ SUPABASE_DB_URL 環境變數未設定")

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
# 1. 資料庫連線輔助 (單例模式)
# ===========================
_db_engine = None

def get_db_engine():
    """
    取得資料庫引擎 (Singleton 模式)
    避免重複 create_engine 導致連線數爆滿 (MaxClientsInSessionMode)
    加入 statement_timeout=60000 避免大量歷史資料撈取超時
    """
    global _db_engine
    if _db_engine is None:
        try:
            _db_engine = create_engine(
                SUPABASE_DB_URL, 
                pool_size=5, 
                max_overflow=0,
                pool_pre_ping=True,
                connect_args={'options': '-c statement_timeout=60000'}
            )
        except Exception as e:
            print(f"❌ 資料庫連線設定錯誤: {e}")
            return None
    return _db_engine

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
    print("   🔍 嘗試抓取台指 VIX...")
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.taifex.com.tw/cht/index"
    }
    session.headers.update(headers)

    try:
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
                return price, pct
    except: pass
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
    
    vix_val, vix_pct = fetch_tw_vix_taifex()
    if vix_val:
        data_list.append({"symbol": "VIXTWN", "name": "台指 VIX", "industry": "避險", "close": vix_val, "change_pct": vix_pct, "volume": 0})

    return pd.DataFrame(data_list)

# ===========================
# 4. 資料庫讀取 (基本資料)
# ===========================
def load_db_data(period_type):
    engine = get_db_engine()
    if not engine: return None, "資料庫連線失敗"

    df = None
    latest_date_str = "Unknown"
    
    try:
        with engine.connect() as conn:
            if period_type == 'D':
                res = conn.execute(text("SELECT MAX(date) FROM stock_prices")).fetchone()
                if res and res[0]:
                    latest_date_str = str(res[0])
                    
                    df = pd.read_sql(text(f"SELECT * FROM stock_prices WHERE date = '{latest_date_str}'"), conn)
                    
                    res_prev = conn.execute(text(f"SELECT MAX(date) FROM stock_prices WHERE date < '{latest_date_str}'")).fetchone()
                    if res_prev and res_prev[0]:
                        prev_date = str(res_prev[0])
                        df_prev = pd.read_sql(text(f"SELECT symbol, close as prev_close FROM stock_prices WHERE date = '{prev_date}'"), conn)
                        df = df.merge(df_prev, on='symbol', how='left')
                        df['change_pct'] = ((df['close'] - df['prev_close']) / df['prev_close']) * 100
                    else:
                        df['change_pct'] = 0.0
            
            else:
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
                return None, "無資料"

            try:
                info_df = pd.read_sql(text("SELECT symbol, name, industry FROM stock_info"), conn)
                df = df.merge(info_df, on='symbol', how='left')
                df['name'] = df['name'].fillna(df['symbol'])
                df['industry'] = df['industry'].fillna('其他')
            except:
                df['name'] = df['symbol']
                df['industry'] = '其他'

            try:
                if period_type == 'D':
                    inst = pd.read_sql(text(f"SELECT symbol, foreign_net, trust_net, dealer_net FROM institutional_investors WHERE date = '{latest_date_str}'"), conn)
                    if not inst.empty:
                        df = df.merge(inst, on='symbol', how='left')
            except: pass

    except Exception as e:
        print(f"❌ 資料庫讀取錯誤: {e}")
        return None, f"資料庫錯誤: {str(e)}"
    
    for c in ['change_pct', 'volume', 'foreign_net', 'trust_net', 'dealer_net']:
        if c in df.columns: df[c] = df[c].fillna(0)
    
    df['turnover_billion'] = (df['close'] * df['volume']) / 100000000
    
    return df, latest_date_str

# ===========================
# 5. 市場寬度運算 (MA排列 + 200日新高低)
# ===========================
def calculate_market_breadth_html():
    print("📊 正在計算全市場多空排列 (MA)...")
    engine = get_db_engine()
    if not engine: return "<p>資料庫連線失敗</p>"

    # 往前多抓 120 天作為均線的「暖機期」
    start_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS + 120)).strftime("%Y-%m-%d")
    
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(f"SELECT date, symbol, close FROM stock_prices WHERE date >= '{start_date}'"), conn)
    except:
        return "<div class='error-msg'>資料讀取失敗</div>"

    if df.empty: return "<p>資料不足</p>"

    # 確保時間格式乾淨 (去除可能的時區干擾)
    df['date'] = pd.to_datetime(df['date']).dt.normalize()
    close_matrix = df.pivot(index='date', columns='symbol', values='close')
    
    # 【關鍵修復 1】向前填充 (Forward Fill)
    # 如果某天某檔股票沒有收盤價(NaN)，自動延用前一天的價格，避免 rolling 產生長達數十天的斷層
    close_matrix = close_matrix.ffill()

    # 【關鍵修復 2】加入 min_periods=1
    # 就算剛開始資料筆數不夠，也能及早給出均線數值，不會全部都是 NaN
    ma5 = close_matrix.rolling(window=5, min_periods=1).mean()
    ma10 = close_matrix.rolling(window=10, min_periods=1).mean()
    ma20 = close_matrix.rolling(window=20, min_periods=1).mean()
    ma60 = close_matrix.rolling(window=60, min_periods=1).mean()

    short_bull = ((ma5 > ma10) & (ma10 > ma20)).sum(axis=1)
    short_bear = ((ma5 < ma10) & (ma10 < ma20)).sum(axis=1)
    long_bull = ((ma10 > ma20) & (ma20 > ma60)).sum(axis=1)
    long_bear = ((ma10 < ma20) & (ma20 < ma60)).sum(axis=1)
    
    # 計算有效股票總數 (排除完全沒資料的股票)
    total_stocks = close_matrix.notna().sum(axis=1).replace(0, 1)
    
    res = pd.DataFrame({
        'short_bull_pct': (short_bull / total_stocks) * 100,
        'short_bear_pct': (short_bear / total_stocks) * 100,
        'long_bull_pct': (long_bull / total_stocks) * 100,
        'long_bear_pct': (long_bear / total_stocks) * 100
    })
    
    # 【關鍵修復 3】安全合併加權指數 (TWII)
    try:
        twii = yf.download("^TWII", start=start_date, progress=False)
        if not twii.empty:
            if isinstance(twii.columns, pd.MultiIndex):
                try: twii_close = twii.xs('Close', axis=1, level=0)
                except: twii_close = twii['Close']
            else: twii_close = twii['Close']
            
            if isinstance(twii_close, pd.DataFrame): twii_close = twii_close.iloc[:, 0]
            
            # 確保 yfinance 的日期格式與資料庫完全一致
            twii_close.index = pd.to_datetime(twii_close.index).normalize()
            res = res.join(twii_close.rename("TWII"))
            
            # 將大盤缺漏的日期 (例如台股補班日美股休市) 向前填充，避免 dropna 把有效資料刪除
            res['TWII'] = res['TWII'].ffill().fillna(0)
        else: res['TWII'] = 0
    except: res['TWII'] = 0
    
    # 移除暖機期的資料，只保留我們真正要畫圖的區間 (LOOKBACK_DAYS)
    target_start = pd.to_datetime((datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d"))
    res = res[res.index >= target_start]
    
    # 確保最終沒有異常的 NaN
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

def update_market_breadth_db():
    print("🔍 [200日寬度] 正在智慧更新 200日新高/低資料庫...")
    engine = get_db_engine()
    if not engine: return False
    
    try:
        with engine.connect() as conn:
            dates_df = pd.read_sql("SELECT DISTINCT date FROM stock_prices ORDER BY date DESC LIMIT 300", conn)
            if dates_df.empty:
                print("⚠️ 股價資料庫無資料，跳過寬度計算。")
                return False
                
            available_dates = pd.to_datetime(dates_df['date']).sort_values().tolist()
            
            check_table = text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'market_breadth')")
            table_exists = conn.execute(check_table).scalar()
            
            latest_calc_date = None
            if table_exists:
                latest_df = pd.read_sql("SELECT MAX(date) as max_date FROM market_breadth", conn)
                if not latest_df.empty and pd.notnull(latest_df.iloc[0]['max_date']):
                    latest_calc_date = pd.to_datetime(latest_df.iloc[0]['max_date'])
            
            if latest_calc_date is None:
                print("   🆕 找不到歷史計算紀錄，初始化 (計算近60天)...")
                target_dates = available_dates[-60:]
            else:
                target_dates = [d for d in available_dates if d > latest_calc_date]
                
            if not target_dates:
                print("   ✨ 200日市場寬度已是最新，無需更新。")
                return True
                
            print(f"   ⚙️ 發現 {len(target_dates)} 天新數據需要計算。")
            
            first_target = target_dates[0]
            first_target_idx = available_dates.index(first_target)
            start_idx = max(0, first_target_idx - 200)
            
            fetch_start_date = available_dates[start_idx].strftime('%Y-%m-%d')
            fetch_end_date = target_dates[-1].strftime('%Y-%m-%d')
            
            query_prices = text(f"""
                SELECT symbol, date, close
                FROM stock_prices
                WHERE date >= '{fetch_start_date}' AND date <= '{fetch_end_date}'
            """)
            
            chunks = []
            for chunk in pd.read_sql(query_prices, conn, chunksize=50000):
                chunks.append(chunk)
                
            if not chunks: return False
                
            df_raw = pd.concat(chunks, ignore_index=True)

        # 進行運算 (不需要放在 connection block 內)
        df_raw['date'] = pd.to_datetime(df_raw['date'])
        pivot_df = df_raw.pivot(index='date', columns='symbol', values='close').sort_index()

        max_200 = pivot_df.rolling(window=200, min_periods=1).max()
        min_200 = pivot_df.rolling(window=200, min_periods=1).min()

        is_new_high = (pivot_df >= max_200) & pivot_df.notna()
        is_new_low = (pivot_df <= min_200) & pivot_df.notna()

        result_df = pd.DataFrame({
            'date': pivot_df.index,
            'new_highs': is_new_high.sum(axis=1),
            'new_lows': is_new_low.sum(axis=1),
            'total_stocks': pivot_df.notna().sum(axis=1)
        })

        result_df['total_signals'] = result_df['new_highs'] + result_df['new_lows']
        result_df['net_ratio'] = ((result_df['new_highs'] - result_df['new_lows']) / result_df['total_signals'].replace(0, pd.NA)) * 100
        result_df['net_ratio'] = result_df['net_ratio'].fillna(0).round(2)

        final_insert_df = result_df[result_df['date'].isin(target_dates)].copy()
        final_insert_df = final_insert_df.drop(columns=['total_signals'])
        final_insert_df['date'] = final_insert_df['date'].dt.date

        print(f"   💾 將 {len(final_insert_df)} 筆寬度結果寫入資料庫...")
        final_insert_df.to_sql('market_breadth', engine, if_exists='append', index=False)
        return True
    except Exception as e:
        print(f"❌ 更新200日寬度資料庫失敗: {e}")
        return False

def generate_200d_breadth_html():
    engine = get_db_engine()
    if not engine: return ""
    
    try:
        with engine.connect() as conn:
            df = pd.read_sql("SELECT * FROM market_breadth ORDER BY date DESC LIMIT 60", conn)
        
        if df.empty: return "<p>無市場寬度數據</p>"
            
        df = df.iloc[::-1].reset_index(drop=True)
        df['date_str'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # 紅色線：200日高
        fig.add_trace(go.Scatter(
            x=df['date_str'], y=df['new_highs'], 
            mode='lines', name='200日新高(紅)', 
            line=dict(color='#FF3333', width=2)
        ), secondary_y=False)

        # 綠色線：200日低
        fig.add_trace(go.Scatter(
            x=df['date_str'], y=df['new_lows'], 
            mode='lines', name='200日新低(綠)', 
            line=dict(color='#00CC66', width=2)
        ), secondary_y=False)

        # 藍色線：多空比
        fig.add_trace(go.Scatter(
            x=df['date_str'], y=df['net_ratio'], 
            mode='lines', name='多空比(淨新高%)', 
            line=dict(color='#3498db', width=2)
        ), secondary_y=True)

        fig.update_layout(
            title='<b>近3個月創200日新高/新低家數 與 多空比走勢</b>',
            template="plotly_dark", height=450,
            hovermode='x unified', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=50, r=40, t=50, b=40),
            legend=dict(orientation="h", y=1.05, x=0.5, xanchor="center", bgcolor="rgba(0,0,0,0)")
        )

        fig.update_yaxes(title_text="家數", showgrid=True, gridcolor='#333', secondary_y=False)
        fig.update_yaxes(title_text="多空比 (%)", showgrid=False, zeroline=True, zerolinecolor='rgba(52, 152, 219, 0.5)', zerolinewidth=2, secondary_y=True)

        # 此處 include_plotlyjs=False，因為上面的 MA 圖已經載入過了
        return fig.to_html(full_html=False, include_plotlyjs=False, config={'displayModeBar': False})
    except Exception as e:
        print(f"❌ 產生200日寬度圖表失敗: {e}")
        return ""

# ===========================
# 6. 生成報表與排版
# ===========================
def generate_sector_turnover_html(df):
    if df is None or df.empty or 'industry' not in df.columns:
        return "<div class='card'>無產業數據</div>"

    print("📊 正在計算產業資金流向...")

    mask = (~df['symbol'].str.startswith('00') & (df['industry'] != '其他') & (df['industry'].notna()))
    df_sec = df[mask].copy()
    df_sec['turnover'] = df_sec['close'] * df_sec['volume']
    
    sector_stats = df_sec.groupby('industry').agg(
        total_turnover=('turnover', 'sum'),
        avg_change=('change_pct', 'mean')
    ).reset_index()

    market_turnover = sector_stats['total_turnover'].sum()
    sector_stats['ratio'] = (sector_stats['total_turnover'] / market_turnover) * 100
    sector_stats = sector_stats.sort_values('ratio', ascending=False)
    
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

    fig.update_layout(
        title_text="<b>各產業成交比重 (資金流向)</b>",
        template="plotly_dark",
        height=450,
        margin=dict(l=10, r=10, t=40, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        showlegend=False
    )
    pie_html = fig.to_html(full_html=False, include_plotlyjs=False, config={'displayModeBar': False})

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
    
    if df is None: return f"<div class='error-msg'>資料讀取錯誤: {raw_date_str}</div>"
    
    html_parts = []
    
    df_indices = fetch_indices_data()
    if not df_indices.empty:
        html_parts.append(get_ranking_html(df_indices, "🌏 亞洲股市 & VIX", "symbol", True, lambda x: "", limit=10, show_rank=False))

    df_core = df[df['symbol'].isin(CORE_WEIGHTS)]
    df_no_etf = df[~df['symbol'].str.startswith('00')]
    df_top_val = df_no_etf.sort_values('turnover_billion', ascending=False).head(12)
    df_watch = pd.concat([df_core, df_top_val]).drop_duplicates(subset=['symbol'])
    html_parts.append(get_ranking_html(df_watch, "👀 權值觀察", "turnover_billion", False, lambda x: f"{x:.2f} 億", limit=15))

    html_parts.append(get_ranking_html(df, "👑 高價股", "close", False, lambda x: f"${x:,.0f}", limit=50))

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
         final_html += f'<div class="grid-container" style="grid-template-columns: 1fr;">{html_parts[0]}</div>'
         html_parts = html_parts[1:]
    
    if sector_html:
        final_html += sector_html

    final_html += '<div class="grid-container">' + "".join(html_parts) + '</div>'
    return final_html

# ===========================
# 7. 主程式
# ===========================
def main():
    print("🚀 正在生成台股戰情日報 (整合 200日新高/低 寬度)...")
    
    # 步驟一：確保 200日寬度資料庫是最新的
    update_market_breadth_db()
    
    # 取得當日日期字串
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    
    # 生成各區塊圖表
    market_breadth_ma_chart = calculate_market_breadth_html()
    market_breadth_200d_chart = generate_200d_breadth_html()
    
    html_template = f"""
    <!DOCTYPE html>
    <html ="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>台股戰情日報 {date_str}</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            :root {{ --bg: #121212; --card: #1e1e1e; --text: #e0e0e0; --red: #ff5252; --green: #4caf50; --accent: #2196f3; --border: #333; }}
            body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-seri; padding: 20px; }}
            h1 {{ text-align: center; color: var(--accent); letter-spacing: 1px; margin-bottom: 20px; }}
            
            .tabs {{ display: flex; justify-content: center; gap: 10px; margin-bottom: 20px; }}
            .tab-btn {{ background: #333; color: #aaa; border: none; padding: 10px 20px; border-radius: 20px; cursor: pointer; transition: 0.3s; }}
            .tab-btn.active {{ background: var(--accent); color: white; box-shadow: 0 0 10px rgba(33, 150, 243, 0.4); }}
            
            .tab-content {{ display: none; }}
            .tab-content.active {{ display: block; animation: fadeIn 0.5s; }}
            
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
        <h1>📈 台股戰情日報 <small style="font-size: 0.6em; color: #888;">{date_str}</small></h1>
        
        <div class="tabs">
            <button class="tab-btn active" onclick="openTab('daily')">今日戰報</button>
            <butass="tab-btn" onclick="openTab('weekly')">本週趨勢</button>
            <button class="tab-btn" onclick="openTab('monthly')">本月月報</button>
        </div>
        
        <div id="daily" class="tab-content active">
            <div class="chart-container">
                {market_breadth_ma_chart}
            </div>
            
            <div class="chart-container">
                {market_breadth_200d_chart}
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
      <title>Redirecting.</title>
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
