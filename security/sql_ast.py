# security/sql_ast.py
# 用真正的 SQL 剖析器（sqlglot）驗證語句，取代單純的關鍵字黑名單。
#
# 黑名單的問題：只要語句裡「看不到」INSERT/DROP 這些字面關鍵字就會放行，
# 但多語句夾帶（SELECT ...; DROP TABLE ...）、註解裡藏字（不影響黑名單但
# 也不代表安全）這類情況，光看字串很難完全覆蓋。剖析成 AST 之後直接檢查
# 「這是不是恰好一句 SELECT」，語意層級判斷，不是字面比對。

import sqlglot
from sqlglot import exp


class SQLValidationError(Exception):
    pass


def validate_select(sql: str, dialect: str = "sqlite") -> str:
    """驗證 sql 是恰好一句 SELECT 語句。通過就回傳去掉結尾分號的版本；
    不通過就丟 SQLValidationError，訊息說明原因。"""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        raise SQLValidationError("空白查詢")

    try:
        statements = [s for s in sqlglot.parse(stripped, read=dialect) if s is not None]
    except Exception as e:
        raise SQLValidationError(f"SQL 語法無法解析：{e}")

    if len(statements) == 0:
        raise SQLValidationError("沒有解析出任何語句")
    if len(statements) > 1:
        raise SQLValidationError("偵測到多語句夾帶（一次只能執行一句查詢）")
    if not isinstance(statements[0], exp.Select):
        raise SQLValidationError("僅允許 SELECT 查詢語句")

    return statements[0].sql(dialect=dialect)
