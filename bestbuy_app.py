import streamlit as st
import pandas as pd
import sqlalchemy
import os
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# ===========================
# 1. 資料庫連線與設定
# ===========================
st.set_page_config(page_title="尾盤神探 - 趨勢波段版", layout="wide")

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL") 
if not SUPABASE_DB_URL:
    st.error("❌ 未偵測到 SUPABASE_DB_URL，請設定環境變數。")
    st.stop()

@st.cache_resource
def get_engine():
    return sqlalchemy.create_engine(SUPABASE_DB_URL)

engine = get_engine()

# ===========================
# 2. 資料讀取與預處理
# ===========================
@st.cache_data(ttl=3600)
def load_and_process_data():
    """讀取 365 天資料並預算基礎指標"""
    query = """
    SELECT sp.date, sp.symbol, sp.open, sp.high, sp.low, sp.close, sp.volume, 
           si.name, si.industry
    FROM stock_prices sp
    JOIN stock_info si ON sp.symbol = si.symbol
    WHERE sp.date >= current_date - INTERVAL '400 days' 
    ORDER BY sp.symbol, sp.date
    """
    # 注意：這裡稍微拉長到 400 天，確保有足夠的資料來畫 6 個月前的 MA60
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['symbol', 'date'])
    grouped = df.groupby('symbol')
    
    # 基礎均線
    df['MA5'] = grouped['close'].transform(lambda x: x.rolling(5).mean())
    df['MA10'] = grouped['close'].transform(lambda x: x.rolling(10).mean())
    df['MA20'] = grouped['close'].transform(lambda x: x.rolling(20).mean())
    df['MA60'] = grouped['close'].transform(lambda x: x.rolling(60).mean())
    
    # 比較用數據
    df['prev_close'] = grouped['close'].shift(1)
    df['prev_volume'] = grouped['volume'].shift(1)
    df['pct_change'] = (df['close'] - df['prev_close']) / df['prev_close'] * 100
    
    # 量比
    df['Vol_MA5'] = grouped['volume'].transform(lambda x: x.rolling(5).mean())
    df['vol_ratio'] = df['volume'] / df['Vol_MA5']
    
    return df

# ===========================
# 3. 進階指標計算函式
# ===========================
def calculate_advanced_indicators(df_single):
    """針對單檔股票計算 KD, MACD, CDP"""
    df = df_single.copy()
    
    # --- KD (9, 3, 3) ---
    low_min = df['low'].rolling(9).min()
    high_max = df['high'].rolling(9).max()
    df['RSV'] = (df['close'] - low_min) / (high_max - low_min) * 100
    df['RSV'] = df['RSV'].fillna(50)
    
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    # --- MACD (12, 26, 9) ---
    exp12 = df['close'].ewm(span=12, adjust=False).mean()
    exp26 = df['close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_OSC'] = df['DIF'] - df['MACD']
    
    # --- CDP ---
    prev_high = df['high'].shift(1)
    prev_low = df['low'].shift(1)
    prev_close = df['close'].shift(1)
    
    df['CDP'] = (prev_high + prev_low + 2 * prev_close) / 4
    rng = prev_high - prev_low 
    
    df['AH'] = df['CDP'] + rng
    df['NH'] = 2 * df['CDP'] - prev_low
    df['NL'] = 2 * df['CDP'] - prev_high
    df['AL'] = df['CDP'] - rng
    
    return df

