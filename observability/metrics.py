# observability/metrics.py
# Prometheus 指標。預設完全關閉（ENABLE_METRICS 沒設就什麼事都不做），
# 符合「不要為了裝而裝」——只有設定 ENABLE_METRICS=true 才會在本機開一個
# /metrics endpoint，docker-compose 裡的 Prometheus 容器會透過
# host.docker.internal 連進來 scrape。

import os
import threading

try:
    from prometheus_client import Counter, Histogram, start_http_server
    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False

METRICS_ENABLED = os.environ.get("ENABLE_METRICS", "").strip().lower() in ("1", "true", "yes")
METRICS_PORT = int(os.environ.get("METRICS_PORT", "8000"))


class _NoOpMetric:
    """prometheus_client 沒裝，或 ENABLE_METRICS 沒開時的空實作，
    讓呼叫端程式碼不用到處包 if，永遠可以放心呼叫 .labels()/.inc()/.observe()。"""

    def labels(self, *args, **kwargs):
        return self

    def inc(self, *args, **kwargs):
        pass

    def observe(self, *args, **kwargs):
        pass


if _PROM_AVAILABLE:
    agent_requests_total = Counter("agent_requests_total", "Agent 對話輪數（ask() 呼叫次數）")
    tool_calls_total = Counter("tool_calls_total", "工具呼叫次數", ["tool"])
    tool_errors_total = Counter("tool_errors_total", "工具呼叫失敗次數", ["tool"])
    tool_latency_seconds = Histogram("tool_latency_seconds", "工具執行耗時（秒）", ["tool"])
    approval_requested_total = Counter("approval_requested_total", "產生待核准草稿的次數")
    approval_decisions_total = Counter("approval_decisions_total", "核准/拒絕決定次數", ["decision"])
    permission_denied_total = Counter("permission_denied_total", "RBAC 拒絕次數", ["tool", "role"])
else:
    agent_requests_total = _NoOpMetric()
    tool_calls_total = _NoOpMetric()
    tool_errors_total = _NoOpMetric()
    tool_latency_seconds = _NoOpMetric()
    approval_requested_total = _NoOpMetric()
    approval_decisions_total = _NoOpMetric()
    permission_denied_total = _NoOpMetric()

_server_started = False
_lock = threading.Lock()


def start_metrics_server() -> None:
    global _server_started
    if not (METRICS_ENABLED and _PROM_AVAILABLE):
        return
    with _lock:
        if _server_started:
            return
        start_http_server(METRICS_PORT)
        _server_started = True
