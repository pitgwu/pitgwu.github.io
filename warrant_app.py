import streamlit as st
import pandas as pd
import io
import yfinance as yf

# --- 1. 頁面設定 ---
st.set_page_config(page_title="權證小幫手", layout="wide")
st.title("🏹 權證小幫手")

# --- 2. 參數設定 ---
st.sidebar.header("🎯 參數設定")

# 預設留空
stock_input = st.sidebar.text_input("1. 母股代碼", value="", placeholder="請輸入代碼 (例如: 3587)")

# 初始化變數
current_spot = 0.0
fetch_success = False

# --- 關鍵修正：雙軌偵測函數 (上市/上櫃) ---
def get_stock_price_auto(stock_id):
    """
    自動嘗試 .TW (上市) 與 .TWO (上櫃) 兩種後綴抓取股價
    """
    suffixes = ['.TW', '.TWO'] # 優先試上市，再試上櫃
    
    for suffix in suffixes:
        try:
            full_code = f"{stock_id}{suffix}"
            ticker = yf.Ticker(full_code)
            
            # 方法 A: 嘗試 fast_info (最快)
            price = ticker.fast_info['last_price']
            
            # 方法 B: 嘗試 history (備案)
            if price is None:
                hist = ticker.history(period="1d")
                if not hist.empty:
                    price = hist['Close'].iloc[-1]
            
            # 檢核抓到的價格是否正常
            if price and price > 0:
                return price, suffix # 成功抓到，回傳價格與正確後綴
                
        except Exception:
            continue # 失敗就換下一個後綴試試看
            
    return 0.0, None # 都失敗

# --- 主程式邏輯 ---
if stock_input:
    with st.spinner(f"正在搜尋 {stock_input} (自動偵測上市/上櫃)..."):
        # 呼叫新函數
        price_found, found_suffix = get_stock_price_auto(stock_input)
        
        if price_found > 0:
            current_spot = price_found
            fetch_success = True
            # 顯示偵測到的正確後綴 (Debug用，讓使用者知道抓到了哪一個)
            market_type = "上市" if found_suffix == ".TW" else "上櫃"
            st.sidebar.metric(f"📈 {stock_input} ({market_type}) 現價", f"{current_spot:.2f}")
        else:
            fetch_success = False

# 抓取失敗或是尚未輸入時的處理
if not fetch_success:
    if stock_input: # 有輸入但全失敗
        st.sidebar.warning(f"⚠️ 找不到 {stock_input}，請確認代碼或手動輸入：")
        current_spot = st.sidebar.number_input("母股現價", value=0.0, step=0.1, min_value=0.0)
    else: # 還沒輸入
        st.sidebar.info("請輸入代碼 (支援上市/上櫃)")

st.sidebar.markdown("---")
# 篩選參數
min_delta = st.sidebar.number_input("最低 Delta", value=0.000, step=0.001, format="%.3f")
min_days = st.sidebar.number_input("最低剩餘天數", value=100)
min_leverage = st.sidebar.number_input("最低實質槓桿", value=2.0)
otm_target = st.sidebar.slider("目標價外幅度 (%)", 0, 50, 20)

uploaded_file = st.file_uploader("2. 上傳 CSV", type=["csv"])