def plot_stock_kline(df_stock, symbol, name, show_vol_profile=False):
    """繪製 K 線圖 (6個月範圍)"""
    
    # 🔥 修改點 1: 取更多資料以確保指標穩定 (200天)
    df_plot = df_stock.tail(200).copy()
    df_plot = calculate_advanced_indicators(df_plot)
    
    # 🔥 修改點 2: 顯示範圍改為 130 天 (約 6 個月)
    df_plot = df_plot.tail(130)
    df_plot['date_str'] = df_plot['date'].dt.strftime('%Y-%m-%d')
    
    fig = make_subplots(
        rows=4, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.01,
        row_heights=[0.5, 0.15, 0.15, 0.2],
        subplot_titles=(f"{symbol} {name} - K線圖 (6個月)", "成交量", "KD", "MACD"),
        specs=[[{"secondary_y": False}], [{}], [{}], [{}]] 
    )

    # 籌碼分布浮水印
    hist_values = []
    if show_vol_profile:
        price_bins = 80 # 增加 bin 數量讓長條圖更細緻
        hist_values, bin_edges = np.histogram(df_plot['close'], bins=price_bins, weights=df_plot['volume'])
        bin_mids = (bin_edges[:-1] + bin_edges[1:]) / 2
        fig.add_trace(go.Bar(
            x=hist_values, y=bin_mids, orientation='h', name='籌碼分布',
            marker_color='rgba(100, 100, 100, 0.15)', hoverinfo='none', xaxis='x5'
        ), row=1, col=1)

    # K線
    fig.add_trace(go.Candlestick(
        x=df_plot['date_str'], open=df_plot['open'], high=df_plot['high'],
        low=df_plot['low'], close=df_plot['close'], name='K線',
        increasing_line_color='red', decreasing_line_color='green'
    ), row=1, col=1)
    
    colors_ma = {
        'MA5': '#FFA500',   # 橘
        'MA10': '#00FFFF',  # 青
        'MA20': '#BA55D3',  # 紫
        'MA60': '#4169E1'   # 寶藍
    }
    for ma in ['MA5', 'MA10', 'MA20', 'MA60']:
        if ma in df_plot.columns:
            fig.add_trace(go.Scatter(
                x=df_plot['date_str'], y=df_plot[ma], mode='lines', 
                name=ma, line=dict(color=colors_ma[ma], width=1.5)
            ), row=1, col=1)

    # CDP
    cdp_config = {'AH': ('gray', 'dot'), 'NH': ('gray', 'dash'), 'CDP': ('yellow', 'dashdot'), 'NL': ('gray', 'dash'), 'AL': ('gray', 'dot')}
    for col, (color, dash) in cdp_config.items():
        fig.add_trace(go.Scatter(
            x=df_plot['date_str'], y=df_plot[col], mode='lines', name=f"CDP-{col}",
            line=dict(color=color, width=1, dash=dash), opacity=0.6, hoverinfo='y+name'
        ), row=1, col=1)

    # 成交量
    colors_vol = ['red' if c >= o else 'green' for c, o in zip(df_plot['close'], df_plot['open'])]
    fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['volume'], name='成交量', marker_color=colors_vol), row=2, col=1)

    # KD & MACD
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['K'], name='K', line=dict(color='orange', width=1)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['D'], name='D', line=dict(color='cyan', width=1)), row=3, col=1)
    for y_line in [20, 80]: fig.add_shape(type="line", x0=0, x1=len(df_plot)-1, y0=y_line, y1=y_line, xref='x3', line=dict(color="gray", dash="dot", width=1), row=3, col=1)

    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['DIF'], name='DIF', line=dict(color='orange', width=1)), row=4, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['MACD'], name='MACD', line=dict(color='cyan', width=1)), row=4, col=1)
    osc_colors = ['red' if v >= 0 else 'green' for v in df_plot['MACD_OSC']]
    fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['MACD_OSC'], name='OSC', marker_color=osc_colors), row=4, col=1)

    layout_update = dict(height=850, xaxis_rangeslider_visible=False, showlegend=False, margin=dict(l=20, r=20, t=30, b=20), bargap=0.05, plot_bgcolor='white', paper_bgcolor='white')
    if show_vol_profile and len(hist_values) > 0:
        layout_update['xaxis5'] = dict(overlaying='x', side='top', showgrid=False, visible=False, range=[0, max(hist_values) * 1.2])
    
    fig.update_layout(**layout_update)
    common_axis_config = dict(type='category', showgrid=False, zeroline=False, showline=True, linecolor='black', mirror=True)
    common_yaxis_config = dict(showgrid=False, zeroline=False, showline=True, linecolor='black', mirror=True, autorange=True)
    
    for r in [1, 2, 3]: fig.update_xaxes(**common_axis_config, row=r, col=1)
    fig.update_xaxes(dtick=10, **common_axis_config, row=4, col=1) # 🔥 dtick 改為 10，因為日期變多了
    fig.update_yaxes(**common_yaxis_config)

    return fig

