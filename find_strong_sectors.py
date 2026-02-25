import os
import pandas as pd
import streamlit as st
import sqlalchemy
from sqlalchemy import text
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import bcrypt

# ===========================
# 1. 頁面與連線配置
# ===========================
st.set_page_config(page_title="波段飆股雷達", layout="wide", page_icon="🔥")

# 強制深色主題與自訂 CSS
st.markdown("""
<style>
    .stApp { background-color: #121212 !important; color: #E0E0E0 !important; }
    header { background-color: transparent !important; }
    .stButton>button {
        background-color: #1E1E1E !important;
        color: #2196F3 !important;
        border: 1px solid #333 !important;
        font-weight: bold;
        transition: 0.3s;
    }
    .stButton>button:hover {
        border-color: #2196F3 !important;
        color: #FFFFFF !important;
        background-color: #2196F3 !important;
    }
    .stSelectbox label, .stCheckbox label, .stTextInput label { color: #E0E0E0 !important; }
</style>
""", unsafe_allow_html=True)

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    st.error("❌ 未偵測到 SUPABASE_DB_URL，請設定環境變數。")
    st.stop()

@st.cache_resource
def get_db_engine():
    try:
        return sqlalchemy.create_engine(
            SUPABASE_DB_URL, 
            connect_args={'options': '-c statement_timeout=60000'}
        )
    except Exception as e:
        st.error(f"❌ 資料庫連線失敗: {e}")
        st.stop()

engine = get_db_engine()

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
            exists = conn.execute(
                text("SELECT 1 FROM users WHERE username = :u"), 
                {"u": username}
            ).scalar()
            
            if exists:
                return False, "❌ 此帳號已被註冊，請更換一個帳號名稱"

            hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            conn.execute(
                text("INSERT INTO users (username, password_hash, role, active) VALUES (:u, :p, 'user', 'no')"),
                {"u": username, "p": hashed_pw}
            )
            return True, f"✅ 帳號 {username} 已新增，請等待管理者開通帳號"
    except Exception as e:
        return False, f"系統錯誤: {e}"

def update_password(username, old_password, new_password):
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("SELECT password_hash FROM users WHERE username = :u"),
                {"u": username}
            ).fetchone()
            
            if not result:
                return False, "找不到使用者帳號"
                
            db_hash = result[0]
            
            if not bcrypt.checkpw(old_password.encode('utf-8'), db_hash.encode('utf-8')):
                return False, "❌ 舊密碼輸入錯誤，請重新確認"
                
            new_hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            conn.execute(
                text("UPDATE users SET password_hash = :p WHERE username = :u"),
                {"p": new_hashed_pw, "u": username}
            )
            return True, "✅ 密碼修改成功！下次請使用新密碼登入。"
    except Exception as e:
        return False, f"系統錯誤: {e}"

# 初始化 Session State
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = None
if 'role' not in st.session_state:
    st.session_state['role'] = None

