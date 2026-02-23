import streamlit as st
import pandas as pd
import numpy as np
import sqlalchemy
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta

# ===========================
# 1. 頁面設定與 CSS
# ===========================
st.set_page_config(page_title="均線糾結選股神器", page_icon="📈", layout="wide")
st.markdown("""
<style>
    .stDataFrame {font-size: 14px;}
    div.stButton > button {
        width: 100%;
        border-radius: 5px;
        height: 3em;
        font-weight: bold;
    }
    .diag-pass {color: #00c853; font-weight: bold;}
    .diag-fail {color: #ff5252; font-weight: bold;}
</style>
""", unsafe_allow_html=True)

# ===========================
# 2. 資料庫連線
# ===========================
@st.cache_resource
def get_db_engine():
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url and st.secrets:
        db_url = st.secrets.get("SUPABASE_DB_URL")
    if not db_url:
        st.error("❌ 找不到資料庫連線！請設定 SUPABASE_DB_URL。")
        st.stop()
    return create_engine(db_url)

# ===========================
# 3. 核心邏輯 (使用預計算資料)
# ===========================
@st.cache_data(ttl=600)
def load_precalculated_data():
    """
    直接從 daily_stock_indicators 讀取預先計算好的技術指標與總分
    抓取過去 200 天，確保繪圖時的 120MA 與 BB 不會有空窗期
    """
    engine = get_db_engine()
    query = """
    SELECT d.date, d.symbol, d.name, d.industry, d.open, d.high, d.low, d.close, d.volume,
           d.pct_change, d."MA5", d."MA10", d."MA20", d."MA60",
           d.total_score as "Total_Score",
           d.signal_list as "Signal_List",
           e."Capital", e."2026EPS"
    FROM daily_stock_indicators d
    LEFT JOIN stock_eps e ON d.symbol = e."Symbol"
    WHERE d.date >= current_date - INTERVAL '200 days'
    ORDER BY d.symbol, d.date
    """
    try:
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
    except Exception as e:
        st.error(f"資料讀取失敗: {e}")
        return pd.DataFrame()

    if not df.empty:
        df['symbol'] = df['symbol'].astype(str).str.strip()
        df['date'] = pd.to_datetime(df['date'])
        df['Total_Score'] = df['Total_Score'].fillna(0).astype(int)
        df['Signal_List'] = df['Signal_List'].fillna("")
        
        # 本地端補算 MA120
        df['MA120'] = df.groupby('symbol')['close'].transform(lambda x: x.rolling(120).mean())
        
        # 計算量增比
        df['prev_volume'] = df.groupby('symbol')['volume'].shift(1)
        df['Vol_Ratio'] = np.where(
            (df['prev_volume'] > 0) & df['prev_volume'].notna(),
            df['volume'] / df['prev_volume'],
            np.nan
        )
    return df

