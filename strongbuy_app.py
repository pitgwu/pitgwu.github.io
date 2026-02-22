import streamlit as st
import pandas as pd
import sqlalchemy
from sqlalchemy import text
from sqlalchemy.pool import NullPool
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import bcrypt

# ===========================
# 1. 資料庫連線與設定
# ===========================
st.set_page_config(page_title="尾盤神探 - 全動態數值版v17", layout="wide")

SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL") 
if not SUPABASE_DB_URL:
    st.error("❌ 未偵測到 SUPABASE_DB_URL，請設定環境變數。")
    st.stop()

@st.cache_resource
def get_engine():
    return sqlalchemy.create_engine(SUPABASE_DB_URL, poolclass=NullPool)

engine = get_engine()

# ===========================
# 2. 身份驗證與註冊模組
# ===========================
def check_login(username, password):
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("SELECT password_hash, role, active FROM users WHERE username = :u"), {"u": username}
            ).fetchone()
            if result:
                db_hash, role, active = result
                if bcrypt.checkpw(password.encode('utf-8'), db_hash.encode('utf-8')):
                    if active == 'yes': return True, role, "登入成功"
                    else: return False, None, "⚠️ 您的帳號尚未開通，請聯繫管理員"
            return False, None, "❌ 帳號或密碼錯誤"
    except Exception as e: return False, None, f"系統錯誤: {e}"

def register_user(username, password):
    """處理新使用者註冊，預設 active = 'no'"""
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
    """驗證舊密碼並更新為新密碼"""
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

def login_page():
    st.markdown("<h1 style='text-align: center;'>🔐 尾盤神探系統</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        tab_login, tab_register = st.tabs(["🔑 登入", "📝 註冊新帳號"])
        
        # --- 登入區塊 ---
        with tab_login:
            with st.form("login_form"):
                u = st.text_input("帳號")
                p = st.text_input("密碼", type="password")
                if st.form_submit_button("登入", use_container_width=True):
                    success, role, msg = check_login(u, p)
                    if success:
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = u
                        st.session_state['role'] = role
                        st.success(msg)
                        st.rerun()
                    else: st.error(msg)
        
        # --- 註冊區塊 ---
        with tab_register:
            with st.form("register_form"):
                new_username = st.text_input("設定帳號")
                new_password = st.text_input("設定密碼", type="password")
                confirm_password = st.text_input("確認密碼", type="password")
                reg_submit = st.form_submit_button("註冊", use_container_width=True)
                
                if reg_submit:
                    if not new_username or not new_password:
                        st.error("⚠️ 帳號與密碼不能為空白")
                    elif new_password != confirm_password:
                        st.error("⚠️ 兩次輸入的密碼不一致，請重新確認")
                    else:
                        success, msg = register_user(new_username, new_password)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)

