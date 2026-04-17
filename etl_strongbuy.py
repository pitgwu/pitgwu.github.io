import pandas as pd
import sqlalchemy
from sqlalchemy import text
import os
import numpy as np
from datetime import datetime, timedelta

# ===========================
# 1. 資料庫連線設定
# ===========================
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
if not SUPABASE_DB_URL:
    raise ValueError("❌ 未偵測到 SUPABASE_DB_URL，請設定環境變數。")

engine = sqlalchemy.create_engine(SUPABASE_DB_URL)

# ===========================
# 2. 擷取資料 (Extract)
# ===========================
def extract_data():
    print("📥 [1/4] 開始撈取股價、籌碼與營收資料...")
    
    # --- 1. 撈取基本資訊 (獨立連線) ---
    with engine.connect() as conn:
        df_info = pd.read_sql("SELECT symbol, name, industry FROM stock_info", conn)
        
    # --- 2. 營收查詢區塊 (獨立連線 + 防呆機制) ---
    q_rev = """
    SELECT report_month, symbol, rev_current, yoy_pct, yoy_accumulated_pct 
    FROM monthly_revenue 
    WHERE report_month >= current_date - INTERVAL '400 days'
    """ 
    try:
        with engine.connect() as conn:
            df_rev = pd.read_sql(text(q_rev), conn)
    except Exception as e:
        print(f"⚠️ 營收資料表尚未準備好，暫時 pending (略過營收訊號)。")
        df_rev = pd.DataFrame(columns=['report_month', 'symbol', 'rev_current', 'yoy_pct', 'yoy_accumulated_pct'])

    # --- 3. 股價與籌碼查詢區塊 (獨立連線) ---
    q_price = """
    SELECT sp.date, sp.symbol, sp.open, sp.high, sp.low, sp.close, sp.volume, 
           COALESCE(ii.foreign_net, 0) as foreign_net,
           COALESCE(ii.trust_net, 0) as trust_net,
           COALESCE(ii.dealer_net, 0) as dealer_net
    FROM stock_prices sp
    LEFT JOIN institutional_investors ii ON sp.date = ii.date AND sp.symbol = ii.symbol
    WHERE sp.date >= current_date - INTERVAL '150 days'
    ORDER BY sp.symbol, sp.date
    """
    with engine.connect() as conn:
        df_price = pd.read_sql(text(q_price), conn)

    df = pd.merge(df_price, df_info, on='symbol', how='left')
    return df, df_rev

