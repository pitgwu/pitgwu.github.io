import streamlit as st
import pandas as pd
import sqlalchemy
from sqlalchemy import text
from sqlalchemy.pool import NullPool
import os
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import bcrypt
import time

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
    return sqlalchemy.create_engine(
        SUPABASE_DB_URL,
        poolclass=NullPool,
        connect_args={
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5
        }
    )

engine = get_engine()

# ===========================
# 2. 身份驗證
# ===========================
def check_login(username, password):
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("SELECT password_hash, role, active FROM users WHERE username = :u"),
                {"u": username}
            ).fetchone()
            
            if result:
                db_hash, role, active = result
                if bcrypt.checkpw(password.encode('utf-8'), db_hash.encode('utf-8')):
                    if active == 'yes': return True, role, "登入成功"
                    else: return False, None, "⚠️ 帳號尚未開通"
            return False, None, "❌ 帳號或密碼錯誤"
    except Exception as e:
        return False, None, f"系統錯誤: {e}"

def login_page():
    st.markdown("<h1 style='text-align: center;'>🔐 尾盤神探系統</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login"):
            u = st.text_input("帳號")
            p = st.text_input("密碼", type="password")
            if st.form_submit_button("登入", use_container_width=True):
                success, role, msg = check_login(u, p)
                if success:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = u
                    st.session_state['role'] = role
                    st.rerun()
                else: st.error(msg)

# ===========================
# 3. 資料讀取 (Chunking)
# ===========================
def get_chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

