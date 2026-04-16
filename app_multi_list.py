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
# 3. DB 操作函式 
# ===========================
def clear_db_cache():
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

# 🚀 終極效能核心：預先打包成 O(1) 字典，包含所有糾結參數與漲停標記
@st.cache_resource(ttl=600, show_spinner=False)
def load_precalculated_data():
    query = """
    SELECT d.date, d.symbol, d.name, d.industry, d.open, d.high, d.low, d.close, d.volume,
           d.pct_change, d.foreign_net, d.trust_net,
           d."MA5", d."MA10", d."MA20", d."MA60",
           d."K", d."D", d."MACD_OSC", d."DIF",
           d.total_score as "Total_Score",
           d.signal_list as "Signal_List",
           e."Capital", e."2026EPS", d."Vol_Ratio",
           lu.limit_up_dates   -- 🔥 撈出漲停日期字串
    FROM strongbuy_indicators d
    LEFT JOIN stock_eps e ON d.symbol = e."Symbol"
    LEFT JOIN limit_up_records lu ON d.symbol = lu.symbol
    WHERE d.date >= current_date - INTERVAL '200 days'
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

    # 🔥 極速比對漲停日期
    date_strs = df['date'].dt.strftime('%Y-%m-%d').values
    lu_dates = df['limit_up_dates'].fillna('').values
    df['is_limit_up'] = [1 if d in lu else 0 for d, lu in zip(date_strs, lu_dates)]

    # 🔥 向量化計算進階篩選所需參數 (補回漏掉的糾結神器邏輯)
    df = df.sort_values(['symbol', 'date'])
    is_same = df['symbol'] == df['symbol'].shift(1)

    df['MA120'] = df.groupby('symbol')['close'].transform(lambda x: x.rolling(120).mean())
    df['Vol_MA5'] = df.groupby('symbol')['volume'].transform(lambda x: x.rolling(5).mean())
    df['Vol_MA10'] = df.groupby('symbol')['volume'].transform(lambda x: x.rolling(10).mean())

    df['prev_close'] = np.where(is_same, df['close'].shift(1), np.nan)
    df['prev_high'] = np.where(is_same, df['high'].shift(1), np.nan)
    df['prev_K'] = np.where(is_same, df['K'].shift(1), np.nan)
    df['prev_D'] = np.where(is_same, df['D'].shift(1), np.nan)
    df['prev_MACD_OSC'] = np.where(is_same, df['MACD_OSC'].shift(1), np.nan)
    
    for col in ['MA5', 'MA10', 'MA20', 'MA60', 'MA120']:
        df[f'prev_{col}'] = np.where(is_same, df[col].shift(1), np.nan)

    for i in range(1, 6):
        is_same_i = df['symbol'] == df['symbol'].shift(i)
        df[f'prev{i}_foreign_net'] = np.where(is_same_i, df['foreign_net'].shift(i), np.nan)
        df[f'prev{i}_trust_net'] = np.where(is_same_i, df['trust_net'].shift(i), np.nan)

    # 確保 sq_pct 存在！
    df['max_ma'] = np.maximum(df['MA5'], np.maximum(df['MA10'], df['MA20']))
    df['min_ma'] = np.minimum(df['MA5'], np.minimum(df['MA10'], df['MA20']))
    df['sq_pct'] = (df['max_ma'] - df['min_ma']) / df['min_ma']

    df['is_kd_gc'] = (df['K'] > df['D']) & (df['prev_K'] <= df['prev_D'])
    df['is_kd_gc_mid'] = df['is_kd_gc'] & (df['K'] >= 35) & (df['K'] <= 65)
    kd_mid_1 = df['is_kd_gc_mid'].shift(1).fillna(False) & is_same
    kd_mid_2 = df['is_kd_gc_mid'].shift(2).fillna(False) & (df['symbol'] == df['symbol'].shift(2))
    df['kd_gc_3d_mid_flag'] = df['is_kd_gc_mid'] | kd_mid_1 | kd_mid_2

    # 字典打包
    max_date = df['date'].max()
    avail_dates = sorted(df['date'].dt.date.unique(), reverse=True)
    df_dict_by_date = {dt: group for dt, group in df.groupby('date')}
    df_dict_by_symbol = {sym: group.sort_values('date') for sym, group in df.groupby('symbol')}
    latest_prices_map = df_dict_by_date[max_date].set_index('symbol')['close'].to_dict()

    return df_dict_by_date, df_dict_by_symbol, latest_prices_map, max_date, avail_dates

# --- 繪圖輔助 (✨旗艦白底專業版：修復交叉與扣抵標記) ---
def plot_stock_kline(df_stock, symbol, name, selected_mas, show_ma_cross, show_limit_up, show_vol_ma5, show_vol_ma10, show_macd, show_kd, show_rsi, show_foreign, show_trust):
    df_calc = df_stock.copy()

    df_calc['MA3'] = df_calc['close'].rolling(window=3).mean()
    df_calc['MA120'] = df_calc['close'].rolling(window=120).mean()
    df_calc['std20'] = df_calc['close'].rolling(window=20).std()
    df_calc['BB_up'] = df_calc['MA20'] + 3 * df_calc['std20']
    df_calc['BB_low'] = df_calc['MA20'] - 3 * df_calc['std20']
    df_calc['prev_MA20'] = df_calc['MA20'].shift(1)
    df_calc['prev_MA60'] = df_calc['MA60'].shift(1)

    df_calc['Vol_MA5'] = df_calc['volume'].rolling(window=5).mean()
    df_calc['Vol_MA10'] = df_calc['volume'].rolling(window=10).mean()

    df_calc['MACD_Signal'] = df_calc['DIF'] - df_calc['MACD_OSC']

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

    panels = [{'name': 'volume', 'title': '成交量 (張)'}]
    if show_macd: panels.append({'name': 'macd', 'title': 'MACD'})
    if show_kd: panels.append({'name': 'kd', 'title': 'KD (9,3)'})
    if show_rsi: panels.append({'name': 'rsi', 'title': 'RSI (14)'})
    if show_foreign: panels.append({'name': 'foreign', 'title': '外資買賣超 (張)'})
    if show_trust: panels.append({'name': 'trust', 'title': '投信買賣超 (張)'})
    
    num_subplots = 1 + len(panels)
    row_heights = [0.45] + [(0.55 / len(panels))] * len(panels)
    subplot_titles = [f"📈 {symbol} {name}"] + [f"📊 {p['title']}" for p in panels]

    fig = make_subplots(rows=num_subplots, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=row_heights, subplot_titles=subplot_titles)

    # ================= 區塊 1: K線、布林通道、均線 =================
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['BB_up'], mode='lines', line=dict(color='rgba(80, 80, 80, 0.5)', dash='dot', width=1), name='3倍布林', legendgroup='bb'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['BB_low'], mode='lines', line=dict(color='rgba(80, 80, 80, 0.5)', dash='dot', width=1), name='BB-3', legendgroup='bb', showlegend=False, fill='tonexty', fillcolor='rgba(200, 200, 200, 0.2)'), row=1, col=1)

    ma_col_map = {'3MA': 'MA3', '5MA': 'MA5', '10MA': 'MA10', '20MA': 'MA20', '60MA': 'MA60', '120MA': 'MA120'}
    ma_colors = {'3MA': '#FF69B4', '5MA': 'orange', '10MA': '#00FFFF', '20MA': 'purple', '60MA': 'blue', '120MA': 'green'}
    
    y_range = df_plot['high'].max() - df_plot['low'].min()
    y_offset = y_range * 0.08

    for ma_name in selected_mas:
        col_name = ma_col_map.get(ma_name)
        if col_name and col_name in df_plot.columns:
            is_up = df_plot[col_name].iloc[-1] > df_plot[col_name].iloc[-2]
            fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot[col_name], line=dict(color=ma_colors.get(ma_name, '#333333'), width=1.5), name=f"{ma_name} {'🔺' if is_up else '▼'}"), row=1, col=1)
            
            N = int(ma_name.replace('MA', ''))
            if len(df_plot) >= N:
                deduct_idx = -N 
                x_val = df_plot['date_str'].iloc[deduct_idx]
                c_low = df_plot['low'].iloc[deduct_idx]
                y_marker = c_low - y_offset
                
                fig.add_trace(go.Scatter(x=[x_val, x_val], y=[y_marker, c_low], mode='lines', line=dict(color=ma_colors.get(ma_name, 'black'), width=1.5, dash='dot'), hoverinfo='skip', showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=[x_val], y=[y_marker], mode='markers+text', marker=dict(symbol='circle', size=22, color='white', line=dict(color=ma_colors.get(ma_name, 'black'), width=2.5)), text=[str(N)], textfont=dict(color=ma_colors.get(ma_name, 'black'), size=11, family="Arial Black"), hoverinfo='skip', showlegend=False), row=1, col=1)

    if show_ma_cross:
        gc_df = df_plot[(df_plot['MA20'] > df_plot['MA60']) & (df_plot['prev_MA20'] <= df_plot['prev_MA60'])]
        if not gc_df.empty: fig.add_trace(go.Scatter(x=gc_df['date_str'], y=gc_df['MA20'], mode='markers', marker=dict(symbol='triangle-up', size=14, color='gold', line=dict(width=1, color='darkgoldenrod')), name='20MA金叉60MA', showlegend=False), row=1, col=1)
        dc_df = df_plot[(df_plot['MA20'] < df_plot['MA60']) & (df_plot['prev_MA20'] >= df_plot['prev_MA60'])]
        if not dc_df.empty: fig.add_trace(go.Scatter(x=dc_df['date_str'], y=dc_df['MA20'], mode='markers', marker=dict(symbol='triangle-down', size=14, color='green', line=dict(width=1, color='darkgreen')), name='20MA死叉60MA', showlegend=False), row=1, col=1)

    # 🔥 新增：標記漲停 K 棒
    if show_limit_up and 'is_limit_up' in df_plot.columns:
        limit_up_df = df_plot[df_plot['is_limit_up'] == 1]
        if not limit_up_df.empty:
            fig.add_trace(go.Scatter(
                x=limit_up_df['date_str'],
                y=limit_up_df['high'] + y_offset * 0.6,
                mode='text',
                text=['🔥'] * len(limit_up_df),
                textfont=dict(size=18),
                name='漲停',
                hoverinfo='skip',
                showlegend=False
            ), row=1, col=1)

    fig.add_trace(go.Candlestick(x=df_plot['date_str'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'], name='K線', increasing_line_color='#E13C3C', decreasing_line_color='#2CA045', showlegend=False), row=1, col=1)

    # ================= 區塊 2: 動態副圖 =================
    current_row = 2
    for p in panels:
        if p['name'] == 'volume':
            colors_vol = ['#E13C3C' if c >= o else '#2CA045' for c, o in zip(df_plot['close'], df_plot['open'])]
            fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['volume'], marker_color=colors_vol, name='成交量', showlegend=False), row=current_row, col=1)
            if show_vol_ma5: fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['Vol_MA5'], line=dict(color='orange', width=1.5), name='5日均量', showlegend=False), row=current_row, col=1)
            if show_vol_ma10: fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['Vol_MA10'], line=dict(color='#00FFFF', width=1.5), name='10日均量', showlegend=False), row=current_row, col=1)
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
        current_row += 1

    for annotation in fig['layout']['annotations']:
        annotation['font'] = dict(size=14, color="#333333") 
        annotation['x'] = 0.01  
        annotation['xanchor'] = 'left'

    fig.update_layout(
        template="plotly_white", height=850 + (100 * (len(panels)-2)), margin=dict(l=40, r=20, t=50, b=20), xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="black")),
        paper_bgcolor='rgba(255,255,255,1)', plot_bgcolor='rgba(255,255,255,1)', font=dict(color='black')
    )
    fig.update_xaxes(type='category', categoryorder='category ascending', nticks=20, tickangle=45, showgrid=True, gridcolor='#E0E0E0')
    fig.update_yaxes(showgrid=True, gridcolor='#E0E0E0')
    return fig

# ===========================
# 4. 側邊欄 Callbacks
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

# ===========================
# 5. 登入與註冊介面
# ===========================
def login_page():
    st.markdown("<h1 style='text-align: center;'>🔐 自選股戰情室</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_register = st.tabs(["🔑 登入", "📝 註冊新帳號"])
        with tab_login:
            with st.form("login_form"):
                username = st.text_input("帳號")
                password = st.text_input("密碼", type="password")
                if st.form_submit_button("登入", width="stretch"):
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
                if st.form_submit_button("註冊", width="stretch"):
                    if not new_username or not new_password: st.error("⚠️ 欄位不可為空")
                    elif new_password != confirm_password: st.error("⚠️ 密碼不一致")
                    else:
                        success, msg = register_user(new_username, new_password)
                        if success: st.success(msg)
                        else: st.error(msg)

# ===========================
# 6. 主應用程式邏輯與畫面渲染
# ===========================
def main_app():
    current_user = st.session_state['username']

    # --- 側邊欄：帳號管理 ---
    with st.sidebar:
        st.markdown(f"👤 **{current_user}** ({st.session_state['role']})")
        with st.expander("⚙️ 帳號設定 (修改密碼)"):
            with st.form("change_pwd_form"):
                old_pw = st.text_input("輸入舊密碼", type="password")
                new_pw = st.text_input("輸入新密碼", type="password")
                confirm_pw = st.text_input("確認新密碼", type="password")
                if st.form_submit_button("儲存修改", width="stretch"):
                    if not old_pw or not new_pw or not confirm_pw: st.error("⚠️ 不可為空")
                    elif new_pw != confirm_pw: st.error("⚠️ 密碼不一致")
                    else:
                        success, msg = update_password(current_user, old_pw, new_pw)
                        if success: st.success(msg)
                        else: st.error(msg)
        if st.button("🚪 登出", type="primary", width="stretch"):
            st.session_state.update({'logged_in': False, 'role': None}); st.rerun()
        st.markdown("---")

    # 初始化 Session State
    for k in ['ticker_index', 'query_mode_symbol']:
        if k not in st.session_state: st.session_state[k] = None
    if 'symbol_input_widget' not in st.session_state: st.session_state.symbol_input_widget = ""
    if 'last_df_selection' not in st.session_state: st.session_state.last_df_selection = []
    if 'action_msg' not in st.session_state: st.session_state.action_msg = None
    if 'show_macd' not in st.session_state: st.session_state['show_macd'] = True
    if 'show_kd' not in st.session_state: st.session_state['show_kd'] = True
    if 'show_rsi' not in st.session_state: st.session_state['show_rsi'] = True

    # --- 側邊欄：股票與群組管理 ---
    st.sidebar.header("📝 自選股管理")
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
        c1, c2, c3, c4 = st.columns(4)
        c1.button("新", on_click=action_add)
        c2.button("刪", on_click=action_del)
        c3.button("查", on_click=action_search)
        if c4.button("🔄"):
            # 🔥 必須同時清除兩種快取，才能強制讀取資料庫最新資料
            st.cache_data.clear()
            st.cache_resource.clear()
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
        if st.button("⚠️ 刪除目前群組", type="primary"):
            if len(all_lists) > 1:
                if delete_list_db(selected_list, current_user): st.rerun()
            else: st.warning("至少保留一個群組")

    st.sidebar.markdown("---")

    # 🔥 移植：強大的動態篩選參數區塊 (與 ma_squeeze_pro 完全一致)
    st.sidebar.header("🔍 進階自選過濾器")
    use_adv_filter = st.sidebar.toggle("啟動進階篩選", value=False, help="打開後，將以這些條件過濾您目前的自選股。")

    if use_adv_filter:
        with st.sidebar.expander("⚙️ 基礎篩選參數", expanded=True):
            threshold_pct = st.slider("均線糾結度 (%)", 1.0, 10.0, 10.0, 0.5)
            min_vol = st.slider("最小成交量 (股)", 0, 5000000, 0, 50000)
            min_price = st.slider("最低股價 (元)", 0, 1000, 0, 5)
            filter_capital = st.checkbox("限制股本大小 (小於篩選值)", value=False)
            capital_limit = st.slider("股本上限 (億)", 10.0, 2000.0, 100.0, 10.0) if filter_capital else 100.0
            min_days = st.slider("最少整理天數", 1, 10, 1, 1)

        with st.sidebar.expander("📈 均線進階設定", expanded=False):
            chk_short_bull = st.checkbox("短期多頭排列 (5MA>10MA>20MA)", value=False)
            chk_long_bull = st.checkbox("長期多頭排列 (60MA>120MA)", value=False)
            chk_above_3ma = st.checkbox("股價站上三均 (5, 10, 20MA)", value=False)
            chk_above_5ma = st.checkbox("股價站上五均 (5, 10, 20, 60, 120MA)", value=False)
            chk_bias_60 = st.checkbox("股價與60MA乖離不能太大", value=False)
            bias_60ma_limit = st.slider("季線乖離率上限 (%)", 1.0, 30.0, 15.0, 1.0) if chk_bias_60 else 15.0

        # 🔥 補齊所有均線上揚選項
        with st.sidebar.expander("🔥 攻擊型態與技術指標", expanded=False):
            chk_attack_vol = st.checkbox("先前有出攻擊量 (近10日量增)", value=False)
            attack_vol_ratio = st.slider("量增倍數設定", 1.5, 5.0, 2.0, 0.1) if chk_attack_vol else 2.0
            chk_break_high = st.checkbox("有過昨日高點 (收盤價突破昨高)", value=False)
            chk_up_2pct = st.checkbox("上漲超過2%的紅K棒", value=False)
            chk_solid_red = st.checkbox("實體紅K棒至少要1/3以上", value=False)
            chk_kd_about_gc = st.checkbox("KD即將黃金交叉", value=False)
            chk_kd_3d_mid = st.checkbox("KD在三日內在中檔區黃金交叉 (35-65)", value=False)
            chk_macd_about_red = st.checkbox("MACD即將翻紅", value=False)
            chk_macd_red = st.checkbox("MACD已翻紅或持續紅", value=False)
            chk_ma_all_up = st.checkbox("多頭開花 (5/10/20/60/120全上揚)", value=False)
            chk_ma5_up = st.checkbox("5MA上揚", value=False)
            chk_ma10_up = st.checkbox("10MA上揚", value=False)
            chk_ma20_up = st.checkbox("20MA上揚", value=False)
            chk_ma60_up = st.checkbox("60MA上揚", value=False)
            chk_ma120_up = st.checkbox("120MA上揚", value=False)

        with st.sidebar.expander("🏦 籌碼型態篩選", expanded=False):
            chk_foreign_buy_3d = st.checkbox("外資連三買超", value=False)
            chk_trust_buy_3d = st.checkbox("投信連三買超", value=False)
            chk_tu_yang = st.checkbox("近期土洋合作 (外資和投信都買超)", value=False)
            chk_foreign_buy = st.checkbox("近期外資大買", value=False)
            foreign_buy_vol = st.slider("外資大買張數設定", 100, 5000, 500, 100) if chk_foreign_buy else 500
            chk_trust_buy = st.checkbox("近期投信大買", value=False)
            trust_buy_vol = st.slider("投信大買張數設定", 50, 2000, 100, 50) if chk_trust_buy else 100
            chk_trust_first_buy = st.checkbox("投信買超第一天 (連5日未買後轉買)", value=False)

    # ===========================
    # 戰情室主畫面 (Dashboard)
    # ===========================
    st.title("🚀 自選股戰情室")

    with st.spinner("載入戰情數據..."):
        df_dict_by_date, df_dict_by_symbol, latest_prices_map, max_date, avail_dates = load_precalculated_data()

    if not df_dict_by_date:
        st.error("⚠️ 資料庫中尚無 `strongbuy_indicators` 數據，請先執行 ETL 腳本。")
        st.stop()

    st.sidebar.header("📅 戰情參數")
    sel_date = st.sidebar.selectbox("日期", avail_dates, 0)
    is_past_date = pd.Timestamp(sel_date) < max_date

    sort_opts = ["強勢總分", "加入日期", "漲跌幅", "外資買超", "投信買超", "量增比", "糾結度(%)"]
    if is_past_date: sort_opts.append("回測報酬率")
    sort_opt = st.sidebar.selectbox("排序", sort_opts)
    min_sc = st.sidebar.number_input("總分門檻", 0, 50, 0)

    # 🚀 取出該日 DataFrame 並限縮於自選股
    df_day = df_dict_by_date[pd.Timestamp(sel_date)].copy()
    target_syms = [st.session_state.query_mode_symbol] if st.session_state.query_mode_symbol else current_symbols
    title = f"🔍 查詢：{target_syms[0]}" if st.session_state.query_mode_symbol else f"📊 {selected_list}"

    df_day = df_day[df_day['symbol'].isin(target_syms)]

    # 🚀 動態套用進階篩選邏輯
    if use_adv_filter and not st.session_state.query_mode_symbol:
        cond = (df_day['volume'] >= min_vol) & (df_day['close'] >= min_price) & (df_day['sq_pct'] <= (threshold_pct/100.0))
        if filter_capital: cond &= (df_day['Capital'] <= capital_limit)

        if chk_short_bull: cond &= (df_day['MA5'] > df_day['MA10']) & (df_day['MA10'] > df_day['MA20'])
        if chk_long_bull: cond &= (df_day['MA60'] > df_day['MA120'])
        if chk_above_3ma: cond &= (df_day['close'] > df_day['MA5']) & (df_day['close'] > df_day['MA10']) & (df_day['close'] > df_day['MA20'])
        if chk_above_5ma: cond &= (df_day['close'] > df_day['MA5']) & (df_day['close'] > df_day['MA10']) & (df_day['close'] > df_day['MA20']) & (df_day['close'] > df_day['MA60']) & (df_day['close'] > df_day['MA120'])
        if chk_bias_60: cond &= (abs(df_day['close'] - df_day['MA60']) / df_day['MA60'] <= (bias_60ma_limit / 100.0))

        if chk_break_high: cond &= (df_day['close'] > df_day['prev_high'])
        if chk_up_2pct: cond &= (((df_day['close'] - df_day['prev_close']) / df_day['prev_close'] * 100) >= 2.0) & (df_day['close'] > df_day['open'])
        if chk_solid_red: cond &= ((df_day['close'] - df_day['open']) > 0) & ((df_day['close'] - df_day['open']) >= (df_day['high'] - df_day['low']) / 3.0)
        if chk_kd_about_gc: cond &= (df_day['K'] < df_day['D']) & ((df_day['D'] - df_day['K']) <= 3) & (df_day['K'] > df_day['prev_K'])
        if chk_kd_3d_mid: cond &= (df_day['kd_gc_3d_mid_flag'] == True)
        if chk_macd_about_red: cond &= (df_day['MACD_OSC'] < 0) & (df_day['MACD_OSC'] > df_day['prev_MACD_OSC'])
        if chk_macd_red: cond &= (df_day['MACD_OSC'] > 0)

        # 🔥 補齊篩選邏輯
        if chk_ma5_up: cond &= (df_day['MA5'] > df_day['prev_MA5'])
        if chk_ma10_up: cond &= (df_day['MA10'] > df_day['prev_MA10'])
        if chk_ma20_up: cond &= (df_day['MA20'] > df_day['prev_MA20'])
        if chk_ma60_up: cond &= (df_day['MA60'] > df_day['prev_MA60'])
        if chk_ma120_up: cond &= (df_day['MA120'] > df_day['prev_MA120'])
        if chk_ma_all_up: cond &= (df_day['MA5'] > df_day['prev_MA5']) & (df_day['MA10'] > df_day['prev_MA10']) & (df_day['MA20'] > df_day['prev_MA20']) & (df_day['MA60'] > df_day['prev_MA60']) & (df_day['MA120'] > df_day['prev_MA120'])

        if chk_foreign_buy_3d: cond &= (df_day['foreign_net'] > 0) & (df_day['prev1_foreign_net'] > 0) & (df_day['prev2_foreign_net'] > 0)
        if chk_trust_buy_3d: cond &= (df_day['trust_net'] > 0) & (df_day['prev1_trust_net'] > 0) & (df_day['prev2_trust_net'] > 0)
        if chk_tu_yang: cond &= (df_day['foreign_net'] > 0) & (df_day['trust_net'] > 0)
        if chk_foreign_buy: cond &= (df_day['foreign_net'] >= foreign_buy_vol)
        if chk_trust_buy: cond &= (df_day['trust_net'] >= trust_buy_vol)
        if chk_trust_first_buy: cond &= (df_day['trust_net'] > 0) & (df_day['prev1_trust_net'] <= 0) & (df_day['prev2_trust_net'] <= 0) & (df_day['prev3_trust_net'] <= 0) & (df_day['prev4_trust_net'] <= 0) & (df_day['prev5_trust_net'] <= 0)

        df_day = df_day[cond]

        # 處理需要歷史遍歷的條件 (出量、連續糾結天數)
        if not df_day.empty and (chk_attack_vol or min_days > 1):
            valid_syms = []
            for sym in df_day['symbol']:
                hist = df_dict_by_symbol.get(sym, pd.DataFrame())
                hist = hist[hist['date'].dt.date <= pd.Timestamp(sel_date).date()]
                if chk_attack_vol and not (hist['Vol_Ratio'].tail(10) >= attack_vol_ratio).any(): continue
                if min_days > 1:
                    days = 0
                    for val in (hist['sq_pct'] <= (threshold_pct/100.0)).values[::-1]:
                        if val: days += 1
                        else: break
                    if days < min_days: continue
                valid_syms.append(sym)
            df_day = df_day[df_day['symbol'].isin(valid_syms)]

    # 基礎清單合併
    if not st.session_state.query_mode_symbol:
        df_day = pd.merge(watchlist_df, df_day, on='symbol', how='left')
        df_day['Total_Score'] = df_day['Total_Score'].fillna(0)
        df_day['Signal_List'] = df_day['Signal_List'].fillna("無後端指標資料")
        df_day['name'] = df_day['name'].fillna("未知名稱")
        df_day = df_day.dropna(subset=['close']) # 若資料庫沒該股票資料則隱藏
    else:
        df_day['added_date'] = '查詢'

    if df_day.empty:
        st.warning("⚠️ 無符合過濾條件的股票。")
        return

    # 計算回測
    if is_past_date:
        df_day['latest_close'] = df_day['symbol'].map(latest_prices_map)
        df_day['Backtest_Return'] = (df_day['latest_close'] - df_day['close']) / df_day['close'] * 100

    if min_sc > 0 and not st.session_state.query_mode_symbol:
        df_day = df_day[df_day['Total_Score'] >= min_sc]

    # 計算顯示用的糾結度 %
    df_day['Squeeze_Display'] = df_day['sq_pct'] * 100

    # 排序邏輯
    if not st.session_state.query_mode_symbol:
        if "強勢總分" in sort_opt: df_day = df_day.sort_values(['Total_Score','symbol'], ascending=[False,True])
        elif "加入" in sort_opt: df_day = df_day.sort_values(['added_date','symbol'], ascending=[False,True])
        elif "漲跌" in sort_opt: df_day = df_day.sort_values(['pct_change','symbol'], ascending=[False,True])
        elif "外資" in sort_opt: df_day = df_day.sort_values(['foreign_net','symbol'], ascending=[False,True])
        elif "投信" in sort_opt: df_day = df_day.sort_values(['trust_net','symbol'], ascending=[False,True])
        elif "量增比" in sort_opt: df_day = df_day.sort_values(['Vol_Ratio','symbol'], ascending=[False,True])
        elif "糾結度" in sort_opt: df_day = df_day.sort_values(['Squeeze_Display','symbol'], ascending=[True,True])
        elif "回測報酬率" in sort_opt: df_day = df_day.sort_values(['Backtest_Return','symbol'], ascending=[False,True])
        else: df_day = df_day.sort_values('symbol')

    display_cols = ['symbol','name','added_date','close','pct_change', 'Vol_Ratio', 'Squeeze_Display']
    if is_past_date: display_cols.append('Backtest_Return')
    display_cols.extend(['Capital', '2026EPS', 'PE_Ratio', 'Total_Score','Signal_List'])

    display_df = df_day[display_cols].reset_index(drop=True)
    sym_list = display_df['symbol'].tolist()

    if st.session_state.query_mode_symbol:
        if st.button("🔙 返回群組", width="stretch"):
            st.session_state.query_mode_symbol = None
            st.rerun()

    st.success(f"{title} (符合門檻剩 {len(sym_list)} 檔)")

    def format_vol_ratio(x):
        if pd.isna(x): return "-"
        return f"🔥 {x:.1f}x" if x >= 2.0 else f"{x:.1f}x"

    fmt_dict = {"pct_change": "{:.2f}%", "close": "{:.2f}", "Capital": "{:.1f}", "2026EPS": "{:.2f}", "PE_Ratio": "{:.2f}", "Total_Score": "{:.0f}", "Vol_Ratio": format_vol_ratio, "Squeeze_Display": "{:.2f}%"}
    col_cfg = {"Capital": "股本(億)", "2026EPS": "預估EPS", "PE_Ratio": "本益比", "Vol_Ratio": "量增比", "Squeeze_Display": "糾結度(%)", "Signal_List": st.column_config.TextColumn("觸發訊號", width="large")}
    if is_past_date:
        fmt_dict["Backtest_Return"] = "{:.2f}%"
        col_cfg["Backtest_Return"] = "回測報酬率"

    evt = st.dataframe(
        display_df.style.format(fmt_dict, na_rep="-").background_gradient(subset=['Total_Score'], cmap='Reds'),
        on_select="rerun", selection_mode="single-row", use_container_width=True,
        column_config=col_cfg
    )

    if evt.selection.rows: st.session_state.ticker_index = evt.selection.rows[0]
    if st.session_state.ticker_index is None or st.session_state.ticker_index >= len(sym_list):
        st.session_state.ticker_index = 0

    cur_sym = sym_list[st.session_state.ticker_index]
    cur_info = display_df.iloc[st.session_state.ticker_index]

    st.divider()

    # 🔥 圖表指標設定
    st.markdown("### 🎛️ 圖表指標設定")
    opt_col1, opt_col2, opt_col3 = st.columns(3)
    with opt_col1:
        st.markdown("**K線均線**")
        selected_mas = st.multiselect("顯示均線 (依照勾選順序)", ['3MA', '5MA', '10MA', '20MA', '60MA', '120MA'], default=['5MA', '10MA', '20MA', '60MA'], key="ui_mas")
        show_ma_cross = st.checkbox("標記 20MA / 60MA 交叉", key="ui_cross")
        show_limit_up = st.checkbox("標記漲停K棒 (🔥)", value=True, key="ui_limit_up")
    with opt_col2:
        st.markdown("**成交量均線**")
        show_vol_ma5 = st.checkbox("顯示 5日均量", key="ui_v5")
        show_vol_ma10 = st.checkbox("顯示 10日均量", key="ui_v10")
    with opt_col3:
        st.markdown("**下方技術與籌碼指標**")
        show_kd = st.checkbox("顯示 KD (9,3,3)", value=True, key="ui_kd")
        show_rsi = st.checkbox("顯示 RSI (14)", value=True, key="ui_rsi")
        show_macd = st.checkbox("顯示 MACD", value=True, key="ui_macd")
        show_foreign = st.checkbox("顯示 外資買賣超", value=True, key="ui_for")
        show_trust = st.checkbox("顯示 投信買賣超", value=True, key="ui_tru")

    st.markdown("---")

    # 導覽按鈕
    def update_state(new_index): st.session_state.ticker_index = new_index
    b1, b2, b3, b4 = st.columns(4)
    b1.button("⏮️ 最前一檔", on_click=lambda: update_state(0), width="stretch")
    b2.button("⬅️ 上一檔", on_click=lambda: update_state(max(0, st.session_state.ticker_index - 1)), width="stretch")
    b3.button("➡️ 下一檔", on_click=lambda: update_state(min(len(sym_list) - 1, st.session_state.ticker_index + 1)), width="stretch")
    b4.button("⏭️ 最後一檔", on_click=lambda: update_state(len(sym_list) - 1), width="stretch")

    # HTML 數據標頭
    pe_str = f"{cur_info['PE_Ratio']:.2f}" if pd.notna(cur_info['PE_Ratio']) else "-"
    eps_str = f"{cur_info['2026EPS']:.2f}" if pd.notna(cur_info['2026EPS']) else "-"
    cap_str = f"{cur_info['Capital']:.1f}" if pd.notna(cur_info['Capital']) else "-"
    vol_ratio_str = f"🔥 {cur_info['Vol_Ratio']:.1f}x" if pd.notna(cur_info['Vol_Ratio']) and cur_info['Vol_Ratio'] >= 2.0 else f"{cur_info['Vol_Ratio']:.1f}x" if pd.notna(cur_info['Vol_Ratio']) else "-"
    pct_change_str = f"{cur_info['pct_change']:.2f}%" if pd.notna(cur_info['pct_change']) else "-"
    sq_str = f"{cur_info['Squeeze_Display']:.2f}%" if pd.notna(cur_info['Squeeze_Display']) else "-"

    title_html = f"{cur_sym} - {cur_info['name']} | 評分: {int(cur_info['Total_Score'])}"
    if is_past_date and pd.notna(cur_info.get('Backtest_Return')):
        title_html += f" | 回測報酬: <span style='color: {'#FF4B4B' if cur_info['Backtest_Return'] > 0 else '#26a69a'};'>{cur_info['Backtest_Return']:.2f}%</span>"

    pct_color = "#FF4B4B" if pd.notna(cur_info['pct_change']) and cur_info['pct_change'] > 0 else "#26a69a" if pd.notna(cur_info['pct_change']) and cur_info['pct_change'] < 0 else "#888"

    st.markdown(
        '<div style="margin: 20px 0;">'
        f'<h2 style="text-align: center; color: #FF4B4B; margin-bottom: 15px;">{title_html}</h2>'
        '<div style="display: flex; justify-content: space-around; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px 10px; margin-bottom: 15px; text-align: center;">'
        f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">收盤價</span><br><span style="font-size:18px; font-weight:bold;">${cur_info["close"]:.2f}</span></div>'
        f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">漲跌幅</span><br><span style="font-size:18px; font-weight:bold; color:{pct_color};">{pct_change_str}</span></div>'
        f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">糾結度</span><br><span style="font-size:18px; font-weight:bold; color:#2196F3;">{sq_str}</span></div>'
        f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">量增比</span><br><span style="font-size:18px; font-weight:bold; color:#FF4B4B;">{vol_ratio_str}</span></div>'
        f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">本益比</span><br><span style="font-size:18px; font-weight:bold;">{pe_str}</span></div>'
        f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">預估EPS</span><br><span style="font-size:18px; font-weight:bold;">{eps_str}</span></div>'
        f'<div style="flex: 1;"><span style="font-size:13px; color:#888;">股本(億)</span><br><span style="font-size:18px; font-weight:bold;">{cap_str}</span></div>'
        '</div>'
        '<div style="background-color: #F4F9FF; border: 1px solid #D2E3FC; border-radius: 8px; padding: 15px 20px;">'
        f'<span style="color: #FF5A5F; font-weight: bold;">⚡ 觸發訊號：</span> {cur_info["Signal_List"]}'
        '</div></div>', unsafe_allow_html=True
    )

    # 繪製 K 線圖
    chart_src = df_dict_by_symbol.get(cur_sym, pd.DataFrame()).copy()
    chart_src = chart_src[chart_src['date'] <= pd.Timestamp(sel_date)]

    if len(chart_src) < 30: st.error("資料不足以繪圖")
    else:
        fig = plot_stock_kline(
            chart_src, cur_sym, cur_info['name'],
            selected_mas, show_ma_cross, show_limit_up, show_vol_ma5, show_vol_ma10,
            show_macd, show_kd, show_rsi, show_foreign, show_trust
        )
        st.plotly_chart(fig, use_container_width=True, key=f"chart_{cur_sym}_{uuid.uuid4()}")

# ===========================
# 7. 程式進入點 (Entry Point)
# ===========================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login_page()
else: main_app()
