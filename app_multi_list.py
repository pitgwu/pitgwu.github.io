import streamlit as st
import pandas as pd
import numpy as np
import sqlalchemy
from sqlalchemy import text
from sqlalchemy.pool import NullPool
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import uuid
import bcrypt

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
    return sqlalchemy.create_engine(SUPABASE_DB_URL, poolclass=NullPool)

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
                    if active == 'yes': return True, role, "登入成功"
                    else: return False, None, "⚠️ 您的帳號尚未開通，請聯繫管理員"
            return False, None, "❌ 帳號或密碼錯誤"
    except Exception as e: return False, None, f"系統錯誤: {e}"

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
            return True, f"✅ 帳號 {username} 已新增，請等待開通"
    except Exception as e: return False, f"系統錯誤: {e}"

def update_password(username, old_password, new_password):
    try:
        with engine.begin() as conn:
            result = conn.execute(text("SELECT password_hash FROM users WHERE username = :u"), {"u": username}).fetchone()
            if not result: return False, "找不到使用者帳號"
            if not bcrypt.checkpw(old_password.encode('utf-8'), result[0].encode('utf-8')): return False, "❌ 舊密碼錯誤"
            new_hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            conn.execute(text("UPDATE users SET password_hash = :p WHERE username = :u"), {"p": new_hashed_pw, "u": username})
            return True, "✅ 密碼修改成功！"
    except Exception as e: return False, f"系統錯誤: {e}"

# ===========================
# 3. DB 操作函式 (🚀 加入極速快取機制)
# ===========================
def clear_db_cache():
    """當新增/刪除群組或股票時，強制清除快取，以獲取最新資料"""
    get_all_lists_db.clear()
    get_list_data_db.clear()

@st.cache_data(ttl=3600, show_spinner=False)
def get_all_users_db(current_username):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT username FROM users WHERE username != :u ORDER BY username"), {"u": current_username}).fetchall()
            return [row[0] for row in result]
    except Exception: return []

@st.cache_data(ttl=3600, show_spinner=False)
def get_all_lists_db(username):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT name FROM watchlist_menus WHERE username = :u ORDER BY name"), {"u": username})
        return [row[0] for row in result]

@st.cache_data(ttl=3600, show_spinner=False)
def get_list_data_db(list_name, username):
    query = """
    SELECT i.symbol, i.added_date
    FROM watchlist_items i
    JOIN watchlist_menus m ON i.menu_id = m.id
    WHERE m.name = :list_name AND m.username = :u
    ORDER BY i.symbol
    """
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params={"list_name": list_name, "u": username})

def create_list_db(new_name, username):
    current_lists = get_all_lists_db(username)
    if len(current_lists) >= 200: return False, "群組數量已達上限"
    if new_name in current_lists: return False, "名稱已存在"
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO watchlist_menus (name, username) VALUES (:name, :u)"), {"name": new_name, "u": username})
        clear_db_cache()
        return True, "建立成功"
    except Exception as e: return False, str(e)

def rename_list_db(old_name, new_name, username):
    try:
        with engine.begin() as conn:
            exists = conn.execute(text("SELECT 1 FROM watchlist_menus WHERE name = :new AND username = :u"), {"new": new_name, "u": username}).scalar()
            if exists: return False, "名稱已存在"
            conn.execute(text("UPDATE watchlist_menus SET name = :new WHERE name = :old AND username = :u"), {"new": new_name, "old": old_name, "u": username})
        clear_db_cache()
        return True, "改名成功"
    except Exception as e: return False, str(e)

def delete_list_db(list_name, username):
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM watchlist_menus WHERE name = :name AND username = :u"), {"name": list_name, "u": username})
        clear_db_cache()
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
        clear_db_cache()
        return True, "加入成功"
    except Exception as e: return False, str(e)