@st.cache_data(ttl=3600)
def load_data_v17():
    """讀取資料 (120天)"""
    LOOKBACK_DAYS = 120
    
    try:
        with engine.connect() as conn:
            df_info = pd.read_sql(text("SELECT symbol, name, industry FROM stock_info"), conn)
            
            q_rev = f"""
            SELECT report_month, symbol, rev_current, yoy_pct, yoy_accumulated_pct 
            FROM monthly_revenue 
            WHERE report_month >= current_date - INTERVAL '{LOOKBACK_DAYS + 365} days'
            """ 
            try:
                df_rev = pd.read_sql(text(q_rev), conn)
            except:
                df_rev = pd.DataFrame(columns=['report_month', 'symbol', 'rev_current', 'yoy_pct', 'yoy_accumulated_pct'])

    except Exception as e:
        st.error(f"初始化讀取失敗: {e}")
        return pd.DataFrame()

    all_symbols = df_info['symbol'].tolist()
    BATCH_SIZE = 50
    price_frames = []
    chip_frames = []
    
    progress = st.progress(0)
    status = st.empty()
    chunks = list(get_chunks(all_symbols, BATCH_SIZE))
    
    for i, chunk in enumerate(chunks):
        progress.progress(int((i / len(chunks)) * 100))
        status.text(f"📥 下載數據中... ({i+1}/{len(chunks)})")
        
        tuple_str = str(tuple(chunk)) if len(chunk) > 1 else f"('{chunk[0]}')"
        
        try:
            with engine.connect() as conn:
                q_p = f"""
                SELECT date, symbol, open, high, low, close, volume 
                FROM stock_prices 
                WHERE date >= current_date - INTERVAL '{LOOKBACK_DAYS} days' 
                AND symbol IN {tuple_str}
                """
                price_frames.append(pd.read_sql(text(q_p), conn))
                
                try:
                    q_c = f"""
                    SELECT date, symbol, foreign_net, trust_net, dealer_net 
                    FROM institutional_investors 
                    WHERE date >= current_date - INTERVAL '{LOOKBACK_DAYS} days' 
                    AND symbol IN {tuple_str}
                    """
                    chip_frames.append(pd.read_sql(text(q_c), conn))
                except: pass
        except:
            time.sleep(0.5); continue

    progress.empty(); status.empty()

    if not price_frames: return pd.DataFrame()
    
    df = pd.concat(price_frames, ignore_index=True)
    df['date'] = pd.to_datetime(df['date'])
    
    if chip_frames:
        df_chips = pd.concat(chip_frames, ignore_index=True)
        df_chips['date'] = pd.to_datetime(df_chips['date'])
        df = pd.merge(df, df_chips, on=['date','symbol'], how='left')
        
        fill_cols = ['foreign_net','trust_net','dealer_net']
        df[fill_cols] = df[fill_cols].fillna(0).infer_objects(copy=False).astype(int)
    else:
        df['foreign_net'] = 0; df['trust_net'] = 0; df['dealer_net'] = 0

    df = pd.merge(df, df_info, on='symbol', how='left')

    # --- 營收處理 ---
    if not df_rev.empty:
        df_rev['date'] = pd.to_datetime(df_rev['report_month'])
        df_rev = df_rev.sort_values('date')
        g_rev = df_rev.groupby('symbol')
        
        df_rev['rev_max'] = g_rev['rev_current'].expanding().max()
        df_rev['rev_is_ath'] = (df_rev['rev_current'] >= df_rev['rev_max']) & (df_rev['rev_current'] > 0)
        
        df_rev['yoy_pos'] = (df_rev['yoy_pct'] > 0).astype(int)
        df_rev['yoy_streak'] = g_rev['yoy_pos'].transform(lambda x: x.groupby((x != x.shift()).cumsum()).cumsum())
        
        df = df.sort_values('date')
        df = pd.merge_asof(df, df_rev[['date','symbol','rev_is_ath','yoy_streak','yoy_pct','yoy_accumulated_pct']], 
                           on='date', by='symbol', direction='backward')
    else:
        for c in ['rev_is_ath','yoy_streak','yoy_pct','yoy_accumulated_pct']: df[c] = 0

    df['rev_is_ath'] = df['rev_is_ath'].fillna(False)
    df[['yoy_pct','yoy_accumulated_pct']] = df[['yoy_pct','yoy_accumulated_pct']].fillna(0)

    # ==========================
    #   技術指標計算
    # ==========================
    df = df.sort_values(['symbol', 'date'])
    g = df.groupby('symbol')
    
    df['MA5'] = g['close'].transform(lambda x: x.rolling(5).mean())
    df['MA10'] = g['close'].transform(lambda x: x.rolling(10).mean())
    df['MA20'] = g['close'].transform(lambda x: x.rolling(20).mean())
    df['MA60'] = g['close'].transform(lambda x: x.rolling(60).mean())
    
    df['Vol_MA5'] = g['volume'].transform(lambda x: x.rolling(5).mean())
    df['Vol_MA10'] = g['volume'].transform(lambda x: x.rolling(10).mean())
    df['Vol_MA20'] = g['volume'].transform(lambda x: x.rolling(20).mean())
    
    df['prev_close'] = g['close'].shift(1)
    df['prev_volume'] = g['volume'].shift(1)
    df['pct_change'] = (df['close'] - df['prev_close']) / df['prev_close'] * 100
    df['pct_change_3d'] = g['close'].pct_change(3) * 100
    df['pct_change_5d'] = g['close'].pct_change(5) * 100
    
    df['high_3d'] = g['high'].transform(lambda x: x.rolling(3).max())
    df['vol_max_3d'] = g['volume'].transform(lambda x: x.rolling(3).max())
    
    low_min = g['low'].transform(lambda x: x.rolling(9).min())
    high_max = g['high'].transform(lambda x: x.rolling(9).max())
    rsv = (df['close'] - low_min) / (high_max - low_min) * 100
    df['K'] = rsv.ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    
    ema12 = g['close'].transform(lambda x: x.ewm(span=12).mean())
    ema26 = g['close'].transform(lambda x: x.ewm(span=26).mean())
    df['DIF'] = ema12 - ema26
    df['MACD'] = g['DIF'].transform(lambda x: x.ewm(span=9).mean())
    df['MACD_OSC'] = df['DIF'] - df['MACD']
    
    df['bias_ma5'] = (df['close'] - df['MA5']) / df['MA5'] * 100
    df['bias_ma20'] = (df['close'] - df['MA20']) / df['MA20'] * 100
    df['bias_ma60'] = (df['close'] - df['MA60']) / df['MA60'] * 100
    
    df['vol_bias_ma5'] = (df['volume'] - df['Vol_MA5']) / df['Vol_MA5'] * 100
    df['vol_bias_ma10'] = (df['volume'] - df['Vol_MA10']) / df['Vol_MA10'] * 100
    df['vol_bias_ma20'] = (df['volume'] - df['Vol_MA20']) / df['Vol_MA20'] * 100
    
    df['above_ma20'] = (df['close'] > df['MA20']).astype(int)
    df['days_above_ma20'] = g['above_ma20'].transform(lambda x: x.groupby((x != x.shift()).cumsum()).cumsum())
    
    df['above_ma60'] = (df['close'] > df['MA60']).astype(int)
    df['days_above_ma60'] = g['above_ma60'].transform(lambda x: x.groupby((x != x.shift()).cumsum()).cumsum())

    df['f_buy_pos'] = (df['foreign_net'] > 0).astype(int)
    df['f_buy_streak'] = g['f_buy_pos'].transform(lambda x: x.groupby((x != x.shift()).cumsum()).cumsum())
    
    df['f_sum_5d'] = g['foreign_net'].transform(lambda x: x.rolling(5).sum())

    # --- 週K計算 ---
    df_w = df.set_index('date').groupby('symbol').resample('W-FRI').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
    }).dropna().reset_index()
    
    df_w['is_red'] = (df_w['close'] > df_w['open']).astype(int)
    g_w = df_w.groupby('symbol')
    df_w['w_red_streak'] = g_w['is_red'].transform(lambda x: x.groupby((x != x.shift()).cumsum()).cumsum())
    
    df = df.sort_values('date')
    df_w = df_w.sort_values('date')
    df = pd.merge_asof(df, df_w[['date','symbol','w_red_streak']], on='date', by='symbol', direction='backward')
    df['w_red_streak'] = df['w_red_streak'].fillna(0)

    return df

