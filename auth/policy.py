# auth/policy.py
# 集中式的權限判斷層。刻意不寫在 prompt 裡讓 LLM 自己遵守——
# 這裡的 is_tool_allowed() 是在 graph/nodes.py 的 tools_node 裡，
# 工具真的被呼叫「之前」擋下來的，屬於伺服器端強制執行，
# LLM 沒有辦法用換句話說的方式繞過。

ALL_ROLES = {"employee", "manager", "sales", "hr", "finance", "admin"}

# 讀取信箱/行事曆、草擬、知識庫、計算、外部搜尋——每個角色都能用
_BASE_TOOLS = {
    "search_knowledge_base",
    "web_search",
    "calculate",
    "search_email",
    "draft_email",
    "list_calendar_events",
    "draft_calendar_event",
}

# 企業結構化資料（訂單/客戶/產品）比一般文件敏感，一般員工不開放
_SQL_TOOLS = {"list_database_tables", "run_sql_query"}

PERMISSIONS: dict[str, set[str]] = {
    "employee": set(_BASE_TOOLS),
    "sales":    _BASE_TOOLS | _SQL_TOOLS,
    "hr":       _BASE_TOOLS | _SQL_TOOLS,
    "finance":  _BASE_TOOLS | _SQL_TOOLS,
    "manager":  _BASE_TOOLS | _SQL_TOOLS,
    "admin":    _BASE_TOOLS | _SQL_TOOLS,
}


def is_tool_allowed(role: str, tool_name: str) -> bool:
    return tool_name in PERMISSIONS.get(role, set())