# 只有在資料齊全時才運算
if uploaded_file is not None:
    if current_spot <= 0:
        st.error("🚨 請先輸入有效的「母股代碼」或手動填寫「母股現價」。")
    else:
        try:
            # --- 讀取與清洗 ---
            raw_bytes = uploaded_file.read()
            try:
                decoded = raw_bytes.decode('utf-8')
            except:
                decoded = raw_bytes.decode('big5', errors='ignore')
            clean_content = decoded.replace('="', '').replace('"', '')
            
            df = pd.read_csv(io.StringIO(clean_content), skiprows=0)
            if '代碼' not in str(df.columns) and 'code' not in str(df.columns):
                 df = pd.read_csv(io.StringIO(clean_content), skiprows=1)
            df.columns = [str(c).strip() for c in df.columns]

            def get_col(candidates):
                for c in candidates:
                    for col in df.columns:
                        if c in col: return col
                return None

            col_code = get_col(['代碼', 'code'])
            col_name = get_col(['名稱', 'name'])
            col_strike = get_col(['履約價', 'strike'])
            col_days = get_col(['剩餘天數', 'days'])
            col_lev = get_col(['實質槓桿', '實際槓桿', 'leverage'])
            col_delta = get_col(['Delta', 'delta'])
            col_vol = get_col(['成交量', 'volume', 'vol'])
            col_price = get_col(['成交價', 'price', 'close'])

            # 代碼補 0
            if col_code:
                df[col_code] = df[col_code].astype(str).str.zfill(6)

            cols = [col_strike, col_days, col_lev, col_delta, col_vol, col_price]
            for c in cols:
                if c: df[c] = pd.to_numeric(df[c].astype(str).str.replace(',', ''), errors='coerce')

            # 計算價外%
            df['自算價外%'] = ((df[col_strike] - current_spot) / current_spot * 100).round(2)
            
            # --- 篩選邏輯 ---
            mask = (
                (df[col_days] >= min_days) & 
                (df[col_lev] >= min_leverage) &
                (df['自算價外%'] >= (otm_target - 10)) & (df['自算價外%'] <= (otm_target + 10)) &
                (df[col_delta] >= min_delta)
            )
            res = df[mask].sort_values(by=col_lev, ascending=False)

            # --- 結果展示 ---
            st.subheader(f"✅ 篩選結果：共 {len(res)} 檔")
            
            if not res.empty:
                res['技術分析'] = res[col_code].apply(lambda x: f"https://www.cmoney.tw/finance/warrantsquery.aspx?warrant={x}")
                display_cols = [col_code, col_name, '技術分析', col_price, col_vol, col_strike, '自算價外%', col_days, col_delta, col_lev]
                final_df = res[[c for c in display_cols if c]].copy()

                def highlight_tiers(row):
                    lev = row[col_lev]
                    vol = row[col_vol]
                    if lev >= 3.0 and vol >= 50:
                        return ['background-color: #fff3cd; color: #856404'] * len(row)
                    elif lev >= 2.5:
                        return ['background-color: #d4edda; color: #155724'] * len(row)
                    else:
                        return [''] * len(row)

                st.markdown("""
                <div style="display: flex; gap: 20px; margin-bottom: 10px;">
                    <span style="background-color: #fff3cd; padding: 4px 8px; border-radius: 4px; border: 1px solid #ffeeba; color: #856404;">
                        🌟 <b>S級旗艦</b>：高槓桿(>3) + 高流動性
                    </span>
                    <span style="background-color: #d4edda; padding: 4px 8px; border-radius: 4px; border: 1px solid #c3e6cb; color: #155724;">
                        🟢 <b>A級優選</b>：不錯的槓桿(>2.5)
                    </span>
                </div>
                """, unsafe_allow_html=True)

                st.dataframe(
                    final_df.style.apply(highlight_tiers, axis=1),
                    column_config={
                        "技術分析": st.column_config.LinkColumn("K線傳送門", display_text="📈 CMoney線圖"),
                        col_lev: st.column_config.NumberColumn("槓桿倍數", format="%.2f x"),
                        col_vol: st.column_config.NumberColumn("成交量", format="%d 張"),
                        "自算價外%": st.column_config.NumberColumn("價外程度", format="%.2f %%"),
                        col_price: st.column_config.NumberColumn("價格", format="%.2f"),
                    },
                    hide_index=True
                )
                
                # --- 戰略建議 ---
                best = res.iloc[0]
                vol = best[col_vol] if pd.notnull(best[col_vol]) else 0
                
                if vol < 10:
                    liq_status, liq_color = "🔴 危險", "red"
                    liq_advice = "成交量過低，建議觀察次佳標的。"
                elif vol < 50:
                    liq_status, liq_color = "🟡 普通", "orange"
                    liq_advice = "流動性尚可，建議掛限價單。"
                else:
                    liq_status, liq_color = "🟢 優秀", "green"
                    liq_advice = "流動性充足，可積極操作。"

                st.markdown("---")
                st.subheader("🏆 小幫手戰略分析")
                
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.success(f"🔥 **今日首選：{best[col_code]}**")
                    st.metric("實質槓桿", f"{best[col_lev]} 倍")
                    st.metric("價外程度", f"{best['自算價外%']}%")
                
                with c2:
                    st.info(f"""
                    **📊 {best[col_name]} 重點報告**
                    1. **攻擊力道**：實質槓桿 **{best[col_lev]} 倍**。
                    2. **流動性**：成交 **{int(vol)} 張** —— :{liq_color}[{liq_status}] ({liq_advice})
                    3. **SOP 檢核**：剩餘 **{int(best[col_days])} 天** | 價外 **{best['自算價外%']}%**
                    """)

            else:
                st.warning("⚠️ 無符合條件標的，請調整參數。")

        except Exception as e:
            st.error(f"系統錯誤: {e}")
