import streamlit as st
import pandas as pd
import sqlalchemy
from sqlalchemy import text
import os
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
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
# 2. 身份驗證模組
# ===========================
def check_login(username, password):
    """驗證帳號密碼，並檢查 Active 狀態"""
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

def login_page():
    st.markdown("<h1 style='text-align: center;'>🔐 自選股戰情室</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
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

# ===========================
# 3. DB 操作函式 (Watchlist - 綁定使用者版)
# ===========================
def get_all_lists_db(username):
    """取得特定使用者的所有清單"""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT name FROM watchlist_menus WHERE username = :u ORDER BY name"),
            {"u": username}
        )
        return [row[0] for row in result]

def get_list_data_db(list_name, username):
    """取得特定使用者某清單內的股票"""
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
    if len(current_lists) >= 200: return False, "清單數量已達上限"
    if new_name in current_lists: return False, "名稱已存在"
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO watchlist_menus (name, username) VALUES (:name, :u)"), 
                {"name": new_name, "u": username}
            )
        return True, "建立成功"
    except Exception as e: return False, str(e)

def rename_list_db(old_name, new_name, username):
    try:
        with engine.begin() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM watchlist_menus WHERE name = :new AND username = :u"), 
                {"new": new_name, "u": username}
            ).scalar()
            if exists: return False, "名稱已存在"
            
            conn.execute(
                text("UPDATE watchlist_menus SET name = :new WHERE name = :old AND username = :u"), 
                {"new": new_name, "old": old_name, "u": username}
            )
        return True, "改名成功"
    except Exception as e: return False, str(e)

def delete_list_db(list_name, username):
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM watchlist_menus WHERE name = :name AND username = :u"), 
                {"name": list_name, "u": username}
            )
        return True, "刪除成功"
    except Exception as e: return False, str(e)

