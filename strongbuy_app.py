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
st.set_page_config(page_title="尾盤神探 - 動態訊號版", layout="wide")

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
    """讀取 400 天資料並預算基礎指標 (向量化運算)"""
    query = """
    SELECT sp.date, sp.symbol, sp.open, sp.high, sp.low, sp.close, sp.volume, 
           si.name, si.industry
    FROM stock_prices sp
    JOIN stock_info si ON sp.symbol = si.symbol
    WHERE sp.date >= current_date - INTERVAL '400 days' 
    ORDER BY sp.symbol, sp.date
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['symbol', 'date'])
    grouped = df.groupby('symbol')
    
    # --- 1. 基礎均線 ---
    df['MA5'] = grouped['close'].transform(lambda x: x.rolling(5).mean())
    df['MA10'] = grouped['close'].transform(lambda x: x.rolling(10).mean())
    df['MA20'] = grouped['close'].transform(lambda x: x.rolling(20).mean())
    df['MA60'] = grouped['close'].transform(lambda x: x.rolling(60).mean())
    
    # --- 2. 成交量均線 ---
    df['Vol_MA5'] = grouped['volume'].transform(lambda x: x.rolling(5).mean())
    df['Vol_MA10'] = grouped['volume'].transform(lambda x: x.rolling(10).mean())
    df['Vol_MA20'] = grouped['volume'].transform(lambda x: x.rolling(20).mean())
    
    # --- 3. 漲跌幅與比較數據 ---
    df['prev_close'] = grouped['close'].shift(1)
    df['prev_volume'] = grouped['volume'].shift(1)
    df['pct_change'] = (df['close'] - df['prev_close']) / df['prev_close'] * 100
    df['pct_change_3d'] = grouped['close'].pct_change(3) * 100
    df['pct_change_5d'] = grouped['close'].pct_change(5) * 100
    
    # --- 4. 創高邏輯 ---
    df['high_3d'] = grouped['high'].transform(lambda x: x.rolling(3).max())
    df['vol_max_3d'] = grouped['volume'].transform(lambda x: x.rolling(3).max())
    
    # --- 5. 連續站上均線 ---
    df['above_ma20'] = (df['close'] > df['MA20']).astype(int)
    df['days_above_ma20'] = grouped['above_ma20'].transform(lambda x: x.rolling(47).sum())
    
    df['above_ma60'] = (df['close'] > df['MA60']).astype(int)
    df['days_above_ma60'] = grouped['above_ma60'].transform(lambda x: x.rolling(177).sum())

    # --- 6. 量比 ---
    df['vol_ratio'] = df['volume'] / df['Vol_MA5']
    
    return df

# ===========================
# 3. 進階指標計算函式
# ===========================
def calculate_advanced_indicators_and_score(df_stock, is_single_stock=False):
    """計算指標 (KD, MACD, CDP)"""
    df = df_stock.copy()
    
    # KD
    low_min = df['low'].rolling(9).min()
    high_max = df['high'].rolling(9).max()
    df['RSV'] = (df['close'] - low_min) / (high_max - low_min) * 100
    df['RSV'] = df['RSV'].fillna(50)
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    # MACD
    exp12 = df['close'].ewm(span=12, adjust=False).mean()
    exp26 = df['close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_OSC'] = df['DIF'] - df['MACD']
    
    # CDP
    prev_high = df['high'].shift(1)
    prev_low = df['low'].shift(1)
    prev_close = df['close'].shift(1)
    df['CDP'] = (prev_high + prev_low + 2 * prev_close) / 4
    rng = prev_high - prev_low 
    df['AH'] = df['CDP'] + rng
    df['NH'] = 2 * df['CDP'] - prev_low
    df['NL'] = 2 * df['CDP'] - prev_high
    df['AL'] = df['CDP'] - rng

    return df, {}

def plot_stock_kline(df_stock, symbol, name, active_signals_text):
    """繪製 K 線圖 + 訊號區"""
    df_plot = df_stock.tail(130).copy()
    df_plot['date_str'] = df_plot['date'].dt.strftime('%Y-%m-%d')
    
    # 計算分數顯示
    score_val = active_signals_text.count(',') + 1 if active_signals_text else 0
    
    fig = make_subplots(
        rows=5, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.01,
        row_heights=[0.45, 0.1, 0.1, 0.1, 0.15],
        subplot_titles=(f"{symbol} {name} (評分:{score_val}分)", "成交量", "KD", "MACD", "重點訊號"),
        specs=[[{"secondary_y": False}], [{}], [{}], [{}], [{}]] 
    )

    # K線
    fig.add_trace(go.Candlestick(
        x=df_plot['date_str'], open=df_plot['open'], high=df_plot['high'],
        low=df_plot['low'], close=df_plot['close'], name='K線',
        increasing_line_color='red', decreasing_line_color='green'
    ), row=1, col=1)
    
    colors_ma = {'MA5': '#FFA500', 'MA10': '#00FFFF', 'MA20': '#BA55D3', 'MA60': '#4169E1'}
    for ma in ['MA5', 'MA10', 'MA20', 'MA60']:
        if ma in df_plot.columns:
            fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot[ma], mode='lines', name=ma, line=dict(color=colors_ma[ma], width=1.5)), row=1, col=1)

    # 成交量
    colors_vol = ['red' if c >= o else 'green' for c, o in zip(df_plot['close'], df_plot['open'])]
    fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['volume'], name='成交量', marker_color=colors_vol), row=2, col=1)

    # KD & MACD
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['K'], name='K', line=dict(color='orange', width=1)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['D'], name='D', line=dict(color='cyan', width=1)), row=3, col=1)
    
    osc_colors = ['red' if v >= 0 else 'green' for v in df_plot['MACD_OSC']]
    fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['MACD_OSC'], name='OSC', marker_color=osc_colors), row=4, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['DIF'], name='DIF', line=dict(color='orange', width=1)), row=4, col=1)

    # 訊號區 (視覺化)
    signals = [
        ('KD金叉', (df_plot['K'] > df_plot['D']) & (df_plot['K'].shift(1) < df_plot['D'].shift(1)), 'diamond', 'purple'),
        ('量能攻擊', (df_plot['volume'] > df_plot['prev_volume']) & (df_plot['vol_ratio'] > 1.2), 'triangle-up', 'gold'),
        ('MACD翻紅', (df_plot['MACD_OSC'] > 0) & (df_plot['MACD_OSC'].shift(1) < 0), 'square', 'blue')
    ]
    for idx, (label, mask, symbol, color) in enumerate(signals):
        sig_dates = df_plot[mask]['date_str']
        fig.add_trace(go.Scatter(x=sig_dates, y=[idx]*len(sig_dates), mode='markers', name=label, marker=dict(symbol=symbol, size=10, color=color)), row=5, col=1)

    layout_update = dict(height=950, xaxis_rangeslider_visible=False, showlegend=False, margin=dict(l=20, r=20, t=30, b=20), bargap=0.05, plot_bgcolor='white', paper_bgcolor='white')
    fig.update_layout(**layout_update)
    
    common_axis = dict(type='category', showgrid=False, zeroline=False, showline=True, linecolor='black', mirror=True)
    for r in [1,2,3,4]: fig.update_xaxes(**common_axis, row=r, col=1)
    fig.update_xaxes(dtick=10, **common_axis, row=5, col=1)
    fig.update_yaxes(showgrid=False, showline=True, linecolor='black', mirror=True)

    return fig

# ===========================
# 4. Streamlit 主程式
# ===========================
st.title("🏆 尾盤神探 - 動態訊號版")
st.markdown("---")

for key in ['ticker_index', 'last_selected_rows', 'last_viewed_symbol', 'last_sort_option']:
    if key not in st.session_state: st.session_state[key] = 0 if 'index' in key else None

with st.spinner("載入數據中..."):
    df_full = load_and_process_data()

available_dates = sorted(df_full['date'].dt.date.unique(), reverse=True)
all_industries = sorted(df_full['industry'].dropna().astype(str).unique().tolist())

# --- 側邊欄 ---
selected_date = st.sidebar.selectbox("📅 回測日期", available_dates, 0)
st.sidebar.markdown("---")
sort_option = st.sidebar.selectbox("🔢 排序方式", ["強勢總分 (高→低)", "漲跌幅 (高→低)", "量比 (高→低)"])
st.sidebar.markdown("---")
selected_industries = st.sidebar.multiselect("🏭 產業篩選", options=all_industries, default=[])

# ===========================
# 5. 核心運算 (當日切片 + 評分)
# ===========================
target_date_ts = pd.Timestamp(selected_date)
df_day = df_full[df_full['date'] == target_date_ts].copy()

if selected_industries:
    df_day = df_day[df_day['industry'].isin(selected_industries)]

# --- 計算當日排名 ---
df_day['rank_1d'] = df_day['pct_change'].rank(ascending=False)
df_day['rank_5d'] = df_day['pct_change_5d'].rank(ascending=False)

if df_day.empty:
    st.warning("無資料")
else:
    # 預先初始化 list 欄位
    df_day['signals_str'] = [[] for _ in range(len(df_day))]
    
    # 初始化分數
    score = pd.Series(0, index=df_day.index)

    # ==========================================
    # 🔥 關鍵修改：動態計算各項乖離與數值
    # ==========================================
    
    # 1. 計算均線乖離率 (Bias Percentage)
    bias_ma5 = ((df_day['close'] - df_day['MA5']) / df_day['MA5']) * 100
    bias_ma20 = ((df_day['close'] - df_day['MA20']) / df_day['MA20']) * 100
    bias_ma60 = ((df_day['close'] - df_day['MA60']) / df_day['MA60']) * 100
    
    # 2. 計算成交量增幅
    vol_diff_ma5 = ((df_day['volume'] - df_day['Vol_MA5']) / df_day['Vol_MA5']) * 100
    vol_diff_ma10 = ((df_day['volume'] - df_day['Vol_MA10']) / df_day['Vol_MA10']) * 100
    vol_diff_ma20 = ((df_day['volume'] - df_day['Vol_MA20']) / df_day['Vol_MA20']) * 100
    vol_diff_prev = ((df_day['volume'] - df_day['prev_volume']) / df_day['prev_volume']) * 100 # 比昨日增減

    # 定義動態訊號策略
    # 格式: (Mask條件, 顯示的文字內容(Series或字串))
    # 若是 Series，則會自動填入該列對應的數值
    
    strategies_dynamic = [
        # --- 均線突破/乖離 (顯示實際 %) ---
        (df_day['close'] > df_day['MA5'], "突破週線 " + bias_ma5.map('{:+.2f}%'.format)),
        (df_day['close'] > df_day['MA20'], "突破月線 " + bias_ma20.map('{:+.2f}%'.format)),
        (df_day['close'] > df_day['MA60'], "突破季線 " + bias_ma60.map('{:+.2f}%'.format)),
        
        # --- 漲跌幅 (顯示實際 %) ---
        (df_day['pct_change'] > 3, "今日漲幅 " + df_day['pct_change'].map('{:+.2f}%'.format)),
        (df_day['pct_change_3d'] > 10, "3日漲幅 " + df_day['pct_change_3d'].map('{:+.2f}%'.format)),
        (df_day['pct_change_5d'] > 15, "5日漲幅 " + df_day['pct_change_5d'].map('{:+.2f}%'.format)),
        (df_day['pct_change'] > 9.5, "🔥漲停板"),

        # --- 成交量 (顯示實際 %) ---
        (df_day['volume'] > df_day['Vol_MA5'], "量>5日均 " + vol_diff_ma5.map('{:+.1f}%'.format)),
        (df_day['volume'] > df_day['Vol_MA10'] * 1.3, "量>10日均30% (實" + vol_diff_ma10.map('{:+.1f}%'.format) + ")"),
        (df_day['volume'] > df_day['prev_volume'] * 1.5, "量爆增 (月增" + vol_diff_prev.map('{:+.1f}%'.format) + ")"),

        # --- 型態與連續性 (靜態文字) ---
        ((df_day['close'] - df_day['open']) / df_day['open'] > 0.03, "長紅棒>3%"),
        (df_day['close'] >= df_day['high_3d'], "創3日新高"),
        (df_day['days_above_ma20'] >= 47, "連47日站月線"),
        (df_day['days_above_ma60'] >= 177, "連177日站季線"),
        
        # --- 排名 (顯示實際名次) ---
        (df_day['rank_1d'] <= 10, "單日漲幅第" + df_day['rank_1d'].astype(int).astype(str) + "名"),
        
        # --- 排列 ---
        ((df_day['close'] > df_day['MA5']) & (df_day['MA5'] > df_day['MA10']) & (df_day['MA10'] > df_day['MA20']), "短線多頭排列"),
        ((df_day['close'] > df_day['MA10']) & (df_day['MA10'] > df_day['MA20']) & (df_day['MA20'] > df_day['MA60']), "長線多頭排列"),
    ]
    
    # 執行所有策略
    for mask, signal_content in strategies_dynamic:
        # 1. 加分
        score += mask.astype(int)
        
        # 2. 記錄觸發的訊號 (處理動態文字)
        if mask.any():
            # 判斷 signal_content 是固定字串還是 Series
            if isinstance(signal_content, pd.Series):
                # 取出符合 mask 的字串 series
                dynamic_texts = signal_content[mask]
                # 更新到 list 中
                df_day.loc[mask, 'signals_str'] = df_day.loc[mask].apply(
                    lambda row: (row['signals_str'] + [dynamic_texts[row.name]]) 
                    if row.name in dynamic_texts.index else row['signals_str'], 
                    axis=1
                )
            else:
                # 固定字串
                df_day.loc[mask, 'signals_str'] = df_day.loc[mask, 'signals_str'].apply(lambda x: x + [signal_content])

    # 寫回總分
    df_day['Total_Score'] = score
    df_day['Signal_List'] = df_day['signals_str'].apply(lambda x: ", ".join(x))

    # --- 篩選 ---
    min_score = st.sidebar.number_input("最低總分門檻", 0, 50, 5)
    results = df_day[df_day['Total_Score'] >= min_score].copy()

    # --- 排序 ---
    if sort_option == "強勢總分 (高→低)":
        results = results.sort_values(by=['Total_Score', 'pct_change', 'symbol'], ascending=[False, False, True])
    elif sort_option == "漲跌幅 (高→低)":
        results = results.sort_values(by=['pct_change', 'Total_Score', 'symbol'], ascending=[False, False, True])
    else:
        results = results.sort_values(by=['vol_ratio', 'Total_Score'], ascending=[False, False])

    # --- 顯示 ---
    display_df = results[['symbol', 'name', 'industry', 'close', 'pct_change', 'Total_Score', 'Signal_List']].copy()
    display_df = display_df.reset_index(drop=True)
    symbol_list = display_df['symbol'].tolist()

    if st.session_state.last_sort_option != sort_option:
        if st.session_state.last_viewed_symbol in symbol_list:
            st.session_state.ticker_index = symbol_list.index(st.session_state.last_viewed_symbol)
        else:
            st.session_state.ticker_index = 0
        st.session_state.last_sort_option = sort_option

    st.success(f"🎉 篩選出 {len(symbol_list)} 檔強勢股！(門檻: {min_score}分)")

    event = st.dataframe(
        display_df.style.format({"pct_change": "{:.2f}%", "close": "{:.2f}", "Total_Score": "{:.0f}"})
        .background_gradient(subset=['Total_Score'], cmap='Reds'),
        on_select="rerun", selection_mode="single-row", use_container_width=True,
        column_config={
            "symbol": "代號", "name": "名稱", "Total_Score": st.column_config.NumberColumn("🔥 強勢總分"),
            "Signal_List": st.column_config.TextColumn("⚡ 動態觸發訊號", width="large")
        }
    )

    if event.selection.rows and event.selection.rows != st.session_state.last_selected_rows:
        st.session_state.ticker_index = event.selection.rows[0]
        st.session_state.last_selected_rows = event.selection.rows
    if st.session_state.ticker_index >= len(symbol_list): st.session_state.ticker_index = 0

    st.markdown("---")
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
        st.markdown(f"<h3 style='text-align: center; color: #FF4B4B;'>{current_symbol} {current_info['name']} | 總分: {current_info['Total_Score']}</h3>", unsafe_allow_html=True)
        st.info(f"⚡ **訊號詳情**: {current_info['Signal_List']}")

    df_chart_source = df_full[df_full['symbol'] == current_symbol].sort_values('date')
    df_chart_source = df_chart_source[df_chart_source['date'] <= target_date_ts]
    
    if len(df_chart_source) < 30:
        st.error("歷史資料不足")
    else:
        df_chart_source, _ = calculate_advanced_indicators_and_score(df_chart_source, is_single_stock=True)
        fig = plot_stock_kline(df_chart_source, current_symbol, current_info['name'], current_info['Signal_List'])
        st.plotly_chart(fig, use_container_width=True)
