# tests/test_sql_ast_validation.py
# P6：security/sql_ast.py 用真正的剖析器取代關鍵字黑名單。這裡專門測
# 「黑名單容易漏掉、但 AST 剖析能抓到」的案例——最主要是多語句夾帶。

import pytest

from security.sql_ast import SQLValidationError, validate_select

VALID_QUERIES = [
    "SELECT * FROM customers",
    "SELECT * FROM customers WHERE country = 'Germany'",
    "SELECT c.country, COUNT(*) FROM customers c GROUP BY c.country ORDER BY 2 DESC",
    "SELECT * FROM customers -- ; DROP TABLE customers",  # 只是註解，不是真的第二句
    "SELECT * FROM customers /* comment */ WHERE 1=1",
    "SELECT (SELECT COUNT(*) FROM order_items) AS total",
]

REJECTED_QUERIES = [
    "SELECT * FROM customers; DROP TABLE customers",   # 多語句夾帶
    "SELECT * FROM t; SELECT * FROM t2",                # 多語句夾帶（就算兩句都是 SELECT）
    "DELETE FROM customers",
    "UPDATE customers SET country='x'",
    "INSERT INTO customers VALUES (1, 'x')",
    "DROP TABLE customers",
    "PRAGMA table_info(customers)",
    "ATTACH DATABASE 'x.db' AS x",
    "",
    "   ",
]


@pytest.mark.parametrize("sql", VALID_QUERIES)
def test_valid_select_passes(sql):
    validate_select(sql)  # 不該丟例外


@pytest.mark.parametrize("sql", REJECTED_QUERIES)
def test_non_select_and_injection_rejected(sql):
    with pytest.raises(SQLValidationError):
        validate_select(sql)