# ===========================
# 3. 戰情室核心資料邏輯
# ===========================
@st.cache_data(ttl=3600)
def load_and_process_data():
    with engine.connect() as conn:
        dates_df = pd.read_sql("SELECT DISTINCT date FROM stock_prices ORDER BY date DESC LIMIT 200", conn)
        if dates_df.empty:
            return None, None, None, "無資料"
            
        available_dates = dates_df['date'].sort_values().tolist()
        latest_date = available_dates[-1]
        min_date = available_dates[0]
        date_3m_ago = available_dates[-60] if len(available_dates) >= 60 else available_dates[0]
        date_150_ago = available_dates[-150] if len(available_dates) >= 150 else available_dates[0]

        query_prices = text(f"SELECT symbol, date, close FROM stock_prices WHERE date >= '{min_date}'")
        df_prices = pd.concat([chunk for chunk in pd.read_sql(query_prices, conn, chunksize=50000)], ignore_index=True)

        query_inst = text(f"""
            SELECT symbol, SUM(foreign_net) as foreign_net, SUM(trust_net) as trust_net
            FROM institutional_investors
            WHERE date >= '{date_3m_ago}' AND date <= '{latest_date}'
            GROUP BY symbol
        """)
        df_inst = pd.read_sql(query_inst, conn)
        df_inst['foreign_net'] = (df_inst['foreign_net'] / 1000).fillna(0).astype(int)
        df_inst['trust_net'] = (df_inst['trust_net'] / 1000).fillna(0).astype(int)
        
        df_info = pd.read_sql("SELECT symbol, name, industry FROM stock_info", conn)

    df_prices['date'] = pd.to_datetime(df_prices['date'])
    pivot_df = df_prices.pivot(index='date', columns='symbol', values='close').sort_index()
    
    max_200 = pivot_df.max()
    latest_closes = pivot_df.iloc[-1]
    is_new_high = latest_closes >= max_200
    new_high_symbols = is_new_high[is_new_high].index.tolist()
    
    df_result = pd.DataFrame({'symbol': new_high_symbols})
    df_result = df_result.merge(latest_closes.reset_index(name='close'), on='symbol')
    df_result = df_result.merge(df_inst, on='symbol', how='left')
    df_result['foreign_net'] = df_result['foreign_net'].fillna(0)
    df_result['trust_net'] = df_result['trust_net'].fillna(0)
    
    df_result = df_result[(df_result['foreign_net'] > 0) | (df_result['trust_net'] > 0)]
    
    if df_result.empty:
        return pd.DataFrame(), pd.DataFrame(), {}, str(latest_date)
        
    df_result = df_result.merge(df_info, on='symbol', how='left')
    df_result['name'] = df_result['name'].fillna(df_result['symbol'])
    df_result['industry'] = df_result['industry'].fillna('其他')
    df_result['total_net'] = df_result['foreign_net'] + df_result['trust_net']
    df_result = df_result.sort_values('total_net', ascending=False)

    sector_stats = df_result.groupby('industry').agg(
        stock_count=('symbol', 'count'),
        total_foreign_net=('foreign_net', 'sum'),
        total_trust_net=('trust_net', 'sum'),
        total_net=('total_net', 'sum')
    ).reset_index().sort_values(by=['stock_count', 'total_net'], ascending=[False, False])

    target_symbols = df_result['symbol'].tolist()
    symbols_str = "','".join(target_symbols)
    
    with engine.connect() as conn:
        query_history = text(f"""
            SELECT p.symbol, p.date, p.open, p.high, p.low, p.close, p.volume,
                   COALESCE(i.foreign_net, 0) as daily_foreign, 
                   COALESCE(i.trust_net, 0) as daily_trust
            FROM stock_prices p
            LEFT JOIN institutional_investors i ON p.symbol = i.symbol AND p.date = i.date
            WHERE p.symbol IN ('{symbols_str}') AND p.date >= '{date_150_ago}'
            ORDER BY p.symbol, p.date ASC
        """)
        df_history = pd.read_sql(query_history, conn)

    df_history['date'] = pd.to_datetime(df_history['date'])
    df_history['daily_foreign'] = (df_history['daily_foreign'] / 1000).fillna(0).astype(int)
    df_history['daily_trust'] = (df_history['daily_trust'] / 1000).fillna(0).astype(int)
    
    history_dict = {}

    for sym, group in df_history.groupby('symbol'):
        group = group.sort_values('date').ffill()
        close_s = group['close']
        
        group['sma3'] = close_s.rolling(3, min_periods=1).mean()
        group['sma5'] = close_s.rolling(5, min_periods=1).mean()
        group['sma10'] = close_s.rolling(10, min_periods=1).mean()
        group['sma20'] = close_s.rolling(20, min_periods=1).mean()
        group['sma60'] = close_s.rolling(60, min_periods=1).mean()
        std20 = close_s.rolling(20, min_periods=1).std().fillna(0)
        group['upper'] = group['sma20'] + 3 * std20
        group['lower'] = group['sma20'] - 3 * std20

        ema12 = close_s.ewm(span=12, adjust=False).mean()
        ema26 = close_s.ewm(span=26, adjust=False).mean()
        group['macd'] = ema12 - ema26
        group['signal'] = group['macd'].ewm(span=9, adjust=False).mean()
        group['hist'] = group['macd'] - group['signal']

        low_min = group['low'].rolling(9, min_periods=1).min()
        high_max = group['high'].rolling(9, min_periods=1).max()
        rsv = ((close_s - low_min) / (high_max - low_min).replace(0, 1)) * 100
        rsv = rsv.fillna(50)
        group['kd_k'] = rsv.ewm(com=2, adjust=False).mean()
        group['kd_d'] = group['kd_k'].ewm(com=2, adjust=False).mean()

        delta = close_s.diff()
        gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / loss.replace(0, float('nan'))
        group['rsi'] = 100 - (100 / (1 + rs))
        group['rsi'] = group['rsi'].fillna(50)
        
        group['vol_color'] = ['#ff5252' if c >= o else '#4caf50' for c, o in zip(close_s, group['open'])]
        group['macd_color'] = ['#ff5252' if h >= 0 else '#4caf50' for h in group['hist']]

        history_dict[sym] = group

    date_str = latest_date.strftime("%Y-%m-%d") if hasattr(latest_date, 'strftime') else str(latest_date)
    return df_result, sector_stats, history_dict, date_str