def remove_stock_db(list_name, symbol, username):
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM watchlist_items
                WHERE symbol=:s AND menu_id=(SELECT id FROM watchlist_menus WHERE name=:n AND username=:u)
            """), {"s": symbol, "n": list_name, "u": username})
        clear_db_cache()
        return True, "移除成功"
    except Exception as e: return False, str(e)

def clone_list_db(list_name, source_username, target_username):
    if source_username == target_username: return False, "⚠️ 不能分享給自己喔！"
    try:
        with engine.begin() as conn:
            target_exists = conn.execute(text("SELECT 1 FROM users WHERE username = :u"), {"u": target_username}).scalar()
            if not target_exists: return False, f"❌ 找不到帳號 '{target_username}'"
            target_list_name = list_name
            name_conflict = conn.execute(text("SELECT 1 FROM watchlist_menus WHERE name = :n AND username = :u"), {"n": target_list_name, "u": target_username}).scalar()
            if name_conflict: return False, f"❌ 對方已有 '{target_list_name}'，請先更名。"
            source_menu_id = conn.execute(text("SELECT id FROM watchlist_menus WHERE name = :n AND username = :u"), {"n": list_name, "u": source_username}).scalar()
            items = conn.execute(text("SELECT symbol FROM watchlist_items WHERE menu_id = :mid"), {"mid": source_menu_id}).fetchall()
            new_menu_id = conn.execute(text("INSERT INTO watchlist_menus (name, username) VALUES (:n, :u) RETURNING id"), {"n": target_list_name, "u": target_username}).scalar()
            if items:
                added_date = datetime.now().strftime('%Y-%m-%d')
                insert_data = [{"mid": new_menu_id, "sym": row[0], "date": added_date} for row in items]
                conn.execute(text("INSERT INTO watchlist_items (menu_id, symbol, added_date) VALUES (:mid, :sym, :date) ON CONFLICT DO NOTHING"), insert_data)
        return True, f"✅ 已成功將「{list_name}」分享給 {target_username}！"
    except Exception as e: return False, f"系統錯誤: {str(e)}"

@st.cache_data(ttl=3600, show_spinner=False)
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

# 🚀 終極效能核心：預先打包成 O(1) 字典，告別全表掃描！
@st.cache_resource(ttl=600, show_spinner=False)
def load_precalculated_data():
    query = """
    SELECT d.date, d.symbol, d.name, d.industry, d.open, d.high, d.low, d.close, d.volume,
           d.pct_change, d.foreign_net, d.trust_net,
           d."MA5", d."MA10", d."MA20", d."MA60",
           d."K", d."D", d."MACD_OSC", d."DIF",
           d.total_score as "Total_Score",
           d.signal_list as "Signal_List",
           e."Capital", e."2026EPS", d."Vol_Ratio"
    FROM strongbuy_indicators d
    LEFT JOIN stock_eps e ON d.symbol = e."Symbol"
    WHERE d.date >= current_date - INTERVAL '160 days'
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)

    if df.empty:
        return {}, {}, {}, None, []

    df['symbol'] = df['symbol'].astype(str).str.strip()
    df['date'] = pd.to_datetime(df['date'])
    df['Total_Score'] = df['Total_Score'].fillna(0).astype(int)
    df['Signal_List'] = df['Signal_List'].fillna("")
    df['Capital'] = pd.to_numeric(df['Capital'], errors='coerce')
    df['2026EPS'] = pd.to_numeric(df['2026EPS'], errors='coerce')
    df['PE_Ratio'] = np.where((df['2026EPS'] > 0) & df['2026EPS'].notna(), df['close'] / df['2026EPS'], np.nan)

    # 💎 神奇魔法：在這裡把 30 萬筆資料群組化並轉成字典，之後每次點擊都只要 0.0001 秒！
    max_date = df['date'].max()
    avail_dates = sorted(df['date'].dt.date.unique(), reverse=True)
    
    # 建立以 "日期" 為 Key 的字典
    df_dict_by_date = {dt: group for dt, group in df.groupby('date')}
    
    # 建立以 "股票代號" 為 Key 的字典
    df_dict_by_symbol = {sym: group.sort_values('date') for sym, group in df.groupby('symbol')}
    
    # 預先算好最新一天的收盤價字典
    latest_prices_map = df_dict_by_date[max_date].set_index('symbol')['close'].to_dict()

    return df_dict_by_date, df_dict_by_symbol, latest_prices_map, max_date, avail_dates

