# agent.py
# 對外公開介面。實際的推理/工具/核准/執行邏輯都在 graph/ 底下的 LangGraph
# StateGraph 裡（見 graph/build.py 的流程圖說明），這裡只負責：
#   1. 呼叫 graph，把使用者問題丟進去（ask）
#   2. 使用者按下確認／拒絕後，恢復被 interrupt() 暫停的 graph（confirm）
#   3. 把 graph 回傳的 messages/interrupt 整理成 UI 需要的形狀

from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from graph.build import get_graph
from observability import metrics


def ask(question: str, thread_id: str, user: str = "unknown", role: str = "employee") -> dict[str, Any]:
    """開始新的一輪對話。user/role 會被放進 graph 的 config，供
    graph/nodes.py 的 tools_node 做 RBAC 權限檢查與稽核紀錄——這是
    P2 的「伺服器端強制執行」，不是只寫在 system prompt 裡。

    回傳 dict：
      - answer: str | None          最終回答（若正在等待核准，這是草稿的說明文字）
      - steps: list[dict]           呼叫過的工具（tool/input/output）
      - sources: list[str]          知識庫引用來源
      - interrupt: dict | None      非 None 時代表 graph 正暫停等待人工核准
      - execution_result: str | None
    """
    metrics.agent_requests_total.inc()
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id, "user": user, "role": role}}
    result = graph.invoke(
        {
            "messages": [("human", question)],
            "pending_action": None,
            "approval_decision": None,
            "execution_result": None,
        },
        config=config,
    )
    return _package(result)


def confirm(
    thread_id: str, approve: bool, edited_params: dict | None = None,
    user: str = "unknown", role: str = "employee",
) -> dict[str, Any]:
    """恢復被 interrupt() 暫停的 graph。approve=False 時，send_gmail /
    create_calendar_event 保證不會被呼叫——graph 上沒有任何一條這樣的路徑。
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id, "user": user, "role": role}}
    resume_value = {"decision": "approve" if approve else "reject", "params": edited_params}
    result = graph.invoke(Command(resume=resume_value), config=config)
    return _package(result)


def _package(result: dict) -> dict[str, Any]:
    interrupt_payload = None
    interrupts = result.get("__interrupt__")
    if interrupts:
        interrupt_payload = interrupts[0].value

    messages = result.get("messages", [])

    call_args_by_id: dict[str, Any] = {}
    for m in messages:
        if isinstance(m, AIMessage) and m.tool_calls:
            for call in m.tool_calls:
                call_args_by_id[call["id"]] = call["args"]

    steps = []
    sources = set()
    for m in messages:
        if isinstance(m, ToolMessage):
            steps.append({
                "tool": m.name,
                "input": call_args_by_id.get(m.tool_call_id, {}),
                "output": str(m.content)[:300],
            })
            if m.name == "search_knowledge_base":
                for line in str(m.content).split("\n"):
                    if line.startswith("[來源"):
                        src = line.split("：")[-1].rstrip("]")
                        sources.add(src)

    # Gemini 3 的 AIMessage.content 可能是 content block 的 list（含 thought
    # signature 等），.text 只取出純文字部分。
    answer = None
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.text:
            answer = m.text
            break

    return {
        "answer": answer,
        "steps": steps,
        "sources": list(sources),
        "interrupt": interrupt_payload,
        "approval_decision": result.get("approval_decision"),
        "execution_result": result.get("execution_result"),
    }
