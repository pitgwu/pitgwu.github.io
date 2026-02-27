import streamlit as st
import pandas as pd
import numpy as np
import sqlalchemy
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
import bcrypt

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
# 3. 身份驗證與註冊模組
# ===========================
def check_login(username, password):
    engine = get_db_engine()
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
    engine = get_db_engine()
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
    engine = get_db_engine()
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
# 4. 核心快取邏輯 (資料載入)
# ===========================
@st.cache_data(ttl=600)
def load_precalculated_data():
    engine = get_db_engine()
    query = """
    SELECT d.date, d.symbol, d.name, d.industry, d.open, d.high, d.low, d.close, d.volume,
           d.pct_change, d.foreign_net, d.trust_net,
           d."MA5", d."MA10", d."MA20", d."MA60",
           d."K", d."D", d."MACD_OSC", d."DIF",
           d."Vol_Ratio",
           d.total_score as "Total_Score",
           d.signal_list as "Signal_List",
           e."Capital", e."2026EPS"
    FROM daily_stock_indicators d
    LEFT JOIN stock_eps e ON d.symbol = e."Symbol"
    WHERE d.date >= current_date - INTERVAL '400 days'
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
        
        for col in ['foreign_net', 'trust_net', 'K', 'D', 'MACD_OSC', 'DIF', 'Vol_Ratio']:
            if col not in df.columns:
                df[col] = np.nan
        
        df['MA120'] = df.groupby('symbol')['close'].transform(lambda x: x.rolling(120).mean())
        df['Vol_MA5'] = df.groupby('symbol')['volume'].transform(lambda x: x.rolling(5).mean())
        df['Vol_MA10'] = df.groupby('symbol')['volume'].transform(lambda x: x.rolling(10).mean())
        
    return df

def get_squeeze_candidates(df_full, target_date, min_vol, min_price, filter_capital, capital_limit, sq_thresh, short_bull, long_bull, ma20_up, above_ma5, ma60_up, above_ma60, limit_bias_60ma, bias_60ma_limit, kd_about_gc, kd_gc_3d_mid, macd_about_red, macd_red_or_cont, attack_vol, vol_ma5_up, vol_ma10_up, break_high, up_2pct_red, solid_red_body, min_days):
    if df_full.empty: return pd.DataFrame()

    df_full['max_ma'] = df_full[['MA5', 'MA10', 'MA20']].max(axis=1)
    df_full['min_ma'] = df_full[['MA5', 'MA10', 'MA20']].min(axis=1)
    df_full['sq_pct'] = (df_full['max_ma'] - df_full['min_ma']) / df_full['min_ma']
    df_full['is_sq'] = df_full['sq_pct'] <= sq_thresh

    is_same_sym = df_full['symbol'] == df_full['symbol'].shift(1)
    df_full['prev_MA5'] = np.where(is_same_sym, df_full['MA5'].shift(1), np.nan)
    df_full['prev_MA10'] = np.where(is_same_sym, df_full['MA10'].shift(1), np.nan)
    df_full['prev_MA20'] = np.where(is_same_sym, df_full['MA20'].shift(1), np.nan)
    df_full['prev_MA60'] = np.where(is_same_sym, df_full['MA60'].shift(1), np.nan)

    df_full['prev_high'] = np.where(is_same_sym, df_full['high'].shift(1), np.nan)
    df_full['prev_close'] = np.where(is_same_sym, df_full['close'].shift(1), np.nan)
    df_full['prev_K'] = np.where(is_same_sym, df_full['K'].shift(1), np.nan)
    df_full['prev_D'] = np.where(is_same_sym, df_full['D'].shift(1), np.nan)
    df_full['prev_MACD_OSC'] = np.where(is_same_sym, df_full['MACD_OSC'].shift(1), np.nan)
    df_full['prev_Vol_MA5'] = np.where(is_same_sym, df_full['Vol_MA5'].shift(1), np.nan)
    df_full['prev_Vol_MA10'] = np.where(is_same_sym, df_full['Vol_MA10'].shift(1), np.nan)

    df_full['is_kd_gc'] = (df_full['K'] > df_full['D']) & (df_full['prev_K'] <= df_full['prev_D'])
    df_full['is_kd_gc_mid'] = df_full['is_kd_gc'] & (df_full['K'] >= 35) & (df_full['K'] <= 75)

    is_same_sym_2 = df_full['symbol'] == df_full['symbol'].shift(2)
    kd_mid_0 = df_full['is_kd_gc_mid']
    kd_mid_1 = df_full['is_kd_gc_mid'].shift(1).fillna(False) & is_same_sym
    kd_mid_2 = df_full['is_kd_gc_mid'].shift(2).fillna(False) & is_same_sym_2
    df_full['kd_gc_3d_mid_flag'] = kd_mid_0 | kd_mid_1 | kd_mid_2

    df_target_day = df_full[df_full['date'].dt.date == target_date].copy()
    if df_target_day.empty: return pd.DataFrame()

    cond_vol = df_target_day['volume'] >= min_vol
    cond_price = df_target_day['close'] >= min_price
    cond_capital = (df_target_day['Capital'] <= capital_limit) if filter_capital else True
    cond_sq = df_target_day['is_sq'] == True

    cond_short = (df_target_day['MA5'] > df_target_day['MA10']) & (df_target_day['MA10'] > df_target_day['MA20']) if short_bull else True
    cond_long = (df_target_day['MA60'] > df_target_day['MA120']) if long_bull else True
    cond_ma20_up = (df_target_day['MA20'] > df_target_day['prev_MA20']) if ma20_up else True
    cond_above_ma5 = (df_target_day['close'] > df_target_day['MA5']) if above_ma5 else True
    cond_ma60_up = (df_target_day['MA60'] > df_target_day['prev_MA60']) if ma60_up else True
    cond_above_ma60 = (df_target_day['close'] > df_target_day['MA60']) if above_ma60 else True
    cond_bias_60 = (abs(df_target_day['close'] - df_target_day['MA60']) / df_target_day['MA60'] <= (bias_60ma_limit / 100.0)) if limit_bias_60ma else True
    cond_kd_about = (df_target_day['K'] < df_target_day['D']) & ((df_target_day['D'] - df_target_day['K']) <= 3) & (df_target_day['K'] > df_target_day['prev_K']) if kd_about_gc else True
    cond_kd_3d = df_target_day['kd_gc_3d_mid_flag'] == True if kd_gc_3d_mid else True
    cond_macd_about = (df_target_day['MACD_OSC'] < 0) & (df_target_day['MACD_OSC'] > df_target_day['prev_MACD_OSC']) if macd_about_red else True
    cond_macd_red = (df_target_day['MACD_OSC'] > 0) if macd_red_or_cont else True
    cond_break_high = (df_target_day['close'] > df_target_day['prev_high']) if break_high else True
    pct_chg = (df_target_day['close'] - df_target_day['prev_close']) / df_target_day['prev_close'] * 100
    cond_up_2pct = (pct_chg >= 2.0) & (df_target_day['close'] > df_target_day['open']) if up_2pct_red else True
    k_len = df_target_day['high'] - df_target_day['low']
    body_len = df_target_day['close'] - df_target_day['open']
    cond_solid_red = (body_len > 0) & (body_len >= k_len / 3.0) if solid_red_body else True
    cond_vol_ma5_up = (df_target_day['Vol_MA5'] > df_target_day['prev_Vol_MA5']) if vol_ma5_up else True
    cond_vol_ma10_up = (df_target_day['Vol_MA10'] > df_target_day['prev_Vol_MA10']) if vol_ma10_up else True

    candidates = df_target_day[cond_vol & cond_price & cond_capital & cond_sq & cond_short & cond_long & cond_ma20_up & cond_above_ma5 & cond_ma60_up & cond_above_ma60 & cond_bias_60 & cond_kd_about & cond_kd_3d & cond_macd_about & cond_macd_red & cond_break_high & cond_up_2pct & cond_solid_red & cond_vol_ma5_up & cond_vol_ma10_up]['symbol'].tolist()

    max_date = df_full['date'].dt.date.max()
    is_past_date = target_date < max_date
    latest_closes = {}
    if is_past_date:
        df_latest = df_full[df_full['date'].dt.date == max_date]
        latest_closes = dict(zip(df_latest['symbol'], df_latest['close']))

    df_history = df_full[df_full['date'].dt.date <= target_date]

    results = []
    def get_ma_str(curr, prev):
        if pd.isna(curr) or pd.isna(prev): return "-"
        arrow = "🔺" if curr > prev else "▼"
        return f"{curr:.2f} {arrow}"

    for sym in candidates:
        sym_df = df_history[df_history['symbol'] == sym]
        if sym_df.empty: continue

        if attack_vol:
            if not (sym_df['Vol_Ratio'].tail(10) >= 2.0).any():
                continue

        is_sq_arr = sym_df['is_sq'].values[::-1]
        days = 0
        for val in is_sq_arr:
            if val: days += 1
            else: break

        if days >= min_days:
            last = sym_df.iloc[-1]

            v_ratio = last['Vol_Ratio'] if pd.notna(last['Vol_Ratio']) else 0.0
            v_ratio_str = f"🔥 {v_ratio:.1f}x" if v_ratio >= 1.5 else f"{v_ratio:.1f}x"
            pe = last['close'] / last['2026EPS'] if pd.notna(last['2026EPS']) and last['2026EPS'] > 0 else np.nan

            backtest_ret = np.nan
            if is_past_date:
                latest_c = latest_closes.get(sym, np.nan)
                target_c = last['close']
                if pd.notna(latest_c) and target_c > 0:
                    backtest_ret = ((latest_c - target_c) / target_c) * 100

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
                'Backtest_Return': backtest_ret,
                'ma5_str': get_ma_str(last['MA5'], last['prev_MA5']),
                'ma10_str': get_ma_str(last['MA10'], last['prev_MA10']),
                'ma20_str': get_ma_str(last['MA20'], last['prev_MA20']),
                'ma60_str': get_ma_str(last['MA60'], last['prev_MA60']),
                'link': f"https://www.wantgoo.com/stock/{sym.replace('.TW','').replace('.TWO','')}"
            })

    return pd.DataFrame(results)

def diagnose_stock(symbol_code, df_full, target_date, min_vol, min_price, filter_capital, capital_limit, sq_threshold, short_bull, long_bull, ma20_up, above_ma5, ma60_up, above_ma60, limit_bias_60ma, bias_60ma_limit, kd_about_gc, kd_gc_3d_mid, macd_about_red, macd_red_or_cont, attack_vol, vol_ma5_up, vol_ma10_up, break_high, up_2pct_red, solid_red_body, min_days):
    symbol_code = symbol_code.strip().upper()
    st.sidebar.markdown(f"#### 🕵️ 診斷報告: {symbol_code}")

    df_history = df_full[df_full['date'].dt.date <= target_date]
    sym_df = df_history[df_history['symbol'].str.contains(symbol_code, case=False)]

    if sym_df.empty:
        st.sidebar.error("❌ 該日期無此代號或無資料")
        return

    target_sym = sym_df['symbol'].iloc[0]
    df = df_history[df_history['symbol'] == target_sym].copy()

    df['max_ma'] = df[['MA5','MA10','MA20']].max(axis=1)
    df['min_ma'] = df[['MA5','MA10','MA20']].min(axis=1)
    df['sq_pct'] = (df['max_ma'] - df['min_ma']) / df['min_ma']
    df['is_sq'] = df['sq_pct'] <= sq_threshold

    df['prev_MA20'] = df['MA20'].shift(1)
    df['prev_MA60'] = df['MA60'].shift(1)
    df['prev_high'] = df['high'].shift(1)
    df['prev_close'] = df['close'].shift(1)
    df['prev_K'] = df['K'].shift(1)
    df['prev_D'] = df['D'].shift(1)
    df['prev_MACD_OSC'] = df['MACD_OSC'].shift(1)
    df['prev_Vol_MA5'] = df['Vol_MA5'].shift(1)
    df['prev_Vol_MA10'] = df['Vol_MA10'].shift(1)

    days = 0
    for val in df['is_sq'].values[::-1]:
        if val: days += 1
        else: break

    last = df.iloc[-1]
    st.sidebar.caption(f"{target_sym} {last['name']} | {last['date'].strftime('%Y-%m-%d')}")

    v_ok = last['volume'] >= min_vol
    is_capital_ok = (last['Capital'] <= capital_limit) if pd.notna(last['Capital']) else False
    t_capital_ok = is_capital_ok if filter_capital else True
    is_long = last['MA60'] > last['MA120']
    t_long_ok = is_long if long_bull else True
    is_short = (last['MA5'] > last['MA10'] and last['MA10'] > last['MA20'])
    t_short_ok = is_short if short_bull else True
    is_ma20_up = last['MA20'] > last['prev_MA20']
    t_ma20_ok = is_ma20_up if ma20_up else True
    is_above_ma5 = last['close'] > last['MA5']
    t_above_ma5_ok = is_above_ma5 if above_ma5 else True
    is_ma60_up = last['MA60'] > last['prev_MA60']
    t_ma60_ok = is_ma60_up if ma60_up else True
    is_above_ma60 = last['close'] > last['MA60']
    t_above_ma60_ok = is_above_ma60 if above_ma60 else True
    is_bias_ok = (abs(last['close'] - last['MA60']) / last['MA60']) <= (bias_60ma_limit / 100.0)
    t_bias_ok = is_bias_ok if limit_bias_60ma else True
    is_kd_about = (last['K'] < last['D']) and ((last['D'] - last['K']) <= 3) and (last['K'] > last['prev_K'])
    t_kd_about_ok = is_kd_about if kd_about_gc else True

    last_3 = df.tail(3)
    gc_in_3d = False
    for _, row in last_3.iterrows():
        if pd.notna(row['prev_K']) and (row['prev_K'] <= row['prev_D']) and (row['K'] > row['D']):
            if 35 <= row['K'] <= 75:
                gc_in_3d = True
                break
    t_kd_3d_ok = gc_in_3d if kd_gc_3d_mid else True
    is_macd_about = (last['MACD_OSC'] < 0) and (last['MACD_OSC'] > last['prev_MACD_OSC'])
    t_macd_about_ok = is_macd_about if macd_about_red else True
    is_macd_red_cont = (last['MACD_OSC'] > 0)
    t_macd_red_ok = is_macd_red_cont if macd_red_or_cont else True
    is_attack_vol = (df['Vol_Ratio'].tail(10) >= 2.0).any()
    t_attack_vol_ok = is_attack_vol if attack_vol else True
    is_v5_up = last['Vol_MA5'] > last['prev_Vol_MA5']
    t_v5_up_ok = is_v5_up if vol_ma5_up else True
    is_v10_up = last['Vol_MA10'] > last['prev_Vol_MA10']
    t_v10_up_ok = is_v10_up if vol_ma10_up else True
    is_break_high = last['close'] > last['prev_high']
    t_break_high_ok = is_break_high if break_high else True
    pct_chg = (last['close'] - last['prev_close']) / last['prev_close'] * 100 if pd.notna(last['prev_close']) and last['prev_close'] > 0 else 0
    is_up_2pct = (pct_chg >= 2.0) and (last['close'] > last['open'])
    t_up_2pct_ok = is_up_2pct if up_2pct_red else True
    k_len = last['high'] - last['low']
    body_len = last['close'] - last['open']
    is_solid_red = (body_len > 0) and (body_len >= k_len / 3.0)
    t_solid_red_ok = is_solid_red if solid_red_body else True

    s_ok = last['is_sq']
    d_ok = days >= min_days

    def show_check(label, ok, val, target):
        icon = "✅" if ok else "❌"
        cls = "diag-pass" if ok else "diag-fail"
        st.sidebar.markdown(f"{label}: <span class='{cls}'>{icon} {val}</span> / {target}", unsafe_allow_html=True)

    show_check("01. 成交量", v_ok, int(last['volume']), min_vol)
    show_check("02. 股本大小", t_capital_ok, f"{last['Capital']} 億" if pd.notna(last['Capital']) else "無資料", f"<={capital_limit} 億" if filter_capital else "不拘")
    show_check("03. 長線多頭(60>120)", t_long_ok, "是" if is_long else "否", "必要" if long_bull else "不拘")
    show_check("04. 短線多頭(5>10>20)", t_short_ok, "是" if is_short else "否", "必要" if short_bull else "不拘")
    show_check("05. 月線上揚(20MA↑)", t_ma20_ok, "是" if is_ma20_up else "否", "必要" if ma20_up else "不拘")
    show_check("06. 站上5MA", t_above_ma5_ok, "是" if is_above_ma5 else "否", "必要" if above_ma5 else "不拘")
    show_check("07. 季線上揚(60MA↑)", t_ma60_ok, "是" if is_ma60_up else "否", "必要" if ma60_up else "不拘")
    show_check("08. 站上60MA", t_above_ma60_ok, "是" if is_above_ma60 else "否", "必要" if above_ma60 else "不拘")
    show_check(f"09. 離60MA乖離<={bias_60ma_limit}%", t_bias_ok, "是" if is_bias_ok else "否", "必要" if limit_bias_60ma else "不拘")
    show_check("10. 近10日出攻擊量", t_attack_vol_ok, "是" if is_attack_vol else "否", "必要" if attack_vol else "不拘")
    show_check("11. 5日均量上揚", t_v5_up_ok, "是" if is_v5_up else "否", "必要" if vol_ma5_up else "不拘")
    show_check("12. 10日均量上揚", t_v10_up_ok, "是" if is_v10_up else "否", "必要" if vol_ma10_up else "不拘")
    show_check("13. 過昨高(收盤>昨高)", t_break_high_ok, "是" if is_break_high else "否", "必要" if break_high else "不拘")
    show_check("14. 上漲>2%紅K棒", t_up_2pct_ok, "是" if is_up_2pct else "否", "必要" if up_2pct_red else "不拘")
    show_check("15. 實體紅K>1/3", t_solid_red_ok, "是" if is_solid_red else "否", "必要" if solid_red_body else "不拘")
    show_check("16. KD即將黃金交叉", t_kd_about_ok, "是" if is_kd_about else "否", "必要" if kd_about_gc else "不拘")
    show_check("17. KD 3日內中段金叉", t_kd_3d_ok, "是" if gc_in_3d else "否", "必要" if kd_gc_3d_mid else "不拘")
    show_check("18. MACD即將翻紅", t_macd_about_ok, "是" if is_macd_about else "否", "必要" if macd_about_red else "不拘")
    show_check("19. MACD翻紅或持續紅", t_macd_red_ok, "是" if is_macd_red_cont else "否", "必要" if macd_red_or_cont else "不拘")
    show_check("20. 糾結度", s_ok, f"{last['sq_pct']*100:.2f}%", f"{sq_threshold*100:.1f}%")
    show_check("21. 連續天數", d_ok, f"{days} 天", f"{min_days} 天")

# ===========================
# 5. 登入與註冊頁面 UI
# ===========================
def login_page():
    st.markdown("<h1 style='text-align: center;'>🔐 均線糾結選股神器</h1>", unsafe_allow_html=True)
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
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        with tab_register:
            with st.form("register_form"):
                new_username = st.text_input("設定帳號")
                new_password = st.text_input("設定密碼", type="password")
                confirm_password = st.text_input("確認密碼", type="password")
                if st.form_submit_button("註冊", use_container_width=True):
                    if not new_username or not new_password:
                        st.error("⚠️ 欄位不可為空")
                    elif new_password != confirm_password:
                        st.error("⚠️ 密碼不一致")
                    else:
                        success, msg = register_user(new_username, new_password)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)

def main_app():
    current_user = st.session_state.get('username', 'Guest')

    with st.sidebar:
        st.markdown(f"👤 **使用者: {current_user}** ({st.session_state.get('role', 'user')})")
        with st.expander("⚙️ 帳號設定 (修改密碼)"):
            with st.form("change_pwd_form"):
                old_pw = st.text_input("輸入舊密碼", type="password")
                new_pw = st.text_input("輸入新密碼", type="password")
                confirm_pw = st.text_input("確認新密碼", type="password")
                if st.form_submit_button("儲存修改", use_container_width=True):
                    if not old_pw or not new_pw or not confirm_pw:
                        st.error("⚠️ 欄位不可為空")
                    elif new_pw != confirm_pw:
                        st.error("⚠️ 密碼不一致")
                    else:
                        success, msg = update_password(current_user, old_pw, new_pw)
                        if success: st.success(msg)
                        else: st.error(msg)
        if st.button("🚪 登出系統", type="primary", use_container_width=True):
            st.session_state.update({'logged_in': False, 'role': None})
            st.rerun()
        st.markdown("---")

    st.title("📈 均線糾結選股神器 (究極優化旗艦版)")

    with st.spinner("🚀 極速載入全市場數據中..."):
        df_full = load_precalculated_data()

    if df_full.empty:
        st.error("⚠️ 資料庫中尚無數據。")
        st.stop()

    st.sidebar.header("📅 篩選條件")
    avail_dates = sorted(df_full['date'].dt.date.unique(), reverse=True)
    sel_date = st.sidebar.selectbox("選擇日期 (選過去日期可看回測)", avail_dates, index=0)
    is_past_date = sel_date < avail_dates[0]

    st.sidebar.header("⚙️ 篩選參數")
    threshold_pct = st.sidebar.slider("均線糾結度 (%)", 1.0, 10.0, 3.0, 0.5)
    min_vol = st.sidebar.slider("最小成交量 (股)", 0, 5000000, 500000, 50000)
    min_price = st.sidebar.slider("最低股價 (元)", 0, 1000, 30, 5)

    filter_capital = st.sidebar.checkbox("限制股本大小 (小於篩選值)", value=True)
    capital_limit = 100.0
    if filter_capital:
        capital_limit = st.sidebar.slider("股本上限 (億)", 10.0, 2000.0, 100.0, 10.0)

    st.sidebar.subheader("進階設定")
    short_term_bull = st.sidebar.checkbox("短線多頭排列 (5MA > 10MA > 20MA)", value=True)
    long_term_bull = st.sidebar.checkbox("長線多頭排列 (60MA > 120MA)", value=False)
    ma20_up = st.sidebar.checkbox("月線上揚 (20MA向上)", value=False)
    above_ma5 = st.sidebar.checkbox("站上5MA (收盤價 > 5MA)", value=False)

    ma60_up = st.sidebar.checkbox("季線上揚 (60MA向上)", value=False)
    above_ma60 = st.sidebar.checkbox("站上60MA (收盤價 > 60MA)", value=False)

    limit_bias_60ma = st.sidebar.checkbox("離60MA乖離不能太大", value=False)
    bias_60ma_limit = 15.0
    if limit_bias_60ma:
        bias_60ma_limit = st.sidebar.slider("季線乖離率上限 (%)", 1.0, 30.0, 15.0, 1.0)

    st.sidebar.markdown("---")
    st.sidebar.subheader("🔥 攻擊型態與指標篩選 (預設關閉)")
    attack_vol = st.sidebar.checkbox("先前有出攻擊量 (近10日量增2倍)", value=False)
    vol_ma5_up = st.sidebar.checkbox("5日均量上揚", value=False)
    vol_ma10_up = st.sidebar.checkbox("10日均量上揚", value=False)
    break_high = st.sidebar.checkbox("過昨天的高點 (收盤價突破昨高)", value=False)
    up_2pct_red = st.sidebar.checkbox("上漲超過2%的紅K棒", value=False)
    solid_red_body = st.sidebar.checkbox("實體紅K棒至少要1/3以上", value=False, help="排除長上影線或避雷針型態")

    kd_about_gc = st.sidebar.checkbox("KD即將黃金交叉", value=False)
    kd_gc_3d_mid = st.sidebar.checkbox("KD在三日內已在非低檔區黃金交叉（35-75）", value=False)
    macd_about_red = st.sidebar.checkbox("MACD即將翻紅", value=False)
    macd_red_or_cont = st.sidebar.checkbox("MACD翻紅或持續紅", value=False)

    min_days = st.sidebar.slider("最少整理天數", 1, 10, 2, 1)

    with st.spinner(f"🚀 運算 {sel_date} 篩選結果..."):
        df_res = get_squeeze_candidates(df_full, sel_date, min_vol, min_price, filter_capital, capital_limit, threshold_pct/100, short_term_bull, long_term_bull, ma20_up, above_ma5, ma60_up, above_ma60, limit_bias_60ma, bias_60ma_limit, kd_about_gc, kd_gc_3d_mid, macd_about_red, macd_red_or_cont, attack_vol, vol_ma5_up, vol_ma10_up, break_high, up_2pct_red, solid_red_body, min_days)

    st.sidebar.divider()
    st.sidebar.subheader("🔍 為什麼找不到？")
    diag_code = st.sidebar.text_input("輸入代號 (如 3563)")
    if diag_code:
        diagnose_stock(diag_code, df_full, sel_date, min_vol, min_price, filter_capital, capital_limit, threshold_pct/100, short_term_bull, long_term_bull, ma20_up, above_ma5, ma60_up, above_ma60, limit_bias_60ma, bias_60ma_limit, kd_about_gc, kd_gc_3d_mid, macd_about_red, macd_red_or_cont, attack_vol, vol_ma5_up, vol_ma10_up, break_high, up_2pct_red, solid_red_body, min_days)

    if df_res.empty:
        st.warning(f"⚠️ 在 {sel_date} 無符合條件股票，請嘗試放寬側邊欄的篩選條件。")
    else:
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
            if is_past_date:
                sort_col_map["回測報酬率"] = "Backtest_Return"

            sort_label = st.radio("排序依據", list(sort_col_map.keys()), horizontal=True, index=0)
            sort_key = sort_col_map[sort_label]

        with c_sort2:
            sort_order = st.radio("排序方式", ["遞減 (大到小)", "遞增 (小到大)"], horizontal=True, index=0)
            ascending = True if sort_order == "遞增 (小到大)" else False

        df_sorted = df_res.sort_values(by=sort_key, ascending=ascending).reset_index(drop=True)

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

        c1, c2, c3 = st.columns([1, 1, 2])
        c1.metric("符合檔數", f"{len(df_sorted)}")
        c2.metric("最長整理", f"{df_sorted['days'].max()} 天")
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            auto_focus = st.toggle("🎯 表格動態跟隨 (自動置中目前個股)", value=True, help="開啟後，表格會變成滑動視窗，自動將您選取的個股對齊在中央。")

        def color_arrow(val):
            if '🔺' in str(val): return 'color: #ff4b4b; font-weight: bold'
            elif '▼' in str(val): return 'color: #26a69a; font-weight: bold'
            return ''

        def color_backtest(val):
            if pd.isna(val): return ''
            if val > 0: return 'color: #ff4b4b; font-weight: bold'
            elif val < 0: return 'color: #26a69a; font-weight: bold'
            return ''

        def highlight_active_row(row):
            if row.name == st.session_state.selected_index:
                return ['background-color: rgba(33, 150, 243, 0.25); font-weight: bold;'] * len(row)
            return [''] * len(row)

        if auto_focus and len(df_sorted) > 7:
            idx = st.session_state.selected_index
            start_idx = max(0, idx - 3)
            end_idx = min(len(df_sorted), start_idx + 7)
            if end_idx - start_idx < 7:
                start_idx = max(0, end_idx - 7)
            display_df = df_sorted.iloc[start_idx:end_idx]
        else:
            display_df = df_sorted

        styled_df = display_df.style.map(color_arrow, subset=['ma5_str', 'ma10_str', 'ma20_str', 'ma60_str'])
        if is_past_date: styled_df = styled_df.map(color_backtest, subset=['Backtest_Return'])
        styled_df = styled_df.apply(highlight_active_row, axis=1)

        col_cfg = {
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
        }

        col_order = [
            "symbol", "name", "Total_Score", "capital", "eps2026", "pe_ratio",
            "days", "vol_str", "squeeze_pct", "close", "volume",
            "ma5_str", "ma10_str", "ma20_str", "ma60_str", "link"
        ]

        if is_past_date:
            col_cfg["Backtest_Return"] = st.column_config.NumberColumn("回測報酬率", format="%.2f%%")
            col_order.insert(3, "Backtest_Return")

        selection_event = st.dataframe(
            styled_df,
            column_config=col_cfg,
            column_order=col_order,
            hide_index=True, use_container_width=True, height=300,
            on_select="rerun", selection_mode="single-row"
        )

        if selection_event.selection.rows:
            local_idx = selection_event.selection.rows[0]
            actual_idx = display_df.index[local_idx]
            if actual_idx != st.session_state.selected_index:
                update_state(actual_idx)
                st.rerun()

        st.divider()

        # ===========================
        # 🔥 圖表動態設定面板與繪圖
        # ===========================
        st.markdown("### 🎛️ 圖表指標設定")
        opt_col1, opt_col2, opt_col3 = st.columns(3)

        with opt_col1:
            st.markdown("**K線均線**")
            ma_options = ['3MA', '5MA', '10MA', '20MA', '60MA', '120MA']
            selected_mas = st.multiselect("顯示均線 (依照勾選順序)", ma_options, default=['5MA', '10MA', '20MA', '60MA'])
            show_ma_cross = st.checkbox("標記 20MA / 60MA 交叉", value=False, key="chk_ma_cross")

        with opt_col2:
            st.markdown("**成交量均線**")
            show_vol_ma5 = st.checkbox("顯示 5日均量", value=False)
            show_vol_ma10 = st.checkbox("顯示 10日均量", value=False)

        with opt_col3:
            st.markdown("**下方技術與籌碼指標**")
            show_kd = st.checkbox("顯示 KD (9,3,3)", value=False)
            show_rsi = st.checkbox("顯示 RSI (6,12)", value=False)
            show_macd = st.checkbox("顯示 MACD", value=False)
            show_foreign = st.checkbox("顯示 外資買賣超", value=False)
            show_trust = st.checkbox("顯示 投信買賣超", value=False)

        st.markdown("---")

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
            chart = df_full[(df_full['symbol'] == sym) & (df_full['date'].dt.date <= sel_date)].copy()

            if not chart.empty:
                signals_str = cur_info['Signal_List'] if cur_info['Signal_List'] else '無特別訊號'

                title_html = f"{current_sym_str} | 評分: {cur_info['Total_Score']}"
                if is_past_date and pd.notna(cur_info['Backtest_Return']):
                    color = "#FF4B4B" if cur_info['Backtest_Return'] > 0 else "#26a69a"
                    title_html += f" | 回測報酬: <span style='color: {color};'>{cur_info['Backtest_Return']:.2f}%</span>"

                pe_str = f"{cur_info['pe_ratio']:.2f}" if pd.notna(cur_info['pe_ratio']) else "-"
                eps_str = f"{cur_info['eps2026']:.2f}" if pd.notna(cur_info['eps2026']) else "-"
                cap_str = f"{cur_info['capital']:.1f}" if pd.notna(cur_info['capital']) else "-"

                html_dashboard = (
                    '<div style="margin: 20px 0;">'
                    f'<h2 style="text-align: center; color: #FF4B4B; margin-bottom: 15px; font-weight: bold;">{title_html}</h2>'
                    '<div style="display: flex; justify-content: space-around; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px 10px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); text-align: center;">'
                    f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">收盤價</span><br><span style="font-size:18px; font-weight:bold;">${cur_info["close"]:.2f}</span></div>'
                    f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">糾結天數</span><br><span style="font-size:18px; font-weight:bold; color:#2196F3;">{cur_info["days"]} 天</span></div>'
                    f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">糾結度</span><br><span style="font-size:18px; font-weight:bold;">{cur_info["squeeze_pct"]:.2f}%</span></div>'
                    f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">量增比</span><br><span style="font-size:18px; font-weight:bold; color:#FF4B4B;">{cur_info["vol_str"]}</span></div>'
                    f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">本益比</span><br><span style="font-size:18px; font-weight:bold;">{pe_str}</span></div>'
                    f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">預估EPS</span><br><span style="font-size:18px; font-weight:bold;">{eps_str}</span></div>'
                    f'<div style="flex: 1;"><span style="font-size:13px; color:#888;">股本</span><br><span style="font-size:18px; font-weight:bold;">{cap_str}</span></div>'
                    '</div>'
                    '<div style="background-color: #F4F9FF; border: 1px solid #D2E3FC; border-radius: 8px; padding: 15px 20px; font-size: 15px; color: #5F6368; width: 100%; box-sizing: border-box; line-height: 1.8;">'
                    f'<span style="color: #FF5A5F; font-weight: bold; font-size: 16px; margin-right: 4px;">⚡ 多方訊號：</span> {signals_str}'
                    '</div>'
                    '</div>'
                )
                st.markdown(html_dashboard, unsafe_allow_html=True)

                for c in ['open','high','low','close', 'volume']: chart[c] = pd.to_numeric(chart[c])

                chart['MA3'] = chart['close'].rolling(3).mean()

                is_same = chart['symbol'] == chart['symbol'].shift(1)
                chart['prev_MA20'] = np.where(is_same, chart['MA20'].shift(1), np.nan)
                chart['prev_MA60'] = np.where(is_same, chart['MA60'].shift(1), np.nan)

                chart['Golden_Cross'] = (chart['MA20'] > chart['MA60']) & (chart['prev_MA20'] <= chart['prev_MA60'])
                chart['Death_Cross'] = (chart['MA20'] < chart['MA60']) & (chart['prev_MA20'] >= chart['prev_MA60'])

                delta = chart['close'].diff()
                up = delta.clip(lower=0)
                down = -1 * delta.clip(upper=0)
                ema_up6 = up.ewm(com=5, adjust=False).mean()
                ema_down6 = down.ewm(com=5, adjust=False).mean()
                rs6 = ema_up6 / ema_down6
                chart['RSI6'] = 100 - (100 / (1 + rs6))

                ema_up12 = up.ewm(com=11, adjust=False).mean()
                ema_down12 = down.ewm(com=11, adjust=False).mean()
                rs12 = ema_up12 / ema_down12
                chart['RSI12'] = 100 - (100 / (1 + rs12))

                if 'K' not in chart.columns or chart['K'].isnull().all():
                    chart['9d_high'] = chart['high'].rolling(9, min_periods=1).max()
                    chart['9d_low'] = chart['low'].rolling(9, min_periods=1).min()
                    chart['RSV'] = np.where((chart['9d_high'] - chart['9d_low']) == 0, 50,
                                            100 * (chart['close'] - chart['9d_low']) / (chart['9d_high'] - chart['9d_low']))
                    k_list, d_list = [50], [50]
                    for rsv in chart['RSV'].tolist()[1:]:
                        if pd.isna(rsv):
                            k_list.append(k_list[-1])
                            d_list.append(d_list[-1])
                        else:
                            k_list.append(k_list[-1] * 2/3 + rsv * 1/3)
                            d_list.append(d_list[-1] * 2/3 + k_list[-1] * 1/3)
                    chart['K'], chart['D'] = k_list, d_list

                if 'MACD' not in chart.columns:
                    if 'DIF' in chart.columns and 'MACD_OSC' in chart.columns and not chart['DIF'].isnull().all():
                        chart['MACD'] = chart['DIF'] - chart['MACD_OSC']
                    else:
                        chart['EMA12'] = chart['close'].ewm(span=12, adjust=False).mean()
                        chart['EMA26'] = chart['close'].ewm(span=26, adjust=False).mean()
                        chart['DIF'] = chart['EMA12'] - chart['EMA26']
                        chart['MACD'] = chart['DIF'].ewm(span=9, adjust=False).mean()
                        chart['MACD_OSC'] = chart['DIF'] - chart['MACD']

                if 'foreign_net' not in chart.columns: chart['foreign_net'] = 0
                if 'trust_net' not in chart.columns: chart['trust_net'] = 0

                chart['std20'] = chart['close'].rolling(20).std()
                chart['BB_upper'] = chart['MA20'] + 3 * chart['std20']
                chart['BB_lower'] = chart['MA20'] - 3 * chart['std20']

                active_subplots = []
                if show_kd: active_subplots.append("KD (9,3,3)")
                if show_rsi: active_subplots.append("RSI (6,12)")
                if show_macd: active_subplots.append("MACD")
                if show_foreign: active_subplots.append("外資買賣超(張)")
                if show_trust: active_subplots.append("投信買賣超(張)")

                total_rows = 2 + len(active_subplots)
                row_heights = [0.4, 0.15] + [0.45 / max(1, len(active_subplots))] * len(active_subplots)

                base_height = 500
                fig_height = base_height + (150 * len(active_subplots))

                subplot_titles = [f"日K線圖 (3倍布林帶寬)", "成交量"] + active_subplots

                # 切割 150 天繪圖
                chart = chart.tail(150).copy()
                chart_dates = chart['date'].dt.strftime('%Y-%m-%d')

                fig = make_subplots(
                    rows=total_rows, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.03,
                    row_heights=row_heights,
                    subplot_titles=subplot_titles
                )

                # 🔥 隱藏 K 線圖例 (保留 Hover)
                fig.add_trace(go.Candlestick(
                    x=chart_dates, open=chart['open'], high=chart['high'], low=chart['low'], close=chart['close'],
                    increasing_line_color='#ef5350', decreasing_line_color='#26a69a', name='K線', showlegend=False
                ), row=1, col=1)

                ma_col_map = {'3MA': 'MA3', '5MA': 'MA5', '10MA': 'MA10', '20MA': 'MA20', '60MA': 'MA60', '120MA': 'MA120'}
                ma_colors = {'3MA': '#FF69B4', '5MA': 'orange', '10MA': '#00FFFF', '20MA': 'purple', '60MA': 'blue', '120MA': 'green'}

                y_range = chart['high'].max() - chart['low'].min()
                y_offset = y_range * 0.08

                for ma_name in selected_mas:
                    col_name = ma_col_map.get(ma_name)
                    if col_name and col_name in chart.columns:
                        is_up = chart[col_name].iloc[-1] > chart[col_name].iloc[-2]
                        trend_icon = "🔺" if is_up else "▼"
                        display_name = f"{ma_name} {trend_icon}"

                        # 🔥 唯一保留圖例的項目：MA 均線 (讓使用者能辨識顏色)
                        fig.add_trace(go.Scatter(
                            x=chart_dates, y=chart[col_name],
                            line=dict(color=ma_colors.get(ma_name, 'black'), width=1.5),
                            name=display_name
                        ), row=1, col=1)

                        N = int(ma_name.replace('MA', ''))
                        if len(chart) >= N:
                            deduct_idx = -N
                            x_val = chart_dates.iloc[deduct_idx]
                            c_low = chart['low'].iloc[deduct_idx]
                            color = ma_colors.get(ma_name, 'black')
                            y_marker = c_low - y_offset

                            fig.add_trace(go.Scatter(
                                x=[x_val, x_val],
                                y=[y_marker, c_low],
                                mode='lines',
                                line=dict(color=color, width=1.5, dash='dot'),
                                hoverinfo='skip',
                                showlegend=False
                            ), row=1, col=1)

                            fig.add_trace(go.Scatter(
                                x=[x_val],
                                y=[y_marker],
                                mode='markers+text',
                                marker=dict(symbol='circle', size=22, color='white', line=dict(color=color, width=2.5)),
                                text=[str(N)],
                                textfont=dict(color=color, size=11, family="Arial Black"),
                                hoverinfo='skip',
                                showlegend=False
                            ), row=1, col=1)

                if show_ma_cross:
                    gc_df = chart[chart['Golden_Cross']]
                    if not gc_df.empty:
                        # 🔥 隱藏交叉圖例
                        fig.add_trace(go.Scatter(
                            x=gc_df['date'].dt.strftime('%Y-%m-%d'), y=gc_df['MA20'],
                            mode='markers',
                            marker=dict(symbol='triangle-up', size=14, color='gold', line=dict(width=1, color='darkgoldenrod')),
                            name='20MA金叉60MA', showlegend=False
                        ), row=1, col=1)

                    dc_df = chart[chart['Death_Cross']]
                    if not dc_df.empty:
                        # 🔥 隱藏交叉圖例
                        fig.add_trace(go.Scatter(
                            x=dc_df['date'].dt.strftime('%Y-%m-%d'), y=dc_df['MA20'],
                            mode='markers',
                            marker=dict(symbol='triangle-down', size=14, color='green', line=dict(width=1, color='darkgreen')),
                            name='20MA死叉60MA', showlegend=False
                        ), row=1, col=1)

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

                # 🔥 隱藏成交量圖例
                vol_colors = ['#ef5350' if c >= o else '#26a69a' for c, o in zip(chart['close'], chart['open'])]
                fig.add_trace(go.Bar(
                    x=chart_dates, y=chart['volume'], marker_color=vol_colors, name='成交量', showlegend=False
                ), row=2, col=1)

                if show_vol_ma5:
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['Vol_MA5'], line=dict(color='orange', width=1.5), name='5日均量', showlegend=False), row=2, col=1)
                if show_vol_ma10:
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['Vol_MA10'], line=dict(color='#00FFFF', width=1.5), name='10日均量', showlegend=False), row=2, col=1)

                current_row = 3

                # 🔥 隱藏 KD 圖例
                if show_kd:
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['K'], name='K', line=dict(color='orange'), showlegend=False), row=current_row, col=1)
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['D'], name='D', line=dict(color='cyan'), showlegend=False), row=current_row, col=1)
                    current_row += 1

                # 🔥 隱藏 RSI 圖例
                if show_rsi:
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['RSI6'], name='RSI 6', line=dict(color='orange'), showlegend=False), row=current_row, col=1)
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['RSI12'], name='RSI 12', line=dict(color='cyan'), showlegend=False), row=current_row, col=1)
                    current_row += 1

                # 🔥 隱藏 MACD 圖例
                if show_macd:
                    osc_colors = ['#ef5350' if v >= 0 else '#26a69a' for v in chart['MACD_OSC']]
                    fig.add_trace(go.Bar(x=chart_dates, y=chart['MACD_OSC'], marker_color=osc_colors, name='OSC', showlegend=False), row=current_row, col=1)
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['DIF'], name='DIF', line=dict(color='orange'), showlegend=False), row=current_row, col=1)
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['MACD'], name='MACD', line=dict(color='cyan'), showlegend=False), row=current_row, col=1)
                    current_row += 1

                # 🔥 隱藏籌碼圖例
                if show_foreign:
                    foreign_colors = ['#ef5350' if v >= 0 else '#26a69a' for v in chart['foreign_net']]
                    fig.add_trace(go.Bar(x=chart_dates, y=chart['foreign_net'], marker_color=foreign_colors, name='外資買賣超', showlegend=False), row=current_row, col=1)
                    current_row += 1

                if show_trust:
                    trust_colors = ['#ef5350' if v >= 0 else '#26a69a' for v in chart['trust_net']]
                    fig.add_trace(go.Bar(x=chart_dates, y=chart['trust_net'], marker_color=trust_colors, name='投信買賣超', showlegend=False), row=current_row, col=1)
                    current_row += 1

                fig.update_xaxes(type='category', nticks=15)
                fig.update_layout(
                    xaxis_rangeslider_visible=False,
                    height=fig_height,
                    margin=dict(t=30,b=0,l=0,r=0),
                    legend=dict(orientation="h", y=1.01, x=0.5, xanchor='center'),
                    hovermode='x unified'
                )

                st.plotly_chart(fig, use_container_width=True)

# ===========================
# 7. 程式進入點 (Entry Point)
# ===========================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    login_page()
else:
    main_app()