# --- 繪圖輔助 (✨全新優化：白底專業風格配色) ---
def plot_stock_kline(df_stock, symbol, name, show_macd, show_kd, show_rsi):
    df_calc = df_stock.copy()

    # 計算 3倍布林帶寬與 MA3
    df_calc['MA3'] = df_calc['close'].rolling(window=3).mean()
    df_calc['std20'] = df_calc['close'].rolling(window=20).std()
    df_calc['BB_up'] = df_calc['MA20'] + 3 * df_calc['std20']
    df_calc['BB_low'] = df_calc['MA20'] - 3 * df_calc['std20']

    # 計算 MACD Signal
    df_calc['MACD_Signal'] = df_calc['DIF'] - df_calc['MACD_OSC']

    # 計算 RSI(14)
    delta = df_calc['close'].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, float('nan'))
    df_calc['RSI'] = 100 - (100 / (1 + rs))
    df_calc['RSI'] = df_calc['RSI'].fillna(50)

    df_plot = df_calc.tail(130).copy()
    df_plot['date_str'] = df_plot['date'].dt.strftime('%Y-%m-%d')
    df_plot['prev_volume'] = df_plot['volume'].shift(1)
    df_plot['vol_ratio_ma'] = df_plot['volume'] / (df_plot['volume'].rolling(5).mean() + 1e-9)

    # 決定要顯示的動態副圖
    panels = [{'name': 'volume', 'title': '成交量 (張)'}]
    if show_macd: panels.append({'name': 'macd', 'title': 'MACD'})
    if show_kd: panels.append({'name': 'kd', 'title': 'KD (9,3)'})
    if show_rsi: panels.append({'name': 'rsi', 'title': 'RSI (14)'})
    panels.append({'name': 'foreign', 'title': '外資買賣超 (張)'})
    panels.append({'name': 'trust', 'title': '投信買賣超 (張)'})
    panels.append({'name': 'signals', 'title': '觸發訊號'})

    num_subplots = 1 + len(panels)
    row_heights = [0.45] + [(0.55 / len(panels))] * len(panels)
    subplot_titles = [f"📈 {symbol} {name}"] + [f"📊 {p['title']}" for p in panels]

    fig = make_subplots(
        rows=num_subplots, cols=1, shared_xaxes=True,
        vertical_spacing=0.03, row_heights=row_heights,
        subplot_titles=subplot_titles
    )

    # ================= 區塊 1: K線、布林通道、均線 (白底專業配色) =================
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['BB_up'], mode='lines', line=dict(color='rgba(80, 80, 80, 0.5)', dash='dot', width=1), name='3倍布林', legendgroup='bb'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['BB_low'], mode='lines', line=dict(color='rgba(80, 80, 80, 0.5)', dash='dot', width=1), name='BB-3', legendgroup='bb', showlegend=False, fill='tonexty', fillcolor='rgba(200, 200, 200, 0.2)'), row=1, col=1)

    if 'MA3' in df_plot: fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['MA3'], line=dict(color='#FF00FF', width=1.5), name='3MA(紫紅)'), row=1, col=1)
    if 'MA5' in df_plot: fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['MA5'], line=dict(color='#000000', width=1.5), name='5MA(黑)'), row=1, col=1)
    if 'MA10' in df_plot: fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['MA10'], line=dict(color='#8B008B', width=1.5), name='10MA(深紫)'), row=1, col=1)
    if 'MA20' in df_plot: fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['MA20'], line=dict(color='#FF8C00', width=1.5), name='20MA(橘)'), row=1, col=1)
    if 'MA60' in df_plot: fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['MA60'], line=dict(color='#0000FF', width=1.5), name='60MA(藍)'), row=1, col=1)

    fig.add_trace(go.Candlestick(
        x=df_plot['date_str'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'],
        name='K線', increasing_line_color='#E13C3C', decreasing_line_color='#2CA045', showlegend=False
    ), row=1, col=1)

    # ================= 區塊 2: 動態副圖 =================
    current_row = 2
    for p in panels:
        if p['name'] == 'volume':
            colors_vol = ['#E13C3C' if c >= o else '#2CA045' for c, o in zip(df_plot['close'], df_plot['open'])]
            fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['volume'], marker_color=colors_vol, name='成交量', showlegend=False), row=current_row, col=1)

        elif p['name'] == 'macd':
            macd_colors = ['#E13C3C' if v >= 0 else '#2CA045' for v in df_plot['MACD_OSC']]
            fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['DIF'], line=dict(color='#0000FF', width=1.5), name='DIF', showlegend=False), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['MACD_Signal'], line=dict(color='#FF8C00', width=1.5), name='Signal', showlegend=False), row=current_row, col=1)
            fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['MACD_OSC'], marker_color=macd_colors, name='OSC', showlegend=False), row=current_row, col=1)

        elif p['name'] == 'kd':
            fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['K'], line=dict(color='#FF8C00', width=1.5), name='K(9)', showlegend=False), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['D'], line=dict(color='#0000FF', width=1.5), name='D(3)', showlegend=False), row=current_row, col=1)
            fig.add_hline(y=80, line_dash="dash", line_color="#999999", row=current_row, col=1)
            fig.add_hline(y=20, line_dash="dash", line_color="#999999", row=current_row, col=1)

        elif p['name'] == 'rsi':
            fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['RSI'], line=dict(color='#8A2BE2', width=1.5), name='RSI(14)', showlegend=False), row=current_row, col=1)

        elif p['name'] == 'foreign':
            colors_for = ['#E13C3C' if v > 0 else '#2CA045' for v in df_plot['foreign_net']]
            fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['foreign_net'], marker_color=colors_for, name='外資進出', showlegend=False), row=current_row, col=1)

        elif p['name'] == 'trust':
            colors_tru = ['#E13C3C' if v > 0 else '#2CA045' for v in df_plot['trust_net']]
            fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['trust_net'], marker_color=colors_tru, name='投信進出', showlegend=False), row=current_row, col=1)

        elif p['name'] == 'signals':
            signals = [('KD金叉', (df_plot['K']>df_plot['D'])&(df_plot['K'].shift(1)<df_plot['D'].shift(1)), 'diamond','#FF8C00'),
                       ('量攻', (df_plot['volume']>df_plot['prev_volume'])&(df_plot['vol_ratio_ma']>1.2), 'triangle-up','#E13C3C'),
                       ('MACD紅', (df_plot['MACD_OSC']>0)&(df_plot['MACD_OSC'].shift(1)<0), 'square','#0000FF')]

            for i, (lbl, mask, sym, clr) in enumerate(signals):
                sig_dates = df_plot[mask]['date_str']
                fig.add_trace(go.Scatter(x=sig_dates, y=[i]*len(sig_dates), mode='markers', name=lbl, marker=dict(symbol=sym, size=10, color=clr), showlegend=False), row=current_row, col=1)

        current_row += 1

    for annotation in fig['layout']['annotations']:
        annotation['font'] = dict(size=14, color="#333333")
        annotation['x'] = 0.01
        annotation['xanchor'] = 'left'

    fig.update_layout(
        template="plotly_white",
        height=850 + (100 * (len(panels)-4)),
        margin=dict(l=40, r=20, t=50, b=20),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="black")),
        paper_bgcolor='rgba(255,255,255,1)',
        plot_bgcolor='rgba(255,255,255,1)',
        font=dict(color='black')
    )
    fig.update_xaxes(type='category', categoryorder='category ascending', nticks=20, tickangle=45, showgrid=True, gridcolor='#E0E0E0')
    fig.update_yaxes(showgrid=True, gridcolor='#E0E0E0')
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
        st.session_state.symbol_input_widget = code
        if code not in get_list_data_db(sel_list, usr)['symbol'].tolist():
            if add_stock_db(sel_list, code, usr):
                st.session_state.action_msg = ("success", f"✅ {code} 已加入群組")
        else:
            st.session_state.action_msg = ("warning", f"⚠️ 查詢成功，但 {code} 已在群組中")
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
    else: st.session_state.action_msg = ("warning", f"❌ 群組中無 {code}")
    st.session_state.query_mode_symbol = None

