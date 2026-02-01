import streamlit as st
import pandas as pd
import sqlalchemy
import os
import glob
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import subprocess
import uuid

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

WATCHLIST_DIR = "watchlists"
OLD_WATCHLIST_FILE = "watchlist.txt"

# ===========================
# 2. 檔案系統與 Git 管理
# ===========================
def init_filesystem():
    if not os.path.exists(WATCHLIST_DIR):
        os.makedirs(WATCHLIST_DIR)
    
    if os.path.exists(OLD_WATCHLIST_FILE):
        try:
            try:
                df = pd.read_csv(OLD_WATCHLIST_FILE, dtype=str)
                if 'symbol' not in df.columns:
                    df = pd.read_csv(OLD_WATCHLIST_FILE, header=None, names=['symbol'], dtype=str)
                    df['added_date'] = datetime.now().strftime('%Y-%m-%d')
            except:
                df = pd.DataFrame(columns=['symbol', 'added_date'])
            
            df['symbol'] = df['symbol'].str.strip()
            df.to_csv(os.path.join(WATCHLIST_DIR, "預設清單.csv"), index=False)
            os.rename(OLD_WATCHLIST_FILE, OLD_WATCHLIST_FILE + ".bak")
        except:
            pass

    if not glob.glob(os.path.join(WATCHLIST_DIR, "*.csv")):
        df = pd.DataFrame(columns=['symbol', 'added_date'])
        df.to_csv(os.path.join(WATCHLIST_DIR, "預設清單.csv"), index=False)

def get_all_lists():
    files = glob.glob(os.path.join(WATCHLIST_DIR, "*.csv"))
    names = [os.path.splitext(os.path.basename(f))[0] for f in files]
    return sorted(names)

def get_list_data(list_name):
    file_path = os.path.join(WATCHLIST_DIR, f"{list_name}.csv")
    if not os.path.exists(file_path):
        return pd.DataFrame(columns=['symbol', 'added_date'])
    try:
        df = pd.read_csv(file_path, dtype=str)
        if 'symbol' not in df.columns: return pd.DataFrame(columns=['symbol', 'added_date'])
        df['symbol'] = df['symbol'].str.strip()
        return df
    except:
        return pd.DataFrame(columns=['symbol', 'added_date'])

def save_list_data(list_name, df):
    file_path = os.path.join(WATCHLIST_DIR, f"{list_name}.csv")
    df['symbol'] = df['symbol'].astype(str).str.strip()
    df = df.drop_duplicates(subset=['symbol'], keep='last')
    df = df.sort_values('symbol')
    df.to_csv(file_path, index=False)
    return file_path

def create_list(new_name):
    if len(get_all_lists()) >= 20: return False, "清單數量達上限"
    file_path = os.path.join(WATCHLIST_DIR, f"{new_name}.csv")
    if os.path.exists(file_path): return False, "名稱已存在"
    pd.DataFrame(columns=['symbol', 'added_date']).to_csv(file_path, index=False)
    return True, "建立成功"

def rename_list(old_name, new_name):
    old_path = os.path.join(WATCHLIST_DIR, f"{old_name}.csv")
    new_path = os.path.join(WATCHLIST_DIR, f"{new_name}.csv")
    if os.path.exists(new_path): return False, "新名稱已存在"
    os.rename(old_path, new_path)
    return True, "改名成功"

def delete_list(list_name):
    file_path = os.path.join(WATCHLIST_DIR, f"{list_name}.csv")
    if os.path.exists(file_path):
        os.remove(file_path)
        return True, "刪除成功"
    return False, "檔案不存在"

def git_commit_and_push(file_path, action_msg):
    try:
        subprocess.run(["git", "add", file_path], check=True)
        subprocess.run(["git", "commit", "-m", f"Watchlist: {action_msg}"], check=True)
        subprocess.run(["git", "push"], check=True)
        return True, "Git 同步成功"
    except Exception as e:
        return False, f"Git 錯誤: {e}"

init_filesystem()

# ===========================
# 3. 資料讀取 (分段載入)
# ===========================
@st.cache_data(ttl=3600)
def get_all_symbols_fast():
    try:
        with engine.connect() as conn:
            df = pd.read_sql("SELECT symbol FROM stock_info", conn)
        return set(df['symbol'].astype(str).str.strip().unique())
    except:
        return set()