def add_stock_db(list_name, symbol, username):
    added_date = datetime.now().strftime('%Y-%m-%d')
    try:
        with engine.begin() as conn:
            menu_id = conn.execute(
                text("SELECT id FROM watchlist_menus WHERE name = :name AND username = :u"), 
                {"name": list_name, "u": username}
            ).scalar()
            
            if not menu_id: return False, "清單不存在"
            
            count = conn.execute(text("SELECT COUNT(*) FROM watchlist_items WHERE menu_id = :mid"), {"mid": menu_id}).scalar()
            if count >= 1000: return False, "數量達上限"
            
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
                WHERE symbol=:s 
                AND menu_id=(SELECT id FROM watchlist_menus WHERE name=:n AND username=:u)
            """), {"s": symbol, "n": list_name, "u": username})
        return True, "移除成功"
    except Exception as e: return False, str(e)

# --- 資料讀取與指標運算 ---
@st.cache_data(ttl=3600)
def get_all_symbols_fast():
    try:
        with engine.connect() as conn:
            df = pd.read_sql("SELECT symbol FROM stock_info", conn)
        return set(df['symbol'].astype(str).str.strip().unique())
    except: return set()

@st.cache_data(ttl=3600)
def get_stock_mapping():
    """建立名稱、短代號與完整代號的對照表"""
    try:
        with engine.connect() as conn:
            df = pd.read_sql("SELECT symbol, name FROM stock_info", conn)
        
        mapping = {}
        for _, row in df.iterrows():
            sym = str(row['symbol']).strip()
            name = str(row['name']).strip()
            short_code = sym.split('.')[0]
            
            mapping[sym.upper()] = sym           
            mapping[short_code.upper()] = sym    
            mapping[name.upper()] = sym          
        return mapping
    except: 
        return {}

def resolve_stock_symbol(input_val, mapping):
    """透過對照表解析使用者輸入，回傳完整代號"""
    if not input_val: return None
    val = str(input_val).strip().upper()
    return mapping.get(val, None)

@st.cache_data(ttl=3600)
def load_and_process_data():
    query = """
    SELECT sp.date, sp.symbol, sp.open, sp.high, sp.low, sp.close, sp.volume, 
           si.name, si.industry,
           COALESCE(ii.foreign_net, 0) as foreign_net
    FROM stock_prices sp
    JOIN stock_info si ON sp.symbol = si.symbol
    LEFT JOIN institutional_investors ii ON sp.date = ii.date AND sp.symbol = ii.symbol
    WHERE sp.date >= current_date - INTERVAL '400 days' 
    ORDER BY sp.symbol, sp.date
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    
    df['symbol'] = df['symbol'].astype(str).str.strip()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['symbol', 'date'])
    grouped = df.groupby('symbol')

    # 1. 均線與量能
    df['MA5'] = grouped['close'].transform(lambda x: x.rolling(5).mean())
    df['MA10'] = grouped['close'].transform(lambda x: x.rolling(10).mean())
    df['MA20'] = grouped['close'].transform(lambda x: x.rolling(20).mean())
    df['MA60'] = grouped['close'].transform(lambda x: x.rolling(60).mean())
    
    df['Vol_MA5'] = grouped['volume'].transform(lambda x: x.rolling(5).mean())
    df['Vol_MA10'] = grouped['volume'].transform(lambda x: x.rolling(10).mean())
    df['Vol_MA20'] = grouped['volume'].transform(lambda x: x.rolling(20).mean())

    # 2. 漲跌與前值
    df['prev_close'] = grouped['close'].shift(1)
    df['prev_volume'] = grouped['volume'].shift(1)
    df['pct_change'] = (df['close'] - df['prev_close']) / df['prev_close'] * 100
    df['pct_change_3d'] = grouped['close'].pct_change(3) * 100
    df['pct_change_5d'] = grouped['close'].pct_change(5) * 100
    
    df['high_3d'] = grouped['high'].transform(lambda x: x.rolling(3).max())
    df['vol_max_3d'] = grouped['volume'].transform(lambda x: x.rolling(3).max())

    # 3. 技術指標 (KD/MACD)
    low_min = grouped['low'].transform(lambda x: x.rolling(9).min())
    high_max = grouped['high'].transform(lambda x: x.rolling(9).max())
    df['RSV'] = (df['close'] - low_min) / (high_max - low_min) * 100
    df['K'] = grouped['RSV'].transform(lambda x: x.ewm(com=2, adjust=False).mean())
    df['D'] = grouped['K'].transform(lambda x: x.ewm(com=2, adjust=False).mean())
    
    ema12 = grouped['close'].transform(lambda x: x.ewm(span=12, adjust=False).mean())
    ema26 = grouped['close'].transform(lambda x: x.ewm(span=26, adjust=False).mean())
    df['DIF'] = ema12 - ema26
    df['MACD'] = grouped['DIF'].transform(lambda x: x.ewm(span=9, adjust=False).mean())
    df['MACD_OSC'] = df['DIF'] - df['MACD']

    # 4. 衍生指標
    df['bias_ma5'] = (df['close'] - df['MA5']) / df['MA5'] * 100
    df['bias_ma20'] = (df['close'] - df['MA20']) / df['MA20'] * 100
    df['bias_ma60'] = (df['close'] - df['MA60']) / df['MA60'] * 100
    
    df['vol_bias_ma5'] = (df['volume'] - df['Vol_MA5']) / df['Vol_MA5'] * 100
    df['vol_bias_ma10'] = (df['volume'] - df['Vol_MA10']) / df['Vol_MA10'] * 100
    df['vol_bias_ma20'] = (df['volume'] - df['Vol_MA20']) / df['Vol_MA20'] * 100

    df['above_ma20'] = (df['close'] > df['MA20']).astype(int)
    df['days_above_ma20'] = grouped['above_ma20'].transform(lambda x: x.rolling(47).sum())
    
    df['above_ma60'] = (df['close'] > df['MA60']).astype(int)
    df['days_above_ma60'] = grouped['above_ma60'].transform(lambda x: x.rolling(177).sum())

    # 5. 籌碼
    df['f_buy_pos'] = (df['foreign_net'] > 0).astype(int)
    df['f_buy_streak'] = grouped['f_buy_pos'].transform(lambda x: x.groupby((x != x.shift()).cumsum()).cumsum())
    df['f_sum_5d'] = grouped['foreign_net'].transform(lambda x: x.rolling(5).sum())

    df['vol_ratio'] = df['volume'] / df['Vol_MA5']
    return df