def get_squeeze_candidates(df_full, min_vol, min_price, sq_thresh, short_bull, long_bull, min_days):
    """
    在記憶體中利用 Pandas Vectorization 進行極速篩選，並整理表格所需欄位
    """
    if df_full.empty: return pd.DataFrame()
    
    # 1. 計算每一天的糾結度
    df_full['max_ma'] = df_full[['MA5', 'MA10', 'MA20']].max(axis=1)
    df_full['min_ma'] = df_full[['MA5', 'MA10', 'MA20']].min(axis=1)
    df_full['sq_pct'] = (df_full['max_ma'] - df_full['min_ma']) / df_full['min_ma']
    df_full['is_sq'] = df_full['sq_pct'] <= sq_thresh
    
    # 2. 計算昨日均線，用來判斷趨勢箭頭 (紅上/綠下)
    df_full['prev_MA5'] = df_full.groupby('symbol')['MA5'].shift(1)
    df_full['prev_MA10'] = df_full.groupby('symbol')['MA10'].shift(1)
    df_full['prev_MA20'] = df_full.groupby('symbol')['MA20'].shift(1)
    df_full['prev_MA60'] = df_full.groupby('symbol')['MA60'].shift(1)
    
    # 3. 針對最新一天進行條件過濾
    latest_date = df_full['date'].max()
    df_latest = df_full[df_full['date'] == latest_date].copy()
    
    cond_vol = df_latest['volume'] >= min_vol
    cond_price = df_latest['close'] >= min_price
    cond_sq = df_latest['is_sq'] == True
    
    cond_short = (df_latest['MA5'] > df_latest['MA10']) & (df_latest['MA10'] > df_latest['MA20']) if short_bull else True
    cond_long = (df_latest['MA60'] > df_latest['MA120']) if long_bull else True
    
    candidates = df_latest[cond_vol & cond_price & cond_sq & cond_short & cond_long]['symbol'].tolist()
    
    # 4. 計算連續天數並整理最終表格資料
    results = []
    
    def get_ma_str(curr, prev):
        if pd.isna(curr) or pd.isna(prev): return "-"
        arrow = "🔺" if curr >= prev else "▼"
        return f"{curr:.2f} {arrow}"

    for sym in candidates:
        sym_df = df_full[df_full['symbol'] == sym]
        
        is_sq_arr = sym_df['is_sq'].values[::-1]
        days = 0
        for val in is_sq_arr:
            if val: days += 1
            else: break
            
        if days >= min_days:
            last = sym_df.iloc[-1]
            
            # 處理量增比
            v_ratio = last['Vol_Ratio'] if pd.notna(last['Vol_Ratio']) else 0.0
            v_ratio_str = f"🔥 {v_ratio:.1f}x" if v_ratio >= 1.5 else f"{v_ratio:.1f}x"
            
            # 計算本益比
            pe = last['close'] / last['2026EPS'] if pd.notna(last['2026EPS']) and last['2026EPS'] > 0 else np.nan

            results.append({
                'symbol': sym,
                'name': last['name'],
                'close': last['close'],
                'volume': int(last['volume']),
                'vol_ratio': v_ratio,
                'vol_str': v_ratio_str,
                'squeeze_pct': last['sq_pct'] * 100,
                'days': days,
                'capital': last['Capital'],
                'eps2026': last['2026EPS'],
                'pe_ratio': pe,
                'Total_Score': last['Total_Score'],
                'Signal_List': last['Signal_List'],
                'ma5_str': get_ma_str(last['MA5'], last['prev_MA5']),
                'ma10_str': get_ma_str(last['MA10'], last['prev_MA10']),
                'ma20_str': get_ma_str(last['MA20'], last['prev_MA20']),
                'ma60_str': get_ma_str(last['MA60'], last['prev_MA60']),
                'link': f"https://www.wantgoo.com/stock/{sym.replace('.TW','').replace('.TWO','')}"
            })
            
    return pd.DataFrame(results)