# ===========================
# 3. ETL 資料讀取 (極度簡化)
# ===========================
@st.cache_data(ttl=600)
def load_precalculated_data():
    query = """
    SELECT date, symbol, name, industry, open, high, low, close, volume, 
           pct_change, foreign_net, trust_net, yoy_pct,
           "MA5", "MA10", "MA20", "MA60", 
           "K", "D", "MACD_OSC", "DIF", "MACD",
           total_score as "Total_Score", 
           signal_list as "Signal_List"
    FROM strongbuy_indicators
    WHERE date >= current_date - INTERVAL '130 days'
    ORDER BY symbol, date
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
    
    if not df.empty:
        df['symbol'] = df['symbol'].astype(str).str.strip()
        df['date'] = pd.to_datetime(df['date'])
        df['Total_Score'] = df['Total_Score'].fillna(0).astype(int)
        df['Signal_List'] = df['Signal_List'].fillna("")
    return df

# ===========================
# 4. 繪圖
# ===========================
def plot_chart(df, symbol, name):
    d = df[df['symbol'] == symbol].tail(100).copy()
    d['date_str'] = d['date'].dt.strftime('%Y-%m-%d')
    
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, row_heights=[0.5, 0.15, 0.15, 0.2],
                        subplot_titles=(f"{symbol} {name}", "成交量", "KD", "MACD"), vertical_spacing=0.03)
    
    fig.add_trace(go.Candlestick(x=d['date_str'], open=d['open'], high=d['high'], low=d['low'], close=d['close'], name='Price', increasing_line_color='red', decreasing_line_color='green'), row=1, col=1)
    
    for ma, color in zip(['MA5','MA10','MA20','MA60'], ['#FFA500','#00FFFF','#BA55D3','#4169E1']):
        fig.add_trace(go.Scatter(x=d['date_str'], y=d[ma], line=dict(color=color, width=1), name=ma), row=1, col=1)
    
    colors = ['red' if c>=o else 'green' for c,o in zip(d['close'], d['open'])]
    fig.add_trace(go.Bar(x=d['date_str'], y=d['volume'], marker_color=colors, name='Volume'), row=2, col=1)
    
    fig.add_trace(go.Scatter(x=d['date_str'], y=d['K'], line=dict(color='orange'), name='K'), row=3, col=1)
    fig.add_trace(go.Scatter(x=d['date_str'], y=d['D'], line=dict(color='cyan'), name='D'), row=3, col=1)
    
    colors_macd = ['red' if v >= 0 else 'green' for v in d['MACD_OSC']]
    fig.add_trace(go.Bar(x=d['date_str'], y=d['MACD_OSC'], marker_color=colors_macd, name='OSC'), row=4, col=1)
    fig.add_trace(go.Scatter(x=d['date_str'], y=d['DIF'], line=dict(color='orange'), name='DIF'), row=4, col=1)
    fig.add_trace(go.Scatter(x=d['date_str'], y=d['MACD'], line=dict(color='cyan'), name='MACD'), row=4, col=1)

    fig.update_xaxes(type='category', categoryorder='category ascending', tickmode='auto', nticks=15)
    fig.update_layout(height=900, xaxis_rangeslider_visible=False, showlegend=False, margin=dict(t=30, l=20, r=20, b=20))
    return fig

# ===========================
# 5. 主程式邏輯
# ===========================
def main_app():
    current_user = st.session_state['username']
    
    with st.sidebar:
        st.markdown(f"👤 **{current_user}** ({st.session_state['role']})")
        
        # 🔥 修改密碼區塊
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
        
        if st.button("🚪 登出", key="logout", type="primary", use_container_width=True):
            st.session_state['logged_in'] = False; st.rerun()
        st.markdown("---")

    st.title("🚀 尾盤神探 - 全動態數值版v17")
    
    for k in ['ticker_index']: 
        if k not in st.session_state: st.session_state[k] = 0

    with st.spinner("載入戰情數據..."):
        df_full = load_precalculated_data()

    if df_full.empty:
        st.error("❌ 資料庫中尚無 strongbuy_indicators 數據，請先執行 ETL 腳本。")
        return

    dates = sorted(df_full['date'].dt.date.unique(), reverse=True)
    
    st.sidebar.header("篩選條件")
    sel_date = st.sidebar.selectbox("📅 日期", dates, 0)
    sort_opt = st.sidebar.selectbox("排序", ["總分", "漲跌幅", "外資買超", "營收YOY"])
    min_sc = st.sidebar.number_input("最低分", 0, 50, 3)

    target_ts = pd.Timestamp(sel_date)
    df_day = df_full[df_full['date'] == target_ts].copy()
    
    if df_day.empty:
        st.warning("該日無資料"); return

    res = df_day[df_day['Total_Score'] >= min_sc].copy()
    
    if sort_opt == "總分": res = res.sort_values(['Total_Score','symbol'], ascending=[False,True])
    elif sort_opt == "漲跌幅": res = res.sort_values(['pct_change','symbol'], ascending=[False,True])
    elif sort_opt == "外資買超": res = res.sort_values(['foreign_net','symbol'], ascending=[False,True])
    elif sort_opt == "營收YOY": res = res.sort_values(['yoy_pct','symbol'], ascending=[False,True])

    disp = res[['symbol','name','close','pct_change','Total_Score','Signal_List']].reset_index(drop=True)
    syms = disp['symbol'].tolist()

    st.success(f"篩選出 {len(syms)} 檔 (門檻:{min_sc})")
    
    evt = st.dataframe(disp.style.format({"pct_change":"{:.2f}%","close":"{:.2f}", "Total_Score":"{:.0f}"}).background_gradient(subset=['Total_Score'], cmap='Reds'),
                       on_select="rerun", selection_mode="single-row", use_container_width=True,
                       column_config={"Signal_List": st.column_config.TextColumn("觸發訊號", width="large")})
    
    if evt.selection.rows: st.session_state.ticker_index = evt.selection.rows[0]
    if not syms: return

    st.markdown("---")
    c1,c2,c3,c4 = st.columns([1,1,1,1])
    if c1.button("⏮️"): st.session_state.ticker_index = 0
    if c2.button("⬅️"): st.session_state.ticker_index = max(0, st.session_state.ticker_index - 1)
    if c3.button("➡️"): st.session_state.ticker_index = min(len(syms)-1, st.session_state.ticker_index + 1)
    if c4.button("⏭️"): st.session_state.ticker_index = len(syms) - 1

    cur_sym = syms[st.session_state.ticker_index]
    cur_row = res[res['symbol']==cur_sym].iloc[0]
    
    st.markdown(f"### {cur_sym} {cur_row['name']} | 分數: {int(cur_row['Total_Score'])}")
    st.info(f"💡 {cur_row['Signal_List']}")

    chart_data = df_full[df_full['symbol']==cur_sym].sort_values('date')
    chart_data = chart_data[chart_data['date']<=target_ts]
    
    if len(chart_data) > 30:
        fig = plot_chart(chart_data, cur_sym, cur_row['name'])
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("資料不足以繪圖")

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login_page()
else: main_app()
