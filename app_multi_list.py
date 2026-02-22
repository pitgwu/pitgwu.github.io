import streamlit as st
import pandas as pd
import sqlalchemy
from sqlalchemy import text
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import uuid
import bcrypt # 需 pip install bcrypt

# ===========================
# 1. 資料庫連線與全域設定
# ===========================
st.set_page_config(page_title="自選股戰情室", layout="wide")

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
    st.markdown("<h1 style='text-align: center;'>🔐 自選股戰情室</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        tab_login, tab_register = st.tabs(["🔑 登入", "📝 註冊新帳號"])
        
        # --- 登入區塊 ---
        with tab_login:
            with st.form("login_form"):
                username = st.text_input("帳號")
                password = st.text_input("密碼", type="password")
                submit = st.form_submit_button("登入", use_container_width=True)
                if submit:
                    success, role, msg = check_login(username, password)
                    if success:
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = username
                        st.session_state['role'] = role
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                        
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
# 3. DB 操作函式
# ===========================
def get_all_lists_db(username):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT name FROM watchlist_menus WHERE username = :u ORDER BY name"), {"u": username})
        return [row[0] for row in result]

def get_list_data_db(list_name, username):
    query = """
    SELECT i.symbol, i.added_date
    FROM watchlist_items i
    JOIN watchlist_menus m ON i.menu_id = m.id
    WHERE m.name = :list_name AND m.username = :u
    ORDER BY i.symbol
    """
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params={"list_name": list_name, "u": username})
    return df

def create_list_db(new_name, username):
    current_lists = get_all_lists_db(username)
    if len(current_lists) >= 200: return False, "群組數量已達上限"
    if new_name in current_lists: return False, "名稱已存在"
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO watchlist_menus (name, username) VALUES (:name, :u)"), {"name": new_name, "u": username})
        return True, "建立成功"
    except Exception as e: return False, str(e)

def rename_list_db(old_name, new_name, username):
    try:
        with engine.begin() as conn:
            exists = conn.execute(text("SELECT 1 FROM watchlist_menus WHERE name = :new AND username = :u"), {"new": new_name, "u": username}).scalar()
            if exists: return False, "名稱已存在"
            conn.execute(text("UPDATE watchlist_menus SET name = :new WHERE name = :old AND username = :u"), {"new": new_name, "old": old_name, "u": username})
        return True, "改名成功"
    except Exception as e: return False, str(e)

def delete_list_db(list_name, username):
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM watchlist_menus WHERE name = :name AND username = :u"), {"name": list_name, "u": username})
        return True, "刪除成功"
    except Exception as e: return False, str(e)

def add_stock_db(list_name, symbol, username):
    added_date = datetime.now().strftime('%Y-%m-%d')
    try:
        with engine.begin() as conn:
            menu_id = conn.execute(text("SELECT id FROM watchlist_menus WHERE name = :name AND username = :u"), {"name": list_name, "u": username}).scalar()
            if not menu_id: return False, "群組不存在"
            conn.execute(text("""
                INSERT INTO watchlist_items (menu_id, symbol, added_date) VALUES (:mid, :sym, :date)
                ON CONFLICT (menu_id, symbol) DO NOTHING
            """), {"mid": menu_id, "sym": symbol, "date": added_date})
        return True, "加入成功"
    except Exception as e: return False, str(e)

def remove_stock_db(list_name, symbol, username):
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM watchlist_items
                WHERE symbol=:s AND menu_id=(SELECT id FROM watchlist_menus WHERE name=:n AND username=:u)
            """), {"s": symbol, "n": list_name, "u": username})
        return True, "移除成功"
    except Exception as e: return False, str(e)

# --- ETL 資料讀取 ---
@st.cache_data(ttl=3600)
def get_stock_mapping():
    try:
        with engine.connect() as conn:
            df = pd.read_sql("SELECT symbol, name FROM stock_info", conn)
        mapping = {}
        for _, row in df.iterrows():
            sym, name = str(row['symbol']).strip(), str(row['name']).strip()
            mapping[sym.upper()] = sym
            mapping[sym.split('.')[0].upper()] = sym
            mapping[name.upper()] = sym
        return mapping
    except: return {}

def resolve_stock_symbol(input_val, mapping):
    if not input_val: return None
    return mapping.get(str(input_val).strip().upper(), None)

@st.cache_data(ttl=600)
def load_precalculated_data():
    query = """
    SELECT date, symbol, name, industry, open, high, low, close, volume,
           pct_change, foreign_net, trust_net,
           "MA5", "MA10", "MA20", "MA60",
           "K", "D", "MACD_OSC", "DIF",
           total_score as "Total_Score",
           signal_list as "Signal_List"
    FROM daily_stock_indicators
    WHERE date >= current_date - INTERVAL '130 days'
    ORDER BY symbol, date
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    if not df.empty:
        df['symbol'] = df['symbol'].astype(str).str.strip()
        df['date'] = pd.to_datetime(df['date'])
        df['Total_Score'] = df['Total_Score'].fillna(0).astype(int)
        df['Signal_List'] = df['Signal_List'].fillna("")

    return df

