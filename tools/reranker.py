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

import os

from observability.logging_config import get_logger

_logger = get_logger("reranker")

# 原本用英文模型 cross-encoder/ms-marco-MiniLM-L-6-v2，但知識庫是中文文件：
# 2026-10 以 8 題中文查詢量測正確段落是否進前 4 名（Recall@4），
#   不 rerank 8/8 · ms-marco（英文）5/8 · bge-reranker-base 8/8（CPU 約 4 秒/題）
#   · bge-reranker-v2-m3 8/8（約 15 秒/題）
# 英文模型反而把正確段落擠出前 4 名，因此改用多語模型 bge-reranker-base。
# 設 RERANKER_MODEL=none 可關閉 rerank，直接用向量檢索順序。
_MODEL_NAME = os.environ.get("RERANKER_MODEL", "BAAI/bge-reranker-base")
_model = None
_load_failed = False


def _get_model():
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    if _MODEL_NAME.lower() == "none":
        _load_failed = True  # 視同不可用：rerank() 會直接回傳原始順序
        return None
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