# ===========================
# 4. Streamlit 主程式
# ===========================
st.title("🔥 尾盤神探 - 趨勢波段版 (6個月)")
st.markdown("---")

# 初始化 session state
if 'ticker_index' not in st.session_state:
    st.session_state.ticker_index = 0
if 'last_selected_rows' not in st.session_state:
    st.session_state.last_selected_rows = []
if 'last_viewed_symbol' not in st.session_state:
    st.session_state.last_viewed_symbol = None
if 'last_sort_option' not in st.session_state:
    st.session_state.last_sort_option = None

with st.spinner("載入數據中..."):
    df_full = load_and_process_data()

available_dates = sorted(df_full['date'].dt.date.unique(), reverse=True)
all_industries = sorted(df_full['industry'].dropna().astype(str).unique().tolist())

# --- 側邊欄 ---
st.sidebar.header("📅 日期與參數")
selected_date = st.sidebar.selectbox("回測日期", available_dates, 0)
st.sidebar.markdown("---")
show_vol_profile = st.sidebar.checkbox("顯示分價量表 (Volume Profile)", value=False)
st.sidebar.markdown("---")
st.sidebar.header("🔢 排序方式")
sort_option = st.sidebar.selectbox("請選擇清單排序", ["漲跌幅 (高→低)", "近月熱度 (高→低)", "量比 (高→低)", "股票代號 (小→大)"])
st.sidebar.markdown("---")
st.sidebar.header("🏭 產業篩選")
selected_industries = st.sidebar.multiselect("選擇產業 (留空則全選)", options=all_industries, default=[])
st.sidebar.markdown("---")
st.sidebar.header("⚙️ 技術參數")
p_change_min = st.sidebar.number_input("漲幅下限 (%)", 0.0, 10.0, 3.0)
p_change_max = st.sidebar.number_input("漲幅上限 (%)", 3.0, 10.0, 6.0)
vol_ratio_min = st.sidebar.number_input("量比最小值", 0.5, 5.0, 1.0)

# ===========================
# 5. 核心篩選與排序邏輯
# ===========================
target_date_ts = pd.Timestamp(selected_date)
df_day = df_full[df_full['date'] == target_date_ts].copy()

if selected_industries:
    df_day = df_day[df_day['industry'].isin(selected_industries)]

def get_selection_mask(df):
    cond_a = (df['MA5'] > df['MA10']) & (df['MA10'] > df['MA20'])
    cond_b = (df['close'] > df['MA10']) & (df['MA10'] > df['MA20'])
    return (
        (df['pct_change'].between(p_change_min, p_change_max)) & 
        (df['vol_ratio'] >= vol_ratio_min) & 
        (df['volume'] > df['prev_volume']) & 
        (cond_a | cond_b) & 
        (df['close'] >= df['MA10'])
    )

mask_today = get_selection_mask(df_day)
results = df_day[mask_today].copy()

if results.empty:
    st.warning(f"⚠️ {selected_date} 在所選條件下無符合股票。")
