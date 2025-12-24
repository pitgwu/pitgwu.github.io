import requests
import pandas as pd
import os
from datetime import datetime, timedelta

OUT_DIR = "stock_train/data_highest"
os.makedirs(OUT_DIR, exist_ok=True)

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"

# 2024年最飆的股票
COMPONENTS = [
    "5314","6442","8937","3230","8374","3450","6199","6640","4583","2359"
]

def fetch_daily(stock_id):

    start_date = "2024-01-01"
    end_date = "2024-12-31"

    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date
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

