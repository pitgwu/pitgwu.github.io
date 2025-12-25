import twstock

print("🔄 正在從證交所與櫃買中心下載最新股票代碼...")
try:
    # 這是 twstock 內建的隱藏更新函式
    twstock.__update_codes()
    print("✅ 更新完成！")
except PermissionError:
    print("❌ 權限不足！請嘗試使用 sudo 執行，或檢查你的安裝路徑權限。")
except Exception as e:
    print(f"❌ 更新失敗: {e}")

# --- 驗證更新結果 ---
print("\n🔍 驗證：檢查 3135 (茂林-KY) 是否存在...")
# 重新載入模組以讀取新資料 (在實際 script 中通常重啟程式即可)
import importlib
importlib.reload(twstock)

if '3135' in twstock.codes:
    print("✅ 成功找到 3135！")
    print(twstock.codes['3135'])
else:
    print("⚠️ 仍然找不到 3135，可能需要檢查網路或手動修補。")
