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
# 2. 資料庫連線 & 登入模組
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

def add_to_watchlist_db(symbol, username):
    engine = get_db_engine()
    try:
        with engine.begin() as conn:
            # 1. 檢查該使用者的「觀察清單」群組是否存在，若無則自動建立
            menu_id = conn.execute(
                text("SELECT id FROM watchlist_menus WHERE name = '觀察清單' AND username = :u"), 
                {"u": username}
            ).scalar()
            
            if not menu_id:
                menu_id = conn.execute(
                    text("INSERT INTO watchlist_menus (name, username) VALUES ('觀察清單', :u) RETURNING id"), 
                    {"u": username}
                ).scalar()

            # 2. 將股票加入該群組
            added_date = datetime.now().strftime('%Y-%m-%d')
            conn.execute(text("""
                INSERT INTO watchlist_items (menu_id, symbol, added_date) 
                VALUES (:mid, :sym, :date)
                ON CONFLICT (menu_id, symbol) DO NOTHING
            """), {"mid": menu_id, "sym": symbol, "date": added_date})
            
        return True, f"{symbol} 已成功加入「觀察清單」！"
    except Exception as e: 
        return False, f"加入失敗: {str(e)}"

# ===========================
# 3. 🚀 雙層快取架構 (終極提速)
# ===========================
@st.cache_data(ttl=600, show_spinner=False)
def load_screener_data():
    engine = get_db_engine()
    query_long = """
    SELECT date, symbol, close, volume 
    FROM daily_stock_indicators 
    WHERE date >= current_date - INTERVAL '200 days'
    ORDER BY symbol, date
    """
    query_recent = """
    SELECT d.date, d.symbol, d.name, d.industry, d.open, d.high, d.low, d.close, d.volume,
           d.pct_change, d.foreign_net, d.trust_net, d."MA5", d."MA10", d."MA20", d."MA60",
           d."K", d."D", d."MACD_OSC", d."DIF", d."Vol_Ratio",
           d.total_score as "Total_Score", d.signal_list as "Signal_List",
           e."Capital", e."2026EPS"
    FROM daily_stock_indicators d
    LEFT JOIN stock_eps e ON d.symbol = e."Symbol"
    WHERE d.date >= current_date - INTERVAL '40 days'
    ORDER BY d.symbol, d.date
    """
    try:
        with engine.connect() as conn:
            df_long = pd.read_sql(query_long, conn)
            df = pd.read_sql(query_recent, conn)
    except Exception as e:
        st.error(f"資料讀取失敗: {e}")
        return {}, {}, None, []

    if df.empty: return {}, {}, None, []

    df_long['date'] = pd.to_datetime(df_long['date'])
    df['date'] = pd.to_datetime(df['date'])
    df_long['symbol'] = df_long['symbol'].astype(str).str.strip()
    df['symbol'] = df['symbol'].astype(str).str.strip()

    # 算 120MA 與均量
    df_long['MA120'] = df_long['close'].rolling(120).mean()
    df_long['Vol_MA5'] = df_long['volume'].rolling(5).mean()
    df_long['Vol_MA10'] = df_long['volume'].rolling(10).mean()
    df_long.loc[df_long['symbol'] != df_long['symbol'].shift(119), 'MA120'] = np.nan
    df_long.loc[df_long['symbol'] != df_long['symbol'].shift(4), 'Vol_MA5'] = np.nan
    df_long.loc[df_long['symbol'] != df_long['symbol'].shift(9), 'Vol_MA10'] = np.nan

    df = pd.merge(df, df_long[['date', 'symbol', 'MA120', 'Vol_MA5', 'Vol_MA10']], on=['date', 'symbol'], how='left')
    del df_long  

    df['Total_Score'] = df['Total_Score'].fillna(0).astype(np.int16)
    df['Signal_List'] = df['Signal_List'].fillna("")
    for col in ['foreign_net', 'trust_net', 'K', 'D', 'MACD_OSC', 'DIF', 'Vol_Ratio']:
        if col not in df.columns: df[col] = np.nan

    # 產生「前一日」指標比較基準
    is_same_sym = df['symbol'] == df['symbol'].shift(1)
    for col in ['MA5', 'MA10', 'MA20', 'MA60', 'MA120', 'high', 'close', 'K', 'D', 'MACD_OSC', 'Vol_MA5', 'Vol_MA10']:
        df[f'prev_{col}'] = np.where(is_same_sym, df[col].shift(1), np.nan)

    # 籌碼面：計算前 1~5 日的外資/投信紀錄 (為了連買與初次買超過濾)
    for i in range(1, 6):
        is_same_i = df['symbol'] == df['symbol'].shift(i)
        df[f'prev{i}_foreign_net'] = np.where(is_same_i, df['foreign_net'].shift(i), np.nan)
        df[f'prev{i}_trust_net'] = np.where(is_same_i, df['trust_net'].shift(i), np.nan)

    df['max_ma'] = np.maximum(df['MA5'], np.maximum(df['MA10'], df['MA20']))
    df['min_ma'] = np.minimum(df['MA5'], np.minimum(df['MA10'], df['MA20']))
    df['sq_pct'] = (df['max_ma'] - df['min_ma']) / df['min_ma']

    # KD 金叉 35-65 中檔區
    df['is_kd_gc'] = (df['K'] > df['D']) & (df['prev_K'] <= df['prev_D'])
    df['is_kd_gc_mid'] = df['is_kd_gc'] & (df['K'] >= 35) & (df['K'] <= 65)
    kd_mid_1 = df['is_kd_gc_mid'].shift(1).fillna(False) & is_same_sym
    kd_mid_2 = df['is_kd_gc_mid'].shift(2).fillna(False) & (df['symbol'] == df['symbol'].shift(2))
    df['kd_gc_3d_mid_flag'] = df['is_kd_gc_mid'] | kd_mid_1 | kd_mid_2

    # 字典打包
    df_dict_by_date = {dt.date(): group for dt, group in df.groupby('date')}
    df_dict_by_symbol = {sym: group for sym, group in df.groupby('symbol')}
    max_date = df['date'].dt.date.max()
    avail_dates = sorted(df['date'].dt.date.unique(), reverse=True)

    return df_dict_by_date, df_dict_by_symbol, max_date, avail_dates