else:
    with st.spinner("計算排序與熱度..."):
        start_date_hist = target_date_ts - timedelta(days=45)
        end_date_hist = target_date_ts - timedelta(days=1)
        df_hist = df_full[(df_full['date'] >= start_date_hist) & (df_full['date'] <= end_date_hist)].copy()
        mask_hist = get_selection_mask(df_hist)
        df_hist_hits = df_hist[mask_hist]
        hit_counts = df_hist_hits[df_hist_hits['symbol'].isin(results['symbol'])].groupby('symbol').size()
        results['past_hits'] = results['symbol'].map(hit_counts).fillna(0).astype(int)

        if sort_option == "漲跌幅 (高→低)":
            results = results.sort_values(by=['pct_change', 'symbol'], ascending=[False, True])
        elif sort_option == "近月熱度 (高→低)":
            results = results.sort_values(by=['past_hits', 'pct_change', 'symbol'], ascending=[False, False, True])
        elif sort_option == "量比 (高→低)":
            results = results.sort_values(by=['vol_ratio', 'symbol'], ascending=[False, True])
        else: 
            results = results.sort_values(by='symbol', ascending=True)

    display_df = results[['symbol', 'name', 'industry', 'close', 'pct_change', 'vol_ratio', 'past_hits']].copy()
    display_df = display_df.reset_index(drop=True)
    symbol_list = display_df['symbol'].tolist()

    if st.session_state.last_sort_option != sort_option:
        if st.session_state.last_viewed_symbol in symbol_list:
            st.session_state.ticker_index = symbol_list.index(st.session_state.last_viewed_symbol)
        else:
            st.session_state.ticker_index = 0
        st.session_state.last_sort_option = sort_option

    st.success(f"🎉 篩選出 {len(symbol_list)} 檔股票！(目前排序：{sort_option})")
    
    event = st.dataframe(
        display_df.style.format({
            "pct_change": "{:.2f}%", "close": "{:.2f}", 
            "vol_ratio": "{:.2f}", "past_hits": "{:d} 次"
        })
        .background_gradient(subset=['pct_change'], cmap='Reds')
        .background_gradient(subset=['past_hits'], cmap='Blues'),
        on_select="rerun", selection_mode="single-row", use_container_width=True,
        column_config={
            "symbol": "代號", "name": "名稱", "industry": "產業",
            "close": "收盤價", "pct_change": "漲跌幅", "vol_ratio": "量比",
            "past_hits": st.column_config.NumberColumn("🔥 近月入選", format="%d 次")
        }
    )
    
    if event.selection.rows and event.selection.rows != st.session_state.last_selected_rows:
        st.session_state.ticker_index = event.selection.rows[0]
        st.session_state.last_selected_rows = event.selection.rows

    if st.session_state.ticker_index >= len(symbol_list):
        st.session_state.ticker_index = 0

    st.markdown("---")
    st.markdown("### 🔍 個股 K 線檢視")
    
    c1, c2, c_info, c3, c4 = st.columns([1, 1, 4, 1, 1])
    with c1:
        if st.button("⏮️ 最前"): st.session_state.ticker_index = 0
    with c2:
        if st.button("⬅️ 上一檔"): st.session_state.ticker_index = (st.session_state.ticker_index - 1) % len(symbol_list)
    with c3:
        if st.button("下一檔 ➡️"): st.session_state.ticker_index = (st.session_state.ticker_index + 1) % len(symbol_list)
    with c4:
        if st.button("最後 ⏭️"): st.session_state.ticker_index = len(symbol_list) - 1
            
    current_symbol = symbol_list[st.session_state.ticker_index]
    current_info = results[results['symbol'] == current_symbol].iloc[0]
    st.session_state.last_viewed_symbol = current_symbol

    with c_info:
        st.markdown(
            f"<h3 style='text-align: center; color: #FF4B4B; margin: 0;'>"
            f"{st.session_state.ticker_index + 1} / {len(symbol_list)} : "
            f"{current_symbol} {current_info['name']} ({current_info['industry']}) "
            f"漲幅: {current_info['pct_change']:.2f}% | 熱度: {current_info['past_hits']} 次"
            f"</h3>", 
            unsafe_allow_html=True
        )

    df_chart_source = df_full[df_full['symbol'] == current_symbol].sort_values('date')
    df_chart_source = df_chart_source[df_chart_source['date'] <= target_date_ts]
    
    if len(df_chart_source) < 30:
        st.error("歷史資料不足，無法繪製完整圖表。")
    else:
        fig = plot_stock_kline(df_chart_source, current_symbol, current_info['name'], show_vol_profile)
        st.plotly_chart(fig, use_container_width=True)
