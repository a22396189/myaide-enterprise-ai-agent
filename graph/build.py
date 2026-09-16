# graph/build.py
# 組出實際的 StateGraph：
#
#   START → agent ⇄ tools（LLM 持續要求呼叫工具就一直迴圈）
#             │
#             ├─ 沒有工具呼叫、沒有待核准草稿 → END（純粹回答）
#             └─ 沒有工具呼叫、有待核准草稿   → approval
#                                                 │
#                                        interrupt() 在這裡真正暫停
#                                                 │
#                                  ┌────── reject → END
#                                  └────── approve → execute → END
#
# execute 節點只有一條入邊，來自 approval 的 approve 分支：
# 見 tests/test_graph_safety.py。

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from graph.nodes import (
    agent_node,
    approval_node,
    execute_node,
    route_after_agent,
    route_after_approval,
    tools_node,
)
from graph.state import AgentState


def build_graph(checkpointer=None):
    g = StateGraph(AgentState)
    g.add_node("agent", agent_node)
    g.add_node("tools", tools_node)
    g.add_node("approval", approval_node)
    g.add_node("execute", execute_node)

    g.add_edge(START, "agent")
    g.add_conditional_edges(
        "agent", route_after_agent, {"tools": "tools", "approval": "approval", "end": END}
    )
    g.add_edge("tools", "agent")
    g.add_conditional_edges(
        "approval", route_after_approval, {"execute": "execute", "end": END}
    )
    g.add_edge("execute", END)

    return g.compile(checkpointer=checkpointer or InMemorySaver())


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