@st.cache_data(ttl=600, show_spinner=False)
def load_single_chart_data(symbol):
    engine = get_db_engine()
    query = f"""
    SELECT date, open, high, low, close, volume, foreign_net, trust_net,
           "MA5", "MA10", "MA20", "MA60", "K", "D", "MACD_OSC", "DIF"
    FROM daily_stock_indicators
    WHERE symbol = '{symbol}' AND date >= current_date - INTERVAL '400 days'
    ORDER BY date
    """
    try:
        with engine.connect() as conn:
            chart = pd.read_sql(query, conn)
        if chart.empty: return chart
        
        chart['date'] = pd.to_datetime(chart['date'])
        for c in ['open','high','low','close', 'volume']: chart[c] = pd.to_numeric(chart[c])
        
        chart['MA3'] = chart['close'].rolling(3).mean()
        chart['MA120'] = chart['close'].rolling(120).mean()
        chart['Vol_MA5'] = chart['volume'].rolling(5).mean()
        chart['Vol_MA10'] = chart['volume'].rolling(10).mean()
        chart['prev_MA20'] = chart['MA20'].shift(1)
        chart['prev_MA60'] = chart['MA60'].shift(1)
        chart['Golden_Cross'] = (chart['MA20'] > chart['MA60']) & (chart['prev_MA20'] <= chart['prev_MA60'])
        chart['Death_Cross'] = (chart['MA20'] < chart['MA60']) & (chart['prev_MA20'] >= chart['prev_MA60'])

        delta = chart['close'].diff()
        up = delta.clip(lower=0); down = -1 * delta.clip(upper=0)
        chart['RSI6'] = 100 - (100 / (1 + up.ewm(com=5, adjust=False).mean() / down.ewm(com=5, adjust=False).mean()))
        chart['RSI12'] = 100 - (100 / (1 + up.ewm(com=11, adjust=False).mean() / down.ewm(com=11, adjust=False).mean()))

        if 'K' not in chart.columns or chart['K'].isnull().all():
            chart['9d_high'] = chart['high'].rolling(9, min_periods=1).max()
            chart['9d_low'] = chart['low'].rolling(9, min_periods=1).min()
            chart['RSV'] = np.where((chart['9d_high'] - chart['9d_low']) == 0, 50, 100 * (chart['close'] - chart['9d_low']) / (chart['9d_high'] - chart['9d_low']))
            k_list, d_list = [50], [50]
            for rsv in chart['RSV'].tolist()[1:]:
                if pd.isna(rsv):
                    k_list.append(k_list[-1]); d_list.append(d_list[-1])
                else:
                    k_list.append(k_list[-1]*2/3 + rsv*1/3); d_list.append(d_list[-1]*2/3 + k_list[-1]*1/3)
            chart['K'], chart['D'] = k_list, d_list

        if 'MACD' not in chart.columns:
            chart['EMA12'] = chart['close'].ewm(span=12, adjust=False).mean()
            chart['EMA26'] = chart['close'].ewm(span=26, adjust=False).mean()
            chart['DIF'] = chart['EMA12'] - chart['EMA26']
            chart['MACD'] = chart['DIF'].ewm(span=9, adjust=False).mean()
            chart['MACD_OSC'] = chart['DIF'] - chart['MACD']

        chart['std20'] = chart['close'].rolling(20).std()
        chart['BB_upper'] = chart['MA20'] + 3 * chart['std20']
        chart['BB_lower'] = chart['MA20'] - 3 * chart['std20']
        
        return chart
    except Exception as e:
        return pd.DataFrame()

