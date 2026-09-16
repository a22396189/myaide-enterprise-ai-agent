# tests/test_graph_safety.py
# 驗證 P1 的核心安全不變量：
#   「send_gmail() / create_calendar_event() 不可能在沒有經過人工核准的情況下被呼叫」
#
# 分兩種驗證方式：
#   1. 結構面：直接檢查編譯後的 graph，execute 節點只能有一條入邊，且來自
#      approval 節點的 approve 分支。這是「就算以後有人改壞 routing 邏輯，
#      也會被 CI 抓到」的防線。
#   2. 行為面：真的跑一輪「使用者要求寄信 → 產生草稿 → 使用者拒絕／核准」，
#      用 mock 盯著 send_gmail，證明拒絕時完全不會被呼叫、核准時剛好被呼叫一次。
#
# 這裡刻意不呼叫真正的 Gemini：agent 節點的 LLM 是用 FakeLLM 取代，因為這裡要
# 驗證的是「graph 的路線」，不是「LLM 選工具選得準不準」（那是 P3 的事）。

from unittest.mock import Mock, patch

import pytest
from langchain_core.messages import AIMessage

import graph.nodes as nodes
from graph.build import build_graph
from langgraph.checkpoint.memory import InMemorySaver


class FakeLLM:
    """依序回傳事先寫好的回應，取代需要真實 API Key 的 ChatGoogleGenerativeAI。"""

    def __init__(self, responses):
        self._responses = list(responses)

    def invoke(self, messages):
        return self._responses.pop(0)


def _draft_email_then_final_answer():
    """模擬：第一輪 LLM 決定呼叫 draft_email；工具執行完、結果丟回去後，
    第二輪 LLM 產生一段純文字說明（沒有再呼叫任何工具）。"""
    return FakeLLM([
        AIMessage(content="", tool_calls=[{
            "name": "draft_email",
            "args": {"to": "john@example.com", "subject": "會議取消通知", "body": "會議已取消。"},
            "id": "call_1",
        }]),
        AIMessage(content="已產生郵件草稿，請確認後才會送出。"),
    ])


# ── 1. 結構面 ──────────────────────────────────────────

def test_execute_node_has_exactly_one_inbound_edge_from_approval():
    g = build_graph(checkpointer=InMemorySaver())
    edges = g.get_graph().edges

    inbound_to_execute = [e for e in edges if e.target == "execute"]
    assert len(inbound_to_execute) == 1, (
        f"execute 節點應該只有一條入邊，實際有 {len(inbound_to_execute)} 條：{inbound_to_execute}"
    )
    assert inbound_to_execute[0].source == "approval", (
        "execute 節點的唯一入邊必須來自 approval 節點"
    )

    # agent、tools 都不可以有直接通往 execute 的邊
    for node_name in ("agent", "tools"):
        direct_edges = [e for e in edges if e.source == node_name and e.target == "execute"]
        assert not direct_edges, f"{node_name} 不應該有直接通往 execute 的路徑"


# ── 2. 行為面 ──────────────────────────────────────────

def test_reject_path_never_calls_send_gmail():
    with patch.object(nodes, "_get_llm", return_value=_draft_email_then_final_answer()), \
         patch.object(nodes, "send_gmail") as mock_send:
        g = build_graph(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "reject-test"}}

        result = g.invoke({
            "messages": [("human", "幫我寄信通知 John 會議取消")],
            "pending_action": None,
            "approval_decision": None,
            "execution_result": None,
        }, config=config)

        assert "__interrupt__" in result, "應該在 approval 節點暫停等待人工核准"

        from langgraph.types import Command
        result = g.invoke(Command(resume={"decision": "reject", "params": None}), config=config)

        mock_send.assert_not_called()
        assert result.get("execution_result") is None
        assert result.get("approval_decision") == "reject"


def test_approve_path_calls_send_gmail_exactly_once():
    with patch.object(nodes, "_get_llm", return_value=_draft_email_then_final_answer()), \
         patch.object(nodes, "send_gmail", return_value="郵件已寄出") as mock_send:
        g = build_graph(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "approve-test"}}

        g.invoke({
            "messages": [("human", "幫我寄信通知 John 會議取消")],
            "pending_action": None,
            "approval_decision": None,
            "execution_result": None,
        }, config=config)

        from langgraph.types import Command
        result = g.invoke(Command(resume={"decision": "approve", "params": None}), config=config)

        mock_send.assert_called_once_with(
            to="john@example.com", subject="會議取消通知", body="會議已取消。"
        )
        assert result.get("execution_result") == "郵件已寄出"
        assert result.get("approval_decision") == "approve"


def test_no_side_effect_path_never_interrupts():
    """單純的問答（不涉及寄信/建立行程）不應該觸發 approval / interrupt。"""
    plain_llm = FakeLLM([AIMessage(content="病假一年有 30 天。")])
    with patch.object(nodes, "_get_llm", return_value=plain_llm):
        g = build_graph(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "plain-test"}}

        result = g.invoke({
            "messages": [("human", "病假一年有幾天？")],
            "pending_action": None,
            "approval_decision": None,
            "execution_result": None,
        }, config=config)

        assert "__interrupt__" not in result
        assert result["messages"][-1].content == "病假一年有 30 天。"