# ===========================
# 4. 診斷工具
# ===========================
def diagnose_stock(symbol_code, df_full, min_vol, min_price, sq_threshold, short_bull, long_bull, min_days):
    symbol_code = symbol_code.strip().upper()
    st.sidebar.markdown(f"#### 🕵️ 診斷報告: {symbol_code}")
    
    sym_df = df_full[df_full['symbol'].str.contains(symbol_code, case=False)]
    if sym_df.empty:
        st.sidebar.error("❌ 資料庫無此代號或近期無資料")
        return
        
    target_sym = sym_df['symbol'].iloc[0]
    df = df_full[df_full['symbol'] == target_sym].copy()
    
    df['max_ma'] = df[['MA5','MA10','MA20']].max(axis=1)
    df['min_ma'] = df[['MA5','MA10','MA20']].min(axis=1)
    df['sq_pct'] = (df['max_ma'] - df['min_ma']) / df['min_ma']
    df['is_sq'] = df['sq_pct'] <= sq_threshold
    
    days = 0
    for val in df['is_sq'].values[::-1]:
        if val: days += 1
        else: break
        
    last = df.iloc[-1]
    st.sidebar.caption(f"{target_sym} {last['name']} | {last['date'].strftime('%Y-%m-%d')}")
    
    v_ok = last['volume'] >= min_vol
    is_long = last['MA60'] > last['MA120']
    t_long_ok = is_long if long_bull else True
    is_short = (last['MA5'] > last['MA10'] and last['MA10'] > last['MA20'])
    t_short_ok = is_short if short_bull else True
    s_ok = last['is_sq']
    d_ok = days >= min_days
    
    def show_check(label, ok, val, target):
        icon = "✅" if ok else "❌"
        cls = "diag-pass" if ok else "diag-fail"
        st.sidebar.markdown(f"{label}: <span class='{cls}'>{icon} {val}</span> / {target}", unsafe_allow_html=True)
        
    show_check("1. 成交量", v_ok, int(last['volume']), min_vol)
    show_check("2. 長線多頭(60>120)", t_long_ok, "是" if is_long else "否", "必要" if long_bull else "不拘")
    show_check("3. 短線多頭(5>10>20)", t_short_ok, "是" if is_short else "否", "必要" if short_bull else "不拘")
    show_check("4. 糾結度", s_ok, f"{last['sq_pct']*100:.2f}%", f"{sq_threshold*100:.1f}%")
    show_check("5. 連續天數", d_ok, f"{days} 天", f"{min_days} 天")

# ===========================
# 5. UI 介面
# ===========================
st.sidebar.header("⚙️ 篩選參數")
threshold_pct = st.sidebar.slider("均線糾結度 (%)", 1.0, 10.0, 3.0, 0.5)
min_vol = st.sidebar.slider("最小成交量 (股)", 0, 5000000, 500000, 50000)
min_price = st.sidebar.slider("最低股價 (元)", 0, 1000, 30, 5)

st.sidebar.subheader("進階設定")
short_term_bull = st.sidebar.checkbox("短線多頭排列 (5MA > 10MA > 20MA)", value=True)
long_term_bull = st.sidebar.checkbox("長線多頭排列 (60MA > 120MA)", value=False)
min_days = st.sidebar.slider("最少整理天數", 1, 10, 2, 1)

st.title("📈 均線糾結選股神器")

with st.spinner("🚀 極速運算中..."):
    df_full = load_precalculated_data()
    df_res = get_squeeze_candidates(df_full, min_vol, min_price, threshold_pct/100, short_term_bull, long_term_bull, min_days)

st.sidebar.divider()
st.sidebar.subheader("🔍 為什麼找不到？")
diag_code = st.sidebar.text_input("輸入代號 (如 3563)")
if diag_code:
    diagnose_stock(diag_code, df_full, min_vol, min_price, threshold_pct/100, short_term_bull, long_term_bull, min_days)

if df_res.empty:
    st.warning("⚠️ 無符合條件股票，請嘗試放寬側邊欄的篩選條件。")
