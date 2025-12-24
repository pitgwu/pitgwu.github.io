import requests
import pandas as pd
import os
from datetime import datetime, timedelta

OUT_DIR = "stock_train/data_981a"
os.makedirs(OUT_DIR, exist_ok=True)

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"

YEARS = 1  # 最近一年

# 你的 00981A 成分股（你之前已有）
COMPONENTS = [
    "2330","2317","6669","1475","2368","3665","2308","2345","6223","3653",
    "6274","6805","2449","2317","8210","2454","2059","3231","1303",
    "3661","6510","6139","6191","5536","3533","8358","4958","3515","2354",
    "6515","3715","3081","1560","3711","3211","5347","1319","3044","3217",
    "5274","3008","2327","2357","2439","2884","3037","3045","3583","8996",
    "8299"
]

def fetch_daily(stock_id):
    end = datetime.today()
    start = end - timedelta(days=365 * YEARS)

    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d")
    }

    print(f"下載：{stock_id} ...")
    r = requests.get(FINMIND_API, params=params)

    try:
        data = r.json()
    except:
        print("JSON 解析失敗，跳過", stock_id)
        return None

    if len(data.get("data", [])) == 0:
        print("無資料，跳過", stock_id)
        return None

    df = pd.DataFrame(data["data"])
    df = df.rename(columns={
        "date": "date",
        "open": "open",
        "max": "high",
        "min": "low",
        "close": "close",
        "Trading_Volume": "volume",
    })
    df = df[["date", "open", "high", "low", "close", "volume"]]

    return df

def main():
    for stock in COMPONENTS:
        df = fetch_daily(stock)
        if df is None:
            continue

        out_path = f"{OUT_DIR}/{stock}.csv"
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print("✔ 已儲存", out_path)

    print("全部完成！")

if __name__ == "__main__":
    main()

