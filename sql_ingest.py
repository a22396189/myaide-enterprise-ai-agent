# sql_ingest.py
# 執行一次：python sql_ingest.py
#
# 從 UCI Machine Learning Repository 下載「真實」企業交易資料
# ——Online Retail II：一間英國網路零售商 2009-2011 年間的真實訂單紀錄
# （非模擬／非 LLM 生成資料），整理成標準化的企業資料庫（客戶／產品／訂單／
# 訂單明細），作為 SQL 工具（tools/sql_query.py）查詢的預設內部資料來源。
#
# 資料集：UCI Online Retail II, CC BY 4.0
# https://archive.ics.uci.edu/dataset/502/online+retail+ii
#
# 正式環境請改用 DATABASE_URL 環境變數接上真正的企業內部資料庫
# （見 tools/sql_query.py 與 README.md），此腳本僅用於建立可直接體驗
# SQL 工具的預設範例資料庫。

import io
import sqlite3
import zipfile
from pathlib import Path

import pandas as pd
import requests

DATA_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
DB_DIR = Path("./enterprise_data")
DB_PATH = DB_DIR / "enterprise.db"
CACHE_XLSX = DB_DIR / "online_retail_ii.xlsx"


def download_dataset() -> Path:
    DB_DIR.mkdir(exist_ok=True)
    if CACHE_XLSX.exists():
        print(f"使用已下載的快取檔案：{CACHE_XLSX}")
        return CACHE_XLSX

    print("下載真實企業交易資料集（UCI Online Retail II，約數十 MB，請稍候）...")
    resp = requests.get(DATA_URL, timeout=120)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xlsx_name = next(n for n in zf.namelist() if n.lower().endswith(".xlsx"))
        with zf.open(xlsx_name) as src, open(CACHE_XLSX, "wb") as dst:
            dst.write(src.read())
    print(f"已下載並快取至 {CACHE_XLSX}")
    return CACHE_XLSX


def load_raw(xlsx_path: Path) -> pd.DataFrame:
    print("讀取交易明細（2009-2010、2010-2011 兩個年度工作表）...")
    sheets = pd.read_excel(xlsx_path, sheet_name=None, engine="openpyxl")
    df = pd.concat(sheets.values(), ignore_index=True)
    df = df.rename(columns={
        "Invoice": "invoice_no",
        "StockCode": "stock_code",
        "Description": "description",
        "Quantity": "quantity",
        "InvoiceDate": "invoice_date",
        "Price": "unit_price",
        "Customer ID": "customer_id",
        "Country": "country",
    })

    df = df.dropna(subset=["invoice_no", "stock_code", "customer_id"])
    df["customer_id"] = df["customer_id"].astype(int)
    df["invoice_no"] = df["invoice_no"].astype(str)
    df["stock_code"] = df["stock_code"].astype(str)

    # 發票號以 C 開頭代表取消訂單；數量或單價非正數為異常紀錄，一併排除
    df = df[~df["invoice_no"].str.startswith("C")]
    df = df[(df["quantity"] > 0) & (df["unit_price"] > 0)]

    print(f"清理後共 {len(df):,} 筆真實交易明細")
    return df


def build_tables(df: pd.DataFrame):
    customers = (
        df[["customer_id", "country"]]
        .drop_duplicates(subset="customer_id")
        .sort_values("customer_id")
        .reset_index(drop=True)
    )
    products = (
        df[["stock_code", "description"]]
        .dropna()
        .drop_duplicates(subset="stock_code")
        .sort_values("stock_code")
        .reset_index(drop=True)
    )
    orders = (
        df[["invoice_no", "invoice_date", "customer_id"]]
        .drop_duplicates(subset="invoice_no")
        .sort_values("invoice_date")
        .reset_index(drop=True)
    )
    orders["invoice_date"] = orders["invoice_date"].astype(str)
    order_items = df[["invoice_no", "stock_code", "quantity", "unit_price"]].reset_index(drop=True)
    return customers, products, orders, order_items


def write_db(customers, products, orders, order_items):
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    customers.to_sql("customers", conn, index=False)
    products.to_sql("products", conn, index=False)
    orders.to_sql("orders", conn, index=False)
    order_items.to_sql("order_items", conn, index=False)
    conn.execute("CREATE INDEX idx_order_items_invoice ON order_items(invoice_no)")
    conn.execute("CREATE INDEX idx_orders_customer ON orders(customer_id)")
    conn.commit()
    conn.close()
    print(f"\n企業資料庫建立完成：{DB_PATH}")
    print(f"  customers   {len(customers):,} 筆")
    print(f"  products    {len(products):,} 筆")
    print(f"  orders      {len(orders):,} 筆")
    print(f"  order_items {len(order_items):,} 筆")


if __name__ == "__main__":
    xlsx = download_dataset()
    raw = load_raw(xlsx)
    customers, products, orders, order_items = build_tables(raw)
    write_db(customers, products, orders, order_items)