def login_page():
    st.markdown("<h1 style='text-align: center;'>🔐 自選股戰情室</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["🔑 登入", "📝 註冊新帳號"])
        with tab_login:
            with st.form("login_form"):
                username = st.text_input("帳號")
                password = st.text_input("密碼", type="password")
                if st.form_submit_button("登入", use_container_width=True):
                    success, role, msg = check_login(username, password)
                    if success:
                        st.session_state.update({'logged_in': True, 'username': username, 'role': role})
                        st.success(msg); st.rerun()
                    else: st.error(msg)
        with tab_register:
            with st.form("register_form"):
                new_username = st.text_input("設定帳號")
                new_password = st.text_input("設定密碼", type="password")
                confirm_password = st.text_input("確認密碼", type="password")
                if st.form_submit_button("註冊", use_container_width=True):
                    if not new_username or not new_password: st.error("⚠️ 欄位不可為空")
                    elif new_password != confirm_password: st.error("⚠️ 密碼不一致")
                    else:
                        success, msg = register_user(new_username, new_password)
                        if success: st.success(msg)
                        else: st.error(msg)

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
                    if not old_pw or not new_pw or not confirm_pw: st.error("⚠️ 不可為空")
                    elif new_pw != confirm_pw: st.error("⚠️ 密碼不一致")
                    else:
                        success, msg = update_password(current_user, old_pw, new_pw)
                        if success: st.success(msg)
                        else: st.error(msg)
        if st.button("🚪 登出", type="primary", use_container_width=True):
            st.session_state.update({'logged_in': False, 'role': None}); st.rerun()
        st.markdown("---")

    for k in ['ticker_index', 'query_mode_symbol']:
        if k not in st.session_state: st.session_state[k] = None
    if 'symbol_input_widget' not in st.session_state: st.session_state.symbol_input_widget = ""
    if 'last_df_selection' not in st.session_state: st.session_state.last_df_selection = []
    if 'action_msg' not in st.session_state: st.session_state.action_msg = None

    if 'show_macd' not in st.session_state: st.session_state['show_macd'] = True
    if 'show_kd' not in st.session_state: st.session_state['show_kd'] = True
    if 'show_rsi' not in st.session_state: st.session_state['show_rsi'] = True

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
        c1, c2, c3, c4 = st.columns(4) # 多加一格給重整按鈕
        c1.button("新", on_click=action_add)
        c2.button("刪", on_click=action_del)
        c3.button("查", on_click=action_search)
        
        # 👇 補上這個強制清除快取的按鈕
        if c4.button("🔄"):
            st.cache_data.clear()
            st.rerun()

    if st.session_state.action_msg:
        m_type, m_txt = st.session_state.action_msg
        if m_type == "success": st.sidebar.success(m_txt)
        elif m_type == "warning": st.sidebar.warning(m_txt)
        elif m_type == "info": st.sidebar.info(m_txt)
        st.session_state.action_msg = None

    with st.sidebar.expander("⚙️ 群組管理"):
        new_list_name = st.text_input("建立新群組名稱")
        if st.button("建立"):
            if new_list_name:
                success, msg = create_list_db(new_list_name, current_user)
                if success: st.success(msg); st.rerun()
                else: st.error(msg)
            else: st.warning("⚠️ 請輸入群組名稱")

        st.markdown("---")
        rename_text = st.text_input("改名為")
        if st.button("改名"):
            if rename_text:
                success, msg = rename_list_db(selected_list, rename_text, current_user)
                if success: st.success(msg); st.rerun()
                else: st.error(msg)
            else: st.warning("⚠️ 請輸入新名稱")

        st.markdown("---")
        other_users = get_all_users_db(current_user)
        if other_users:
            target_user = st.selectbox("分享目前群組給", options=other_users)
            if st.button("分享"):
                if target_user:
                    success, msg = clone_list_db(selected_list, current_user, target_user)
                    if success: st.success(msg)
                    else: st.error(msg)
        else: st.info("目前無其他帳號可分享。")

        st.markdown("---")
        if st.button("⚠️ 刪除", type="primary"):
            if len(all_lists) > 1:
                if delete_list_db(selected_list, current_user): st.rerun()
            else: st.warning("至少保留一個群組")

    st.sidebar.markdown("---")

    # --- 主畫面資料載入 (🚀 極速 O(1) 提取) ---
    with st.spinner("載入戰情數據..."):
        df_dict_by_date, df_dict_by_symbol, latest_prices_map, max_date, avail_dates = load_precalculated_data()

    if not df_dict_by_date:
        st.error("⚠️ 資料庫中尚無 `strongbuy_indicators` 數據，請先執行 ETL 腳本。")
        st.stop()

    st.sidebar.header("📅 戰情參數")
    sel_date = st.sidebar.selectbox("日期", avail_dates, 0)
    is_past_date = pd.Timestamp(sel < max_date

    sort_opts = ["強勢總分", "加入日期", "漲跌幅", "外資買超", "投信買超", "量增比"]
    if is_past_date: sort_opts.append("回測報酬率")

    sort_opt = st.sidebar.selectbox("排序", sort_opts)
    min_sc = st.sidebar.number_input("分數門檻", 0, 50, 4)

    # 🚀 O(1) 取出該日的 DataFrame
    df_day = df_dict_by_date[pd.Timestamp(sel_date)].copy()

    if st.session_state.query_mode_symbol:
        target_syms = [st.session_state.query_mode_symbol]
        查詢：{target_syms[0]}"
    else:
        target_syms = current_symbols
        title = f"📊 {selected_list}：{len(target_syms)} 檔"

    # 🚀 O(1) 篩選出目前群組的股票 (免去了 merge 的龐大負擔)
    df_day = df_day[df_day['symbol'].isin(target_syms)]

    if not st.session_state.query_mode_symbol:
        df_day = pd.merge(df_day, watchlist_df, on='symbol', how='left')
    else:
        df_day['added_date'] = '查詢'

    if df_day.empty:
        st.warning("⚠️ 無符合資æ       return

    # 🚀 極速回測計算：用 map 代替 pandas 的跨日大掃描
    if is_past_date:
        df_day['latest_close'] = df_day['symbol'].map(latest_prices_map)
        df_day['Backtest_Return'] = (df_day['latest_close'] - df_day['close']) / df_day['close'] * 100

    if min_sc > 0 and not st.session_state.query_mode_symbol:
        df_day = df_day[df_day['Total_Score'] >= min_sc]

    if not st.session_state.query_mode_symbol:
        if "強勢總分" in sort_opt: df_day = df_day.sor'Total_Score','symbol'], ascending=[False,True])
        elif "加入" in sort_opt: df_day = df_day.sort_values(['added_date','symbol'], ascending=[False,True])
        elif "漲跌" in sort_opt: df_day = df_day.sort_values(['pct_change','symbol'], ascending=[False,True])
        elif "外資" in sort_opt: df_day = df_day.sort_values(['foreign_net','symbol'], ascending=[False,True])
        elif "投信" in sort_opt: df_day = df_day.sort_values(['trust_net','symbol'], ascending=[False,True])
        elif "é比" in sort_opt: df_day = df_day.sort_values(['Vol_Ratio','symbol'], ascending=[False,True])
        elif "回測報酬率" in sort_opt: df_day = df_day.sort_values(['Backtest_Return','symbol'], ascending=[False,True])
        else: df_day = df_day.sort_values('symbol')

    display_cols = ['symbol','name','added_date','industry','close','pct_change', 'Vol_Ratio']
    if is_past_date: display_cols.append('Backtest_Return')
    display_cols.extend(['Capital', '2026EPS', 'PE_Ratio', 'Total_Score','Signal_isplay_df = df_day[display_cols].reset_index(drop=True)
    sym_list = display_df['symbol'].tolist()

    if st.session_state.query_mode_symbol:
        if st.button("🔙 返回群組"):
            st.session_state.query_mode_symbol = None
            st.rerun()

    st.success(f"{title} (符合門檻剩 {len(sym_list)} 檔)")

    def format_vol_ratio(x):
        if pd.isna(x): return "-"
        if x >= 2.0: return f"🔥 {x:.1f}x"
        return f"{x:.1f}x"

    fmt_dict = {"pct_change": "{:.2f}%", "cl:.2f}", "Capital": "{:.1f}", "2026EPS": "{:.2f}", "PE_Ratio": "{:.2f}", "Total_Score": "{:.0f}", "Vol_Ratio": format_vol_ratio}
    col_cfg = {"Capital": "股本", "2026EPS": "2026EPS", "PE_Ratio": "本益比", "Vol_Ratio": "量增比", "Signal_List": st.column_config.TextColumn("觸發訊號", width="large")}
    if is_past_date:
        fmt_dict["Backtest_Return"] = "{:.2f}%"
        col_cfg["Backtest_Return"] = "回測報酬率"

    evt = st.dataframe(
        display_df.style.format(fmt_dict, na_rep="-.background_gradient(subset=['Total_Score'], cmap='Reds'),
        on_select="rerun", selection_mode="single-row", use_container_width=True,
        column_config=col_cfg
    )

    if evt.selection.rows: st.session_state.ticker_index = evt.selection.rows[0]

    if not sym_list:
        st.warning("目前無符合過濾條件的股票。")
        return

    if st.session_state.ticker_index is None or st.session_state.ticker_index >= len(sym_list):
        st.session_state.ticker_index = 0

    st.markdow   c1,c2,c3,c4,c5 = st.columns([1,1,4,1,1])
    if c1.button("⏮️"): st.session_state.ticker_index = 0
    if c2.button("⬅️"): st.session_state.ticker_index = (st.session_state.ticker_index - 1) % len(sym_list)
    if c4.button("➡️"): st.session_state.ticker_index = (st.session_state.ticker_index + 1) % len(sym_list)
    if c5.button("⏭️"): st.session_state.ticker_index = len(sym_list) - 1

    cur_sym = sym_list[st.session_state.ticker_index]
    cur_info = display_df.iloc[st.session_state.ticker_index]

    with c3:
        if is_past_date and pd.notna(cur_info.get('Backtest_Return')):
            st.markdown(f"<h3 style='text-align:center;color:#FF4B4B'>{cur_sym} {cur_info['name']} | 分:{int(cur_info['Total_Score'])} | 回測: {cur_info['Backtest_Return']:.2f}%</h3>", unsafe_allow_html=True)
        else:
            st.markdown(f"<h3 style='text-align:center;color:#FF4B4B'>{cur_sym} {cur_info['name']} | 分:{int(cur_info['Total_Score'])}</h3>", unsafe_allow_html=True)

        st.info(f"â['Signal_List']}")

        col_m, col_k, col_r = st.columns(3)
        with col_m: st.checkbox("MACD", key="show_macd")
        with col_k: st.checkbox("KD(9,3)", key="show_kd")
        with col_r: st.checkbox("RSI(14)", key="show_rsi")

    # 🚀 從預處理好的字典直接拿畫圖資料，O(1) 速度，免掃描！
    chart_src = df_dict_by_symbol.get(cur_sym, pd.DataFrame()).copy()
    chart_src = chart_src[chart_src['date'] <= pd.Timestamp(sel_date)]

    if len(chart_src) < 30: st.error("資料圖")
    else:
        fig = plot_stock_kline(chart_src, cur_sym, cur_info['name'], st.session_state['show_macd'], st.session_state['show_kd'], st.session_state['show_rsi'])
        st.plotly_chart(fig, use_container_width=True, key=f"chart_{cur_sym}_{uuid.uuid4()}")

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login_page()
else: main_app()
