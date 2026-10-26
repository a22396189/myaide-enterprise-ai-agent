# graph/studio.py
# LangGraph Studio 的進入點（langgraph.json 指向這裡的 `graph`）。
#
# 執行：langgraph dev   → 本機 Agent Server（http://127.0.0.1:2024），
# 再用瀏覽器開 LangGraph Studio 連上它，就能看到由 graph/build.py 的
# nodes / edges 自動畫出的流程圖，並逐步檢視每個節點的輸入、輸出與 State。
#
# 和 Streamlit 共用同一份 graph 定義（build_state_graph），只差在這裡不帶
# checkpointer：Agent Server 會自己管理 thread 與 checkpoint。

import os
import tomllib
from pathlib import Path

from graph.build import build_state_graph

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Streamlit 從 .streamlit/secrets.toml 讀 API Key；Agent Server 不會讀這個檔，
# 所以環境變數沒設時，從同一個檔案補上，不必把金鑰再寫進另一個 .env。
if not os.environ.get("GOOGLE_API_KEY"):
    _secrets = _PROJECT_ROOT / ".streamlit" / "secrets.toml"
    if _secrets.exists():
        _key = tomllib.loads(_secrets.read_text(encoding="utf-8")).get("GOOGLE_API_KEY")
        if _key:
            os.environ["GOOGLE_API_KEY"] = _key

# 工具裡的 ./chroma_db、./enterprise_data、./logs 都是相對路徑，
# 確保從專案根目錄解析（langgraph dev 在其他目錄啟動時也正確）。
os.chdir(_PROJECT_ROOT)

graph = build_state_graph().compile()