# ===========================
# 4. 繪圖
# ===========================
def plot_chart(df, symbol, name):
    d = df[df['symbol'] == symbol].tail(100).copy()
    d['date_str'] = d['date'].dt.strftime('%Y-%m-%d')
    
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, row_heights=[0.5, 0.15, 0.15, 0.2],
                        subplot_titles=(f"{symbol} {name}", "成交量", "KD", "MACD"), vertical_spacing=0.03)
    
    fig.add_trace(go.Candlestick(
        x=d['date_str'], open=d['open'], high=d['high'], low=d['low'], close=d['close'], name='Price',
        increasing_line_color='red', decreasing_line_color='green'
    ), row=1, col=1)
    
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
# 5. 主程式邏輯 (訊號整合)
# ===========================
def main_app():
    with st.sidebar:
        st.markdown(f"👤 **{st.session_state['username']}** ({st.session_state['role']})")
        if st.button("🚪 登出", key="logout"):
            st.session_state['logged_in'] = False; st.rerun()
        st.markdown("---")

    st.title("🚀 尾盤神探 - 全動態數值版v17")
    
    for k in ['ticker_index','last_selected_rows']: 
        if k not in st.session_state: st.session_state[k] = 0

    df_full = load_data_v17()
    if df_full.empty:
        st.error("❌ 無法載入資料"); return

    dates = sorted(df_full['date'].dt.date.unique(), reverse=True)
    sel_date = st.sidebar.selectbox("📅 日期", dates, 0)
    sort_opt = st.sidebar.selectbox("排序", ["總分", "漲跌幅", "外資買超", "營收YOY"])
    min_sc = st.sidebar.number_input("最低分", 0, 50, 3)

    target_ts = pd.Timestamp(sel_date)
    df_day = df_full[df_full['date'] == target_ts].copy()
    
    if df_day.empty:
        st.warning("無資料"); return

    # --- 即時計算排名 ---
    df_day['rank_pct_1d'] = df_day['pct_change'].rank(ascending=False, method='min')
    df_day['rank_pct_5d'] = df_day['pct_change_5d'].rank(ascending=False, method='min')
    df_day['rank_f_1d'] = df_day['foreign_net'].rank(ascending=False, method='min')
    df_day['rank_f_5d'] = df_day['f_sum_5d'].rank(ascending=False, method='min')

    score = pd.Series(0, index=df_day.index)
    df_day['signals'] = [[] for _ in range(len(df_day))]

    # --- 動態文字 Helper ---
    def fmt(val, template):
        return val.fillna(0).apply(lambda x: template.format(x))

    # 1. 乖離與突破
    txt_bias_w_1 = fmt(df_day['bias_ma5'], "突破週線{:.2f}%")
    txt_bias_w_5 = fmt(df_day['bias_ma5'], "正乖離週線{:.2f}%")
    txt_bias_m_5 = fmt(df_day['bias_ma20'], "正乖離月線{:.2f}%")
    txt_bias_w = fmt(df_day['bias_ma5'], "突破週線{:.2f}%")
    txt_bias_m = fmt(df_day['bias_ma20'], "突破月線{:.2f}%")
    txt_bias_q = fmt(df_day['bias_ma60'], "突破季線{:.2f}%")

    # 2. 漲跌幅
    txt_pct_1 = fmt(df_day['pct_change'], "今日漲幅{:.2f}%")
    txt_pct_3 = fmt(df_day['pct_change_3d'], "3天漲幅{:.2f}%")
    txt_pct_5 = fmt(df_day['pct_change_5d'], "5天漲幅{:.2f}%")
    txt_rank_1d = df_day['rank_pct_1d'].fillna(999).astype(int).apply(lambda x: f"漲幅第{x}名")
    txt_rank_5d = df_day['rank_pct_5d'].fillna(999).astype(int).apply(lambda x: f"5日漲幅第{x}名")

    # 3. 量能
    txt_vol_5 = fmt(df_day['vol_bias_ma5'], "較5日量增{:.1f}%")
    txt_vol_10 = fmt(df_day['vol_bias_ma10'], "較10日量增{:.1f}%")
    txt_vol_20 = fmt(df_day['vol_bias_ma20'], "較20日量增{:.1f}%")
    txt_vol_double = fmt((df_day['volume'] / df_day['prev_volume']).fillna(0), "量增{:.1f}倍")

    # 4. 籌碼與營收 (🔥 全部改為動態)
    txt_f_rank_1d = df_day['rank_f_1d'].fillna(999).astype(int).apply(lambda x: f"外資買超第{x}名")
    txt_f_rank_5d = df_day['rank_f_5d'].fillna(999).astype(int).apply(lambda x: f"外資5日買超第{x}名")
    txt_yoy = fmt(df_day['yoy_pct'], "營收年增{:.1f}%")
    txt_acc_yoy = fmt(df_day['yoy_accumulated_pct'], "累計年增{:.2f}%")
    
    # 🔥 連續天數動態化
    txt_days_ma20 = df_day['days_above_ma20'].fillna(0).astype(int).apply(lambda x: f"連{x}日站月線")
    txt_days_ma60 = df_day['days_above_ma60'].fillna(0).astype(int).apply(lambda x: f"連{x}日站季線")
    txt_w_red = df_day['w_red_streak'].fillna(0).astype(int).apply(lambda x: f"🔥週K連{x}紅")
    txt_rev_streak = df_day['yoy_streak'].fillna(0).astype(int).apply(lambda x: f"營收連{x}月成長")
    txt_f_buy = df_day['f_buy_streak'].fillna(0).astype(int).apply(lambda x: f"外資連買{x}天")

    # --- 策略清單 ---
    strategies = [
        # 股價 vs 均線
        (df_day['bias_ma5'] > 1, txt_bias_w_1),
        (df_day['bias_ma5'] > 5, txt_bias_w_5),
        (df_day['bias_ma20'] > 5, txt_bias_m_5),
        (df_day['close'] > df_day['MA5'], txt_bias_w),
        (df_day['close'] > df_day['MA20'], txt_bias_m),
        (df_day['close'] > df_day['MA60'], txt_bias_q),
        
        # 價格型態
        ((df_day['close'] - df_day['open']) / df_day['open'] > 0.03, "盤中長紅>3%"),
        (df_day['close'] >= df_day['high_3d'], "創3日新高"),
        (df_day['pct_change'] > 3, txt_pct_1),
        (df_day['pct_change_3d'] > 10, txt_pct_3),
        (df_day['pct_change_5d'] > 15, txt_pct_5),
        (df_day['pct_change'] > 9.5, "🔥今日漲停"),
        ((df_day['pct_change'] > 3) & (df_day['volume'] >= df_day['vol_max_3d']), "漲>3%且量創3日高"),
        (df_day['rank_pct_1d'] <= 10, txt_rank_1d),
        (df_day['rank_pct_5d'] <= 67, txt_rank_5d),

        # 趨勢 (🔥 改用動態文字)
        (df_day['w_red_streak'] >= 2, txt_w_red), # 門檻放寬至2以顯示更多
        (df_day['days_above_ma20'] >= 47, txt_days_ma20),
        (df_day['days_above_ma60'] >= 177, txt_days_ma60),
        ((df_day['close']>df_day['MA5'])&(df_day['MA5']>df_day['MA10'])&(df_day['MA10']>df_day['MA20']), "短線多頭排列"),
        ((df_day['close']>df_day['MA10'])&(df_day['MA10']>df_day['MA20'])&(df_day['MA20']>df_day['MA60']), "長線多頭排列"),

        # 成交量
        (df_day['vol_bias_ma5'] > 31, txt_vol_5),
        (df_day['vol_bias_ma10'] > 30, txt_vol_10),
        (df_day['vol_bias_ma20'] > 40, txt_vol_20),
        (df_day['volume'] > df_day['Vol_MA5'], "量大於5日均量"),
        (df_day['volume'] > df_day['prev_volume'] * 1.5, txt_vol_double),

        # 技術指標
        (df_day['K'] > df_day['K'].shift(1), "K值向上"),
        (df_day['K'] > df_day['D'], "K>D多頭"),
        ((df_day['K'] > df_day['D']) & (df_day['K'].shift(1) < df_day['D'].shift(1)), "KD金叉"),
        ((df_day['MACD_OSC'] > 0) & (df_day['MACD_OSC'] > df_day['MACD_OSC'].shift(1)), "MACD紅柱延長"),
        ((df_day['MACD_OSC'] < 0) & (df_day['MACD_OSC'] > df_day['MACD_OSC'].shift(1)), "MACD綠柱縮短"),
        ((df_day['MACD_OSC'] > 0) & (df_day['MACD_OSC'].shift(1) < 0), "MACD轉紅"),

        # 籌碼與營收 (🔥 改用動態文字)
        (df_day['f_buy_streak'] >= 2, txt_f_buy), # 門檻放寬
        (df_day['rank_f_1d'] <= 12, txt_f_rank_1d),
        (df_day['rank_f_5d'] <= 22, txt_f_rank_5d),
        (df_day['rev_is_ath'], "🔥營收創歷史新高"),
        (df_day['yoy_streak'] >= 3, txt_rev_streak), # 門檻放寬
        (df_day['yoy_accumulated_pct'] > 20, txt_acc_yoy),
    ]

    for mask, txt in strategies:
        score += mask.astype(int)
        if mask.any():
            if isinstance(txt, pd.Series):
                vals = txt[mask]
                df_day.loc[mask, 'signals'] = df_day.loc[mask].apply(
                    lambda row: row['signals'] + [vals[row.name]] if row.name in vals.index else row['signals'], 
                    axis=1
                )
            else:
                df_day.loc[mask, 'signals'] = df_day.loc[mask, 'signals'].apply(lambda x: x + [txt])

    df_day['Total_Score'] = score
    df_day['Signal_List'] = df_day['signals'].apply(lambda x: ", ".join(x))

    res = df_day[df_day['Total_Score'] >= min_sc].copy()
    if sort_opt == "總分": res = res.sort_values(['Total_Score','symbol'], ascending=[False,True])
    elif sort_opt == "漲跌幅": res = res.sort_values(['pct_change','symbol'], ascending=[False,True])
    elif sort_opt == "外資買超": res = res.sort_values(['foreign_net','symbol'], ascending=[False,True])
    elif sort_opt == "營收YOY": res = res.sort_values(['yoy_pct','symbol'], ascending=[False,True])

    disp = res[['symbol','name','close','pct_change','Total_Score','Signal_List']].reset_index(drop=True)
    syms = disp['symbol'].tolist()

    st.success(f"篩選出 {len(syms)} 檔 (門檻:{min_sc})")
    
    evt = st.dataframe(disp.style.format({"pct_change":"{:.2f}%","close":"{:.2f}"}).background_gradient(subset=['Total_Score'], cmap='Reds'),
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
    
    st.markdown(f"### {cur_sym} {cur_row['name']} | 分數: {cur_row['Total_Score']}")
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