# ===========================
# 3. 轉換與運算 (Transform)
# ===========================
def transform_data(df, df_rev):
    print("⚙️ [2/4] 計算均線、技術指標與週K...")
    df['symbol'] = df['symbol'].astype(str).str.strip()
    df['date'] = pd.to_datetime(df['date'])
    
    # --- 營收處理 ---
    if not df_rev.empty:
        df_rev['date'] = pd.to_datetime(df_rev['report_month'])
        df_rev = df_rev.sort_values('date')
        g_rev = df_rev.groupby('symbol')
        
        df_rev['rev_max'] = g_rev['rev_current'].transform(lambda x: x.cummax())
        df_rev['rev_is_ath'] = (df_rev['rev_current'] >= df_rev['rev_max']) & (df_rev['rev_current'] > 0)
        df_rev['yoy_pos'] = (df_rev['yoy_pct'] > 0).astype(int)
        df_rev['yoy_streak'] = g_rev['yoy_pos'].transform(lambda x: x.groupby((x != x.shift()).cumsum()).cumsum())
        
        # 🔥 merge_asof 前，確保雙方依 date 排序
        df = df.sort_values('date')
        df = pd.merge_asof(df, df_rev[['date','symbol','rev_is_ath','yoy_streak','yoy_pct','yoy_accumulated_pct']], 
                           on='date', by='symbol', direction='backward')
    else:
        for c in ['rev_is_ath','yoy_streak','yoy_pct','yoy_accumulated_pct']: 
            df[c] = 0

    df['rev_is_ath'] = df['rev_is_ath'].fillna(False)
    df[['yoy_pct','yoy_accumulated_pct']] = df[['yoy_pct','yoy_accumulated_pct']].fillna(0)

    # --- 基本股價與技術指標 ---
    # 🔥 計算前必須強制切換回「股票代號 -> 日期」的排序，否則 shift(1) 會亂掉
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

    # 👇👇👇 [新增這一段] 預先算好量增比 👇👇👇
    df['Vol_Ratio'] = np.where(
        (df['prev_volume'] > 0) & df['prev_volume'].notna(),
        df['volume'] / df['prev_volume'],
        np.nan
    )
    # 👆👆👆 [新增結束] 👆👆👆

    df['pct_change'] = (df['close'] - df['prev_close']) / df['prev_close'] * 100
    df['pct_change_3d'] = g['close'].pct_change(3) * 100
    df['pct_change_5d'] = g['close'].pct_change(5) * 100
    df['high_3d'] = g['high'].transform(lambda x: x.rolling(3).max())
    df['vol_max_3d'] = g['volume'].transform(lambda x: x.rolling(3).max())
    
    low_min = g['low'].transform(lambda x: x.rolling(9).min())
    high_max = g['high'].transform(lambda x: x.rolling(9).max())
    rsv = (df['close'] - low_min) / (high_max - low_min) * 100
    df['K'] = rsv.ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    ema12 = g['close'].transform(lambda x: x.ewm(span=12, adjust=False).mean())
    ema26 = g['close'].transform(lambda x: x.ewm(span=26, adjust=False).mean())
    df['DIF'] = ema12 - ema26
    df['MACD'] = g['DIF'].transform(lambda x: x.ewm(span=9, adjust=False).mean())
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

    # --- 週K運算 ---
    df_w = df.set_index('date').groupby('symbol').resample('W-FRI').agg({'open': 'first', 'close': 'last'}).dropna().reset_index()
    df_w['is_red'] = (df_w['close'] > df_w['open']).astype(int)
    df_w['w_red_streak'] = df_w.groupby('symbol')['is_red'].transform(lambda x: x.groupby((x != x.shift()).cumsum()).cumsum())
    
    # 🔥 merge_asof 前，強制重新依 date 排序
    df = df.sort_values('date')
    df_w = df_w.sort_values('date')
    df = pd.merge_asof(df, df_w[['date','symbol','w_red_streak']], on='date', by='symbol', direction='backward')
    df['w_red_streak'] = df['w_red_streak'].fillna(0)

    # ==========================
    # 🔥 訊號與排名計算 (擷取近 30 天)
    # ==========================
    print("📊 [3/4] 產生動態訊號與排名...")
    cutoff_date = df['date'].max() - pd.Timedelta(days=30)
    df_recent = df[df['date'] >= cutoff_date].copy()

    # 跨股排名 (排除小於等於0的雜訊)
    df_recent['rank_pct_1d'] = df_recent.groupby('date')['pct_change'].rank(ascending=False, method='min')
    df_recent['rank_pct_5d'] = df_recent.groupby('date')['pct_change_5d'].rank(ascending=False, method='min')
    
    f_net_pos = df_recent['foreign_net'].where(df_recent['foreign_net'] > 0)
    f_sum5_pos = df_recent['f_sum_5d'].where(df_recent['f_sum_5d'] > 0)
    df_recent['rank_f_1d'] = f_net_pos.groupby(df_recent['date']).rank(ascending=False, method='min')
    df_recent['rank_f_5d'] = f_sum5_pos.groupby(df_recent['date']).rank(ascending=False, method='min')

    df_recent['signals_str'] = [[] for _ in range(len(df_recent))]
    score = pd.Series(0, index=df_recent.index)

    def fmt(val, template): 
        return val.fillna(0).apply(lambda x: template.format(x))
    def fmt_r(val, template): 
        return val.apply(lambda x: template.format(int(x)) if pd.notna(x) else "")

    strategies = [
        (df_recent['bias_ma5'] > 1, fmt(df_recent['bias_ma5'], "突破週線{:.2f}%")),
        (df_recent['bias_ma5'] > 5, fmt(df_recent['bias_ma5'], "正乖離週線{:.2f}%")),
        (df_recent['bias_ma20'] > 5, fmt(df_recent['bias_ma20'], "正乖離月線{:.2f}%")),
        (df_recent['close'] > df_recent['MA5'], fmt(df_recent['bias_ma5'], "突破週線{:.2f}%")),
        (df_recent['close'] > df_recent['MA20'], fmt(df_recent['bias_ma20'], "突破月線{:.2f}%")),
        (df_recent['close'] > df_recent['MA60'], fmt(df_recent['bias_ma60'], "突破季線{:.2f}%")),
        (((df_recent['close'] - df_recent['open']) / df_recent['open']) > 0.03, "盤中長紅>3%"),
        (df_recent['close'] >= df_recent['high_3d'], "創3日新高"),
        (df_recent['pct_change'] > 3, fmt(df_recent['pct_change'], "今日漲幅{:.2f}%")),
        (df_recent['pct_change_3d'] > 10, fmt(df_recent['pct_change_3d'], "3天漲幅{:.2f}%")),
        (df_recent['pct_change_5d'] > 15, fmt(df_recent['pct_change_5d'], "5天漲幅{:.2f}%")),
        (df_recent['pct_change'] > 9.5, "🔥今日漲停"),
        ((df_recent['pct_change'] > 3) & (df_recent['volume'] >= df_recent['vol_max_3d']), "漲>3%且量創3日高"),
        (df_recent['rank_pct_1d'] <= 10, fmt_r(df_recent['rank_pct_1d'], "漲幅第{}名")),
        (df_recent['rank_pct_5d'] <= 67, fmt_r(df_recent['rank_pct_5d'], "5日漲幅第{}名")),
        (df_recent['w_red_streak'] >= 2, df_recent['w_red_streak'].fillna(0).astype(int).apply(lambda x: f"🔥週K連{x}紅")),
        (df_recent['days_above_ma20'] >= 47, df_recent['days_above_ma20'].fillna(0).astype(int).apply(lambda x: f"連{x}日站月線")),
        (df_recent['days_above_ma60'] >= 177, df_recent['days_above_ma60'].fillna(0).astype(int).apply(lambda x: f"連{x}日站季線")),
        ((df_recent['close']>df_recent['MA5'])&(df_recent['MA5']>df_recent['MA10'])&(df_recent['MA10']>df_recent['MA20']), "短線多頭排列"),
        ((df_recent['close']>df_recent['MA10'])&(df_recent['MA10']>df_recent['MA20'])&(df_recent['MA20']>df_recent['MA60']), "長線多頭排列"),
        (df_recent['vol_bias_ma5'] > 31, fmt(df_recent['vol_bias_ma5'], "較5日量增{:.1f}%")),
        (df_recent['vol_bias_ma10'] > 30, fmt(df_recent['vol_bias_ma10'], "較10日量增{:.1f}%")),
        (df_recent['vol_bias_ma20'] > 40, fmt(df_recent['vol_bias_ma20'], "較20日量增{:.1f}%")),
        (df_recent['volume'] > df_recent['Vol_MA5'], "量大於5日均量"),
        (df_recent['volume'] > df_recent['prev_volume'] * 1.5, fmt((df_recent['volume'] / df_recent['prev_volume']).fillna(0), "量增{:.1f}倍")),
        (df_recent['K'] > df_recent['K'].shift(1), "K值向上"),
        (df_recent['K'] > df_recent['D'], "K>D多頭"),
        ((df_recent['K'] > df_recent['D']) & (df_recent['K'].shift(1) < df_recent['D'].shift(1)), "KD金叉"),
        ((df_recent['MACD_OSC'] > 0) & (df_recent['MACD_OSC'] > df_recent['MACD_OSC'].shift(1)), "MACD紅柱延長"),
        ((df_recent['MACD_OSC'] < 0) & (df_recent['MACD_OSC'] > df_recent['MACD_OSC'].shift(1)), "MACD綠柱縮短"),
        ((df_recent['MACD_OSC'] > 0) & (df_recent['MACD_OSC'].shift(1) < 0), "MACD轉紅"),
        (df_recent['f_buy_streak'] >= 2, df_recent['f_buy_streak'].fillna(0).astype(int).apply(lambda x: f"外資連買{x}天")),
        (df_recent['rank_f_1d'] <= 12, fmt_r(df_recent['rank_f_1d'], "外資買超第{}名")),
        (df_recent['rank_f_5d'] <= 22, fmt_r(df_recent['rank_f_5d'], "外資5日買超第{}名")),
        (df_recent['rev_is_ath'], "🔥營收創歷史新高"),
        (df_recent['yoy_streak'] >= 3, df_recent['yoy_streak'].fillna(0).astype(int).apply(lambda x: f"營收連{x}月成長")),
        (df_recent['yoy_accumulated_pct'] > 20, fmt(df_recent['yoy_accumulated_pct'], "累計年增{:.2f}%")),
    ]

    for mask, txt in strategies:
        m = mask.fillna(False)
        score += m.astype(int)
        if m.any():
            if isinstance(txt, pd.Series):
                vals = txt[m]
                df_recent.loc[m, 'signals_str'] = df_recent.loc[m].apply(
                    lambda row: row['signals_str'] + [vals[row.name]] if row.name in vals.index and vals[row.name] else row['signals_str'], axis=1)
            else:
                df_recent.loc[m, 'signals_str'] = df_recent.loc[m, 'signals_str'].apply(lambda x: x + [txt])

    df_recent['total_score'] = score
    df_recent['signal_list'] = df_recent['signals_str'].apply(lambda x: ", ".join(x))

    # 合併分數與文字回原表
    df = pd.merge(df, df_recent[['symbol', 'date', 'total_score', 'signal_list']], on=['symbol', 'date'], how='left')
    return df

# ===========================
# 4. 寫入資料庫 (Load)
# ===========================
def load_data(df):
    print("📤 [4/4] 覆寫至資料庫中...")
    # 👇 在這個陣列的最後面加上 'Vol_Ratio'
    cols_to_keep = ['date', 'symbol', 'name', 'industry', 'open', 'high', 'low', 'close', 'volume', 
                    'pct_change', 'foreign_net', 'trust_net', 'yoy_pct', 'MA5', 'MA10', 'MA20', 'MA60', 
                    'K', 'D', 'MACD_OSC', 'DIF', 'MACD', 'total_score', 'signal_list', 'Vol_Ratio']
    
    df_final = df[cols_to_keep].dropna(subset=['close'])
    
    with engine.begin() as conn:
        min_date = df_final['date'].min()
        # 清除舊有重疊區間的資料
        conn.execute(text("DELETE FROM strongbuy_indicators WHERE date >= :d"), {"d": min_date})
        # 寫入最新算好的結果
        df_final.to_sql('strongbuy_indicators', conn, if_exists='append', index=False, chunksize=5000)
    print("✅ 更新完成！")

if __name__ == "__main__":
    df_p, df_r = extract_data()
    df_transformed = transform_data(df_p, df_r)
    load_data(df_transformed)
