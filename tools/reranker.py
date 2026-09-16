# tools/reranker.py
# 用本機 cross-encoder 對候選文件重新排序，取代單純依賴 Chroma 向量
# 相似度（MMR）排出來的順序。刻意選本機模型（sentence-transformers）
# 而不是雲端付費 rerank API——不需要額外帳號/金鑰，符合這個專案「能在
# 本機跑起來」的定位。
#
# 模型第一次使用時才會延遲載入／下載（跟 tools/knowledge_base.py 的
# retriever、graph/nodes.py 的 LLM 一樣的 lazy-init 模式）。如果套件沒裝
# 好、或模型下載失敗，rerank() 會記一筆警告並直接把原始順序原封不動退回
# ——重新排序失敗不應該讓整個知識庫查詢掛掉。

from __future__ import annotations

from observability.logging_config import get_logger

_logger = get_logger("reranker")

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_model = None
_load_failed = False


def _get_model():
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    try:
        from sentence_transformers import CrossEncoder
        _model = CrossEncoder(_MODEL_NAME)
    except Exception as e:
        _load_failed = True
        _logger.warning(f"reranker 模型載入失敗，改用原始檢索順序：{e}")
    return _model


def rerank(query: str, docs: list, top_k: int = 4) -> list:
    """docs 是 langchain Document 物件的 list。回傳重新排序後的前 top_k 筆；
    模型不可用時原封不動回傳前 top_k 筆（等於沒有 rerank，但不會出錯）。"""
    if not docs:
        return docs

    model = _get_model()
    if model is None:
        return docs[:top_k]

    try:
        pairs = [(query, d.page_content) for d in docs]
        scores = model.predict(pairs)
        ranked = [doc for _, doc in sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)]
        return ranked[:top_k]
    except Exception as e:
        _logger.warning(f"reranker 執行失敗，改用原始檢索順序：{e}")
        return docs[:top_k]
