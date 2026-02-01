import os
from sqlalchemy import create_engine, text

def test_connection():
    print("="*50)
    print("🔌 Supabase 連線測試工具")
    print("="*50)

    # 1. 取得連線字串
    db_url = os.environ.get("SUPABASE_DB_URL")

    if not db_url:
        print("❌ 錯誤: 未設定 SUPABASE_DB_URL 環境變數")
        print("💡 請先執行:")
        print("   export SUPABASE_DB_URL='postgresql://postgres.[REF]:[PASSWORD]@[HOST]:5432/postgres'")
        return

    # 隱藏密碼顯示 Host，確認是否連對地方
    try:
        host_part = db_url.split("@")[1].split("/")[0]
        print(f"📡 目標主機: {host_part}")
    except:
        print(f"📡 目標主機: (無法解析)")

    try:
        # 2. 建立引擎
        engine = create_engine(db_url)

        # 3. 嘗試連線並執行查詢
        with engine.connect() as conn:
            print("\n🔄 正在嘗試連線...")
            
            # 測試 1: 簡單查詢
            start_time = os.times()[4] # 用於簡單計時
            result = conn.execute(text("SELECT 1"))
            end_time = os.times()[4]
            
            if result.fetchone()[0] == 1:
                print(f"✅ 連線成功！ (耗時: {end_time - start_time:.4f} 秒)")
            
            # 測試 2: 列出所有表格
            print("\n📂 資料庫內的表格清單:")
            tables_query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """)
            tables = conn.execute(tables_query).fetchall()
            
            if not tables:
                print("   (目前無任何表格)")
            else:
                for t in tables:
                    # 簡單檢查表格資料量 (選用)
                    try:
                        count = conn.execute(text(f'SELECT COUNT(*) FROM "{t[0]}"')).scalar()
                        print(f"   - {t[0]:<25} : {count:>8,} 筆")
                    except:
                        print(f"   - {t[0]:<25}")

    except Exception as e:
        print("\n❌ 連線失敗")
        print(f"錯誤訊息: {e}")

if __name__ == "__main__":
    test_connection()