def create_kline_chart(df_data, symbol_name, show_macd, show_kd, show_rsi):
    dates = df_data['date'].dt.strftime('%Y-%m-%d')
    
    panels = [{'name': 'volume', 'title': '成交量 (張)'}]
    if show_macd: panels.append({'name': 'macd', 'title': 'MACD'})
    if show_kd: panels.append({'name': 'kd', 'title': 'KD (9,3)'})
    if show_rsi: panels.append({'name': 'rsi', 'title': 'RSI (14)'})
    panels.append({'name': 'foreign', 'title': '外資買賣超 (張)'})
    panels.append({'name': 'trust', 'title': '投信買賣超 (張)'})

    num_subplots = 1 + len(panels)
    row_heights = [0.45] + [(0.55 / len(panels))] * len(panels)
    subplot_titles = [f"📈 {symbol_name} (股價與均線)"] + [f"📊 {p['title']}" for p in panels]
    
    fig = make_subplots(
        rows=num_subplots, cols=1, shared_xaxes=True, 
        vertical_spacing=0.04, row_heights=row_heights,
        subplot_titles=subplot_titles 
    )

    fig.add_trace(go.Scatter(x=dates, y=df_data['upper'], mode='lines', line=dict(color='rgba(255,255,255,0.2)', dash='dot'), name='3倍布林', legendgroup='bb'), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=df_data['lower'], mode='lines', line=dict(color='rgba(255,255,255,0.2)', dash='dot'), name='BB-3', legendgroup='bb', showlegend=False, fill='tonexty', fillcolor='rgba(255,255,255,0.05)'), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=df_data['sma3'], line=dict(color='#ffeb3b', width=1.5), name='3MA'), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=df_data['sma5'], line=dict(color='#ffffff', width=1.5), name='5MA'), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=df_data['sma10'], line=dict(color='#9c27b0', width=1.5), name='10MA'), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=df_data['sma20'], line=dict(color='#ff9800', width=1.5), name='20MA'), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=df_data['sma60'], line=dict(color='#2196f3', width=1.5), name='60MA'), row=1, col=1)
    fig.add_trace(go.Candlestick(
        x=dates, open=df_data['open'], high=df_data['high'], low=df_data['low'], close=df_data['close'],
        name='K線', increasing_line_color='#ff5252', decreasing_line_color='#4caf50', showlegend=False
    ), row=1, col=1)

    current_row = 2
    fig.add_trace(go.Bar(x=dates, y=df_data['volume'], marker_color=df_data['vol_color'], name='成交量', showlegend=False), row=current_row, col=1)
    current_row += 1

    if show_macd:
        fig.add_trace(go.Scatter(x=dates, y=df_data['macd'], line=dict(color='#2196f3'), name='MACD', showlegend=False), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=dates, y=df_data['signal'], line=dict(color='#ff9800'), name='Signal', showlegend=False), row=current_row, col=1)
        fig.add_trace(go.Bar(x=dates, y=df_data['hist'], marker_color=df_data['macd_color'], name='OSC', showlegend=False), row=current_row, col=1)
        current_row += 1

    if show_kd:
        fig.add_trace(go.Scatter(x=dates, y=df_data['kd_k'], line=dict(color='#ff9800'), name='K(9)', showlegend=False), row=current_row, col=1)
        fig.add_trace(go.Scatter(x=dates, y=df_data['kd_d'], line=dict(color='#2196f3'), name='D(3)', showlegend=False), row=current_row, col=1)
        fig.add_hline(y=80, line_dash="dash", line_color="gray", row=current_row, col=1)
        fig.add_hline(y=20, line_dash="dash", line_color="gray", row=current_row, col=1)
        current_row += 1

    if show_rsi:
        fig.add_trace(go.Scatter(x=dates, y=df_data['rsi'], line=dict(color='#e91e63'), name='RSI(14)', showlegend=False), row=current_row, col=1)
        current_row += 1

    fig.add_trace(go.Bar(x=dates, y=df_data['daily_foreign'], marker_color='#e91e63', name='外資進出', showlegend=False), row=current_row, col=1)
    current_row += 1
    fig.add_trace(go.Bar(x=dates, y=df_data['daily_trust'], marker_color='#00bcd4', name='投信進出', showlegend=False), row=current_row, col=1)

    for annotation in fig['layout']['annotations']:
        annotation['font'] = dict(size=15, color="#00bcd4") 
        annotation['x'] = 0.01  
        annotation['xanchor'] = 'left'

    fig.update_layout(
        template="plotly_dark", height=850 + (100 * (len(panels)-3)), 
        margin=dict(l=40, r=20, t=50, b=20), xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)'
    )
    
    fig.update_xaxes(type='category', categoryorder='category ascending', nticks=20, tickangle=45, showgrid=True, gridcolor='#333')
    fig.update_yaxes(showgrid=True, gridcolor='#333')
    return fig


