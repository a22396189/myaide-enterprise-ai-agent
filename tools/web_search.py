# tools/web_search.py
# 外部公開資訊搜尋工具（DuckDuckGo）。

from ddgs import DDGS
from langchain_core.tools import tool


@tool
def web_search(query: str) -> str:
    """搜尋網際網路上的公開資訊。
    當公司知識庫中找不到相關資訊，或問題涉及外部法規、市場資訊、一般知識時，使用此工具。
    不適合用於查詢公司內部政策或機密資訊。
    重要：請將 query 翻譯成英文再搜尋，效果更好。例如「地震時設備斷電」→「earthquake equipment shutdown procedure」。
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results:
            return "找不到相關網路資料。"
        return "\n\n---\n\n".join(
            f"[{r['title']}]\n{r['body']}\n\n來源：{r['href']}"
            for r in results
        )
    except Exception as e:
        return f"網路搜尋失敗：{e}"
