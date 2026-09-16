# security/audit.py
# 單一路徑的稽核紀錄：誰（user/role）、對什麼（tool/resource）、
# 做了什麼決定（allowed/denied/executed）、什麼時候。
# 刻意只記截斷後的參數摘要，不整段記錄郵件內文/SQL結果——稽核紀錄本身
# 也可能外洩敏感資料，記錄「這件事發生過」比記錄「完整內容」重要。

import json
import time
from pathlib import Path

AUDIT_LOG_PATH = Path("./logs/audit.jsonl")
_MAX_PAYLOAD_CHARS = 200


def _truncate(value) -> str:
    text = str(value)
    return text if len(text) <= _MAX_PAYLOAD_CHARS else text[:_MAX_PAYLOAD_CHARS] + "…（已截斷）"


def record(*, user: str, role: str, tool: str, decision: str, detail: str = "") -> None:
    """decision 例如："allowed" | "denied" | "executed" | "error" """
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "user": user,
        "role": role,
        "tool": tool,
        "decision": decision,
        "detail": _truncate(detail),
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
