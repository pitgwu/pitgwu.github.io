import pandas as pd
import sqlalchemy
from sqlalchemy import text
import os
import numpy as np

# 1. 資料庫連線
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
engine = sqlalchemy.create_engine(SUPABASE_DB_URL)

def extract_data():
    print("📥 [1/4] 開始撈取近 200 天歷史資料...")
    query = """
    SELECT sp.date, sp.symbol, sp.open, sp.high, sp.low, sp.close, sp.volume, 
           si.name, si.industry, 
           COALESCE(ii.foreign_net, 0) as foreign_net,
           COALESCE(ii.trust_net, 0) as trust_net
    FROM stock_prices sp
    JOIN stock_info si ON sp.symbol = si.symbol
    LEFT JOIN institutional_investors ii ON sp.date = ii.date AND sp.symbol = ii.symbol
    WHERE sp.date >= current_date - INTERVAL '200 days' 
    ORDER BY sp.symbol, sp.date
    """
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df

def transform_data(df):
    print("⚙️ [2/4] 開始計算技術指標與籌碼排名...")
    df['symbol'] = df['symbol'].astype(str).str.strip()
    df['date'] = pd.to_datetime(df['date'])
    grouped = df.groupby('symbol')

    # --- 基本指標計算 (MA, KD, MACD) ---
    df['MA5'] = grouped['close'].transform(lambda x: x.rolling(5).mean())
    df['MA10'] = grouped['close'].transform(lambda x: x.rolling(10).mean())
    df['MA20'] = grouped['close'].transform(lambda x: x.rolling(20).mean())
    df['MA60'] = grouped['close'].transform(lambda x: x.rolling(60).mean())
    df['Vol_MA5'] = grouped['volume'].transform(lambda x: x.rolling(5).mean())
    
    df['prev_close'] = grouped['close'].shift(1)
    df['prev_volume'] = grouped['volume'].shift(1)
    df['pct_change'] = (df['close'] - df['prev_close']) / df['prev_close'] * 100
    df['pct_change_5d'] = grouped['close'].pct_change(5) * 100
    df['close_max_3d'] = grouped['close'].transform(lambda x: x.rolling(3).max())
    df['vol_max_3d'] = grouped['volume'].transform(lambda x: x.rolling(3).max())

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

    df['bias_ma5'] = (df['close'] - df['MA5']) / df['MA5'] * 100
    df['vol_bias_ma5'] = (df['volume'] - df['Vol_MA5']) / df['Vol_MA5'] * 100
    df['above_ma20'] = (df['close'] > df['MA20']).astype(int)
    df['days_above_ma20'] = grouped['above_ma20'].transform(lambda x: x.rolling(47).sum())

    df['f_buy_pos'] = (df['foreign_net'] > 0).astype(int)
    df['f_buy_streak'] = grouped['f_buy_pos'].transform(lambda x: x.groupby((x != x.shift()).cumsum()).cumsum())
    df['f_sum_5d'] = grouped['foreign_net'].transform(lambda x: x.rolling(5).sum())

    df['t_buy_pos'] = (df['trust_net'] > 0).astype(int)
    df['t_buy_streak'] = grouped['t_buy_pos'].transform(lambda x: x.groupby((x != x.shift()).cumsum()).cumsum())
    df['t_sum_5d'] = grouped['trust_net'].transform(lambda x: x.rolling(5).sum())

    # --- 處理最新一日的排名與分數 ---
    # 為避免全歷史運算太久，我們只對「最後一天」算分數與排名
    latest_date = df['date'].max()
    df_day = df[df['date'] == latest_date].copy()

    f_net_pos = df_day['foreign_net'].where(df_day['foreign_net'] > 0)
    f_sum5_pos = df_day['f_sum_5d'].where(df_day['f_sum_5d'] > 0)
    t_net_pos = df_day['trust_net'].where(df_day['trust_net'] > 0)
    t_sum5_pos = df_day['t_sum_5d'].where(df_day['t_sum_5d'] > 0)

    df_day['global_rank_f_1d'] = f_net_pos.rank(ascending=False, method='min')
    df_day['global_rank_f_5d'] = f_sum5_pos.rank(ascending=False, method='min')
    df_day['global_rank_t_1d'] = t_net_pos.rank(ascending=False, method='min')
    df_day['global_rank_t_5d'] = t_sum5_pos.rank(ascending=False, method='min')

    df_day['signals_str'] = [[] for _ in range(len(df_day))]
    score = pd.Series(0, index=df_day.index)

    def fmt(val, template): return val.fillna(0).apply(lambda x: template.format(x))
    def fmt_r(val, template): return val.apply(lambda x: template.format(int(x)) if pd.notna(x) else "")

    txt_bias_w = fmt(df_day['bias_ma5'], "突破週線{:.2f}%")
    txt_vol_5 = fmt(df_day['vol_bias_ma5'], "較5日量增{:.1f}%")
    txt_f_buy = df_day['f_buy_streak'].fillna(0).astype(int).apply(lambda x: f"外資連買超{x}天")
    txt_t_buy = df_day['t_buy_streak'].fillna(0).astype(int).apply(lambda x: f"投信連買超{x}天")
    
    strategies = [
        (df_day['close'] > df_day['MA5'], txt_bias_w),
        (df_day['close'] > df_day['MA20'], "突破月線"),
        (df_day['close'] > df_day['MA60'], "突破季線"),
        (df_day['close'] >= df_day['close_max_3d'], "股價創下3日新高"),
        (df_day['pct_change'] > 3, fmt(df_day['pct_change'], "漲幅{:.2f}%")),
        (df_day['pct_change'] > 9.5, "🔥漲停"),
        ((df_day['close'] > df_day['MA5']) & (df_day['MA5'] > df_day['MA10']) & (df_day['MA10'] > df_day['MA20']), "短線多頭排列"),
        ((df_day['close'] > df_day['MA10']) & (df_day['MA10'] > df_day['MA20']) & (df_day['MA20'] > df_day['MA60']), "長線多頭排列"),
        (df_day['days_above_ma20'] >= 47, fmt(df_day['days_above_ma20'], "連{:.0f}日站月線")),
        (df_day['vol_bias_ma5'] > 30, txt_vol_5),
        (df_day['volume'] > df_day['Vol_MA5'], "今日成交量大於5日均量"),
        (df_day['volume'] >= df_day['prev_volume'] * 1.5, "今日成交量為前日的1.5倍以上"),
        ((df_day['pct_change'] > 3) & (df_day['volume'] >= df_day['vol_max_3d']), "漲幅>3%且量創3日高"),
        (df_day['K'] > df_day['D'], "KD多頭"),
        ((df_day['K'] > df_day['D']) & (df_day['K'].shift(1) < df_day['D'].shift(1)), "KD金叉"),
        ((df_day['MACD_OSC'] > 0) & (df_day['MACD_OSC'].shift(1) < 0), "MACD轉紅"),
        (df_day['f_buy_streak'] >= 3, txt_f_buy),
        (df_day['global_rank_f_1d'] <= 12, fmt_r(df_day['global_rank_f_1d'], "外資今日買超第{}名")),
        (df_day['global_rank_f_5d'] <= 22, fmt_r(df_day['global_rank_f_5d'], "外資近5日買超第{}名")),
        (df_day['t_buy_streak'] >= 3, txt_t_buy),
        (df_day['global_rank_t_1d'] <= 12, fmt_r(df_day['global_rank_t_1d'], "投信今日買超第{}名")),
        (df_day['global_rank_t_5d'] <= 22, fmt_r(df_day['global_rank_t_5d'], "投信近5日買超第{}名")),
    ]

    for mask, txt in strategies:
        m = mask.fillna(False)
        score += m.astype(int)
        if m.any():
            if isinstance(txt, pd.Series):
                vals = txt[m]
                df_day.loc[m, 'signals_str'] = df_day.loc[m].apply(lambda row: row['signals_str'] + [vals[row.name]] if row.name in vals.index and vals[row.name] != "" else row['signals_str'], axis=1)
            else:
                df_day.loc[m, 'signals_str'] = df_day.loc[m, 'signals_str'].apply(lambda x: x + [txt])

    df_day['total_score'] = score
    df_day['signal_list'] = df_day['signals_str'].apply(lambda x: ", ".join(x))

    # 將算好的今日分數與訊號，合併回歷史大表
    df = pd.merge(df, df_day[['symbol', 'date', 'total_score', 'signal_list']], on=['symbol', 'date'], how='left')
    return df