# ===========================
# 4. 主程式控制 (登入/儀表板 切換)
# ===========================
if not st.session_state['logged_in']:
    st.markdown("<h1 style='text-align: center; color: #ff5252;'>🔐 波段飆股雷達 - 系統登入</h1>", unsafe_allow_html=True)
    
    col_spacer1, col_login, col_spacer2 = st.columns([1, 2, 1])
    with col_login:
        tab_login, tab_register = st.tabs(["🔑 登入", "📝 註冊帳號"])
        
        with tab_login:
            with st.form("login_form"):
                st.subheader("使用者登入")
                u_login = st.text_input("帳號名稱")
                p_login = st.text_input("使用者密碼", type="password")
                submit_login = st.form_submit_button("登入系統", use_container_width=True)
                
                if submit_login:
                    if u_login and p_login:
                        success, role, msg = check_login(u_login, p_login)
                        if success:
                            st.session_state['logged_in'] = True
                            st.session_state['username'] = u_login
                            st.session_state['role'] = role
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.warning("⚠️ 請輸入帳號與密碼")
                        
        with tab_register:
            with st.form("register_form"):
                st.subheader("建立新帳號")
                u_reg = st.text_input("設定帳號")
                p_reg = st.text_input("設定密碼", type="password")
                p_reg_confirm = st.text_input("確認密碼", type="password")
                submit_reg = st.form_submit_button("註冊帳號", use_container_width=True)
                
                if submit_reg:
                    if not u_reg or not p_reg:
                        st.warning("⚠️ 帳號與密碼不可為空")
                    elif p_reg != p_reg_confirm:
                        st.error("⚠️ 兩次輸入的密碼不一致")
                    else:
                        success, msg = register_user(u_reg, p_reg)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)