# --- 繪圖輔助 ---
def plot_stock_kline(df_stock, symbol, name, active_signals_text, show_vol_profile=False):
    df_plot = df_stock.tail(130).copy()
    df_plot['date_str'] = df_plot['date'].dt.strftime('%Y-%m-%d')
    score_val = active_signals_text.count(',') + 1 if active_signals_text else 0
    
    fig = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.01,
                        row_heights=[0.45, 0.1, 0.1, 0.1, 0.15],
                        subplot_titles=(f"{symbol} {name} (評分:{score_val})", "量", "KD", "MACD", "訊號"))

    # K線 (紅漲綠跌)
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
# 4. 主應用程式邏輯
# ===========================
def main_app():
    current_user = st.session_state['username']

    with st.sidebar:
        st.markdown(f"👤 **{current_user}** ({st.session_state['role']})")
        if st.button("🚪 登出"):
            st.session_state['logged_in'] = False
            st.session_state['role'] = None
            st.rerun()
        st.markdown("---")

    # State Init
    for k in ['ticker_index', 'last_selected_rows', 'symbol_input', 'query_mode_symbol']:
        if k not in st.session_state: st.session_state[k] = None
    if st.session_state.symbol_input is None: st.session_state.symbol_input = ""

    stock_mapping = get_stock_mapping()

    # --- 側邊欄：股票管理 ---
    st.sidebar.header("📝 股票管理")
    
    all_lists = get_all_lists_db(current_user)
    if not all_lists:
        create_list_db("預設清單", current_user)
        all_lists = get_all_lists_db(current_user)
    
    selected_list = st.sidebar.selectbox("📂 選擇清單", all_lists, index=0)
    
    watchlist_df = get_list_data_db(selected_list, current_user)
    current_symbols = watchlist_df['symbol'].tolist()

    # 點擊表格時，更新輸入框的值
    with st.sidebar.expander(f"📋 查看清單 ({len(current_symbols)})", expanded=True):
        event = st.dataframe(watchlist_df, hide_index=True, on_select="rerun", selection_mode="single-row", use_container_width=True)
        if len(event.selection.rows) > 0:
            idx = event.selection.rows[0]
            if idx < len(watchlist_df): 
                st.session_state.symbol_input = watchlist_df.iloc[idx]['symbol']

    # 🔥 關鍵修復：不綁定 key，改用 value 來避免 StreamlitAPIException
    col_in, col_act = st.sidebar.columns([1.5, 2])
    inp_code = col_in.text_input("代號/名稱", value=st.session_state.symbol_input).strip()
    
    # 即時同步使用者的輸入內容回 session_state
    st.session_state.symbol_input = inp_code

    with col_act:
        c1, c2, c3 = st.columns(3)
        
        if c1.button("新"):
            st.session_state.query_mode_symbol = None
            code = resolve_stock_symbol(inp_code, stock_mapping)
            if code and code not in current_symbols:
                if add_stock_db(selected_list, code, current_user): 
                    st.session_state.symbol_input = code # 將完整代碼回寫文字方塊
                    st.sidebar.success("✅"); st.rerun()
            else: st.sidebar.warning("❌")
            
        if c2.button("刪"):
            st.session_state.query_mode_symbol = None
            code = resolve_stock_symbol(inp_code, stock_mapping) or inp_code
            if code in current_symbols:
                if remove_stock_db(selected_list, code, current_user): 
                    st.session_state.symbol_input = "" # 清空文字方塊
                    st.sidebar.success("🗑️"); st.rerun()
                    
        if c3.button("查"):
            code = resolve_stock_symbol(inp_code, stock_mapping)
            if code:
                st.session_state.query_mode_symbol = code
                st.session_state.ticker_index = 0
                st.session_state.symbol_input = code # 將完整代碼回寫文字方塊
                st.sidebar.info("🔍"); st.rerun()
            else:
                st.sidebar.warning("❌ 找不到該股票")

    with st.sidebar.expander("⚙️ 清單管理"):
        new_list_name = st.text_input("建立新清單名稱")
        if st.button("建立"): 
            if new_list_name:
                success, msg = create_list_db(new_list_name, current_user)
                if success: st.success(msg); st.rerun()
                else: st.error(msg)
        
        rename_text = st.text_input("改名為")
        if st.button("改名"):
            if rename_text:
                success, msg = rename_list_db(selected_list, rename_text, current_user)
                if success: st.success(msg); st.rerun()
                else: st.error(msg)
            
        if st.button("⚠️ 刪除", type="primary"):
            if len(all_lists) > 1:
                if delete_list_db(selected_list, current_user): st.rerun()
            else: st.warning("至少保留一個清單")

    st.sidebar.markdown("---")

    # --- 主畫面 ---
    with st.spinner("載入資料..."):
        df_full = load_and_process_data()

    avail_dates = sorted(df_full['date'].dt.date.unique(), reverse=True)
    st.sidebar.header("📅 戰情參數")
    sel_date = st.sidebar.selectbox("日期", avail_dates, 0)
    sort_opt = st.sidebar.selectbox("排序", ["強勢總分", "加入日期", "漲跌幅", "外資買超"])
    min_sc = st.sidebar.number_input("分數門檻", 0, 50, 4)
    
    target_date_ts = pd.Timestamp(sel_date)
    df_day = df_full[df_full['date'] == target_date_ts].copy()

    # 篩選
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
        st.warning("⚠️ 無資料")
        return

    # --- 動態訊號產生 ---
    df_day['rank_pct_1d'] = df_day['pct_change'].rank(ascending=False, method='min')
    df_day['rank_pct_5d'] = df_day['pct_change_5d'].rank(ascending=False, method='min')
    df_day['rank_f_1d'] = df_day['foreign_net'].rank(ascending=False, method='min')
    df_day['rank_f_5d'] = df_day['f_sum_5d'].rank(ascending=False, method='min')

    df_day['signals_str'] = [[] for _ in range(len(df_day))]
    score = pd.Series(0, index=df_day.index)

    def fmt(val, template):
        return val.fillna(0).apply(lambda x: template.format(x))

    txt_bias_w = fmt(df_day['bias_ma5'], "突破週線{:.2f}%")
    txt_vol_5 = fmt(df_day['vol_bias_ma5'], "較5日量增{:.1f}%")
    txt_f_buy = df_day['f_buy_streak'].fillna(0).astype(int).apply(lambda x: f"外資連買{x}天")
    txt_rank_1d = df_day['rank_pct_1d'].fillna(999).astype(int).apply(lambda x: f"漲幅第{x}名")
    
    strategies = [
        (df_day['close'] > df_day['MA5'], txt_bias_w),
        (df_day['close'] > df_day['MA20'], "突破月線"),
        (df_day['close'] > df_day['MA60'], "突破季線"),
        (df_day['pct_change'] > 3, fmt(df_day['pct_change'], "漲幅{:.2f}%")),
        (df_day['pct_change'] > 9.5, "🔥漲停"),
        (df_day['vol_bias_ma5'] > 30, txt_vol_5),
        (df_day['volume'] > df_day['prev_volume'] * 1.5, "量增1.5倍"),
        (df_day['f_buy_streak'] >= 2, txt_f_buy),
        (df_day['rank_f_1d'] <= 10, fmt(df_day['rank_f_1d'], "外資買超第{:.0f}名")),
        (df_day['days_above_ma20'] >= 47, fmt(df_day['days_above_ma20'], "連{:.0f}日站月線")),
        (df_day['K'] > df_day['D'], "KD多頭"),
        ((df_day['K'] > df_day['D']) & (df_day['K'].shift(1) < df_day['D'].shift(1)), "KD金叉"),
        ((df_day['MACD_OSC'] > 0) & (df_day['MACD_OSC'].shift(1) < 0), "MACD轉紅")
    ]

    for mask, txt in strategies:
        score += mask.astype(int)
        if mask.any():
            if isinstance(txt, pd.Series):
                vals = txt[mask]
                df_day.loc[mask, 'signals_str'] = df_day.loc[mask].apply(
                    lambda row: row['signals_str'] + [vals[row.name]] if row.name in vals.index else row['signals_str'], 
                    axis=1
                )
            else:
                df_day.loc[mask, 'signals_str'] = df_day.loc[mask, 'signals_str'].apply(lambda x: x + [txt])

    df_day['Total_Score'] = score
    df_day['Signal_List'] = df_day['signals_str'].apply(lambda x: ", ".join(x))

    # 🔥 修復 Bug：如果是「查詢模式」，則強制顯示，略過分數過濾
    if min_sc > 0 and not st.session_state.query_mode_symbol: 
        df_day = df_day[df_day['Total_Score'] >= min_sc]

    # Sort
    if not st.session_state.query_mode_symbol:
        if "強勢總分" in sort_opt: df_day = df_day.sort_values(['Total_Score','symbol'], ascending=[False,True])
        elif "加入" in sort_opt: df_day = df_day.sort_values(['added_date','symbol'], ascending=[False,True])
        elif "漲跌" in sort_opt: df_day = df_day.sort_values(['pct_change','symbol'], ascending=[False,True])
        elif "外資" in sort_opt: df_day = df_day.sort_values(['foreign_net','symbol'], ascending=[False,True])
        else: df_day = df_day.sort_values('symbol')

    display_df = df_day[['symbol','name','added_date','industry','close','pct_change','Total_Score','Signal_List']].reset_index(drop=True)
    sym_list = display_df['symbol'].tolist()

    if st.session_state.query_mode_symbol:
        if st.button("🔙 返回清單"):
            st.session_state.query_mode_symbol = None
            st.rerun()
    
    st.success(f"{title} (符合門檻剩 {len(sym_list)} 檔)")
    
    evt = st.dataframe(display_df.style.format({"pct_change":"{:.2f}%","close":"{:.2f}"}).background_gradient(subset=['Total_Score'], cmap='Reds'),
                       on_select="rerun", selection_mode="single-row", use_container_width=True,
                       column_config={"Signal_List": st.column_config.TextColumn("觸發訊號", width="large")})
    
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
        st.markdown(f"<h3 style='text-align:center;color:#FF4B4B'>{cur_sym} {cur_info['name']} | 分:{cur_info['Total_Score']}</h3>", unsafe_allow_html=True)
        st.info(f"⚡ {cur_info['Signal_List']}")

    chart_src = df_full[df_full['symbol']==cur_sym].sort_values('date')
    chart_src = chart_src[chart_src['date'] <= target_date_ts]
    
    if len(chart_src)<30: st.error("資料不足")
    else:
        fig = plot_stock_kline(chart_src, cur_sym, cur_info['name'], cur_info['Signal_List'])
        st.plotly_chart(fig, use_container_width=True, key=f"chart_{cur_sym}_{uuid.uuid4()}")

# ===========================
# 6. 程式進入點
# ===========================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    login_page()
else:
    main_app()
