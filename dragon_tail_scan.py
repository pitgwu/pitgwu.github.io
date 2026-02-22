import streamlit as st
import pandas as pd
import sqlalchemy
from sqlalchemy import text
import os
import bcrypt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import uuid

# ===========================
# 1. 資料庫連線與全域設定
# ===========================
st.set_page_config(page_title="神龍擺尾 - 策略開發版", layout="wide")

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    st.error("❌ 未偵測到 SUPABASE_DB_URL，請設定環境變數。")
    st.stop()

@st.cache_resource
def get_engine():
    return sqlalchemy.create_engine(SUPABASE_DB_URL)

engine = get_engine()

# ===========================
# 2. 身份驗證與註冊模組
# ===========================
def check_login(username, password):
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT password_hash, role, active FROM users WHERE username = :u"),
                {"u": username}
            ).fetchone()

            if result:
                db_hash, role, active = result
                if bcrypt.checkpw(password.encode('utf-8'), db_hash.encode('utf-8')):
                    if active == 'yes':
                        return True, role, "登入成功"
                    else:
                        return False, None, "⚠️ 您的帳號尚未開通，請聯繫管理員"
            return False, None, "❌ 帳號或密碼錯誤"
    except Exception as e:
        return False, None, f"系統錯誤: {e}"

def register_user(username, password):
    try:
        with engine.begin() as conn:
            exists = conn.execute(text("SELECT 1 FROM users WHERE username = :u"), {"u": username}).scalar()
            if exists: return False, "❌ 此帳號已被註冊"
            hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            conn.execute(
                text("INSERT INTO users (username, password_hash, role, active) VALUES (:u, :p, 'user', 'no')"),
                {"u": username, "p": hashed_pw}
            )
            return True, f"✅ 帳號 {username} 已新增，請等待管理者開通帳號"
    except Exception as e: return False, f"系統錯誤: {e}"

