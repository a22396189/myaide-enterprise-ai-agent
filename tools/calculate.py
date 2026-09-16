# tools/calculate.py
# 純數值計算工具。

from langchain_core.tools import tool


@tool
def calculate(expression: str) -> str:
    """執行數值計算。輸入標準 Python 數學運算式，例如：
    '30000 * 1.5 * 1.2'（計算年終獎金）或 '(12000 / 12) * 0.85'（計算折扣）。
    僅用於純數值計算，不包含文字。
    """
    try:
        # 只允許安全的數學運算
        allowed = set("0123456789+-*/().% ")
        if not all(c in allowed for c in expression):
            return "不支援此運算式，請使用基本數學符號。"
        result = eval(expression)  # noqa: S307
        return f"計算結果：{expression} = {result:,.2f}"
    except Exception as e:
        return f"計算錯誤：{e}"