@st.cache_data(ttl=3600)
def load_and_process_data():
    query = """
    SELECT sp.date, sp.symbol, sp.open, sp.high, sp.low, sp.close, sp.volume, 
           si.name, si.industry
    FROM stock_prices sp
    JOIN stock_info si ON sp.symbol = si.symbol
    WHERE sp.date >= current_date - INTERVAL '400 days' 
    ORDER BY sp.symbol, sp.date
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    
    df['symbol'] = df['symbol'].astype(str).str.strip()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['symbol', 'date'])
    grouped = df.groupby('symbol')
    
    df['MA5'] = grouped['close'].transform(lambda x: x.rolling(5).mean())
    df['MA10'] = grouped['close'].transform(lambda x: x.rolling(10).mean())
    df['MA20'] = grouped['close'].transform(lambda x: x.rolling(20).mean())
    df['MA60'] = grouped['close'].transform(lambda x: x.rolling(60).mean())
    
    df['Vol_MA5'] = grouped['volume'].transform(lambda x: x.rolling(5).mean())
    df['Vol_MA10'] = grouped['volume'].transform(lambda x: x.rolling(10).mean())
    df['Vol_MA20'] = grouped['volume'].transform(lambda x: x.rolling(20).mean())
    
    df['prev_close'] = grouped['close'].shift(1)
    df['prev_volume'] = grouped['volume'].shift(1)
    df['pct_change'] = (df['close'] - df['prev_close']) / df['prev_close'] * 100
    df['pct_change_3d'] = grouped['close'].pct_change(3) * 100
    df['pct_change_5d'] = grouped['close'].pct_change(5) * 100
    
    df['high_3d'] = grouped['high'].transform(lambda x: x.rolling(3).max())
    df['vol_max_3d'] = grouped['volume'].transform(lambda x: x.rolling(3).max())
    
    df['above_ma20'] = (df['close'] > df['MA20']).astype(int)
    df['days_above_ma20'] = grouped['above_ma20'].transform(lambda x: x.rolling(47).sum())
    df['above_ma60'] = (df['close'] > df['MA60']).astype(int)
    df['days_above_ma60'] = grouped['above_ma60'].transform(lambda x: x.rolling(177).sum())
    
    df['vol_ratio'] = df['volume'] / df['Vol_MA5']
    return df

# ===========================
# 4. 指標與繪圖
# ===========================
def resolve_stock_symbol(input_code, valid_symbols_set):
    code = input_code.strip().upper()
    if code in valid_symbols_set: return code
    if f"{code}.TW" in valid_symbols_set: return f"{code}.TW"
    if f"{code}.TWO" in valid_symbols_set: return f"{code}.TWO"
    return None

def calculate_advanced_indicators_and_score(df_stock, is_single_stock=False):
    df = df_stock.copy()
    low_min = df['low'].rolling(9).min()
    high_max = df['high'].rolling(9).max()
    df['RSV'] = (df['close'] - low_min) / (high_max - low_min) * 100
    df['RSV'] = df['RSV'].fillna(50)
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    exp12 = df['close'].ewm(span=12, adjust=False).mean()
    exp26 = df['close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_OSC'] = df['DIF'] - df['MACD']
    prev_high = df['high'].shift(1)
    prev_low = df['low'].shift(1)
    prev_close = df['close'].shift(1)
    df['CDP'] = (prev_high + prev_low + 2 * prev_close) / 4
    rng = prev_high - prev_low 
    df['AH'] = df['CDP'] + rng
    df['NH'] = 2 * df['CDP'] - prev_low
    df['NL'] = 2 * df['CDP'] - prev_high
    df['AL'] = df['CDP'] - rng
    df['Sig_KD_Gold'] = (df['K'] > df['D']) & (df['K'].shift(1) < df['D'].shift(1))
    df['Sig_Vol_Attack'] = (df['volume'] > df['prev_volume']) & (df['vol_ratio'] > 1.2)
    df['Sig_MACD_Bull'] = (df['MACD_OSC'] > 0) & (df['MACD_OSC'].shift(1) < 0)
    df['Sig_MA_Bull'] = (df['MA5'] > df['MA10']) & (df['MA10'] > df['MA20'])
    return df

def plot_stock_kline(df_stock, symbol, name, active_signals_text, show_vol_profile=False):
    df_plot = df_stock.tail(200).copy()
    df_plot = calculate_advanced_indicators_and_score(df_plot, is_single_stock=True)
    df_plot = df_plot.tail(130)
    df_plot['date_str'] = df_plot['date'].dt.strftime('%Y-%m-%d')
    score_val = active_signals_text.count(',') + 1 if active_signals_text else 0
    
    fig = make_subplots(
        rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.01,
        row_heights=[0.45, 0.1, 0.1, 0.1, 0.15],
        subplot_titles=(f"{symbol} {name} (評分:{score_val}分)", "成交量", "KD", "MACD", "重點訊號"),
        specs=[[{"secondary_y": False}], [{}], [{}], [{}], [{}]] 
    )

    layout_xaxis5 = dict(visible=False)
    if show_vol_profile:
        price_bins = 80 
        hist_values, bin_edges = np.histogram(df_plot['close'], bins=price_bins, weights=df_plot['volume'])
        bin_mids = (bin_edges[:-1] + bin_edges[1:]) / 2
        fig.add_trace(go.Bar(x=hist_values, y=bin_mids, orientation='h', name='籌碼分布', marker_color='rgba(100, 100, 100, 0.15)', hoverinfo='none', xaxis='x5'), row=1, col=1)
        layout_xaxis5 = dict(overlaying='x', side='top', showgrid=False, visible=False, range=[0, max(hist_values) * 1.2])

    fig.add_trace(go.Candlestick(x=df_plot['date_str'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'], name='K線', increasing_line_color='red', decreasing_line_color='green'), row=1, col=1)
    
    colors_ma = {'MA5': '#FFA500', 'MA10': '#00FFFF', 'MA20': '#BA55D3', 'MA60': '#4169E1'}
    for ma in ['MA5', 'MA10', 'MA20', 'MA60']:
        if ma in df_plot.columns:
            fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot[ma], mode='lines', name=ma, line=dict(color=colors_ma[ma], width=1.5)), row=1, col=1)

    colors_vol = ['red' if c >= o else 'green' for c, o in zip(df_plot['close'], df_plot['open'])]
    fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['volume'], name='成交量', marker_color=colors_vol), row=2, col=1)

    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['K'], name='K', line=dict(color='orange', width=1)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['D'], name='D', line=dict(color='cyan', width=1)), row=3, col=1)
    
    osc_colors = ['red' if v >= 0 else 'green' for v in df_plot['MACD_OSC']]
    fig.add_trace(go.Bar(x=df_plot['date_str'], y=df_plot['MACD_OSC'], name='OSC', marker_color=osc_colors), row=4, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date_str'], y=df_plot['DIF'], name='DIF', line=dict(color='orange', width=1)), row=4, col=1)

    signals_map = [('KD金叉', 'Sig_KD_Gold', 'diamond', 'purple'), ('量能攻擊', 'Sig_Vol_Attack', 'triangle-up', 'gold'), ('MACD翻紅', 'Sig_MACD_Bull', 'square', 'blue'), ('均線多頭', 'Sig_MA_Bull', 'circle', 'red')]
    for idx, (label, col_name, symbol, color) in enumerate(signals_map):
        if col_name in df_plot.columns:
            sig_dates = df_plot[df_plot[col_name] == True]['date_str']
            fig.add_trace(go.Scatter(x=sig_dates, y=[idx]*len(sig_dates), mode='markers', name=label, marker=dict(symbol=symbol, size=10, color=color), hovertemplate=label), row=5, col=1)

    force_reset_key = str(uuid.uuid4())
    layout_update = dict(height=950, xaxis_rangeslider_visible=False, showlegend=False, margin=dict(l=20, r=20, t=30, b=20), bargap=0.05, plot_bgcolor='white', paper_bgcolor='white', xaxis5=layout_xaxis5, uirevision=force_reset_key)
    fig.update_layout(**layout_update)
    common_axis = dict(type='category', showgrid=False, zeroline=False, showline=True, linecolor='black', mirror=True)
    fig.update_yaxes(autorange=True, fixedrange=False)
    for r in [1,2,3,4]: fig.update_xaxes(**common_axis, row=r, col=1)
    fig.update_xaxes(dtick=10, **common_axis, row=5, col=1)
    fig.update_yaxes(tickvals=[0,1,2,3], ticktext=['KD','量攻','MACD','均線'], showgrid=False, linecolor='black', mirror=True, row=5, col=1)
    fig.update_yaxes(showgrid=False, showline=True, linecolor='black', mirror=True, row=1, col=1)
    return fig

# ===========================
# 5. 主程式 UI
# ===========================
st.title("自選股戰情室")
st.markdown("---")

for key in ['ticker_index', 'last_selected_rows', 'last_viewed_symbol', 'last_sort_option', 'query_mode_symbol', 'symbol_input']:
    if key not in st.session_state: st.session_state[key] = None
    if key == 'symbol_input' and st.session_state[key] is None:
        st.session_state.symbol_input = ""

# --- 0. 載入智慧搜尋所需的代碼清單 (極速) ---
valid_symbols_set = get_all_symbols_fast()

# --- 側邊欄 ---
st.sidebar.header("📝 股票管理")

all_lists = get_all_lists()
if not all_lists:
    init_filesystem()
    all_lists = get_all_lists()
selected_list = st.sidebar.selectbox("📂 選擇清單", all_lists, index=0)

watchlist_df = get_list_data(selected_list)
current_watchlist_symbols = watchlist_df['symbol'].tolist()

# 🔥 優化：將清單表格移到上方，並加入點選連動邏輯
with st.sidebar.expander(f"📋 查看清單 ({len(current_watchlist_symbols)}檔)", expanded=True):
    # 使用 on_select="rerun" 來捕獲點選事件
    event = st.dataframe(
        watchlist_df, 
        hide_index=True, 
        on_select="rerun", 
        selection_mode="single-row",
        use_container_width=True
    )
    # 如果有選取，更新 session state 中的 symbol_input
    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        if idx < len(watchlist_df):
            st.session_state.symbol_input = watchlist_df.iloc[idx]['symbol']

# 股票操作區
col_input, col_action = st.sidebar.columns([1.5, 2])

# 🔥 綁定 key="symbol_input" 實現雙向綁定 (輸入框 <-> 表格點選)
input_code = col_input.text_input("股票代號", key="symbol_input", placeholder="如: 2330").strip()

with col_action:
    c_add, c_del, c_qry = st.columns(3)
    
    if c_add.button("新增"):
        st.session_state.query_mode_symbol = None
        if input_code:
            resolved_code = resolve_stock_symbol(input_code, valid_symbols_set)
            if resolved_code:
                if resolved_code not in current_watchlist_symbols:
                    new_row = {'symbol': resolved_code, 'added_date': datetime.now().strftime('%Y-%m-%d')}
                    watchlist_df = pd.concat([watchlist_df, pd.DataFrame([new_row])], ignore_index=True)
                    file_path = save_list_data(selected_list, watchlist_df)
                    success, msg = git_commit_and_push(file_path, f"Add {resolved_code} to {selected_list}")
                    if success:
                        st.sidebar.success(f"✅")
                        st.rerun()
                    else:
                        st.sidebar.error(msg)
                else:
                    st.sidebar.warning("已在清單")
            else:
                st.sidebar.error(f"❌ 查無: {input_code}")
    
    if c_del.button("刪除"):
        st.session_state.query_mode_symbol = None
        if input_code:
            resolved_code = resolve_stock_symbol(input_code, valid_symbols_set)
            if not resolved_code: resolved_code = input_code
            if resolved_code in current_watchlist_symbols:
                watchlist_df = watchlist_df[watchlist_df['symbol'] != resolved_code]
                file_path = save_list_data(selected_list, watchlist_df)
                success, msg = git_commit_and_push(file_path, f"Del {resolved_code} from {selected_list}")
                if success:
                    st.sidebar.success(f"🗑️")
                    st.session_state.symbol_input = "" # 清空輸入框
                    st.rerun()
                else:
                    st.sidebar.error(msg)
            else:
                st.sidebar.warning("不在清單")

    if c_qry.button("查詢"):
        if input_code:
            resolved_code = resolve_stock_symbol(input_code, valid_symbols_set)
            if resolved_code:
                st.session_state.query_mode_symbol = resolved_code
                st.session_state.ticker_index = 0
                st.sidebar.info(f"🔍")
                st.rerun()
            else:
                st.sidebar.error(f"❌ 查無: {input_code}")

# C. 清單管理 Expander
with st.sidebar.expander("⚙️ 清單管理 (新增/改名/刪除)"):
    new_list_name = st.text_input("建立新清單").strip()
    if st.button("建立"):
        if new_list_name:
            success, msg = create_list(new_list_name)
            if success: st.rerun()
            else: st.error(msg)
            
    st.markdown("---")
    rename_new = st.text_input("重新命名目前清單").strip()
    if st.button("改名"):
        if rename_new:
            success, msg = rename_list(selected_list, rename_new)
            if success: st.rerun()
            else: st.error(msg)
            
    st.markdown("---")
    if st.button("⚠️ 刪除此清單", type="primary"):
        if len(all_lists) <= 1:
            st.error("至少保留一個")
        else:
            success, msg = delete_list(selected_list)
            if success: st.rerun()
            else: st.error(msg)

st.sidebar.markdown("---")

# --- 1. 第二階段：載入完整歷史資料 ---
with st.spinner("載入 K 線與運算中..."):
    df_full = load_and_process_data()

available_dates = sorted(df_full['date'].dt.date.unique(), reverse=True)
st.sidebar.header("📅 戰情參數")
selected_date = st.sidebar.selectbox("回測日期", available_dates, 0)
sort_option = st.sidebar.selectbox("🔢 排序方式", ["加入日期 (新→舊)", "強勢總分 (高→低)", "漲跌幅 (高→低)", "量比 (高→低)", "股票代號 (小→大)"])
min_score = st.sidebar.number_input("🔥 最低總分門檻", 0, 50, 0)
st.sidebar.markdown("---")
show_vol_profile = st.sidebar.checkbox("顯示分價量表", False)

# --- 核心運算 ---
target_date_ts = pd.Timestamp(selected_date)
df_day = df_full[df_full['date'] == target_date_ts].copy()

if st.session_state.query_mode_symbol:
    target_symbols = [st.session_state.query_mode_symbol]
    display_title = f"🔍 查詢結果：{st.session_state.query_mode_symbol}"
else:
    if watchlist_df.empty:
        st.warning(f"⚠️ 清單「{selected_list}」是空的。")
        st.stop()
    target_symbols = watchlist_df['symbol'].tolist()
    display_title = f"📊 {selected_list}：共 {len(target_symbols)} 檔"

df_day = df_day[df_day['symbol'].astype(str).isin(target_symbols)]

if not st.session_state.query_mode_symbol:
    df_day = pd.merge(df_day, watchlist_df, on='symbol', how='left')
else:
    df_day['added_date'] = '查詢模式'

df_day['rank_1d'] = df_day['pct_change'].rank(ascending=False)
df_day['rank_5d'] = df_day['pct_change_5d'].rank(ascending=False)

if df_day.empty:
    st.warning(f"⚠️ {selected_date} 查無資料。")
else:
    score = pd.Series(0, index=df_day.index)
    df_day['signals_str'] = [[] for _ in range(len(df_day))]

    bias_ma5 = ((df_day['close'] - df_day['MA5']) / df_day['MA5']) * 100
    bias_ma20 = ((df_day['close'] - df_day['MA20']) / df_day['MA20']) * 100
    bias_ma60 = ((df_day['close'] - df_day['MA60']) / df_day['MA60']) * 100
    vol_diff_ma5 = ((df_day['volume'] - df_day['Vol_MA5']) / df_day['Vol_MA5']) * 100
    vol_diff_prev = ((df_day['volume'] - df_day['prev_volume']) / df_day['prev_volume']) * 100

    strategies = [
        (df_day['close'] > df_day['MA5'], "突破週線 " + bias_ma5.map('{:+.2f}%'.format)),
        (df_day['close'] > df_day['MA20'], "突破月線 " + bias_ma20.map('{:+.2f}%'.format)),
        (df_day['close'] > df_day['MA60'], "突破季線 " + bias_ma60.map('{:+.2f}%'.format)),
        (df_day['pct_change'] > 3, "漲 " + df_day['pct_change'].map('{:+.2f}%'.format)),
        (df_day['volume'] > df_day['Vol_MA5'], "量增 " + vol_diff_ma5.map('{:+.1f}%'.format)),
        (df_day['volume'] > df_day['prev_volume'] * 1.5, "爆量 (月增" + vol_diff_prev.map('{:+.1f}%'.format) + ")"),
        (df_day['days_above_ma20'] >= 47, "連47日站月線"),
        ((df_day['close'] > df_day['MA5']) & (df_day['MA5'] > df_day['MA10']), "短線多頭"),
    ]
    for mask, content in strategies:
        score += mask.astype(int)
        if mask.any():
            if isinstance(content, pd.Series):
                dynamic = content[mask]
                df_day.loc[mask, 'signals_str'] = df_day.loc[mask].apply(lambda row: (row['signals_str'] + [dynamic[row.name]]) if row.name in dynamic.index else row['signals_str'], axis=1)
            else:
                df_day.loc[mask, 'signals_str'] = df_day.loc[mask, 'signals_str'].apply(lambda x: x + [content])

    df_day['Total_Score'] = score
    df_day['Signal_List'] = df_day['signals_str'].apply(lambda x: ", ".join(x))

    if min_score > 0:
        results = df_day[df_day['Total_Score'] >= min_score].copy()
    else:
        results = df_day.copy()

    if not st.session_state.query_mode_symbol:
        if sort_option == "加入日期 (新→舊)":
            results = results.sort_values(by=['added_date', 'symbol'], ascending=[False, True])
        elif sort_option == "強勢總分 (高→低)":
            results = results.sort_values(by=['Total_Score', 'pct_change', 'symbol'], ascending=[False, False, True])
        elif sort_option == "漲跌幅 (高→低)":
            results = results.sort_values(by=['pct_change', 'symbol'], ascending=[False, True])
        elif sort_option == "量比 (高→低)":
            results = results.sort_values(by=['vol_ratio', 'symbol'], ascending=[False, True])
        else:
            results = results.sort_values(by='symbol', ascending=True)

    display_df = results[['symbol', 'name', 'added_date', 'industry', 'close', 'pct_change', 'Total_Score', 'Signal_List']].reset_index(drop=True)
    symbol_list = display_df['symbol'].tolist()

    if st.session_state.last_sort_option != sort_option:
        if st.session_state.last_viewed_symbol in symbol_list:
            st.session_state.ticker_index = symbol_list.index(st.session_state.last_viewed_symbol)
        else:
            st.session_state.ticker_index = 0
        st.session_state.last_sort_option = sort_option

    if st.session_state.query_mode_symbol:
        if st.button("🔙 返回清單", key="btn_back_main"):
            st.session_state.query_mode_symbol = None
            st.rerun()
        st.success(f"{display_title}")
    else:
        st.success(f"{display_title} (篩選後剩餘 {len(symbol_list)} 檔)")

    event = st.dataframe(
        display_df.style.format({"pct_change": "{:.2f}%", "close": "{:.2f}", "Total_Score": "{:.0f}"}).background_gradient(subset=['Total_Score'], cmap='Reds'),
        on_select="rerun", selection_mode="single-row", use_container_width=True,
        column_config={"symbol": "代號", "name": "名稱", "added_date": "📅 加入", "Total_Score": "🔥 分數", "Signal_List": st.column_config.TextColumn("訊號", width="large")}
    )

    if event.selection.rows and event.selection.rows != st.session_state.last_selected_rows:
        st.session_state.ticker_index = event.selection.rows[0]
        st.session_state.last_selected_rows = event.selection.rows
    
    if not symbol_list:
        st.warning("沒有符合篩選條件的股票。")
    else:
        if st.session_state.ticker_index >= len(symbol_list):
            st.session_state.ticker_index = 0

        st.markdown("---")
        
        c1, c2, c_info, c3, c4 = st.columns([1, 1, 4, 1, 1])
        with c1: 
            if st.button("⏮️ 最前"): st.session_state.ticker_index = 0
        with c2: 
            if st.button("⬅️ 上一檔"): st.session_state.ticker_index = (st.session_state.ticker_index - 1) % len(symbol_list)
        with c3: 
            if st.button("下一檔 ➡️"): st.session_state.ticker_index = (st.session_state.ticker_index + 1) % len(symbol_list)
        with c4: 
            if st.button("最後 ⏭️"): st.session_state.ticker_index = len(symbol_list) - 1
                
        current_symbol = symbol_list[st.session_state.ticker_index]
        current_info = results[results['symbol'] == current_symbol].iloc[0]
        st.session_state.last_viewed_symbol = current_symbol
        
        with c_info:
            st.markdown(f"<h3 style='text-align: center; color: #FF4B4B;'>{current_symbol} {current_info['name']} | 分數: {current_info['Total_Score']}</h3>", unsafe_allow_html=True)
            st.info(f"📅 加入: {current_info['added_date']} | ⚡ {current_info['Signal_List']}")

        df_chart_source = df_full[df_full['symbol'] == current_symbol].sort_values('date')
        df_chart_source = df_chart_source[df_chart_source['date'] <= target_date_ts]
        
        if len(df_chart_source) < 30:
            st.error("歷史資料不足，無法繪製完整圖表。")
        else:
            fig = plot_stock_kline(df_chart_source, current_symbol, current_info['name'], current_info['Signal_List'], show_vol_profile)
            chart_key = f"chart_{current_symbol}_{show_vol_profile}_{selected_date}_{st.session_state.ticker_index}_{uuid.uuid4()}"
            st.plotly_chart(fig, use_container_width=True, key=chart_key)