def login_page():
    st.markdown("<h1 style='text-align: center;'>🐉 神龍擺尾 (開發版)</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["🔑 登入", "📝 註冊"])
        with tab_login:
            with st.form("login_form"):
                username = st.text_input("帳號")
                password = st.text_input("密碼", type="password")
                if st.form_submit_button("登入", use_container_width=True):
                    success, role, msg = check_login(username, password)
                    if success:
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = username
                        st.session_state['role'] = role
                        st.rerun()
                    else: st.error(msg)
        with tab_register:
            with st.form("register_form"):
                new_username = st.text_input("設定帳號")
                new_password = st.text_input("設定密碼", type="password")
                confirm_password = st.text_input("確認密碼", type="password")
                if st.form_submit_button("註冊", use_container_width=True):
                    if new_password != confirm_password: st.error("密碼不一致")
                    else:
                        success, msg = register_user(new_username, new_password)
                        if success: st.success(msg)
                        else: st.error(msg)

# ===========================
# 3. 資料載入
# ===========================
@st.cache_data(ttl=600)
def load_data():
    query = """
    SELECT date, symbol, name, industry, open, high, low, close, volume, pct_change,
           "MA5", "MA10", "MA20", "MA60",
           "K", "D", "MACD_OSC", "DIF",
           signal_list as "Signal_List"
    FROM daily_stock_indicators
    WHERE date >= current_date - INTERVAL '200 days'
    ORDER BY symbol, date
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    if not df.empty:
        df['symbol'] = df['symbol'].astype(str).str.strip()
        df['date'] = pd.to_datetime(df['date'])
        df['Signal_List'] = df['Signal_List'].fillna("")
        
        # 統一建立以「張」為單位的欄位
        if df['volume'].max() > 1000000:
            df['volume_sheets'] = df['volume'] / 1000
        else:
            df['volume_sheets'] = df['volume']
            
    return df

# ===========================
# 4. 核心策略：動態條件驗證
# ===========================
def run_strategy_scan(df_full, target_date, min_volume, use_cond1, use_cond2_vol, use_cond3_ma, use_cond4, use_cond5):
    df = df_full[df_full['date'] <= pd.to_datetime(target_date)].copy()
    if df.empty: return pd.DataFrame()
    
    # === 基礎前置運算 ===
    # 昨高 (為條件5準備)
    df['prev_high'] = df.groupby('symbol')['high'].shift(1)
    
    # 計算昨日均線，用於判斷趨勢箭頭 (上彎或下彎)
    for ma in [5, 10, 20, 60]:
        df[f'prev_MA{ma}'] = df.groupby('symbol')[f'MA{ma}'].shift(1)

    # 半年低點
    df['Low_120'] = df.groupby('symbol')['low'].transform(lambda x: x.rolling(window=120, min_periods=60).min())

    # 底部放量
    df['Vol_20MA'] = df.groupby('symbol')['volume_sheets'].transform(lambda x: x.rolling(window=20, min_periods=10).mean())
    df['is_vol_break'] = df['volume_sheets'] > (df['Vol_20MA'] * 2)
    df['vol_break_20d'] = df.groupby('symbol')['is_vol_break'].transform(lambda x: x.rolling(window=20, min_periods=1).max())

    # 回測月線
    df['is_below_20ma'] = df['low'] <= df['MA20']
    df['below_20ma_3d'] = df.groupby('symbol')['is_below_20ma'].transform(lambda x: x.rolling(window=3, min_periods=1).max())
    
    today_df = df[df['date'] == pd.to_datetime(target_date)].copy()
    if today_df.empty: return pd.DataFrame()

    # === 動態套用條件 ===
    mask = pd.Series(True, index=today_df.index)
    
    # 基礎過濾：最少成交量
    mask &= (today_df['volume_sheets'] >= min_volume)

     # 條件 1：低位階
    if use_cond1:
        mask &= (today_df['close'] <= (today_df['Low_120'] * 1.3))
        
    # 條件 2：底部放量
    if use_cond2_vol:
        mask &= (today_df['vol_break_20d'] == 1)
        
    # 條件 3：四線多排
    if use_cond3_ma:
        mask &= (
            (today_df['MA5'] > today_df['MA10']) &
            (today_df['MA10'] > today_df['MA20']) &
            (today_df['MA20'] > today_df['MA60'])
        )

    # 條件 4：回測月線後
    if use_cond4:
        mask &= (today_df['below_20ma_3d'] == 1) & (today_df['close'] > today_df['MA20'])

    # 條件 5：紅K過昨日高
    if use_cond5:
        # 收盤 > 開盤 (紅K)，且 收盤 > 昨高
        mask &= (today_df['close'] > today_df['open']) & (today_df['close'] > today_df['prev_high'])

    today_df['is_match'] = mask
    result_df = today_df[today_df['is_match']]
    
    return result_df

# ===========================
# 5. K 線繪圖輔助
# ===========================
def plot_stock_kline(df_stock, symbol, name):
    df_plot = df_stock.tail(130).copy()
    df_plot['date_str'] = df_plot['date'].dt.strftime('%Y-%m-%d')

    df_plot['prev_volume'] = df_plot['volume_sheets'].shift(1)
    df_plot['vol_ratio'] = df_plot['volume_sheets'] / (df_plot['volume_sheets'].rolling(5).mean() + 1e-9)

    fig = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.01,
                        row_heights=[0.45, 0.1, 0.1, 0.1, 0.15],
                        subplot_titles=(f"{symbol} {name}", "量(張)", "KD", "MACD", "訊號"))

    fig.add_trace(go.Candlestick(
        x=df_plot['date_str'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'],
        name='K線', increasing_line_color='red', decreasing_line_color='green'
    ), row=1, col=1)

    for ma, color in zip(['MA5','MA10','MA20','MA60'], ['#FFA500','#00FFFF','#BA55D3','#4169E1']):
        if ma in df_plot: 
            fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot[ma], mode='lines', name=ma, line=dict(color=color, width=1)), row=1, col=1)

    colors_vol = ['red' if c>=o else 'green' for c,o in zip(df_plot['close'], df_plot['open'])]
    fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['volume_sheets'], marker_color=colors_vol, name='量(張)'), row=2, col=1)

    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['K'], name='K', line=dict(color='orange')), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['D'], name='D', line=dict(color='cyan')), row=3, col=1)

    osc_colors = ['red' if v>=0 else 'green' for v in df_plot['MACD_OSC']]
    fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['MACD_OSC'], marker_color=osc_colors, name='OSC'), row=4, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['DIF'], name='DIF', line=dict(color='orange')), row=4, col=1)

    fig.update_xaxes(type='category', categoryorder='category ascending', tickmode='auto', nticks=15)
    fig.update_layout(height=800, xaxis_rangeslider_visible=False, showlegend=False, margin=dict(t=30,l=10,r=10,b=10))
    return fig

# --- 資料表顏色渲染器 ---
def color_ma_trend(val):
    val_str = str(val)
    if '▲' in val_str:
        return 'color: #FF4B4B; font-weight: bold;' # 上彎紅色
    elif '▼' in val_str:
        return 'color: #00CC96; font-weight: bold;' # 下彎綠色
    return ''

# ===========================
# 6. 主程式介面
# ===========================
def main_app():
    with st.sidebar:
        st.markdown(f"👤 **{st.session_state['username']}**")
        if st.button("🚪 登出", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()
            
        st.markdown("---")
        
        with st.spinner("載入歷史資料中..."):
            df_full = load_data()

        if df_full.empty:
            st.error("⚠️ 資料庫中尚無數據，請先執行 ETL 腳本。")
            st.stop()

        avail_dates = sorted(df_full['date'].dt.date.unique(), reverse=True)
        
        st.header("📅 日期設定")
        sel_date = st.selectbox("請選擇掃描日期", avail_dates, 0)
        
        st.markdown("---")
        st.header("⚙️ 篩選條件設定")
        
        min_volume = st.slider("📊 當日最少成交量 (張)", min_value=500, max_value=10000, value=1000, step=100)

        st.markdown("---")
        c1_low_level = st.checkbox("✅ 條件 1：低位階 (距半年低點 <= 30%)", value=True)
        c2_vol_break = st.checkbox("✅ 條件 2：底部放量 (近20日內曾爆量)", value=True)
        c3_ma_bullish = st.checkbox("✅ 條件 3：四線多排 (5 > 10 > 20 > 60)", value=False)
        c4_pullback = st.checkbox("✅ 條件 4：回測月線後 (近3日破月線, 今收上)", value=False)
        c5_red_k_break = st.checkbox("✅ 條件 5：紅K過昨日高 (收盤>開盤 且 收盤>昨高)", value=False)
        
        st.markdown("---")
        if st.button("🚀 執行掃描", type="primary", use_container_width=True):
            with st.spinner("掃描運算中..."):
                st.session_state.scanned_df = run_strategy_scan(
                    df_full, sel_date, min_volume,
                    c1_low_level, c2_vol_break, c3_ma_bullish, c4_pullback, c5_red_k_break
                )
            st.session_state.has_scanned = True
            st.session_state.ticker_index = 0
            
            active_conds = [f"成交量 >= {min_volume}張"]
            if c1_low_level: active_conds.append("低位階")
            if c2_vol_break: active_conds.append("底部放量")
            if c3_ma_bullish: active_conds.append("四線多排")
            if c4_pullback: active_conds.append("回測月線")
            if c5_red_k_break: active_conds.append("紅K過昨高")
            st.session_state.active_conds_text = " + ".join(active_conds)

    st.title("🐉 神龍擺尾 - 策略開發版")
    
    if 'active_conds_text' in st.session_state:
        st.markdown(f"目前啟用條件：**{st.session_state.active_conds_text}**")
    else:
        st.markdown("請在左側設定條件並開始掃描。")

    if 'ticker_index' not in st.session_state: st.session_state.ticker_index = 0

    if st.session_state.get('has_scanned'):
        result_df = st.session_state.scanned_df
        if result_df.empty:
            st.warning(f"{sel_date}：沒有符合所選條件的股票。")
        else:
            st.success(f"✅ {sel_date} 掃描完成！共找出 **{len(result_df)}** 檔股票。")
            
            # --- 整理與格式化表格資料 ---
            display_df = result_df.copy()
            
            # 計算均線箭頭字串
            for ma in [5, 10, 20, 60]:
                ma_col = f'MA{ma}'
                prev_ma_col = f'prev_MA{ma}'
                display_df[f'{ma}MA'] = display_df.apply(
                    lambda row: f"{row[ma_col]:.2f} ▲" if row[ma_col] > row[prev_ma_col] else (
                                f"{row[ma_col]:.2f} ▼" if row[ma_col] < row[prev_ma_col] else f"{row[ma_col]:.2f} -"
                    ), axis=1
                )
            
            # 產生玩股網連結 (去除 .TW / .TWO)
            display_df['玩股網'] = display_df['symbol'].apply(lambda x: f"https://www.wantgoo.com/stock/{str(x).split('.')[0]}")
            
            display_df['volume_sheets'] = display_df['volume_sheets'].astype(int)
            display_df = display_df.rename(
                columns={'close': '當日收盤', 'Low_120': '半年低點', 'volume_sheets': '成交量(張)', 'pct_change': '漲跌幅(%)'}
            )
            
            # 決定顯示欄位與順序
            final_cols = ['symbol', 'name', '玩股網', '當日收盤', '5MA', '10MA', '20MA', '60MA', '半年低點', '成交量(張)', '漲跌幅(%)']
            display_df = display_df[final_cols].sort_values('漲跌幅(%)', ascending=False).reset_index(drop=True)
            
            sym_list = display_df['symbol'].tolist()

            # 套用顏色渲染與超連結設定
            styled_df = display_df.style.format({
                "當日收盤": "{:.2f}",
                "半年低點": "{:.2f}",
                "成交量(張)": "{:,}",
                "漲跌幅(%)": "{:.2f}%"
            }).map(color_ma_trend, subset=['5MA', '10MA', '20MA', '60MA'])

            evt = st.dataframe(
                styled_df,
                on_select="rerun", selection_mode="single-row", use_container_width=True, height=300,
                column_config={
                    "玩股網": st.column_config.LinkColumn("玩股網", display_text="看線圖 🔗")
                }
            )

            if evt.selection.rows: 
                st.session_state.ticker_index = evt.selection.rows[0]

            if st.session_state.ticker_index >= len(sym_list):
                st.session_state.ticker_index = 0

            st.markdown("---")
            
            c1, c2, c3, c4, c5 = st.columns([1, 1, 4, 1, 1])
            if c1.button("⏮️ 首檔"): st.session_state.ticker_index = 0
            if c2.button("⬅️ 上一檔"): st.session_state.ticker_index = (st.session_state.ticker_index - 1) % len(sym_list)
            if c4.button("下一檔 ➡️"): st.session_state.ticker_index = (st.session_state.ticker_index + 1) % len(sym_list)
            if c5.button("末檔 ⏭️"): st.session_state.ticker_index = len(sym_list) - 1

            cur_sym = sym_list[st.session_state.ticker_index]
            cur_info = display_df.iloc[st.session_state.ticker_index]

            with c3:
                st.markdown(f"<h3 style='text-align:center;color:#FF4B4B'>{cur_sym} {cur_info['name']}</h3>", unsafe_allow_html=True)

            chart_src = df_full[df_full['symbol'] == cur_sym].sort_values('date')
            chart_src = chart_src[chart_src['date'] <= pd.Timestamp(sel_date)]

            if len(chart_src) < 30: 
                st.warning("資料不足無法繪製完整圖表")
            else:
                fig = plot_stock_kline(chart_src, cur_sym, cur_info['name'])
                st.plotly_chart(fig, use_container_width=True, key=f"chart_{cur_sym}_{uuid.uuid4()}")

    else:
        st.info("👈 請在左側選擇日期與條件，並點擊「執行掃描」來驗證。")

# ===========================
# 程式進入點
# ===========================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login_page()
else: main_app()