# ===========================
# 4. 極速篩選過濾器
# ===========================
def get_squeeze_candidates(df_dict_by_date, df_dict_by_symbol, max_date, target_date, f):
    df_tgt = df_dict_by_date.get(target_date)
    if df_tgt is None or df_tgt.empty: return pd.DataFrame()
    df_tgt = df_tgt.copy()

    # 基礎過濾
    cond = (df_tgt['volume'] >= f['min_vol']) & (df_tgt['close'] >= f['min_price']) & (df_tgt['sq_pct'] <= f['sq_thresh'])
    if f['filter_capital']: cond &= (df_tgt['Capital'] <= f['capital_limit'])

    # [進階設定]
    if f['short_bull']: cond &= (df_tgt['MA5'] > df_tgt['MA10']) & (df_tgt['MA10'] > df_tgt['MA20'])
    if f['long_bull']: cond &= (df_tgt['MA60'] > df_tgt['MA120'])
    if f['above_3ma']: cond &= (df_tgt['close'] > df_tgt['MA5']) & (df_tgt['close'] > df_tgt['MA10']) & (df_tgt['close'] > df_tgt['MA20'])
    if f['above_5ma']: cond &= (df_tgt['close'] > df_tgt['MA5']) & (df_tgt['close'] > df_tgt['MA10']) & (df_tgt['close'] > df_tgt['MA20']) & (df_tgt['close'] > df_tgt['MA60']) & (df_tgt['close'] > df_tgt['MA120'])
    if f['limit_bias_60']: cond &= (abs(df_tgt['close'] - df_tgt['MA60']) / df_tgt['MA60'] <= (f['bias_limit'] / 100.0))

    # [攻擊型態與技術指標]
    if f['break_high']: cond &= (df_tgt['close'] > df_tgt['prev_high'])
    if f['up_2pct']: cond &= (((df_tgt['close'] - df_tgt['prev_close']) / df_tgt['prev_close'] * 100) >= 2.0) & (df_tgt['close'] > df_tgt['open'])
    if f['solid_red']: cond &= ((df_tgt['close'] - df_tgt['open']) > 0) & ((df_tgt['close'] - df_tgt['open']) >= (df_tgt['high'] - df_tgt['low']) / 3.0)
    if f['kd_about_gc']: cond &= (df_tgt['K'] < df_tgt['D']) & ((df_tgt['D'] - df_tgt['K']) <= 3) & (df_tgt['K'] > df_tgt['prev_K'])
    if f['kd_3d_mid']: cond &= (df_tgt['kd_gc_3d_mid_flag'] == True)
    if f['macd_about_red']: cond &= (df_tgt['MACD_OSC'] < 0) & (df_tgt['MACD_OSC'] > df_tgt['prev_MACD_OSC'])
    if f['macd_red']: cond &= (df_tgt['MACD_OSC'] > 0)

    ma5_up = df_tgt['MA5'] > df_tgt['prev_MA5']
    ma10_up = df_tgt['MA10'] > df_tgt['prev_MA10']
    ma20_up = df_tgt['MA20'] > df_tgt['prev_MA20']
    ma60_up = df_tgt['MA60'] > df_tgt['prev_MA60']
    ma120_up = df_tgt['MA120'] > df_tgt['prev_MA120']

    if f['ma_all_up']: cond &= ma5_up & ma10_up & ma20_up & ma60_up & ma120_up
    if f['ma5_up']: cond &= ma5_up
    if f['ma10_up']: cond &= ma10_up
    if f['ma20_up']: cond &= ma20_up
    if f['ma60_up']: cond &= ma60_up
    if f['ma120_up']: cond &= ma120_up

    # [籌碼指標篩選]
    if f['foreign_buy_3d']: cond &= (df_tgt['foreign_net'] > 0) & (df_tgt['prev1_foreign_net'] > 0) & (df_tgt['prev2_foreign_net'] > 0)
    if f['trust_buy_3d']: cond &= (df_tgt['trust_net'] > 0) & (df_tgt['prev1_trust_net'] > 0) & (df_tgt['prev2_trust_net'] > 0)
    if f['tu_yang']: cond &= (df_tgt['foreign_net'] > 0) & (df_tgt['trust_net'] > 0)
    if f['foreign_buy']: cond &= (df_tgt['foreign_net'] >= f['foreign_buy_vol'])
    if f['trust_buy']: cond &= (df_tgt['trust_net'] >= f['trust_buy_vol'])
    if f['trust_first_buy']:
        cond &= (df_tgt['trust_net'] > 0) & (df_tgt['prev1_trust_net'] <= 0) & (df_tgt['prev2_trust_net'] <= 0) & (df_tgt['prev3_trust_net'] <= 0) & (df_tgt['prev4_trust_net'] <= 0) & (df_tgt['prev5_trust_net'] <= 0)

    candidates_df = df_tgt[cond]
    is_past_date = target_date < max_date
    latest_closes = dict(zip(df_dict_by_date.get(max_date, pd.DataFrame())['symbol'], df_dict_by_date.get(max_date, pd.DataFrame())['close'])) if is_past_date else {}

    results = []
    def get_ma_str(curr, prev):
        if pd.isna(curr) or pd.isna(prev): return "-"
        return f"{curr:.2f} {'🔺' if curr > prev else '▼'}"

    for _, last in candidates_df.iterrows():
        sym = last['symbol']
        sym_df_hist = df_dict_by_symbol.get(sym, pd.DataFrame())
        sym_df_hist = sym_df_hist[sym_df_hist['date'].dt.date <= target_date]

        if f['attack_vol']:
            if not (sym_df_hist['Vol_Ratio'].tail(10) >= f['attack_vol_ratio']).any(): continue

        days = 0
        for val in (sym_df_hist['sq_pct'] <= f['sq_thresh']).values[::-1]:
            if val: days += 1
            else: break

        if days >= f['min_days']:
            v_ratio = last['Vol_Ratio'] if pd.notna(last['Vol_Ratio']) else 0.0
            pe = last['close'] / last['2026EPS'] if pd.notna(last['2026EPS']) and last['2026EPS'] > 0 else np.nan
            ret = ((latest_closes.get(sym, np.nan) - last['close']) / last['close']) * 100 if is_past_date and last['close'] > 0 else np.nan

            dynamic_score = 0; dynamic_signals = []
            if pd.notna(last['close']) and pd.notna(last['prev_high']) and last['close'] > last['prev_high']: dynamic_score += 1; dynamic_signals.append("過昨高")
            if pd.notna(last['K']) and pd.notna(last['D']):
                if last['K'] > last['D'] and last['prev_K'] <= last['prev_D']: dynamic_score += 2; dynamic_signals.append("KD金叉")
                elif last['K'] < last['D'] and (last['D'] - last['K']) <= 3 and last['K'] > last['prev_K']: dynamic_score += 1; dynamic_signals.append("KD將金叉")
            if pd.notna(last['MACD_OSC']) and pd.notna(last['prev_MACD_OSC']):
                if last['MACD_OSC'] > 0 and last['prev_MACD_OSC'] <= 0: dynamic_score += 2; dynamic_signals.append("MACD翻紅")
            if pd.notna(last['trust_net']) and last['trust_net'] > 0 and pd.notna(last['prev1_trust_net']):
                if last['prev1_trust_net'] <= 0 and last['prev2_trust_net'] <= 0 and last['prev3_trust_net'] <= 0 and last['prev4_trust_net'] <= 0 and last['prev5_trust_net'] <= 0:
                    dynamic_score += 2; dynamic_signals.append("投信初次買超")
            if pd.notna(last['foreign_net']) and last['foreign_net'] > 0 and pd.notna(last['trust_net']) and last['trust_net'] > 0:
                dynamic_score += 1; dynamic_signals.append("土洋合作")

            db_score = int(last['Total_Score']) if pd.notna(last['Total_Score']) else 0
            db_signal_str = str(last['Signal_List']).strip() if pd.notna(last['Signal_List']) else ""
            final_score = dynamic_score if db_score == 0 else db_score
            final_signal = "、".join(dynamic_signals) if not db_signal_str or db_signal_str == "nan" else db_signal_str

            results.append({
                'symbol': sym, 'name': last['name'], 'close': last['close'], 'volume': int(last['volume']),
                'vol_ratio': v_ratio, 'vol_str': f"🔥 {v_ratio:.1f}x" if v_ratio >= 1.5 else f"{v_ratio:.1f}x",
                'squeeze_pct': last['sq_pct'] * 100, 'days': days, 'capital': last['Capital'],
                'eps2026': last['2026EPS'], 'pe_ratio': pe, 'Total_Score': final_score,
                'Signal_List': final_signal if final_signal else "無特別訊號", 'Backtest_Return': ret,
                'ma5_str': get_ma_str(last['MA5'], last['prev_MA5']), 'ma10_str': get_ma_str(last['MA10'], last['prev_MA10']),
                'ma20_str': get_ma_str(last['MA20'], last['prev_MA20']), 'ma60_str': get_ma_str(last['MA60'], last['prev_MA60']),
                'link': f"https://www.wantgoo.com/stock/{sym.replace('.TW','').replace('.TWO','')}"
            })
    return pd.DataFrame(results)

