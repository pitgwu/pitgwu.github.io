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
# 1. 頁面設定
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
# 3. 核心邏輯
# ===========================
@st.cache_data(ttl=3600)
def load_and_process_data(lookback_days, min_volume, min_price, squeeze_threshold, strict_trend, min_days):
    engine = get_db_engine()
    
    # --- 步驟 1: 快速篩選 ---
    target_symbols = []
    try:
        with engine.connect() as conn:
            latest_res = conn.execute(text("SELECT MAX(date) FROM stock_prices")).fetchone()
            if not latest_res or not latest_res[0]: return pd.DataFrame(), pd.DataFrame()
            latest_date = latest_res[0]
            
            query = text("""
                SELECT symbol FROM stock_prices 
                WHERE date = :d AND volume >= :v AND close >= :p
            """)
            res = conn.execute(query, {"d": latest_date, "v": min_volume, "p": min_price}).fetchall()
            target_symbols = [r[0] for r in res]
            
            if not target_symbols: return pd.DataFrame(), pd.DataFrame()
    except Exception as e:
        st.error(f"篩選失敗: {e}"); return pd.DataFrame(), pd.DataFrame()

    # --- 步驟 2: 分批下載 ---
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    all_dfs = []
    batch_size = 50 
    
    try:
        with engine.connect() as conn:
            df_info = pd.read_sql("SELECT symbol, name, industry FROM stock_info", conn)
            
            dl_bar = st.progress(0, text="下載資料中...")
            total_batches = (len(target_symbols) // batch_size) + 1
            
            for i in range(0, len(target_symbols), batch_size):
                batch = target_symbols[i : i+batch_size]
                sym_str = "', '".join(batch)
                q = f"SELECT date, symbol, close, volume, open, high, low FROM stock_prices WHERE date >= '{start_date}' AND symbol IN ('{sym_str}')"
                all_dfs.append(pd.read_sql(q, conn))
                dl_bar.progress(min((i // batch_size) / total_batches, 1.0))
            
            dl_bar.empty()
                
    except Exception as e:
        st.error(f"下載失敗: {e}"); return pd.DataFrame(), pd.DataFrame()

    if not all_dfs: return pd.DataFrame(), pd.DataFrame()
    df_prices = pd.concat(all_dfs)
    df_prices['date'] = pd.to_datetime(df_prices['date'])
    df_prices = df_prices.sort_values(['symbol', 'date'])

    # --- 步驟 3: 計算指標 ---
    results = []
    p_bar = st.progress(0, text="分析均線型態...")
    total = len(df_prices['symbol'].unique())
    count = 0

    for symbol, df in df_prices.groupby('symbol'):
        count += 1
        if count % 20 == 0: p_bar.progress(min(count/total, 1.0))
        
        if len(df) < 65: continue 
        
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['ma120'] = df['close'].rolling(120).mean()
        
        df['prev_volume'] = df['volume'].shift(1)
        df['vol_ratio'] = df['volume'] / df['prev_volume']
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        if strict_trend:
            if pd.isna(last['ma60']) or pd.isna(last['ma120']) or last['ma60'] <= last['ma120']:
                continue
            
        mas = [last['ma5'], last['ma10'], last['ma20']]
        if any(pd.isna(mas)): continue
        
        max_ma = df[['ma5','ma10','ma20']].max(axis=1)
        min_ma = df[['ma5','ma10','ma20']].min(axis=1)
        df['sq_pct'] = (max_ma - min_ma) / min_ma
        df['is_sq'] = df['sq_pct'] <= squeeze_threshold
        
        if not df.iloc[-1]['is_sq']:
            continue
            
        days = 0
        for i in range(len(df)-1, -1, -1):
            if df.iloc[i]['is_sq']: days += 1
            else: break
            
        if days >= min_days:
            v_ratio = last['vol_ratio']
            if pd.isna(v_ratio) or np.isinf(v_ratio): v_ratio = 0.0
            v_ratio_str = f"🔥 {v_ratio:.1f}x" if v_ratio >= 1.5 else f"{v_ratio:.1f}x"

            def get_ma_str(curr, prev):
                if pd.isna(curr) or pd.isna(prev): return "-"
                arrow = "🔺" if curr >= prev else "▼"
                return f"{curr:.2f} {arrow}"

            ma5_str = get_ma_str(last['ma5'], prev['ma5'])
            ma10_str = get_ma_str(last['ma10'], prev['ma10'])
            ma20_str = get_ma_str(last['ma20'], prev['ma20'])
            ma60_str = get_ma_str(last['ma60'], prev['ma60'])

            results.append({
                'symbol': symbol, 
                'close': last['close'], 
                'volume': int(last['volume']),
                'vol_ratio': v_ratio,
                'vol_str': v_ratio_str,
                'days': days, 
                'squeeze_pct': round(df.iloc[-1]['sq_pct'] * 100, 2),
                'ma5_str': ma5_str,
                'ma10_str': ma10_str,
                'ma20_str': ma20_str,
                'ma60_str': ma60_str,
                'last_date': last['date']
            })
    
    p_bar.empty()
    
    if not results: return pd.DataFrame(), df_prices
    
    df_res = pd.DataFrame(results)
    df_final = pd.merge(df_res, df_info, on='symbol', how='left')
    df_final['name'] = df_final['name'].fillna('未知名稱')
    df_final['link'] = df_final['symbol'].apply(lambda x: f"https://www.wantgoo.com/stock/{x.replace('.TW','').replace('.TWO','')}")
    
    return df_final, df_prices

# ===========================
# 4. 診斷工具
# ===========================
def diagnose_stock(symbol_code, min_vol, min_price, sq_threshold, strict_trend, min_days):
    engine = get_db_engine()
    symbol_code = symbol_code.strip().upper()
    
    st.sidebar.markdown(f"#### 🕵️ 診斷報告: {symbol_code}")
    try:
        with engine.connect() as conn:
            res = conn.execute(text(f"SELECT symbol, name FROM stock_info WHERE symbol LIKE '%{symbol_code}%' LIMIT 1")).fetchone()
            if not res:
                st.sidebar.error("❌ 無此代號")
                return
            real_symbol, name = res[0], res[1]
            
            df = pd.read_sql(text(f"SELECT * FROM stock_prices WHERE symbol = '{real_symbol}' ORDER BY date ASC"), conn)
            if df.empty or len(df) < 120:
                st.sidebar.error("❌ 資料不足")
                return
            
            df['date'] = pd.to_datetime(df['date'])
            df['ma5'] = df['close'].rolling(5).mean()
            df['ma10'] = df['close'].rolling(10).mean()
            df['ma20'] = df['close'].rolling(20).mean()
            df['ma60'] = df['close'].rolling(60).mean()
            df['ma120'] = df['close'].rolling(120).mean()
            
            df['prev_volume'] = df['volume'].shift(1)
            df['vol_ratio'] = df['volume'] / df['prev_volume']
            
            max_ma = df[['ma5','ma10','ma20']].max(axis=1)
            min_ma = df[['ma5','ma10','ma20']].min(axis=1)
            df['sq_pct'] = (max_ma - min_ma) / min_ma
            df['is_sq'] = df['sq_pct'] <= sq_threshold
            
            days = 0
            for i in range(len(df)-1, -1, -1):
                if df.iloc[i]['is_sq']: days += 1
                else: break
            
            last = df.iloc[-1]
            
            st.sidebar.caption(f"{real_symbol} {name} | {last['date'].strftime('%Y-%m-%d')}")
            
            v_ok = last['volume'] >= min_vol
            t_ok = (last['ma60'] > last['ma120']) if strict_trend else True
            s_ok = df.iloc[-1]['is_sq']
            d_ok = days >= min_days
            
            def show_check(label, ok, val, target):
                icon = "✅" if ok else "❌"
                cls = "diag-pass" if ok else "diag-fail"
                st.sidebar.markdown(f"{label}: <span class='{cls}'>{icon} {val}</span> / {target}", unsafe_allow_html=True)
                
            show_check("1.成交量", v_ok, int(last['volume']), min_vol)
            show_check("2.趨勢(60>120)", t_ok, "多頭" if last['ma60']>last['ma120'] else "非多頭", "必要" if strict_trend else "不拘")
            show_check("3.糾結度", s_ok, f"{last['sq_pct']*100:.2f}%", f"{sq_threshold*100:.1f}%")
            show_check("4.連續天數", d_ok, f"{days} 天", f"{min_days} 天")
            
            v_r = last['vol_ratio']
            if pd.isna(v_r) or np.isinf(v_r): v_r = 0.0
            v_label = f"🔥 {v_r:.2f}x" if v_r >= 1.5 else f"{v_r:.2f}x"
            st.sidebar.markdown(f"📊 今日量增比: **{v_label}**")

    except Exception as e:
        st.sidebar.error(f"診斷錯誤: {e}")

# ===========================
# 5. UI 介面
# ===========================
st.sidebar.header("⚙️ 篩選參數")
threshold_pct = st.sidebar.slider("均線糾結度 (%)", 1.0, 10.0, 3.0, 0.5)
# 修正預設值為 500,000 (500張)
min_vol = st.sidebar.slider("最小成交量 (股)", 0, 5000000, 500000, 50000)
min_price = st.sidebar.slider("最低股價 (元)", 0, 1000, 30, 5)
strict_trend = st.sidebar.checkbox("只看多頭排列 (MA60 > MA120)", value=True)
min_days = st.sidebar.slider("最少整理天數", 1, 10, 2, 1)

st.title("📈 均線糾結選股神器")

with st.spinner("🚀 運算中..."):
    df_res, df_raw = load_and_process_data(400, min_vol, min_price, threshold_pct/100, strict_trend, min_days)

st.sidebar.divider()
st.sidebar.subheader("🔍 為什麼找不到？")
diag_code = st.sidebar.text_input("輸入代號 (如 3563)")
if diag_code:
    diagnose_stock(diag_code, min_vol, min_price, threshold_pct/100, strict_trend, min_days)

if df_res.empty:
    st.warning("⚠️ 無符合條件股票")
else:
    c_sort1, c_sort2 = st.columns([1, 1])
    with c_sort1:
        sort_col_map = {
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

    if 'selected_index' not in st.session_state:
        st.session_state.selected_index = 0
    if st.session_state.selected_index >= len(df_sorted):
        st.session_state.selected_index = 0

    opts = (df_sorted['symbol'] + " - " + df_sorted['name']).tolist()
    max_idx = len(opts) - 1
    
    if 'stock_selector' not in st.session_state:
        st.session_state.stock_selector = opts[0]

    def update_state(new_index):
        st.session_state.selected_index = new_index
        st.session_state.stock_selector = opts[new_index]

    def go_first(): update_state(0)
    def go_prev(): update_state(max(0, st.session_state.selected_index - 1))
    def go_next(): update_state(min(max_idx, st.session_state.selected_index + 1))
    def go_last(): update_state(max_idx)
    
    def on_dropdown_change():
        val = st.session_state.stock_selector
        if val in opts:
            st.session_state.selected_index = opts.index(val)

    c1, c2, c3 = st.columns(3)
    c1.metric("符合檔數", f"{len(df_sorted)}")
    c2.metric("最長整理", f"{df_sorted['days'].max()} 天")
    
    # --- 套用 Styler 樣式 ---
    def color_arrow(val):
        if '🔺' in str(val):
            return 'color: #ff4b4b; font-weight: bold' # 紅
        elif '▼' in str(val):
            return 'color: #26a69a; font-weight: bold' # 綠
        return ''

    styled_df = df_sorted.style.map(color_arrow, subset=['ma5_str', 'ma10_str', 'ma20_str', 'ma60_str'])

    selection_event = st.dataframe(
        styled_df,
        column_config={
            "symbol": "代號", "name": "名稱", "days": "天數",
            "vol_str": st.column_config.TextColumn("量增比"),
            "squeeze_pct": st.column_config.NumberColumn("糾結度", format="%.2f%%"),
            "close": st.column_config.NumberColumn("收盤", format="$%.2f"),
            "volume": st.column_config.NumberColumn("成交量", format="%d"),
            "ma5_str": st.column_config.TextColumn("5MA"),
            "ma10_str": st.column_config.TextColumn("10MA"),
            "ma20_str": st.column_config.TextColumn("20MA"),
            "ma60_str": st.column_config.TextColumn("60MA"),
            "link": st.column_config.LinkColumn("連結", display_text="Go")
        },
        column_order=["symbol", "name", "days", "vol_str", "squeeze_pct", "close", "volume", 
                      "ma5_str", "ma10_str", "ma20_str", "ma60_str", "link"],
        hide_index=True, use_container_width=True, height=300,
        on_select="rerun", selection_mode="single-row"
    )

    if selection_event.selection.rows:
        clicked_idx = selection_event.selection.rows[0]
        if clicked_idx != st.session_state.selected_index:
            update_state(clicked_idx)
            st.rerun()

    st.divider()
    st.subheader("📊 個股走勢")

    b1, b2, b3, b4 = st.columns(4)
    b1.button("⏮️ 最前", on_click=go_first, use_container_width=True)
    b2.button("⬅️ 上一個", on_click=go_prev, use_container_width=True)
    b3.button("➡️ 下一個", on_click=go_next, use_container_width=True)
    b4.button("⏭️ 最後", on_click=go_last, use_container_width=True)

    st.selectbox(
        "選擇股票 (亦可使用上方按鈕切換)", 
        options=opts, 
        key="stock_selector",
        on_change=on_dropdown_change
    )

    current_sym_str = st.session_state.stock_selector
    if current_sym_str:
        sym = current_sym_str.split(" - ")[0]
        chart = df_raw[df_raw['symbol'] == sym].copy().tail(120)
        
        if not chart.empty:
            for c in ['open','high','low','close']: chart[c] = pd.to_numeric(chart[c])
            
            chart['MA5'] = chart['close'].rolling(5).mean()
            chart['MA20'] = chart['close'].rolling(20).mean()
            chart['MA60'] = chart['close'].rolling(60).mean()
            chart['MA120'] = chart['close'].rolling(120).mean()

            fig = make_subplots(
                rows=2, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.03, 
                row_heights=[0.7, 0.3], 
                subplot_titles=(f"{current_sym_str} - 日K線圖", "成交量")
            )

            fig.add_trace(go.Candlestick(
                x=chart['date'], open=chart['open'], high=chart['high'], low=chart['low'], close=chart['close'], 
                increasing_line_color='#ef5350', decreasing_line_color='#26a69a', name='K線'
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(x=chart['date'], y=chart['MA5'], line=dict(color='orange', width=1), name='MA5'), row=1, col=1)
            fig.add_trace(go.Scatter(x=chart['date'], y=chart['MA20'], line=dict(color='purple', width=1), name='MA20'), row=1, col=1)
            fig.add_trace(go.Scatter(x=chart['date'], y=chart['MA60'], line=dict(color='blue', width=1), name='MA60'), row=1, col=1)
            fig.add_trace(go.Scatter(x=chart['date'], y=chart['MA120'], line=dict(color='green', width=1, dash='dot'), name='MA120'), row=1, col=1)
            
            vol_colors = ['#ef5350' if c >= o else '#26a69a' for c, o in zip(chart['close'], chart['open'])]
            fig.add_trace(go.Bar(
                x=chart['date'], y=chart['volume'], marker_color=vol_colors, name='成交量'
            ), row=2, col=1)

            fig.update_layout(
                xaxis_rangeslider_visible=False, 
                height=600, 
                margin=dict(t=30,b=0,l=0,r=0), 
                legend=dict(orientation="h", y=1.01, x=0.5, xanchor='center'),
                hovermode='x unified'
            )
            
            st.plotly_chart(fig, use_container_width=True)
