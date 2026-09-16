# tools/knowledge_base.py
# RAG 工具：對內部文件向量索引（Chroma）做語意檢索。
#
# P5 加了兩件事：
#   1. 角色過濾——每份文件的 metadata 有 allowed_roles，只把目前使用者
#      角色能看的文件交給 LLM，機密文件不會因為換個問法就洩漏出去。
#      角色是由 graph/nodes.py 的 tools_node 在呼叫這個工具「之前」用
#      set_current_role() 設定的，這裡不暴露成 @tool 的參數——不能讓
#      LLM 自己選要用哪個角色查詢。
#   2. Rerank——先撈比較多候選（fetch_k），角色過濾後交給
#      tools/reranker.py 的 cross-encoder 重新排序，取前 4 筆。

import os

from langchain_community.vectorstores import Chroma
from langchain_core.tools import tool
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from tools.reranker import rerank

CHROMA_DIR = "./chroma_db"
COLLECTION = "company_knowledge"
FETCH_K = 12
TOP_K = 4

_embeddings = None
_vectorstore = None

# single-threaded 的 Streamlit + LangGraph 應用，用簡單模組全域變數
# 就足夠safely傳遞「這一次工具呼叫是哪個角色發起的」，不需要 contextvars。
_current_role = "admin"


def set_current_role(role: str) -> None:
    global _current_role
    _current_role = role or "admin"


def _get_vectorstore():
    global _embeddings, _vectorstore
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key or api_key == "your-api-key-here":
        raise ValueError("請先在側邊欄設定有效的 Google API Key。")
    if _vectorstore is None:
        _embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=api_key,
        )
        _vectorstore = Chroma(
            collection_name=COLLECTION,
            embedding_function=_embeddings,
            persist_directory=CHROMA_DIR,
        )
    return _vectorstore


def _role_can_see(doc, role: str) -> bool:
    allowed = doc.metadata.get("allowed_roles", "*")
    return allowed == "*" or role in allowed.split(",")


@tool
def search_knowledge_base(query: str) -> str:
    """搜尋企業內部知識庫，包含公司規章、內部系統操作手冊、常見問題集等文件。
    當問題涉及公司政策、規定、系統操作、設備問題時，必須使用此工具。
    """
    candidates = _get_vectorstore().similarity_search(query, k=FETCH_K)
    visible = [d for d in candidates if _role_can_see(d, _current_role)]
    if not visible:
        return "知識庫中找不到相關資訊。"

    docs = rerank(query, visible, top_k=TOP_K)

    results = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("display_name", doc.metadata.get("source", "未知來源"))
        content = doc.page_content.strip()
        results.append(f"[來源 {i}：{source}]\n{content}")

    return "\n\n---\n\n".join(results)
