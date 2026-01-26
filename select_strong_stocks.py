import os
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta

# ===========================
# 1. 配置與連線
# ===========================
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
BASE_OUTPUT_DIR = "tw_stock_dashboard"  # 報表輸出根目錄

if not SUPABASE_DB_URL:
    # 方便本地測試，若無環境變數可手動填入，但在 GitHub Actions 必須用環境變數
    print("❌ 請設定環境變數 SUPABASE_DB_URL")
    exit(1)

try:
    engine = create_engine(SUPABASE_DB_URL)
except Exception as e:
    print(f"❌ 資料庫連線失敗: {e}")
    exit(1)

# ===========================
# 2. 核心邏輯
# ===========================
def fetch_recent_data(days=40):
    """
    從資料庫抓取最近 N 天的股價資料 (為了計算 MA20，至少需 20 天以上)
    """
    print("📥 正在讀取近期股價資料...")
    
    # 1. 先找出資料庫中最近的 N 個交易日 (避免抓全歷史，太慢)
    with engine.connect() as conn:
        query_dates = text(f"""
            SELECT DISTINCT date 
            FROM stock_prices 
            ORDER BY date DESC 
            LIMIT {days}
        """)
        dates_df = pd.read_sql(query_dates, conn)
        
        if dates_df.empty:
            print("⚠️ 資料庫無股價資料")
            return pd.DataFrame(), None
            
        min_date = dates_df['date'].min()
        latest_date = dates_df['date'].max() # 記錄最新日期
        
        print(f"   📅 分析範圍: {min_date} ~ {latest_date}")

        # 2. 抓取範圍內的股價 + 股票基本資料
        # Join stock_info 取得名稱與產業
        query_prices = text(f"""
            SELECT 
                p.date, p.symbol, p.close, p.volume, 
                i.name, i.industry
            FROM stock_prices p
            LEFT JOIN stock_info i ON p.symbol = i.symbol
            WHERE p.date >= '{min_date}'
        """)
        df = pd.read_sql(query_prices, conn)
        
    return df, latest_date

def analyze_stocks(df, target_date):
    """
    計算技術指標並進行篩選
    """
    print(f"🔄 正在計算技術指標並篩選 (目標日期: {target_date})...")
    
    # 確保日期格式正確並排序
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['symbol', 'date'])
    
    # 用 Groupby 計算移動平均與昨日數據
    # 這裡使用 transform 保持原 DataFrame 大小，方便後續 filter
    grouped = df.groupby('symbol')
    
    df['ma5'] = grouped['close'].transform(lambda x: x.rolling(window=5).mean())
    df['ma10'] = grouped['close'].transform(lambda x: x.rolling(window=10).mean())
    df['ma20'] = grouped['close'].transform(lambda x: x.rolling(window=20).mean())
    
    # 取得前一日數據 (Shift)
    df['prev_close'] = grouped['close'].shift(1)
    df['prev_volume'] = grouped['volume'].shift(1)
    
    # 計算漲跌幅 (%)
    df['pct_change'] = ((df['close'] - df['prev_close']) / df['prev_close']) * 100
    
    # --- 篩選邏輯 ---
    # 1. 只取「最新日期」的資料來檢查
    target_date_ts = pd.to_datetime(target_date)
    today_df = df[df['date'] == target_date_ts].copy()
    
    if today_df.empty:
        print("⚠️ 找不到最新日期的資料，請確認資料庫是否已更新。")
        return pd.DataFrame()

    # 2. 條件 A: 均線多頭排列 (5 > 10 > 20)
    cond_bull_trend = (today_df['ma5'] > today_df['ma10']) & (today_df['ma10'] > today_df['ma20'])
    
    # 3. 條件 B: 股價強勢 (收盤價 > MA5 且 漲幅 > 0)
    cond_strong_price = (today_df['close'] > today_df['ma5']) & (today_df['pct_change'] > 0)
    
    # 4. 條件 C: 量增 (今日成交量 > 昨日成交量)
    cond_vol_increase = (today_df['volume'] > today_df['prev_volume'])
    
    # 5. 綜合篩選
    final_filter = cond_bull_trend & cond_strong_price & cond_vol_increase
    
    result = today_df[final_filter].copy()
    
    # 格式化輸出所需欄位
    result = result[['symbol', 'name', 'industry', 'close', 'pct_change', 'volume', 'prev_volume', 'ma5', 'ma10', 'ma20']]
    
    # 依漲幅排序 (強勢股優先)
    result = result.sort_values('pct_change', ascending=False)
    
    return result

