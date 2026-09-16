# graph/state.py
# LangGraph 的狀態定義。取代 AgentExecutor 內隱藏的迴圈狀態，
# 讓「工具呼叫」「草稿」「人工核准」「執行」都是明確可檢視的狀態欄位。

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class PendingAction(TypedDict):
    type: str          # "draft_email" | "draft_calendar_event"
    params: dict[str, Any]


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    pending_action: PendingAction | None
    approval_decision: str | None      # "approve" | "reject" | None
    execution_result: str | None