# --- 繪圖輔助 ---
def plot_stock_kline(df_stock, symbol, name, active_signals_text):
    df_plot = df_stock.tail(130).copy()
    df_plot['date_str'] = df_plot['date'].dt.strftime('%Y-%m-%d')
    score_val = active_signals_text.count(',') + 1 if active_signals_text else 0

    df_plot['prev_volume'] = df_plot['volume'].shift(1)
    df_plot['vol_ratio'] = df_plot['volume'] / (df_plot['volume'].rolling(5).mean() + 1e-9)

    fig = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.01,
                        row_heights=[0.45, 0.1, 0.1, 0.1, 0.15],
                        subplot_titles=(f"{symbol} {name} (評分:{score_val})", "量", "KD", "MACD", "訊號"))

    fig.add_trace(go.Candlestick(
        x=df_plot['date_str'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'],
        name='K線', increasing_line_color='red', decreasing_line_color='green'
    ), row=1, col=1)

    for ma, color in zip(['MA5','MA10','MA20','MA60'], ['#FFA500','#00FFFF','#BA55D3','#4169E1']):
        if ma in df_plot: fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot[ma], mode='lines', name=ma, line=dict(color=color, width=1)), row=1, col=1)

    colors_vol = ['red' if c>=o else 'green' for c,o in zip(df_plot['close'], df_plot['open'])]
    fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['volume'], marker_color=colors_vol, name='量'), row=2, col=1)

    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['K'], name='K', line=dict(color='orange')), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['D'], name='D', line=dict(color='cyan')), row=3, col=1)

    osc_colors = ['red' if v>=0 else 'green' for v in df_plot['MACD_OSC']]
    fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['MACD_OSC'], marker_color=osc_colors, name='OSC'), row=4, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['DIF'], name='DIF', line=dict(color='orange')), row=4, col=1)

    signals = [('KD金叉', (df_plot['K']>df_plot['D'])&(df_plot['K'].shift(1)<df_plot['D'].shift(1)), 'diamond','purple'),
               ('量攻', (df_plot['volume']>df_plot['prev_volume'])&(df_plot['vol_ratio']>1.2), 'triangle-up','gold'),
               ('MACD紅', (df_plot['MACD_OSC']>0)&(df_plot['MACD_OSC'].shift(1)<0), 'square','blue')]

    for i, (lbl, mask, sym, clr) in enumerate(signals):
        sig_dates = df_plot[mask]['date_str']
        fig.add_trace(go.Scatter(x=sig_dates, y=[i]*len(sig_dates), mode='markers', name=lbl, marker=dict(symbol=sym, size=10, color=clr)), row=5, col=1)

    fig.update_xaxes(type='category', categoryorder='category ascending', tickmode='auto', nticks=15)
    fig.update_layout(height=900, xaxis_rangeslider_visible=False, showlegend=False, margin=dict(t=30,l=10,r=10,b=10))
    return fig

# ===========================
# 4. 主應用程式邏輯與 Callbacks
# ===========================
def action_search():
    inp = st.session_state.get('symbol_input_widget', '').strip()
    mapping = get_stock_mapping()
    code = resolve_stock_symbol(inp, mapping)
    if code:
        st.session_state.query_mode_symbol = code
        st.session_state.ticker_index = 0
        st.session_state.symbol_input_widget = code
        st.session_state.action_msg = ("info", f"🔍 成功查詢：{code}")
    else: st.session_state.action_msg = ("warning", "❌ 找不到該股票")

def action_add():
    sel_list, usr = st.session_state.get('selected_list_widget'), st.session_state.get('username')
    inp = st.session_state.get('symbol_input_widget', '').strip()
    mapping = get_stock_mapping()
    code = resolve_stock_symbol(inp, mapping)
    
    if code:
        # 🔥 優化：將完整的股票代號填回輸入框 (取代原先的模糊搜尋字眼)
        st.session_state.symbol_input_widget = code
        
        # 寫入資料庫
        if code not in get_list_data_db(sel_list, usr)['symbol'].tolist():
            if add_stock_db(sel_list, code, usr):
                st.session_state.action_msg = ("success", f"✅ {code} 已成功加入群組")
        else: 
            st.session_state.action_msg = ("warning", f"⚠️ 查詢成功，但 {code} 已在群組中")
            
        # 🔥 優化：確保返回「群組總覽模式」(取消單檔查詢的鎖定)
        st.session_state.query_mode_symbol = None
    else: 
        st.session_state.action_msg = ("warning", "❌ 找不到該股票")
        st.session_state.query_mode_symbol = None

