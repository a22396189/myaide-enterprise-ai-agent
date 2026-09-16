# evals/run_evals.py
# 迴歸用的評測指令：
#   python evals/run_evals.py                # 預設 --fake-llm，免 API Key，驗證套件機制本身
#   python evals/run_evals.py --live          # 對真正的 Gemini 跑，量測真實模型的工具選擇能力
#
# 不管哪種模式，send_gmail / create_calendar_event 一律被 mock 掉——
# 評測是要量測「Agent 做的決定對不對」，不是真的要寄信/建行程，
# 不然每跑一次評測就會真的寄出測試郵件，這是不可接受的副作用。
#
# 輸出：
#   evals/report.json   機器可讀
#   console 摘要表        人看的

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import graph.nodes as nodes
from evals.datasets.core_cases import CASES, EvalCase
from evals.evaluators import evaluate_case
from graph.build import build_graph


class _StubTool:
    """輕量替身，只提供 tools_node 需要的 .invoke()，用來在 fake-llm 模式下
    頂替會打真實外部服務（Gmail OAuth、Embeddings API）的工具，避免評測套件
    本身變成需要一堆帳號才能跑。"""

    def __init__(self, output: str):
        self._output = output

    def invoke(self, args):
        return self._output


class _ScriptedLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def invoke(self, messages):
        if not self._responses:
            raise RuntimeError("腳本化回應用完了，案例的 fake_responses 不夠長")
        return self._responses.pop(0)


def _run_one_case(case: EvalCase, live: bool) -> dict:
    with contextlib.ExitStack() as stack:
        if not live:
            stack.enter_context(patch.object(nodes, "_get_llm", return_value=_ScriptedLLM(case.fake_responses)))
        # 注意：graph/nodes.py 是用 `from tools.x import y` 把工具物件直接
        # import 進自己的命名空間並放進 TOOLS_BY_NAME，所以 patch 原始模組
        # 路徑對已經 import 進來的物件參照沒有效果。改成直接把
        # TOOLS_BY_NAME 這個 dict 裡對應的值換成一個假物件——LangChain 的
        # 工具是 pydantic model instance，不允許事後幫它加/改 .invoke
        # 屬性（會丟 AttributeError），所以不能用 patch.object 改屬性，
        # 只能整個換掉 dict 裡的值。
        if case.fake_tool_stub:
            stubbed = dict(nodes.TOOLS_BY_NAME)
            for tool_name, stub_output in case.fake_tool_stub.items():
                stubbed[tool_name] = _StubTool(stub_output)
            stack.enter_context(patch.object(nodes, "TOOLS_BY_NAME", stubbed))

        # 評測一律不觸發真正的寄信／建立行程
        stack.enter_context(patch.object(nodes, "send_gmail", return_value="（評測模式，未真的寄出）"))
        stack.enter_context(patch.object(nodes, "create_calendar_event", return_value="（評測模式，未真的建立）"))

        g = build_graph(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": f"eval-{case.name}", "user": "eval", "role": case.role}}

        first_result = g.invoke({
            "messages": [("human", case.input)],
            "pending_action": None, "approval_decision": None, "execution_result": None,
        }, config=config)

        final_result = first_result
        if first_result.get("__interrupt__"):
            final_result = g.invoke(Command(resume={"decision": "approve", "params": None}), config=config)

        return evaluate_case(case, final_result["messages"], first_result, final_result)


def main():
    parser = argparse.ArgumentParser(description="MyAide 迴歸評測")
    parser.add_argument("--live", action="store_true", help="對真正的 Gemini 跑（需要 GOOGLE_API_KEY，會消耗額度）")
    args = parser.parse_args()

    mode = "live" if args.live else "fake-llm"
    print(f"執行模式：{mode}（{len(CASES)} 個案例）\n")

    results = []
    for case in CASES:
        try:
            results.append(_run_one_case(case, live=args.live))
        except Exception as e:
            results.append({"name": case.name, "category": case.category, "passed": False,
                             "checks": {}, "error": str(e)})

    total = len(results)
    passed = sum(1 for r in results if r["passed"])

    print(f"{'案例':32} {'分類':16} 結果")
    print("-" * 64)
    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"{r['name']:32} {r['category']:16} {mark}")
        if not r["passed"]:
            failed_checks = [k for k, v in r.get("checks", {}).items() if not v]
            if failed_checks:
                print(f"  未通過：{', '.join(failed_checks)}")
            if r.get("error"):
                print(f"  錯誤：{r['error']}")

    print("-" * 64)
    print(f"總計：{passed}/{total} 通過\n")

    report = {"mode": mode, "total": total, "passed": passed, "results": results}
    report_path = Path(__file__).parent / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"詳細報告已寫入 {report_path}")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
