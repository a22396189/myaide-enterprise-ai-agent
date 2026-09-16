# observability/logging_config.py
# 結構化（JSON lines）log，取代散落的 print()。每個 graph 節點執行、
# 每次工具呼叫都應該留下一筆可以被機器解析的紀錄（node、延遲、成功/失敗），
# 而不是只有人看得懂的一句話。同時輸出到 stdout（本機開發看得到）與
# logs/agent.jsonl（可以餵給日後接的任何 log 系統）。

import json
import logging
import time
from pathlib import Path

LOG_PATH = Path("./logs/agent.jsonl")

_configured = False


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    formatter = _JsonFormatter()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)

    root = logging.getLogger("myaide")
    root.setLevel(logging.INFO)
    root.handlers = [stream_handler, file_handler]
    root.propagate = False

    _configured = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"myaide.{name}")


def log_event(logger: logging.Logger, message: str, **fields) -> None:
    logger.info(message, extra={"extra_fields": fields})
