# tests/test_package_turn_scope.py
# _package() 只能整理「本輪」的訊息：checkpointer 會保存整段對話，
# 前幾輪的工具步驟、引用來源與回答不得混入本輪結果。

import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent import _package


def _first_turn():
    return [
        HumanMessage(content="Q1"),
        AIMessage(content="", tool_calls=[{"id": "c1", "name": "search_knowledge_base", "args": {"query": "q1"}}]),
        ToolMessage(content="內容\n[來源：A.pdf]", tool_call_id="c1", name="search_knowledge_base"),
        AIMessage(content="第一輪回答"),
    ]


class PackageTurnScopeTest(unittest.TestCase):
    def test_previous_turn_not_leaked_when_current_turn_empty(self):
        messages = _first_turn() + [HumanMessage(content="Q2"), AIMessage(content="")]
        out = _package({"messages": messages})
        self.assertEqual(out["steps"], [])
        self.assertEqual(out["sources"], [])
        self.assertIsNone(out["answer"])

    def test_only_current_turn_steps_and_sources(self):
        messages = _first_turn() + [
            HumanMessage(content="Q2"),
            AIMessage(content="", tool_calls=[{"id": "c2", "name": "search_knowledge_base", "args": {"query": "q2"}}]),
            ToolMessage(content="內容\n[來源：B.pdf]", tool_call_id="c2", name="search_knowledge_base"),
            AIMessage(content="第二輪回答"),
        ]
        out = _package({"messages": messages})
        self.assertEqual(len(out["steps"]), 1)
        self.assertEqual(out["steps"][0]["input"], {"query": "q2"})
        self.assertEqual(out["sources"], ["B.pdf"])
        self.assertEqual(out["answer"], "第二輪回答")


if __name__ == "__main__":
    unittest.main()
