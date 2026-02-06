import streamlit as st
import pandas as pd
import sqlalchemy
import os
import plotly.graph_objects as go  # 【新增】引入 Plotly 畫 K 線
from sqlalchemy import create_engine
from datetime import datetime, timedelta

# ===========================
# 1. 頁面設定與 CSS
# ===========================
st.set_page_config(
    page_title="均線糾結選股神器",
    page_icon="📈",
    layout="wide"
)

st.markdown("""
<style>
    .stDataFrame {font-size: 14px;}
    div[data-testid="stMetricValue"] {font-size: 24px;}
    div.stButton > button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# ===========================
# 2. 資料庫連線
# ===========================
@st.cache_resource
def get_db_engine():
    db_url = None
    if "SUPABASE_DB_URL" in os.environ:
        db_url = os.environ["SUPABASE_DB_URL"]
    
    if not db_url:
        try:
            if st.secrets is not None:
                db_url = st.secrets.get("SUPABASE_DB_URL") or \
                         st.secrets.get("database", {}).get("url")
        except: pass

    if not db_url:
        st.error("❌ 找不到資料庫連線字串！請設定環境變數 SUPABASE_DB_URL 或建立 .streamlit/secrets.toml")
        st.stop()
        
    return create_engine(db_url)

# ===========================
# 3. 資料撈取與計算
# ===========================
@st.cache_data(ttl=3600)
def load_and_process_data(lookback_days, min_volume, min_price, squeeze_threshold):
    engine = get_db_engine()
    
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    
    # 【注意】必須確保 select 出來的欄位包含 open, high, low, close
    query_prices = f"""
        SELECT date, symbol, close, volume, open, high, low
        FROM stock_prices
        WHERE date >= '{start_date}'
    """
    query_info = "SELECT symbol, name, industry FROM stock_info"
    
    try:
        with engine.connect() as conn:
            df_prices = pd.read_sql(query_prices, conn)
            df_info = pd.read_sql(query_info, conn)
    except Exception as e:
        st.error(f"資料庫讀取失敗: {e}")
        return pd.DataFrame(), pd.DataFrame()
    
    if df_prices.empty:
        return pd.DataFrame(), pd.DataFrame()

    df_prices['date'] = pd.to_datetime(df_prices['date'])
    df_prices = df_prices.sort_values(['symbol', 'date'])
    
    results = []
    unique_symbols = df_prices['symbol'].unique()
    progress_bar = st.progress(0, text="正在分析均線型態...")
    total_symbols = len(unique_symbols)
    
    for idx, (symbol, df) in enumerate(df_prices.groupby('symbol')):
        if idx % (total_symbols // 10 + 1) == 0:
            progress_bar.progress(idx / total_symbols, text=f"正在分析: {symbol}")

        if len(df) < 120: continue
        
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        df['ma120'] = df['close'].rolling(120).mean()
        
        last = df.iloc[-1]
        
        if last['volume'] < min_volume or last['close'] < min_price:
            continue
            
        if not (last['ma60'] > last['ma120'] and last['close'] > last['ma60']):
            continue
            
        short_mas = df[['ma5', 'ma10', 'ma20']]
        df['max_ma'] = short_mas.max(axis=1)
        df['min_ma'] = short_mas.min(axis=1)
        
        df['squeeze_pct'] = (df['max_ma'] - df['min_ma']) / df['min_ma']
        df['is_tight'] = df['squeeze_pct'] <= squeeze_threshold
        
        last = df.iloc[-1]
        
        if not last['is_tight']:
            continue
            
        consolidation_days = 0
        for i in range(len(df)-1, -1, -1):
            if df.iloc[i]['is_tight']:
                consolidation_days += 1
            else:
                break
        
        if consolidation_days >= 3:
            results.append({
                'symbol': symbol,
                'close': last['close'],
                'volume': int(last['volume']),
                'ma5': round(last['ma5'], 2),
                'ma20': round(last['ma20'], 2),
                'ma60': round(last['ma60'], 2),
                'squeeze_pct': round(last['squeeze_pct'] * 100, 2),
                'days': consolidation_days,
                'last_date': last['date']
            })
            
    progress_bar.empty()
    
    if not results:
        return pd.DataFrame(), df_prices
        
    df_res = pd.DataFrame(results)
    df_final = pd.merge(df_res, df_info, on='symbol', how='left')
    
    if 'name' in df_final.columns:
        df_final['name'] = df_final['name'].fillna('未知名稱')
    else:
        df_final['name'] = '未知名稱'

    # 【修改 1】更換為玩股網連結
    def make_link(symbol):
        code = symbol.replace('.TW', '').replace('.TWO', '')
        return f"https://www.wantgoo.com/stock/{code}"

    if not df_final.empty:
        df_final['link'] = df_final['symbol'].apply(make_link)
        return df_final.sort_values('days', ascending=False), df_prices
    
    return pd.DataFrame(), df_prices

# ===========================
# 4. Streamlit UI 佈局
# ===========================

st.sidebar.header("⚙️ 篩選參數設定")

st.sidebar.subheader("1. 均線糾結定義")
threshold_percent = st.sidebar.slider(
    "均線差距 (5/10/20 MA) 小於多少 % ?", 
    min_value=1.0, max_value=10.0, value=3.5, step=0.5
)
squeeze_threshold = threshold_percent / 100.0

st.sidebar.subheader("2. 基本面濾網")

min_vol = st.sidebar.slider(
    "最小成交量 (股)", 
    min_value=0, 
    max_value=5000000, 
    value=500000, 
    step=50000
)

min_price = st.sidebar.slider(
    "最低股價 (元)", 
    min_value=0, 
    max_value=1000, 
    value=10, 
    step=5
)

st.sidebar.divider()
st.sidebar.caption("策略邏輯:\n1. 60MA > 120MA (長線多頭)\n2. 5/10/20MA 差距 < N% (短線糾結)")

# --- 主畫面 ---
st.title("📈 均線糾結 + 長線多頭 選股器")

with st.spinner("正在從資料庫撈取並運算..."):
    df_result, df_raw_prices = load_and_process_data(
        lookback_days=400, 
        min_volume=min_vol, 
        min_price=min_price, 
        squeeze_threshold=squeeze_threshold
    )

if df_result.empty:
    st.warning("⚠️ 在此條件下未找到符合的股票，請嘗試放寬篩選條件。")
else:
    # --- 初始化 Session State ---
    if 'selected_index' not in st.session_state:
        st.session_state.selected_index = 0
    
    if st.session_state.selected_index >= len(df_result):
        st.session_state.selected_index = 0

    col1, col2, col3 = st.columns(3)
    col1.metric("符合檔數", f"{len(df_result)} 檔")
    col2.metric("平均整理天數", f"{int(df_result['days'].mean())} 天")
    best_stock = df_result.iloc[0]
    col3.metric("最長整理", f"{best_stock['days']} 天 ({best_stock['name']})")

    st.subheader("📋 選股清單 (點選行可直接切換 K 線)")
    
    selection_event = st.dataframe(
        df_result,
        column_config={
            "symbol": "代號",
            "name": "名稱",
            "industry": "產業",
            "close": st.column_config.NumberColumn("收盤價", format="$%.2f"),
            "days": st.column_config.NumberColumn("連續糾結天數", help="均線符合糾結定義的連續天數"),
            "squeeze_pct": st.column_config.NumberColumn("糾結度 %", format="%.2f%%"),
            "volume": st.column_config.NumberColumn("成交量", format="%d"),
            "link": st.column_config.LinkColumn("玩股網", display_text="查看詳情"), # 修改顯示文字
            "last_date": st.column_config.DateColumn("資料日期", format="YYYY-MM-DD"),
        },
        column_order=["symbol", "name", "days", "squeeze_pct", "close", "industry", "link", "volume", "ma60"],
        hide_index=True,
        width="stretch", 
        height=400,
        on_select="rerun",
        selection_mode="single-row" 
    )

    if selection_event.selection.rows:
        clicked_index = selection_event.selection.rows[0]
        if clicked_index != st.session_state.selected_index:
            st.session_state.selected_index = clicked_index
            st.rerun()

    st.divider()
    st.subheader("📊 技術線圖 (K線 + 均線)")
    
    # 選項清單
    options_list = (df_result['symbol'].astype(str) + " - " + df_result['name'].astype(str)).tolist()

    # 按鈕區塊
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("⏮️ 最前"):
        st.session_state.selected_index = 0
        st.rerun()
    if c2.button("⬅️ 上一個"):
        st.session_state.selected_index = max(0, st.session_state.selected_index - 1)
        st.rerun()
    if c3.button("➡️ 下一個"):
        st.session_state.selected_index = min(len(options_list) - 1, st.session_state.selected_index + 1)
        st.rerun()
    if c4.button("⏭️ 最後"):
        st.session_state.selected_index = len(options_list) - 1
        st.rerun()

    selected_symbol_str = st.selectbox(
        "選擇股票:", 
        options=options_list,
        index=st.session_state.selected_index,
        key="stock_selector"
    )
    
    current_index_in_list = options_list.index(selected_symbol_str)
    if st.session_state.selected_index != current_index_in_list:
        st.session_state.selected_index = current_index_in_list
        st.rerun()

    # --- 【修改 2】改用 Plotly 繪製互動式 K 線圖 ---
    if selected_symbol_str:
        symbol_only = str(selected_symbol_str).split(" - ")[0]
        
        chart_data = df_raw_prices[df_raw_prices['symbol'] == symbol_only].copy()
        
        if not chart_data.empty:
            chart_data = chart_data.tail(120) # 顯示最近 120 天
            
            # 計算均線 (繪圖用)
            chart_data['MA5'] = chart_data['close'].rolling(5).mean()
            chart_data['MA20'] = chart_data['close'].rolling(20).mean()
            chart_data['MA60'] = chart_data['close'].rolling(60).mean()

            # 建立 Plotly 圖表物件
            fig = go.Figure()

            # 1. 畫 K 棒 (Candlestick)
            fig.add_trace(go.Candlestick(
                x=chart_data['date'],
                open=chart_data['open'],
                high=chart_data['high'],
                low=chart_data['low'],
                close=chart_data['close'],
                # 設定台灣股市顏色：紅漲(increasing)、綠跌(decreasing)
                increasing_line_color='#ef5350', # 紅色
                decreasing_line_color='#26a69a', # 綠色
                name='K線'
            ))

            # 2. 畫均線 (MA)
            fig.add_trace(go.Scatter(x=chart_data['date'], y=chart_data['MA5'], 
                                     line=dict(color='orange', width=1), name='MA5 (週)'))
            fig.add_trace(go.Scatter(x=chart_data['date'], y=chart_data['MA20'], 
                                     line=dict(color='purple', width=1), name='MA20 (月)'))
            fig.add_trace(go.Scatter(x=chart_data['date'], y=chart_data['MA60'], 
                                     line=dict(color='blue', width=1), name='MA60 (季)'))

            # 3. 設定圖表版面 (Layout)
            fig.update_layout(
                title=f"{selected_symbol_str} - 日 K 線圖",
                xaxis_title="日期",
                yaxis_title="股價",
                xaxis_rangeslider_visible=False, # 隱藏下方預設的範圍滑桿，節省空間
                height=500,
                margin=dict(l=20, r=20, t=40, b=20),
                legend=dict(
                    orientation="h", # 圖例水平排列
                    yanchor="bottom", y=1.02,
                    xanchor="right", x=1
                )
            )

            # 顯示圖表
            st.plotly_chart(fig, use_container_width=True)
