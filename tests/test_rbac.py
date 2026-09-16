# tests/test_rbac.py
# P2 的伺服器端 RBAC：驗證「權限不足」是在真正呼叫工具之前被擋下來的，
# 不是只靠 system prompt 拜託 LLM 自律。用 mock 盯著底層工具函式，
# 確認被拒絕的角色連工具本身都沒有被呼叫到。

from unittest.mock import patch

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

import graph.nodes as nodes
from graph.build import build_graph


class FakeLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def invoke(self, messages):
        return self._responses.pop(0)


def _sql_question_response():
    return FakeLLM([
        AIMessage(content="", tool_calls=[{
            "name": "run_sql_query",
            "args": {"sql": "SELECT COUNT(*) FROM customers"},
            "id": "call_1",
        }]),
        AIMessage(content="已查詢完成。"),
    ])


def test_employee_role_cannot_reach_run_sql_query():
    with patch.object(nodes, "_get_llm", return_value=_sql_question_response()), \
         patch("tools.sql_query.run_sql_query") as mock_sql:
        g = build_graph(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "t1", "user": "alice", "role": "employee"}}

        result = g.invoke({
            "messages": [("human", "這個月業績多少？")],
            "pending_action": None, "approval_decision": None, "execution_result": None,
        }, config=config)

        mock_sql.invoke.assert_not_called()
        tool_msgs = [m for m in result["messages"] if getattr(m, "name", None) == "run_sql_query"]
        assert tool_msgs, "應該要有一則 run_sql_query 的 ToolMessage（內容是拒絕）"
        assert "權限不足" in tool_msgs[0].content


def test_sales_role_can_reach_run_sql_query():
    with patch.object(nodes, "_get_llm", return_value=_sql_question_response()):
        g = build_graph(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "t2", "user": "ben", "role": "sales"}}

        result = g.invoke({
            "messages": [("human", "這個月業績多少？")],
            "pending_action": None, "approval_decision": None, "execution_result": None,
        }, config=config)

        tool_msgs = [m for m in result["messages"] if getattr(m, "name", None) == "run_sql_query"]
        assert tool_msgs
        assert "權限不足" not in tool_msgs[0].content