def diagnose_stock(symbol_code, df_dict_by_symbol, target_date, f):
    symbol_code = symbol_code.strip().upper()
    st.sidebar.markdown(f"#### 🕵️ 診斷報告: {symbol_code}")
    target_sym = next((sym for sym in df_dict_by_symbol.keys() if symbol_code in sym), None)
    if not target_sym:
        st.sidebar.error("❌ 無此代號或無資料"); return
    df = df_dict_by_symbol[target_sym].copy()
    df = df[df['date'].dt.date <= target_date]
    if df.empty:
        st.sidebar.error("❌ 該日期無資料"); return

    last = df.iloc[-1]
    st.sidebar.caption(f"{target_sym} {last['name']} | {last['date'].strftime('%Y-%m-%d')}")

    days = 0
    for val in (df['sq_pct'] <= f['sq_thresh']).values[::-1]:
        if val: days += 1
        else: break

    k_len = last['high'] - last['low']
    body_len = last['close'] - last['open']
    pct_chg = (last['close'] - last['prev_close']) / last['prev_close'] * 100 if pd.notna(last['prev_close']) and last['prev_close'] > 0 else 0

    def show_check(label, ok, val, target):
        cls = "diag-pass" if ok else "diag-fail"
        st.sidebar.markdown(f"{label}: <span class='{cls}'>{'✅' if ok else '❌'} {val}</span> / {target}", unsafe_allow_html=True)

    show_check("成交量", last['volume'] >= f['min_vol'], int(last['volume']), f['min_vol'])
    show_check("股本大小", (last['Capital'] <= f['capital_limit']) if f['filter_capital'] else True, f"{last['Capital']} 億" if pd.notna(last['Capital']) else "無", f"<={f['capital_limit']} 億" if f['filter_capital'] else "不拘")
    show_check("短期多頭(5>10>20)", (last['MA5'] > last['MA10'] and last['MA10'] > last['MA20']) if f['short_bull'] else True, "是" if (last['MA5'] > last['MA10'] and last['MA10'] > last['MA20']) else "否", "必要" if f['short_bull'] else "不拘")
    show_check("長期多頭(60>120)", last['MA60'] > last['MA120'] if f['long_bull'] else True, "是" if last['MA60'] > last['MA120'] else "否", "必要" if f['long_bull'] else "不拘")
    show_check("站上三均(5,10,20)", (last['close'] > last['MA5'] and last['close'] > last['MA10'] and last['close'] > last['MA20']) if f['above_3ma'] else True, "是" if (last['close'] > last['MA5'] and last['close'] > last['MA10'] and last['close'] > last['MA20']) else "否", "必要" if f['above_3ma'] else "不拘")
    show_check(f"離60MA乖離<={f['bias_limit']}%", (abs(last['close'] - last['MA60']) / last['MA60']) <= (f['bias_limit'] / 100.0) if f['limit_bias_60'] else True, "是", "必要" if f['limit_bias_60'] else "不拘")
    show_check(f"近10日量增 {f['attack_vol_ratio']}倍", (df['Vol_Ratio'].tail(10) >= f['attack_vol_ratio']).any() if f['attack_vol'] else True, "是" if (df['Vol_Ratio'].tail(10) >= f['attack_vol_ratio']).any() else "否", "必要" if f['attack_vol'] else "不拘")
    show_check("過昨高(收盤>昨高)", last['close'] > last['prev_high'] if f['break_high'] else True, "是" if last['close'] > last['prev_high'] else "否", "必要" if f['break_high'] else "不拘")
    show_check("上漲>2%紅K棒", (pct_chg >= 2.0) and (last['close'] > last['open']) if f['up_2pct'] else True, "是" if (pct_chg >= 2.0) and (last['close'] > last['open']) else "否", "必要" if f['up_2pct'] else "不拘")
    show_check("實體紅K>1/3", (body_len > 0) and (body_len >= k_len / 3.0) if f['solid_red'] else True, "是" if (body_len > 0) and (body_len >= k_len / 3.0) else "否", "必要" if f['solid_red'] else "不拘")
    show_check("KD即將黃金交叉", (last['K'] < last['D']) and ((last['D'] - last['K']) <= 3) and (last['K'] > last['prev_K']) if f['kd_about_gc'] else True, "是", "必要" if f['kd_about_gc'] else "不拘")
    show_check("KD 3日內中檔金叉", last['kd_gc_3d_mid_flag'] if f['kd_3d_mid'] else True, "是" if last['kd_gc_3d_mid_flag'] else "否", "必要" if f['kd_3d_mid'] else "不拘")
    show_check("MACD即將翻紅", (last['MACD_OSC'] < 0) and (last['MACD_OSC'] > last['prev_MACD_OSC']) if f['macd_about_red'] else True, "是", "必要" if f['macd_about_red'] else "不拘")
    show_check("MACD翻紅或持續紅", (last['MACD_OSC'] > 0) if f['macd_red'] else True, "是" if (last['MACD_OSC'] > 0) else "否", "必要" if f['macd_red'] else "不拘")

    # 籌碼診斷
    show_check("外資連三買超", (last['foreign_net'] > 0 and last['prev1_foreign_net'] > 0 and last['prev2_foreign_net'] > 0) if f['foreign_buy_3d'] else True, "是", "必要" if f['foreign_buy_3d'] else "不拘")
    show_check("投信連三買超", (last['trust_net'] > 0 and last['prev1_trust_net'] > 0 and last['prev2_trust_net'] > 0) if f['trust_buy_3d'] else True, "是", "必要" if f['trust_buy_3d'] else "不拘")
    show_check("近期土洋合作", (last['foreign_net'] > 0 and last['trust_net'] > 0) if f['tu_yang'] else True, "是", "必要" if f['tu_yang'] else "不拘")
    show_check(f"外資大買(>{f['foreign_buy_vol']}張)", last['foreign_net'] >= f['foreign_buy_vol'] if f['foreign_buy'] else True, f"{last['foreign_net']}張", "必要" if f['foreign_buy'] else "不拘")
    show_check(f"投信大買(>{f['trust_buy_vol']}張)", last['trust_net'] >= f['trust_buy_vol'] if f['trust_buy'] else True, f"{last['trust_net']}張", "必要" if f['trust_buy'] else "不拘")
    is_trust_first = (last['trust_net'] > 0 and last['prev1_trust_net'] <= 0 and last['prev2_trust_net'] <= 0 and last['prev3_trust_net'] <= 0 and last['prev4_trust_net'] <= 0 and last['prev5_trust_net'] <= 0)
    show_check("投信買超第一天", is_trust_first if f['trust_first_buy'] else True, "是", "必要" if f['trust_first_buy'] else "不拘")

    show_check("糾結度", last['sq_pct'] <= f['sq_thresh'], f"{last['sq_pct']*100:.2f}%", f"{f['sq_thresh']*100:.1f}%")
    show_check("連續天數", days >= f['min_days'], f"{days} 天", f"{f['min_days']} 天")

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