def action_del():
    sel_list, usr = st.session_state.get('selected_list_widget'), st.session_state.get('username')
    inp = st.session_state.get('symbol_input_widget', '').strip()
    mapping = get_stock_mapping()
    code = resolve_stock_symbol(inp, mapping) or inp
    if code in get_list_data_db(sel_list, usr)['symbol'].tolist():
        if remove_stock_db(sel_list, code, usr):
            st.session_state.symbol_input_widget = ""
            st.session_state.action_msg = ("success", f"🗑️ {code} 移除成功")
    else: st.session_state.action_msg = ("warning", f"❌ 群組中無 {code} 此股票")
    st.session_state.query_mode_symbol = None

def main_app():
    current_user = st.session_state['username']

    with st.sidebar:
        st.markdown(f"👤 **{current_user}** ({st.session_state['role']})")
        
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
        
        if st.button("🚪 登出", type="primary", use_container_width=True):
            st.session_state['logged_in'], st.session_state['role'] = False, None
            st.rerun()
        st.markdown("---")

    for k in ['ticker_index', 'query_mode_symbol']:
        if k not in st.session_state: st.session_state[k] = None
    if 'symbol_input_widget' not in st.session_state: st.session_state.symbol_input_widget = ""
    if 'last_df_selection' not in st.session_state: st.session_state.last_df_selection = []
    if 'action_msg' not in st.session_state: st.session_state.action_msg = None

    # --- 側邊欄：股票管理 ---
    st.sidebar.header("📝 股票管理")
    all_lists = get_all_lists_db(current_user)
    if not all_lists:
        create_list_db("預設群組", current_user)
        all_lists = get_all_lists_db(current_user)

    st.sidebar.selectbox("📂 選擇群組", all_lists, index=0, key="selected_list_widget")
    selected_list = st.session_state.selected_list_widget

    watchlist_df = get_list_data_db(selected_list, current_user)
    current_symbols = watchlist_df['symbol'].tolist()

    with st.sidebar.expander(f"📋 查看群組 ({len(current_symbols)})", expanded=True):
        event = st.dataframe(watchlist_df, hide_index=True, on_select="rerun", selection_mode="single-row", use_container_width=True)
        if event.selection.rows != st.session_state.last_df_selection:
            st.session_state.last_df_selection = event.selection.rows
            if event.selection.rows:
                st.session_state.symbol_input_widget = watchlist_df.iloc[event.selection.rows[0]]['symbol']

    col_in, col_act = st.sidebar.columns([1.5, 2])
    col_in.text_input("代號/名稱", key="symbol_input_widget")
    with col_act:
        c1, c2, c3 = st.columns(3)
        c1.button("新", on_click=action_add); c2.button("刪", on_click=action_del); c3.button("查", on_click=action_search)

    if st.session_state.action_msg:
        m_type, m_txt = st.session_state.action_msg
        if m_type == "success": st.sidebar.success(m_txt)
        elif m_type == "warning": st.sidebar.warning(m_txt)
        elif m_type == "info": st.sidebar.info(m_txt)
        st.session_state.action_msg = None

    with st.sidebar.expander("⚙️ 群組管理"):
        # 1. 建立群組
        new_list_name = st.text_input("建立新群組名稱")
        if st.button("建立"):
            if new_list_name:
                success, msg = create_list_db(new_list_name, current_user)
                if success: 
                    st.success(msg)
                    st.rerun()
                else: 
                    st.error(msg)
            else:
                st.warning("⚠️ 請輸入群組名稱")
                
        st.markdown("---") 
        
        # 2. 改名群組
        rename_text = st.text_input("改名為")
        if st.button("改名"):
            if rename_text:
                success, msg = rename_list_db(selected_list, rename_text, current_user)
                if success: 
                    st.success(msg)
                    st.rerun()
                else: 
                    st.error(msg)
            else:
                st.warning("⚠️ 請輸入新名稱")
                
        st.markdown("---")
        
        # 3. 刪除群組
        if st.button("⚠️ 刪除", type="primary"):
            if len(all_lists) > 1:
                if delete_list_db(selected_list, current_user): st.rerun()
            else: 
                st.warning("至少保留一個群組")

    st.sidebar.markdown("---")

    # --- 主畫面資料載入 ---
    with st.spinner("載入戰情數據..."):
        df_full = load_precalculated_data()

    if df_full.empty:
        st.error("⚠️ 資料庫中尚無 `daily_stock_indicators` 數據，請先執行 ETL 腳本。")
        st.stop()

    avail_dates = sorted(df_full['date'].dt.date.unique(), reverse=True)
    st.sidebar.header("📅 戰情參數")
    sel_date = st.sidebar.selectbox("日期", avail_dates, 0)
    sort_opt = st.sidebar.selectbox("排序", ["強勢總分", "加入日期", "漲跌幅", "外資買超", "投信買超"])
    min_sc = st.sidebar.number_input("分數門檻", 0, 50, 4)

    df_day = df_full[df_full['date'] == pd.Timestamp(sel_date)].copy()

    if st.session_state.query_mode_symbol:
        target_syms = [st.session_state.query_mode_symbol]
        title = f"🔍 查詢：{target_syms[0]}"
    else:
        target_syms = current_symbols
        title = f"📊 {selected_list}：{len(target_syms)} 檔"

    df_day = df_day[df_day['symbol'].astype(str).isin(target_syms)]

    if not st.session_state.query_mode_symbol:
        df_day = pd.merge(df_day, watchlist_df, on='symbol', how='left')
    else:
        df_day['added_date'] = '查詢'

    if df_day.empty:
        st.warning("⚠️ 無符合資料")
        return

    if min_sc > 0 and not st.session_state.query_mode_symbol:
        df_day = df_day[df_day['Total_Score'] >= min_sc]

    if not st.session_state.query_mode_symbol:
        if "強勢總分" in sort_opt: df_day = df_day.sort_values(['Total_Score','symbol'], ascending=[False,True])
        elif "加入" in sort_opt: df_day = df_day.sort_values(['added_date','symbol'], ascending=[False,True])
        elif "漲跌" in sort_opt: df_day = df_day.sort_values(['pct_change','symbol'], ascending=[False,True])
        elif "外資" in sort_opt: df_day = df_day.sort_values(['foreign_net','symbol'], ascending=[False,True])
        elif "投信" in sort_opt: df_day = df_day.sort_values(['trust_net','symbol'], ascending=[False,True])
        else: df_day = df_day.sort_values('symbol')

    display_df = df_day[['symbol','name','added_date','industry','close','pct_change','Total_Score','Signal_List']].reset_index(drop=True)
    sym_list = display_df['symbol'].tolist()

    if st.session_state.query_mode_symbol:
        if st.button("🔙 返回群組"):
            st.session_state.query_mode_symbol = None
            st.rerun()

    st.success(f"{title} (符合門檻剩 {len(sym_list)} 檔)")

    evt = st.dataframe(
        display_df.style.format({
            "pct_change": "{:.2f}%",
            "close": "{:.2f}",
            "Total_Score": "{:.0f}"
        }).background_gradient(subset=['Total_Score'], cmap='Reds'),
        on_select="rerun", selection_mode="single-row", use_container_width=True,
        column_config={"Signal_List": st.column_config.TextColumn("觸發訊號", width="large")}
    )

    if evt.selection.rows: st.session_state.ticker_index = evt.selection.rows[0]

    if not sym_list:
        st.warning("目前無符合過濾條件的股票。您可以降低「分數門檻」查看更多。")
        return

    if st.session_state.ticker_index is None or st.session_state.ticker_index >= len(sym_list):
        st.session_state.ticker_index = 0

    st.markdown("---")
    c1,c2,c3,c4,c5 = st.columns([1,1,4,1,1])
    if c1.button("⏮️"): st.session_state.ticker_index = 0
    if c2.button("⬅️"): st.session_state.ticker_index = (st.session_state.ticker_index - 1) % len(sym_list)
    if c4.button("➡️"): st.session_state.ticker_index = (st.session_state.ticker_index + 1) % len(sym_list)
    if c5.button("⏭️"): st.session_state.ticker_index = len(sym_list) - 1

    cur_sym = sym_list[st.session_state.ticker_index]
    cur_info = display_df.iloc[st.session_state.ticker_index]
    st.session_state.last_viewed_symbol = cur_sym

    with c3:
        st.markdown(f"<h3 style='text-align:center;color:#FF4B4B'>{cur_sym} {cur_info['name']} | 分:{int(cur_info['Total_Score'])}</h3>", unsafe_allow_html=True)
        st.info(f"⚡ {cur_info['Signal_List']}")

    chart_src = df_full[df_full['symbol']==cur_sym].sort_values('date')
    chart_src = chart_src[chart_src['date'] <= pd.Timestamp(sel_date)]

    if len(chart_src)<30: st.error("資料不足")
    else:
        fig = plot_stock_kline(chart_src, cur_sym, cur_info['name'], cur_info['Signal_List'])
        st.plotly_chart(fig, use_container_width=True, key=f"chart_{cur_sym}_{uuid.uuid4()}")

# ===========================
# 6. 程式進入點
# ===========================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login_page()
else: main_app()