else:
    # --- 1. 排序控制 ---
    c_sort1, c_sort2 = st.columns([1, 1])
    with c_sort1:
        sort_col_map = {
            "強勢總分": "Total_Score",
            "量增比": "vol_ratio", 
            "成交量": "volume",
            "糾結度": "squeeze_pct",
            "天數": "days", 
            "代號": "symbol"
        }
        sort_label = st.radio("排序依據", list(sort_col_map.keys()), horizontal=True, index=0)
        sort_key = sort_col_map[sort_label]
        
    with c_sort2:
        sort_order = st.radio("排序方式", ["遞減 (大到小)", "遞增 (小到大)"], horizontal=True, index=0)
        ascending = True if sort_order == "遞增 (小到大)" else False

    df_sorted = df_res.sort_values(by=sort_key, ascending=ascending).reset_index(drop=True)

    # --- 2. 狀態管理 ---
    if 'selected_index' not in st.session_state: st.session_state.selected_index = 0
    if st.session_state.selected_index >= len(df_sorted): st.session_state.selected_index = 0

    opts = (df_sorted['symbol'] + " - " + df_sorted['name']).tolist()
    max_idx = len(opts) - 1
    if 'stock_selector' not in st.session_state: st.session_state.stock_selector = opts[0]

    def update_state(new_index):
        st.session_state.selected_index = new_index
        st.session_state.stock_selector = opts[new_index]

    def go_first(): update_state(0)
    def go_prev(): update_state(max(0, st.session_state.selected_index - 1))
    def go_next(): update_state(min(max_idx, st.session_state.selected_index + 1))
    def go_last(): update_state(max_idx)
    
    def on_dropdown_change():
        val = st.session_state.stock_selector
        if val in opts: st.session_state.selected_index = opts.index(val)

    # --- 3. 顯示完整表格 (保留原有設計) ---
    c1, c2, c3 = st.columns(3)
    c1.metric("符合檔數", f"{len(df_sorted)}")
    c2.metric("最長整理", f"{df_sorted['days'].max()} 天")
    
    def color_arrow(val):
        if '🔺' in str(val): return 'color: #ff4b4b; font-weight: bold' # 紅
        elif '▼' in str(val): return 'color: #26a69a; font-weight: bold' # 綠
        return ''

    styled_df = df_sorted.style.map(color_arrow, subset=['ma5_str', 'ma10_str', 'ma20_str', 'ma60_str'])

    selection_event = st.dataframe(
        styled_df,
        column_config={
            "symbol": "代號", "name": "名稱", "days": "天數",
            "capital": st.column_config.NumberColumn("股本", format="%.1f"),
            "eps2026": st.column_config.NumberColumn("2026EPS", format="%.2f"),
            "pe_ratio": st.column_config.NumberColumn("本益比", format="%.2f"),
            "vol_str": st.column_config.TextColumn("量增比"),
            "squeeze_pct": st.column_config.NumberColumn("糾結度", format="%.2f%%"),
            "close": st.column_config.NumberColumn("收盤", format="$%.2f"),
            "volume": st.column_config.NumberColumn("成交量", format="%d"),
            "Total_Score": st.column_config.NumberColumn("總分", format="%d"),
            "ma5_str": st.column_config.TextColumn("5MA"),
            "ma10_str": st.column_config.TextColumn("10MA"),
            "ma20_str": st.column_config.TextColumn("20MA"),
            "ma60_str": st.column_config.TextColumn("60MA"),
            "link": st.column_config.LinkColumn("連結", display_text="Go")
        },
        column_order=[
            "symbol", "name", "Total_Score", "capital", "eps2026", "pe_ratio", 
            "days", "vol_str", "squeeze_pct", "close", "volume", 
            "ma5_str", "ma10_str", "ma20_str", "ma60_str", "link"
        ],
        hide_index=True, use_container_width=True, height=300,
        on_select="rerun", selection_mode="single-row"
    )

    if selection_event.selection.rows:
        clicked_idx = selection_event.selection.rows[0]
        if clicked_idx != st.session_state.selected_index:
            update_state(clicked_idx)
            st.rerun()

    # --- 4. 導航與視覺化圖表 ---
    st.divider()
    
    b1, b2, b3, b4 = st.columns(4)
    b1.button("⏮️ 最前", on_click=go_first, use_container_width=True)
    b2.button("⬅️ 上一個", on_click=go_prev, use_container_width=True)
    b3.button("➡️ 下一個", on_click=go_next, use_container_width=True)
    b4.button("⏭️ 最後", on_click=go_last, use_container_width=True)

    st.selectbox("選擇股票 (亦可使用上方按鈕切換)", options=opts, key="stock_selector", on_change=on_dropdown_change)

    current_sym_str = st.session_state.stock_selector
    
    if current_sym_str:
        sym = current_sym_str.split(" - ")[0]
        cur_info = df_sorted[df_sorted['symbol'] == sym].iloc[0]
        chart = df_full[df_full['symbol'] == sym].copy()
        
        if not chart.empty:
            # 🔥 完美還原：淺藍底框、紅標題、灰字、閃電圖示
            signals_str = cur_info['Signal_List'] if cur_info['Signal_List'] else '無特別訊號'
            st.markdown(f"""
            <div style="text-align: center; margin: 20px 0;">
                <h2 style="color: #FF4B4B; margin-bottom: 12px; font-weight: bold;">{current_sym_str} | 分:{cur_info['Total_Score']}</h2>
                <div style="background-color: #F4F9FF; border: 1px solid #D2E3FC; border-radius: 8px; padding: 15px 20px; font-size: 15px; color: #5F6368; width: 100%; box-sizing: border-box; line-height: 1.8;">
                    <span style="color: #FF5A5F; font-weight: bold; font-size: 16px; margin-right: 4px;">⚡ 多方訊號：</span> {signals_str}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # --- 計算圖表需要的 3倍布林通道 ---
            chart['std20'] = chart['close'].rolling(20).std()
            chart['BB_upper'] = chart['MA20'] + 3 * chart['std20']
            chart['BB_lower'] = chart['MA20'] - 3 * chart['std20']
            
            # 截取最後 120 天來繪圖
            chart = chart.tail(120)
            chart_dates = chart['date'].dt.strftime('%Y-%m-%d')

            fig = make_subplots(
                rows=2, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.03, 
                row_heights=[0.7, 0.3], 
                subplot_titles=(f"日K線圖 (3倍布林帶寬)", "成交量")
            )

            fig.add_trace(go.Candlestick(
                x=chart_dates, open=chart['open'], high=chart['high'], low=chart['low'], close=chart['close'], 
                increasing_line_color='#ef5350', decreasing_line_color='#26a69a', name='K線'
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(x=chart_dates, y=chart['MA5'], line=dict(color='orange', width=1), name='MA5'), row=1, col=1)
            fig.add_trace(go.Scatter(x=chart_dates, y=chart['MA20'], line=dict(color='purple', width=1), name='MA20'), row=1, col=1)
            fig.add_trace(go.Scatter(x=chart_dates, y=chart['MA60'], line=dict(color='blue', width=1), name='MA60'), row=1, col=1)
            fig.add_trace(go.Scatter(x=chart_dates, y=chart['MA120'], line=dict(color='green', width=1, dash='dot'), name='MA120'), row=1, col=1)
            
            # 布林通道 (虛線與半透明填色)
            fig.add_trace(go.Scatter(
                x=chart_dates, y=chart['BB_upper'], 
                line=dict(color='rgba(150, 150, 150, 0.5)', width=1, dash='dash'), 
                name='上軌 (3σ)', hoverinfo='skip', showlegend=False
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(
                x=chart_dates, y=chart['BB_lower'], 
                line=dict(color='rgba(150, 150, 150, 0.5)', width=1, dash='dash'), 
                name='下軌 (3σ)', fill='tonexty', fillcolor='rgba(200, 200, 200, 0.1)', 
                hoverinfo='skip', showlegend=False
            ), row=1, col=1)

            # 成交量
            vol_colors = ['#ef5350' if c >= o else '#26a69a' for c, o in zip(chart['close'], chart['open'])]
            fig.add_trace(go.Bar(
                x=chart_dates, y=chart['volume'], marker_color=vol_colors, name='成交量'
            ), row=2, col=1)

            # 強制分類 X 軸消除假日斷層
            fig.update_xaxes(type='category', nticks=15)
            fig.update_layout(
                xaxis_rangeslider_visible=False, 
                height=650, 
                margin=dict(t=30,b=0,l=0,r=0), 
                legend=dict(orientation="h", y=1.01, x=0.5, xanchor='center'),
                hovermode='x unified'
            )
            
            st.plotly_chart(fig, use_container_width=True)