# ===========================
# 6. 主應用程式與圖表渲染
# ===========================
def main_app():
    current_user = st.session_state.get('username', 'Guest')
    with st.sidebar:
        st.markdown(f"👤 **使用者: {current_user}** ({st.session_state.get('role', 'user')})")
        if st.button("🚪 登出系統", type="primary", use_container_width=True):
            st.session_state.update({'logged_in': False, 'role': None}); st.rerun()
        st.markdown("---")

    st.title("📈 均線糾結選股神器 (究極優化旗艦版)")

    with st.spinner("🚀 極速載入全市場數據中 (首次啟動約需 3~5 秒，之後秒開)..."):
        df_dict_by_date, df_dict_by_symbol, max_date, avail_dates = load_screener_data()

    if not df_dict_by_date:
        st.error("⚠️ 資料庫中尚無數據。"); st.stop()

    st.sidebar.header("📅 篩選條件")
    sel_date = st.sidebar.selectbox("選擇日期 (選過去日期可看回測)", avail_dates, index=0)
    is_past_date = sel_date < avail_dates[0]

    st.sidebar.header("⚙️ 篩選參數")
    threshold_pct = st.sidebar.slider("均線糾結度 (%)", 1.0, 10.0, 3.0, 0.5)
    min_vol = st.sidebar.slider("最小成交量 (股)", 0, 5000000, 500000, 50000)
    min_price = st.sidebar.slider("最低股價 (元)", 0, 1000, 30, 5)

    filter_capital = st.sidebar.checkbox("限制股本大小 (小於篩選值)", value=True)
    capital_limit = st.sidebar.slider("股本上限 (億)", 10.0, 2000.0, 100.0, 10.0) if filter_capital else 100.0

    st.sidebar.subheader("進階設定")
    chk_short_bull = st.sidebar.checkbox("短期多頭排列 (5MA>10MA>20MA)", value=True)
    chk_long_bull = st.sidebar.checkbox("長期多頭排列 (60MA>120MA)", value=False)
    chk_above_3ma = st.sidebar.checkbox("股價站上三均 (5, 10, 20MA)", value=False)
    chk_above_5ma = st.sidebar.checkbox("股價站上五均 (5, 10, 20, 60, 120MA)", value=False)
    chk_bias_60 = st.sidebar.checkbox("股價與60MA乖離不能太大", value=False)
    bias_60ma_limit = st.sidebar.slider("季線乖離率上限 (%)", 1.0, 30.0, 15.0, 1.0) if chk_bias_60 else 15.0

    st.sidebar.markdown("---")
    st.sidebar.subheader("🔥 攻擊型態與指標篩選 (預設關閉)")
    chk_attack_vol = st.sidebar.checkbox("先前有出攻擊量 (近10日量增)", value=False)
    attack_vol_ratio = st.sidebar.slider("量增倍數設定", 1.5, 5.0, 2.0, 0.1) if chk_attack_vol else 2.0
    
    chk_break_high = st.sidebar.checkbox("有過昨日高點 (收盤價突破昨高)", value=False)
    chk_up_2pct = st.sidebar.checkbox("上漲超過2%的紅K棒", value=False)
    chk_solid_red = st.sidebar.checkbox("實體紅K棒至少要1/3以上", value=False)
    chk_kd_about_gc = st.sidebar.checkbox("KD即將黃金交叉", value=False)
    chk_kd_3d_mid = st.sidebar.checkbox("KD在三日內在中檔區黃金交叉 (35-65)", value=False)
    chk_macd_about_red = st.sidebar.checkbox("MACD即將翻紅", value=False)
    chk_macd_red = st.sidebar.checkbox("MACD已翻紅或持續紅", value=False)
    chk_ma_all_up = st.sidebar.checkbox("多頭開花 (5/10/20/60/120全上揚)", value=False)
    chk_ma5_up = st.sidebar.checkbox("5MA上揚", value=False)
    chk_ma10_up = st.sidebar.checkbox("10MA上揚", value=False)
    chk_ma20_up = st.sidebar.checkbox("20MA上揚", value=False)
    chk_ma60_up = st.sidebar.checkbox("60MA上揚", value=False)
    chk_ma120_up = st.sidebar.checkbox("120MA上揚", value=False)
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("🏦 籌碼型態篩選 (預設關閉)")
    chk_foreign_buy_3d = st.sidebar.checkbox("外資連三買超", value=False)
    chk_trust_buy_3d = st.sidebar.checkbox("投信連三買超", value=False)
    chk_tu_yang = st.sidebar.checkbox("近期土洋合作 (外資和投信都買超)", value=False)
    
    chk_foreign_buy = st.sidebar.checkbox("近期外資大買", value=False)
    foreign_buy_vol = st.sidebar.slider("外資大買張數設定", 100, 5000, 500, 100) if chk_foreign_buy else 500
    
    chk_trust_buy = st.sidebar.checkbox("近期投信大買", value=False)
    trust_buy_vol = st.sidebar.slider("投信大買張數設定", 50, 2000, 100, 50) if chk_trust_buy else 100
    
    chk_trust_first_buy = st.sidebar.checkbox("投信買超第一天 (連5日未買後轉買)", value=False)
    
    min_days = st.sidebar.slider("最少整理天數", 1, 10, 2, 1)

    filters = {
        'sq_thresh': threshold_pct / 100.0, 'min_vol': min_vol, 'min_price': min_price,
        'filter_capital': filter_capital, 'capital_limit': capital_limit, 'min_days': min_days,
        'short_bull': chk_short_bull, 'long_bull': chk_long_bull, 'above_3ma': chk_above_3ma,
        'above_5ma': chk_above_5ma, 'limit_bias_60': chk_bias_60, 'bias_limit': bias_60ma_limit,
        'attack_vol': chk_attack_vol, 'attack_vol_ratio': attack_vol_ratio, 'break_high': chk_break_high,
        'up_2pct': chk_up_2pct, 'solid_red': chk_solid_red, 'kd_about_gc': chk_kd_about_gc,
        'kd_3d_mid': chk_kd_3d_mid, 'macd_about_red': chk_macd_about_red, 'macd_red': chk_macd_red,
        'ma_all_up': chk_ma_all_up, 'ma5_up': chk_ma5_up, 'ma10_up': chk_ma10_up, 'ma20_up': chk_ma20_up,
        'ma60_up': chk_ma60_up, 'ma120_up': chk_ma120_up, 'tu_yang': chk_tu_yang,
        'foreign_buy': chk_foreign_buy, 'foreign_buy_vol': foreign_buy_vol,
        'trust_buy': chk_trust_buy, 'trust_buy_vol': trust_buy_vol,
        'foreign_buy_3d': chk_foreign_buy_3d, 'trust_buy_3d': chk_trust_buy_3d,
        'trust_first_buy': chk_trust_first_buy
    }

    with st.spinner("🚀 極速運算中... (全向量化，0.1秒完成)"):
        df_res = get_squeeze_candidates(df_dict_by_date, df_dict_by_symbol, max_date, sel_date, filters)

    st.sidebar.divider()
    st.sidebar.subheader("🔍 為什麼找不到？")
    diag_code = st.sidebar.text_input("輸入代號 (如 3563)")
    if diag_code: diagnose_stock(diag_code, df_dict_by_symbol, sel_date, filters)

    if df_res.empty: st.warning(f"⚠️ 在 {sel_date} 無符合條件股票，請嘗試放寬側邊欄的篩選條件。")
    else:
        c_sort1, c_sort2 = st.columns([1, 1])
        with c_sort1:
            sort_col_map = {"強勢總分": "Total_Score", "量增比": "vol_ratio", "成交量": "volume", "糾結度": "squeeze_pct", "天數": "days", "代號": "symbol"}
            if is_past_date: sort_col_map["回測報酬率"] = "Backtest_Return"
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
            auto_focus = st.toggle("🎯 表格動態跟隨", value=True)
        
        def color_arrow(val): return 'color: #ff4b4b; font-weight: bold' if '🔺' in str(val) else 'color: #26a69a; font-weight: bold' if '▼' in str(val) else ''
        def color_backtest(val): return '' if pd.isna(val) else 'color: #ff4b4b; font-weight: bold' if val > 0 else 'color: #26a69a; font-weight: bold'
        def highlight_active_row(row): return ['background-color: rgba(33, 150, 243, 0.25); font-weight: bold;'] * len(row) if row.name == st.session_state.selected_index else [''] * len(row)

        display_df = df_sorted
        if auto_focus and len(df_sorted) > 7:
            start_idx = max(0, st.session_state.selected_index - 3)
            end_idx = min(len(df_sorted), start_idx + 7)
            if end_idx - start_idx < 7: start_idx = max(0, end_idx - 7)
            display_df = df_sorted.iloc[start_idx:end_idx]

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
            "ma5_str": "5MA", "ma10_str": "10MA", "ma20_str": "20MA", "ma60_str": "60MA",
            "link": st.column_config.LinkColumn("連結", display_text="Go")
        }

        col_order = ["symbol", "name", "Total_Score", "capital", "eps2026", "pe_ratio", "days", "vol_str", "squeeze_pct", "close", "volume", "ma5_str", "ma10_str", "ma20_str", "ma60_str", "link"]
        if is_past_date:
            col_cfg["Backtest_Return"] = st.column_config.NumberColumn("回測", format="%.2f%%")
            col_order.insert(3, "Backtest_Return")

        selection_event = st.dataframe(styled_df, column_config=col_cfg, column_order=col_order, hide_index=True, use_container_width=True, height=300, on_select="rerun", selection_mode="single-row")

        if selection_event.selection.rows:
            local_idx = selection_event.selection.rows[0]
            actual_idx = display_df.index[local_idx]
            if actual_idx != st.session_state.selected_index:
                update_state(actual_idx)

        st.divider()

        st.markdown("### 🎛️ 圖表指標設定")
        opt_col1, opt_col2, opt_col3 = st.columns(3)
        with opt_col1:
            st.markdown("**K線均線**")
            selected_mas = st.multiselect("顯示均線 (依照勾選順序)", ['3MA', '5MA', '10MA', '20MA', '60MA', '120MA'], default=['5MA', '10MA', '20MA', '60MA'], key="ui_mas")
            show_ma_cross = st.checkbox("標記 20MA / 60MA 交叉", key="ui_cross")
        with opt_col2:
            st.markdown("**成交量均線**")
            show_vol_ma5 = st.checkbox("顯示 5日均量", key="ui_v5")
            show_vol_ma10 = st.checkbox("顯示 10日均量", key="ui_v10")
        with opt_col3:
            st.markdown("**下方技術與籌碼指標**")
            show_kd = st.checkbox("顯示 KD (9,3,3)", key="ui_kd")
            show_rsi = st.checkbox("顯示 RSI (6,12)", key="ui_rsi")
            show_macd = st.checkbox("顯示 MACD", key="ui_macd")
            show_foreign = st.checkbox("顯示 外資買賣超", key="ui_for")
            show_trust = st.checkbox("顯示 投信買賣超", key="ui_tru")

        st.markdown("---")
        b1, b2, b3, b4 = st.columns(4)
        b1.button("⏮️ 最前", on_click=go_first, use_container_width=True)
        b2.button("⬅️ 上一個", on_click=go_prev, use_container_width=True)
        b3.button("➡️ 下一個", on_click=go_next, use_container_width=True)
        b4.button("⏭️ 最後", on_click=go_last, use_container_width=True)

        # 🚀 新增：股票選擇器與加入觀察清單按鈕並排
        col_sel, col_add = st.columns([4, 1])
        with col_sel:
            st.selectbox("選擇股票 (亦可使用上方按鈕切換)", options=opts, key="stock_selector", on_change=on_dropdown_change)
        with col_add:
            st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True) # 為了與左邊的選單對齊高度
            if st.button("⭐ 加入觀察清單", use_container_width=True):
                if 'stock_selector' in st.session_state and st.session_state.stock_selector:
                    sym_to_add = st.session_state.stock_selector.split(" - ")[0]
                    success, msg = add_to_watchlist_db(sym_to_add, current_user)
                    if success:
                        st.toast(msg, icon="✅") # 使用 toast 彈出提示，不影響版面
                    else:
                        st.error(msg)

        current_sym_str = st.session_state.stock_selector
        if current_sym_str:
            sym = current_sym_str.split(" - ")[0]
            cur_info = df_sorted[df_sorted['symbol'] == sym].iloc[0]
            
            with st.spinner(f"載入 {sym} 圖表資料中..."):
                chart = load_single_chart_data(sym)
                
            if not chart.empty:
                chart = chart[chart['date'].dt.date <= sel_date]
                
                title_html = f"{current_sym_str} | 評分: {cur_info['Total_Score']}"
                if is_past_date and pd.notna(cur_info['Backtest_Return']):
                    title_html += f" | 回測報酬: <span style='color: {'#FF4B4B' if cur_info['Backtest_Return'] > 0 else '#26a69a'};'>{cur_info['Backtest_Return']:.2f}%</span>"
                
                pe_str = f"{cur_info['pe_ratio']:.2f}" if pd.notna(cur_info['pe_ratio']) else "-"
                eps_str = f"{cur_info['eps2026']:.2f}" if pd.notna(cur_info['eps2026']) else "-"
                cap_str = f"{cur_info['capital']:.1f}" if pd.notna(cur_info['capital']) else "-"
                    
                st.markdown(
                    '<div style="margin: 20px 0;">'
                    f'<h2 style="text-align: center; color: #FF4B4B; margin-bottom: 15px;">{title_html}</h2>'
                    '<div style="display: flex; justify-content: space-around; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px 10px; margin-bottom: 15px; text-align: center;">'
                    f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">收盤價</span><br><span style="font-size:18px; font-weight:bold;">${cur_info["close"]:.2f}</span></div>'
                    f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">糾結天數</span><br><span style="font-size:18px; font-weight:bold; color:#2196F3;">{cur_info["days"]} 天</span></div>'
                    f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">糾結度</span><br><span style="font-size:18px; font-weight:bold;">{cur_info["squeeze_pct"]:.2f}%</span></div>'
                    f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">量增比</span><br><span style="font-size:18px; font-weight:bold; color:#FF4B4B;">{cur_info["vol_str"]}</span></div>'
                    f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">本益比</span><br><span style="font-size:18px; font-weight:bold;">{pe_str}</span></div>'
                    f'<div style="flex: 1; border-right: 1px solid #eee;"><span style="font-size:13px; color:#888;">預估EPS</span><br><span style="font-size:18px; font-weight:bold;">{eps_str}</span></div>'
                    f'<div style="flex: 1;"><span style="font-size:13px; color:#888;">股本</span><br><span style="font-size:18px; font-weight:bold;">{cap_str}</span></div>'
                    '</div>'
                    '<div style="background-color: #F4F9FF; border: 1px solid #D2E3FC; border-radius: 8px; padding: 15px 20px;">'
                    f'<span style="color: #FF5A5F; font-weight: bold;">⚡ 多方訊號：</span> {cur_info["Signal_List"]}'
                    '</div></div>', unsafe_allow_html=True
                )

                active_subplots = []
                if show_kd: active_subplots.append("KD (9,3,3)")
                if show_rsi: active_subplots.append("RSI (6,12)")
                if show_macd: active_subplots.append("MACD")
                if show_foreign: active_subplots.append("外資買賣超(張)")
                if show_trust: active_subplots.append("投信買賣超(張)")

                total_rows = 2 + len(active_subplots)
                row_heights = [0.4, 0.15] + [0.45 / max(1, len(active_subplots))] * len(active_subplots)
                fig_height = 500 + (150 * len(active_subplots))

                chart = chart.tail(150).copy()
                chart_dates = chart['date'].dt.strftime('%Y-%m-%d')

                fig = make_subplots(
                    rows=total_rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, 
                    row_heights=row_heights, subplot_titles=[f"日K線圖 (3倍布林帶寬)", "成交量"] + active_subplots
                )

                fig.add_trace(go.Candlestick(x=chart_dates, open=chart['open'], high=chart['high'], low=chart['low'], close=chart['close'], increasing_line_color='#ef5350', decreasing_line_color='#26a69a', name='K線', showlegend=False), row=1, col=1)
                
                ma_col_map = {'3MA': 'MA3', '5MA': 'MA5', '10MA': 'MA10', '20MA': 'MA20', '60MA': 'MA60', '120MA': 'MA120'}
                ma_colors = {'3MA': '#FF69B4', '5MA': 'orange', '10MA': '#00FFFF', '20MA': 'purple', '60MA': 'blue', '120MA': 'green'}
                
                y_range = chart['high'].max() - chart['low'].min()
                y_offset = y_range * 0.08
                
                for ma_name in selected_mas:
                    col_name = ma_col_map.get(ma_name)
                    if col_name and col_name in chart.columns:
                        is_up = chart[col_name].iloc[-1] > chart[col_name].iloc[-2]
                        fig.add_trace(go.Scatter(x=chart_dates, y=chart[col_name], line=dict(color=ma_colors.get(ma_name, 'black'), width=1.5), name=f"{ma_name} {'🔺' if is_up else '▼'}"), row=1, col=1)
                        
                        N = int(ma_name.replace('MA', ''))
                        if len(chart) >= N:
                            deduct_idx = -N 
                            x_val = chart_dates.iloc[deduct_idx]
                            c_low = chart['low'].iloc[deduct_idx]
                            y_marker = c_low - y_offset
                            fig.add_trace(go.Scatter(x=[x_val, x_val], y=[y_marker, c_low], mode='lines', line=dict(color=ma_colors.get(ma_name, 'black'), width=1.5, dash='dot'), hoverinfo='skip', showlegend=False), row=1, col=1)
                            fig.add_trace(go.Scatter(x=[x_val], y=[y_marker], mode='markers+text', marker=dict(symbol='circle', size=22, color='white', line=dict(color=ma_colors.get(ma_name, 'black'), width=2.5)), text=[str(N)], textfont=dict(color=ma_colors.get(ma_name, 'black'), size=11, family="Arial Black"), hoverinfo='skip', showlegend=False), row=1, col=1)

                if show_ma_cross:
                    gc_df = chart[(chart['MA20'] > chart['MA60']) & (chart['prev_MA20'] <= chart['prev_MA60'])]
                    if not gc_df.empty: fig.add_trace(go.Scatter(x=gc_df['date'].dt.strftime('%Y-%m-%d'), y=gc_df['MA20'], mode='markers', marker=dict(symbol='triangle-up', size=14, color='gold', line=dict(width=1, color='darkgoldenrod')), name='20MA金叉60MA', showlegend=False), row=1, col=1)
                    dc_df = chart[(chart['MA20'] < chart['MA60']) & (chart['prev_MA20'] >= chart['prev_MA60'])]
                    if not dc_df.empty: fig.add_trace(go.Scatter(x=dc_df['date'].dt.strftime('%Y-%m-%d'), y=dc_df['MA20'], mode='markers', marker=dict(symbol='triangle-down', size=14, color='green', line=dict(width=1, color='darkgreen')), name='20MA死叉60MA', showlegend=False), row=1, col=1)

                fig.add_trace(go.Scatter(x=chart_dates, y=chart['BB_upper'], line=dict(color='rgba(150, 150, 150, 0.5)', width=1, dash='dash'), name='上軌 (3σ)', hoverinfo='skip', showlegend=False), row=1, col=1)
                fig.add_trace(go.Scatter(x=chart_dates, y=chart['BB_lower'], line=dict(color='rgba(150, 150, 150, 0.5)', width=1, dash='dash'), name='下軌 (3σ)', fill='tonexty', fillcolor='rgba(200, 200, 200, 0.1)', hoverinfo='skip', showlegend=False), row=1, col=1)

                vol_colors = ['#ef5350' if c >= o else '#26a69a' for c, o in zip(chart['close'], chart['open'])]
                fig.add_trace(go.Bar(x=chart_dates, y=chart['volume'], marker_color=vol_colors, name='成交量', showlegend=False), row=2, col=1)
                if show_vol_ma5: fig.add_trace(go.Scatter(x=chart_dates, y=chart['Vol_MA5'], line=dict(color='orange', width=1.5), name='5日均量', showlegend=False), row=2, col=1)
                if show_vol_ma10: fig.add_trace(go.Scatter(x=chart_dates, y=chart['Vol_MA10'], line=dict(color='#00FFFF', width=1.5), name='10日均量', showlegend=False), row=2, col=1)

                current_row = 3
                if show_kd:
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['K'], name='K', line=dict(color='orange'), showlegend=False), row=current_row, col=1)
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['D'], name='D', line=dict(color='cyan'), showlegend=False), row=current_row, col=1)
                    current_row += 1
                if show_rsi:
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['RSI6'], name='RSI 6', line=dict(color='orange'), showlegend=False), row=current_row, col=1)
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['RSI12'], name='RSI 12', line=dict(color='cyan'), showlegend=False), row=current_row, col=1)
                    current_row += 1
                if show_macd:
                    osc_colors = ['#ef5350' if v >= 0 else '#26a69a' for v in chart['MACD_OSC']]
                    fig.add_trace(go.Bar(x=chart_dates, y=chart['MACD_OSC'], marker_color=osc_colors, name='OSC', showlegend=False), row=current_row, col=1)
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['DIF'], name='DIF', line=dict(color='orange'), showlegend=False), row=current_row, col=1)
                    fig.add_trace(go.Scatter(x=chart_dates, y=chart['MACD'], name='MACD', line=dict(color='cyan'), showlegend=False), row=current_row, col=1)
                    current_row += 1
                if show_foreign:
                    foreign_colors = ['#ef5350' if v >= 0 else '#26a69a' for v in chart['foreign_net']]
                    fig.add_trace(go.Bar(x=chart_dates, y=chart['foreign_net'], marker_color=foreign_colors, name='外資買賣超', showlegend=False), row=current_row, col=1)
                    current_row += 1
                if show_trust:
                    trust_colors = ['#ef5350' if v >= 0 else '#26a69a' for v in chart['trust_net']]
                    fig.add_trace(go.Bar(x=chart_dates, y=chart['trust_net'], marker_color=trust_colors, name='投信買賣超', showlegend=False), row=current_row, col=1)
                    current_row += 1

                fig.update_xaxes(type='category', nticks=15)
                fig.update_layout(xaxis_rangeslider_visible=False, height=fig_height, margin=dict(t=30,b=0,l=0,r=0), legend=dict(orientation="h", y=1.01, x=0.5, xanchor='center'), hovermode='x unified')
                st.plotly_chart(fig, use_container_width=True)

# ===========================
# 7. 程式進入點 (Entry Point)
# ===========================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if not st.session_state['logged_in']: login_page()
else: main_app()

