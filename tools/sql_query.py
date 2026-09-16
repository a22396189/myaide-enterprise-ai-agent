# tools/sql_query.py
# 企業內部資料庫（SQL）查詢工具。
#
# 預設連線到 ./enterprise_data/enterprise.db（由 sql_ingest.py 建立，內容為真實的
# 公開交易資料集，見該檔案說明）。若要接上正式的企業內部資料庫（PostgreSQL／MySQL／
# SQL Server 等），設定環境變數 DATABASE_URL 即可，程式碼不需修改，例如：
#   DATABASE_URL=postgresql+psycopg2://readonly_user:***@db.internal:5432/erp
#
# 安全性設計（唯讀，P6 強化版）：
#   1. 用真正的 SQL 剖析器驗證語句是「恰好一句 SELECT」（security/sql_ast.py），
#      不是關鍵字黑名單——能擋掉多語句夾帶這類黑名單容易漏掉的手法
#   2. 查詢一律包在交易中執行，結束後強制 rollback，即使前一層被繞過也不會真的寫入
#   3. 正式環境務必額外搭配「唯讀資料庫帳號」，不要只依賴應用層的驗證
#   4. 結果列數上限 200 筆，查詢逾時上限 10 秒（避免佔滿 Streamlit 的單一 session）

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path

from langchain_core.tools import tool
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from security.sql_ast import SQLValidationError, validate_select

DEFAULT_SQLITE_PATH = Path("./enterprise_data/enterprise.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}")

_MAX_ROWS = 200
_QUERY_TIMEOUT_SECONDS = 10

_engine: Engine | None = None
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sql-query")


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL)
    return _engine


@tool
def list_database_tables() -> str:
    """列出企業內部資料庫（SQL）中所有可查詢的資料表、欄位結構與資料筆數。
    在使用 run_sql_query 之前，應先呼叫此工具了解資料表結構，避免猜測欄位名稱。
    """
    engine = _get_engine()
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        if not tables:
            return (
                "資料庫中沒有資料表。若使用預設的 SQLite 範例資料庫，"
                "請先執行 `python sql_ingest.py` 匯入資料。"
            )
        lines = []
        with engine.connect() as conn:
            for t in tables:
                cols = [f"{c['name']}（{c['type']}）" for c in inspector.get_columns(t)]
                count = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
                lines.append(f"【{t}】共 {count:,} 筆\n  欄位：" + "、".join(cols))
        return "\n\n".join(lines)
    except Exception as e:
        return f"讀取資料庫結構失敗：{e}"


def _execute(stripped_sql: str):
    """實際執行查詢，交給 ThreadPoolExecutor 跑，好讓上層能設 timeout。
    注意：逾時只是「Python 端放棄等待、回傳逾時訊息」，背景執行緒本身不會被
    強制中斷（Python 沒有安全的跨執行緒強制終止機制）；查詢本身仍受限於
    _MAX_ROWS 與唯讀交易，逾時保護的是使用者體驗，不是資料庫負載上限——
    正式環境仍建議在資料庫層另外設定 statement_timeout。"""
    engine = _get_engine()
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            result = conn.execute(text(stripped_sql))
            cols = list(result.keys())
            rows = result.fetchmany(_MAX_ROWS)
            return cols, rows
        finally:
            trans.rollback()  # 一律不 commit，即使語句意外具有副作用也不會寫入


@tool
def run_sql_query(sql: str) -> str:
    """對企業內部資料庫執行「唯讀」SQL 查詢（僅支援 SELECT），用於查詢訂單、客戶、
    產品等結構化企業資料。僅能使用 SELECT 語法，禁止 INSERT/UPDATE/DELETE/DROP 等
    會修改資料的指令，這些一律會被系統拒絕執行。
    請先呼叫 list_database_tables 確認資料表結構後，再組出正確的 SQL。
    """
    try:
        clean_sql = validate_select(sql)
    except SQLValidationError as e:
        return f"拒絕執行：{e}"

    try:
        future = _executor.submit(_execute, clean_sql)
        cols, rows = future.result(timeout=_QUERY_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        return f"查詢逾時（超過 {_QUERY_TIMEOUT_SECONDS} 秒），請縮小查詢範圍後再試。"
    except Exception as e:
        return f"SQL 執行錯誤：{e}"

    if not rows:
        return "查詢成功，但沒有符合條件的資料。"
    header = " | ".join(cols)
    sep = "-" * len(header)
    body = "\n".join(" | ".join(str(v) for v in row) for row in rows)
    note = f"\n\n（結果已截斷，最多顯示 {_MAX_ROWS} 筆）" if len(rows) == _MAX_ROWS else ""
    return f"{header}\n{sep}\n{body}{note}"