else:
    # ---------------------------
    # 已登入：側邊欄 (Sidebar) 設定
    # ---------------------------
    current_user = st.session_state['username']

    with st.sidebar:
        st.markdown(f"👤 **使用者: {current_user}** ({st.session_state['role']})")
        
        with st.expander("⚙️ 帳號設定 (修改密碼)"):
            with st.form("change_pwd_form"):
                old_pw = st.text_input("輸入舊密碼", type="password")
                new_pw = st.text_input("輸入新密碼", type="password")
                confirm_pw = st.text_input("確認新密碼", type="password")
                
                if st.form_submit_button("儲存修改", use_container_width=True):
                    if not old_pw or not new_pw or not confirm_pw:
                        st.error("⚠️ 密碼欄位不可為空白")
                    elif new_pw != confirm_pw:
                        st.error("⚠️ 新密碼與確認密碼不一致")
                    else:
                        success, msg = update_password(current_user, old_pw, new_pw)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)
        
        if st.button("🚪 登出系統", type="primary", use_container_width=True):
            st.session_state['logged_in'] = False
            st.session_state['username'] = None
            st.session_state['role'] = None
            st.rerun()
        st.markdown("---")

    # ---------------------------
    # 已登入：戰情室主畫面 (Dashboard)
    # ---------------------------
    st.title("🔥 波段飆股雷達：創 200 日新高 + 法人進駐")

    with st.spinner('從資料庫拉取與運算籌碼資料中...'):
        df_stocks, df_sectors, history_data, date_str = load_and_process_data()

    if df_stocks is None or df_stocks.empty:
        st.warning("⚠️ 今日無同時符合「創200日新高」且「近3個月法人買超」的股票。")
        st.stop()

    st.caption(f"統計最新交易日: **{date_str}**")

    # 區塊 1：熱力分布圖
    fig_bar = px.bar(
        df_sectors, x='stock_count', y='industry', orientation='h',
        color='total_net', color_continuous_scale='Reds', text='stock_count',
        labels={'stock_count': '符合條件家數', 'industry': '產業', 'total_net': '近3月總買超(張)'},
        title="<b>強勢族群分布圖</b>"
    )
    fig_bar.update_layout(template="plotly_dark", yaxis={'categoryorder':'total ascending'}, height=400, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    fig_bar.update_traces(textposition='outside')
    st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("---")

    # 區塊 2：資料表
    col_table1, col_table2 = st.columns([1, 1.2])

    with col_table1:
        st.subheader("🎯 主流族群統計")
        st.markdown("<div style='height: 73px;'></div>", unsafe_allow_html=True)
        st.dataframe(
            df_sectors[['industry', 'stock_count', 'total_foreign_net', 'total_trust_net']],
            column_config={
                "industry": "產業別",
                "stock_count": "家數",
                "total_foreign_net": "近3月外資(張)",
                "total_trust_net": "近3月投信(張)",
            },
            use_container_width=True, hide_index=True, height=500 
        )

    with col_table2:
        st.subheader("💎 籌碼精選清單")
        industries = ["全市場 (All)"] + df_sectors['industry'].tolist()
        selected_industry = st.selectbox("篩選產業", industries)
        
        if selected_industry != "全市場 (All)":
            display_df = df_stocks[df_stocks['industry'] == selected_industry]
        else:
            display_df = df_stocks
            
        st.dataframe(
            display_df[['symbol', 'name', 'industry', 'close', 'foreign_net', 'trust_net']],
            column_config={
                "symbol": "代號", "name": "名稱", "industry": "產業",
                "close": st.column_config.NumberColumn("最新收盤", format="%.2f"),
                "foreign_net": "近3月外資(張)", "trust_net": "近3月投信(張)",
            },
            use_container_width=True, hide_index=True, height=500 
        )

    st.markdown("---")

    # 區塊 3：動態 K 線與指標
    st.subheader("📈 互動 K 線與籌碼指標")

    # 【修復】強制賦予初始值，並且後續由 st.checkbox 的 key 自動接管
    if 'show_macd' not in st.session_state: st.session_state['show_macd'] = True
    if 'show_kd' not in st.session_state: st.session_state['show_kd'] = True
    if 'show_rsi' not in st.session_state: st.session_state['show_rsi'] = True

    stock_options = [f"{row['symbol']} {row['name']}" for _, row in display_df.iterrows()]

    if not stock_options:
        st.warning("⚠️ 此族群目前無符合條件之個股。")
    else:
        if 'selected_stock' not in st.session_state or st.session_state.selected_stock not in stock_options:
            st.session_state.selected_stock = stock_options[0]

        current_idx = stock_options.index(st.session_state.selected_stock)

        ctrl_prev, ctrl_sel, ctrl_next, ctrl_macd, ctrl_kd, ctrl_rsi = st.columns([1, 4, 1, 1, 1, 1])

        with ctrl_prev:
            st.write("<br>", unsafe_allow_html=True) 
            if st.button("◀ 上一檔", use_container_width=True):
                current_idx = (current_idx - 1) % len(stock_options)
                st.session_state.selected_stock = stock_options[current_idx]
                st.rerun()

        with ctrl_next:
            st.write("<br>", unsafe_allow_html=True)
            if st.button("下一檔 ▶", use_container_width=True):
                current_idx = (current_idx + 1) % len(stock_options)
                st.session_state.selected_stock = stock_options[current_idx]
                st.rerun()

        with ctrl_sel:
            selected_stock_str = st.selectbox("選擇要分析的股票", options=stock_options, index=current_idx)
            if selected_stock_str != st.session_state.selected_stock:
                st.session_state.selected_stock = selected_stock_str
                st.rerun()

        # 【修復重點】拿掉 value 參數，只要有 key=，Streamlit 就會完美自動雙向綁定！
        with ctrl_macd:
            st.write("<br>", unsafe_allow_html=True)
            st.checkbox("MACD", key="show_macd")
        with ctrl_kd:
            st.write("<br>", unsafe_allow_html=True)
            st.checkbox("KD(9,3)", key="show_kd")
        with ctrl_rsi:
            st.write("<br>", unsafe_allow_html=True)
            st.checkbox("RSI(14)", key="show_rsi")

        selected_symbol = st.session_state.selected_stock.split(" ")[0]

        if selected_symbol and selected_symbol in history_data:
            # 從 st.session_state 讀取狀態
            fig_kline = create_kline_chart(
                history_data[selected_symbol], 
                st.session_state.selected_stock, 
                st.session_state['show_macd'], 
                st.session_state['show_kd'], 
                st.session_state['show_rsi']
            )
            st.plotly_chart(fig_kline, use_container_width=True)