def load_data(df):
    print("📤 [3/4] 準備覆寫至資料庫...")
    # 只取需要存入資料庫的欄位
    cols_to_keep = ['date', 'symbol', 'name', 'industry', 'open', 'high', 'low', 'close', 'volume', 
                    'pct_change', 'foreign_net', 'trust_net', 'MA5', 'MA10', 'MA20', 'MA60', 
                    'K', 'D', 'MACD_OSC', 'DIF', 'total_score', 'signal_list']
    
    df_final = df[cols_to_keep].dropna(subset=['close'])
    
    with engine.begin() as conn:
        # 為了簡化更新邏輯，先刪除近 180 天的舊計算資料，再整批塞入最新的
        # (因為技術指標會隨著時間推移而微調收斂，覆蓋寫入是最安全的做法)
        min_date = df_final['date'].min()
        conn.execute(text("DELETE FROM daily_stock_indicators WHERE date >= :d"), {"d": min_date})
        
        # 批次寫入
        print(f"🚀 [4/4] 寫入 {len(df_final)} 筆資料中...")
        df_final.to_sql('daily_stock_indicators', conn, if_exists='append', index=False, chunksize=5000)
    print("✅ 更新完成！")

if __name__ == "__main__":
    raw_df = extract_data()
    processed_df = transform_data(raw_df)
    load_data(processed_df)