# ===========================
# 3. 報表生成模組 (JS 極速排序版)
# ===========================
def generate_html_report(df, target_date):
    """
    生成 HTML 篩選清單，包含高效能排序功能與 No 欄位
    """
    if df.empty: return

    # 準備路徑 tw_stock_dashboard/YYYY/MM/strong_stocks_YYYYMMDD.html
    target_dt = datetime.strptime(str(target_date), "%Y-%m-%d")
    yyyy = target_dt.strftime("%Y")
    mm = target_dt.strftime("%m")
    date_str = target_dt.strftime("%Y%m%d")
    
    output_dir = os.path.join(BASE_OUTPUT_DIR, yyyy, mm)
    os.makedirs(output_dir, exist_ok=True)
    
    filename = f"strong_stocks_{date_str}.html"
    filepath = os.path.join(output_dir, filename)

    # HTML 樣板 (內嵌優化版 JavaScript)
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>強勢股篩選 - {target_date}</title>
        <style>
            :root {{ --bg: #121212; --card: #1e1e1e; --text: #e0e0e0; --red: #ff5252; --green: #4caf50; --accent: #2196f3; --border: #333; }}
            body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; margin: 0; padding: 20px; }}
            h1 {{ text-align: center; color: var(--accent); margin-bottom: 10px; }}
            .info {{ text-align: center; color: #888; margin-bottom: 20px; font-size: 0.9rem; }}
            .container {{ max-width: 1000px; margin: 0 auto; }}
            .card {{ background: var(--card); border-radius: 8px; border: 1px solid var(--border); overflow: hidden; }}
            
            .table-wrapper {{ overflow-x: auto; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; white-space: nowrap; }}
            
            /* 表頭樣式與排序指標 */
            th {{ 
                background: #252525; padding: 12px; text-align: left; color: #aaa; font-weight: 600; 
                position: sticky; top: 0; cursor: pointer; user-select: none; transition: background 0.2s;
            }}
            th:hover {{ background: #333; color: var(--accent); }}
            
            /* 排序箭頭 */
            th.sort-asc::after {{ content: ' ▲'; color: var(--accent); }}
            th.sort-desc::after {{ content: ' ▼'; color: var(--accent); }}
            th::after {{ content: ' ⇅'; font-size: 0.8em; opacity: 0.2; margin-left: 5px; }}
            th.sort-asc::after, th.sort-desc::after {{ opacity: 1; }}

            td {{ border-bottom: 1px solid #2a2a2a; padding: 10px 12px; vertical-align: middle; }}
            tr:hover {{ background: #2c2c2c; }}
            
            .stock-link {{ color: var(--accent); text-decoration: none; font-weight: bold; font-size: 1.05rem; display: block; }}
            .stock-link small {{ color: #777; font-size: 0.75rem; font-weight: normal; display: block; margin-top: 2px; }}
            .stock-link:hover {{ text-decoration: underline; }}
            
            .ind-badge {{ background: #334155; color: #94a3b8; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; }}
            .up {{ color: var(--red); font-weight: bold; }}
            .down {{ color: var(--green); font-weight: bold; }}
            .vol-tag {{ color: #ffa726; font-size: 0.8rem; }}
        </style>
        <script>
            document.addEventListener('DOMContentLoaded', function() {{
                const table = document.getElementById("stockTable");
                const headers = table.querySelectorAll("th");
                const tbody = table.querySelector("tbody");

                headers.forEach((header, index) => {{
                    header.addEventListener("click", () => {{
                        const rows = Array.from(tbody.querySelectorAll("tr"));
                        const isAsc = header.classList.contains("sort-asc");
                        
                        // 重置所有 header 樣式
                        headers.forEach(h => h.classList.remove("sort-asc", "sort-desc"));
                        
                        // 設定當前 header 樣式
                        header.classList.toggle("sort-asc", !isAsc);
                        header.classList.toggle("sort-desc", isAsc);
                        
                        const direction = isAsc ? -1 : 1;

                        // 執行排序 (記憶體內陣列排序，極速)
                        rows.sort((rowA, rowB) => {{
                            const cellA = rowA.children[index].innerText;
                            const cellB = rowB.children[index].innerText;
                            
                            // 清洗數據轉為數字
                            const valA = parseValue(cellA);
                            const valB = parseValue(cellB);

                            if (typeof valA === 'number' && typeof valB === 'number') {{
                                return (valA - valB) * direction;
                            }} else {{
                                return valA.toString().localeCompare(valB.toString()) * direction;
                            }}
                        }});

                        // 一次性將排序好的 rows 放回 tbody (減少 reflow)
                        tbody.append(...rows);

                        // 重新編號
                        reindexRows();
                    }});
                }});
            }});

            function parseValue(str) {{
                // 移除 %, ,, x, 🔥 等符號
                const cleanStr = str.replace(/[%,,🔥x]/g, "").trim();
                const num = parseFloat(cleanStr);
                return isNaN(num) ? str : num;
            }}

            function reindexRows() {{
                const rows = document.querySelectorAll("#stockTable tbody tr");
                rows.forEach((row, index) => {{
                    row.children[0].innerText = index + 1;
                }});
            }}
        </script>
    </head>
    <body>
        <div class="container">
            <h1>🚀 強勢股篩選清單</h1>
            <div class="info">
                📅 日期: {target_date} | 
                🔍 條件: 均線多頭(5>10>20) + 股價強勢 + 量增 | 
                ✅ 符合: {len(df)} 檔
            </div>
            
            <div class="card">
                <div class="table-wrapper">
                    <table id="stockTable">
                        <thead>
                            <tr>
                                <th width="5%">No.</th>
                                <th width="15%">代號/名稱</th>
                                <th width="15%">產業</th>
                                <th width="15%">收盤</th>
                                <th width="15%">漲跌幅</th>
                                <th width="15%">成交量</th>
                                <th width="20%">量增比</th>
                            </tr>
                        </thead>
                        <tbody>
    """

    # 使用 enumerate 產生初始序號
    for idx, (_, row) in enumerate(df.iterrows(), 1):
        symbol = row['symbol']
        name = row['name']
        industry = row['industry'] if row['industry'] else '其他'
        close = f"{row['close']:.2f}"
        pct = row['pct_change']
        vol = int(row['volume'])
        prev_vol = int(row['prev_volume'])
        
        # 計算量增倍數
        vol_ratio = vol / prev_vol if prev_vol > 0 else 0
        vol_ratio_str = f"🔥 {vol_ratio:.1f}x" if vol_ratio >= 1.5 else f"{vol_ratio:.1f}x"
        
        # 顏色樣式
        pct_class = "up" if pct > 0 else "down" if pct < 0 else ""
        pct_str = f"{pct:+.2f}%"
        
        # Yahoo Finance 連結
        link = f"https://tw.stock.yahoo.com/quote/{symbol}"
        
        html_content += f"""
                            <tr>
                                <td>{idx}</td>
                                <td>
                                    <a href="{link}" target="_blank" class="stock-link">
                                        {name} <small>{symbol}</small>
                                    </a>
                                </td>
                                <td><span class="ind-badge">{industry}</span></td>
                                <td>{close}</td>
                                <td class="{pct_class}">{pct_str}</td>
                                <td>{vol:,}</td>
                                <td class="vol-tag">{vol_ratio_str}</td>
                            </tr>
        """

    html_content += """
                        </tbody>
                    </table>
                </div>
            </div>
            <br>
            <div class="info">Generated by AI Stock Screener (Click headers to sort)</div>
        </div>
    </body>
    </html>
    """

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"✅ [HTML] 篩選報表已生成: {filepath}")

# ===========================
# 主程式
# ===========================
def main():
    print("="*60)
    print(f"🚀 台股強勢股篩選器 (Supabase 版)")
    print(f"⏰ 執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # 1. 讀取資料
    df, latest_date = fetch_recent_data(days=60) # 抓60天確保MA20不缺值
    
    if df.empty:
        print("❌ 無法執行分析")
        return

    # 2. 分析與篩選
    results = analyze_stocks(df, latest_date)
    
    print("\n" + "="*60)
    print(f"📊 篩選結果 (日期: {latest_date})")
    print(f"🔍 條件: 均線多頭(5>10>20) + 股價站上MA5 + 今日收紅 + 量增")
    print(f"✅ 符合檔數: {len(results)}")
    print("="*60)
    
    if not results.empty:
        # 終端機顯示前 50 檔
        pd.set_option('display.max_rows', 50)
        pd.set_option('display.unicode.east_asian_width', True)
        
        display_df = results.copy()
        display_df['漲幅%'] = display_df['pct_change'].map('{:+.2f}%'.format)
        display_df['成交量'] = display_df['volume'].map('{:,.0f}'.format)
        display_df['收盤'] = display_df['close'].map('{:.2f}'.format)
        
        cols = ['symbol', 'name', 'industry', '收盤', '漲幅%', '成交量']
        print(display_df[cols].head(50).to_string(index=False))
        
        # 3. 生成 HTML 報表
        generate_html_report(results, latest_date)
        
    else:
        print("🤷‍♂️ 今日無符合條件個股 (市場可能偏弱或剛開盤)")

if __name__ == "__main__":
    main()
