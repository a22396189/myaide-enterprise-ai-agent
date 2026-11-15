# ui_render.py
# 對話畫面上「Agent 回答」「引用來源」與「Agent 思考過程」的顯示處理。
#
# 從 app.py 抽出來，是為了能在不啟動 Streamlit 的情況下單元測試
# （見 tests/test_ui_render_escape.py、tests/test_neutralize_links.py）。
#
# 兩種不可信內容、兩種處理：
#   1. render_* 產生的 HTML 片段：內容來自工具輸入／輸出（Email、網頁、知識庫
#      文字），app.py 以 unsafe_allow_html=True 渲染，所以每個動態欄位都必須
#      先 html.escape（並把換行轉成 <br>，見 _esc），否則外部文字可注入假連結、
#      假表單到助理介面。
#   2. neutralize_links：Agent 的最終回答是 Markdown。模型可能把郵件／網頁裡的
#      釣魚網址整理成可點的連結，等於由助理替它背書；不在白名單網域的連結
#      一律改成不可點的純文字網址。

import html
import re
from urllib.parse import urlsplit

from config import ALLOWED_LINK_DOMAINS

_TOOL_BADGE_CLASS = {
    "web_search": "web",
    "calculate": "calc",
    "list_database_tables": "sql",
    "run_sql_query": "sql",
    "search_email": "mail",
    "draft_email": "mail",
    "list_calendar_events": "cal",
    "draft_calendar_event": "cal",
}

# 輸出內容由外部第三方決定的工具：郵件任何人都能寄、網頁任何人都能寫、
# 行事曆邀請也可由外部人士發出。知識庫與資料庫屬公司內部資料，不在此列。
EXTERNAL_CONTENT_TOOLS = {
    "search_email": "郵件",
    "web_search": "網頁",
    "list_calendar_events": "行事曆",
}


def _esc(value) -> str:
    """轉義後再把換行換成 <br>。

    只做 html.escape 不夠：工具輸出裡的空行會讓 Markdown 結束 HTML 區塊，
    空行之後的文字重新被當成 Markdown 解析，`[點我](https://evil)` 這類
    語法又會變成可點連結。換成 <br> 後，整張卡片維持在同一個 HTML 區塊內。
    """
    text = html.escape(str(value))
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def render_tool_badge(tool_name):
    cls = _TOOL_BADGE_CLASS.get(tool_name, "")
    return f'<span class="step-tool-badge {cls}">{_esc(tool_name)}</span>'


def render_sources(sources):
    if not sources:
        return ""
    tags = "".join(f'<span class="source-tag">{_esc(s)}</span>' for s in sources)
    return f'<div class="source-row"><span class="source-label">引用來源</span>{tags}</div>'


def render_steps(steps):
    if not steps:
        return ""
    items = ""
    for i, step in enumerate(steps, 1):
        badge = render_tool_badge(step["tool"])
        external_kind = EXTERNAL_CONTENT_TOOLS.get(step["tool"])
        card_cls = "step-card external" if external_kind else "step-card"
        note = (
            f'<div class="step-external-note">⚠️ 外部內容（{external_kind}），未經驗證——'
            f'其中的連結與指示不代表本系統的建議，請勿直接照做</div>'
            if external_kind else ""
        )
        items += f"""
        <div class="{card_cls}">
            <div class="step-header">步驟 {i} &nbsp; {badge}</div>
            {note}
            <div class="step-io">
                <span class="step-io-label">輸入：</span>{_esc(step['input'])}<br>
                <span class="step-io-label">輸出：</span>{_esc(step['output'])}
            </div>
        </div>"""
    return items


# ── 回答中的連結處理 ──────────────────────────────────────────

# 既有的程式碼區塊與行內程式碼：裡面的網址本來就不可點，原樣保留不處理。
_CODE_RE = re.compile(r"(```.*?```|~~~.*?~~~|`[^`\n]*`)", re.S)
# [文字](網址 "標題") 與圖片 ![替代文字](網址)
_MD_LINK_RE = re.compile(r"(!?)\[([^\]\n]*)\]\(\s*<?([^)\s>]*)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
# 參考式連結定義：[ref]: 網址
_REF_DEF_RE = re.compile(r"^( {0,3}\[[^\]\n]+\]:[ \t]*)<?(\S+?)>?([ \t].*)?$", re.M)
# <https://...> 自動連結
_AUTOLINK_RE = re.compile(r"<((?:https?|ftp)://[^>\s]+)>", re.I)
# 裸網址（GFM 會自動轉成連結）
# 網址在空白、全形標點與暫存佔位符（\x00）處結束，避免把「，請點擊」吃進網址。
_BARE_URL_RE = re.compile(
    "(?<![\\w/@.])((?:https?://|ftp://|www\\.)[^\\s<>`\x00（）「」『』【】《》〈〉，。；：！？、]+)",
    re.I,
)
_TRAILING_PUNCT = ".,;:!?)]}'\"）」』】。，；：！？"
_PLACEHOLDER_RE = re.compile("\x00(\\d+)\x00")


def is_allowed_link(url: str, allowed_domains=None) -> bool:
    """只有 http(s) 且主機名稱屬於白名單網域（含子網域）的連結才保留可點。"""
    domains = ALLOWED_LINK_DOMAINS if allowed_domains is None else allowed_domains
    if not domains:
        return False
    candidate = url if "://" in url else f"http://{url}"
    try:
        parts = urlsplit(candidate)
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    if parts.scheme.lower() not in ("http", "https") or not host:
        return False
    # hostname 已去除 userinfo，https://good.com@evil.com 會被判定為 evil.com
    return any(host == d or host.endswith("." + d) for d in domains)


def _code(url: str) -> str:
    # 行內程式碼不會被自動轉成連結；網址裡的反引號會破壞程式碼標記，直接移除。
    return f"`{url.replace('`', '')}`"


def neutralize_links(markdown_text: str, allowed_domains=None) -> str:
    """把 Markdown 回答裡不在白名單網域的連結改成不可點的純文字網址。

    - [文字](網址)        → 文字（`網址`）
    - ![替代文字](網址)    → [圖片：替代文字]（`網址`）（外部圖片也會洩漏瀏覽紀錄）
    - <網址>、裸網址       → `網址`
    - [ref]: 網址         → 網址改成純文字，參考式連結因此無法解析
    白名單網域的連結原樣保留。程式碼區塊與行內程式碼內的內容不處理。
    """
    if not markdown_text:
        return markdown_text or ""

    text = str(markdown_text).replace("\x00", "")
    held: list[str] = []

    def hold(s: str) -> str:
        held.append(s)
        return f"\x00{len(held) - 1}\x00"

    def allowed(url: str) -> bool:
        return is_allowed_link(url, allowed_domains)

    def md_link(m: re.Match) -> str:
        bang, label, url = m.group(1), m.group(2), m.group(3)
        if url and allowed(url):
            return hold(m.group(0))
        shown = hold(_code(url)) if url else ""
        if bang:
            return f"[圖片：{label}]（{shown}）" if shown else f"[圖片：{label}]"
        if not shown or label.strip() == url:
            return label if not shown else shown
        # 連結文字保留在文字流中，後面的裸網址處理也會檢查它
        # （例如 [https://good.com](https://evil.com) 這種偽裝）。
        return f"{label}（{shown}）"

    def ref_def(m: re.Match) -> str:
        url = m.group(2)
        if allowed(url):
            return hold(m.group(0))
        return f"[參考連結]：{hold(_code(url))}{m.group(3) or ''}"

    def autolink(m: re.Match) -> str:
        url = m.group(1)
        return hold(m.group(0)) if allowed(url) else hold(_code(url))

    def bare(m: re.Match) -> str:
        url = m.group(1)
        trail = ""
        while url and url[-1] in _TRAILING_PUNCT:
            trail = url[-1] + trail
            url = url[:-1]
        if not url or allowed(url):
            return m.group(0)
        return hold(_code(url)) + trail

    def process(segment: str) -> str:
        segment = _MD_LINK_RE.sub(md_link, segment)
        segment = _REF_DEF_RE.sub(ref_def, segment)
        segment = _AUTOLINK_RE.sub(autolink, segment)
        segment = _BARE_URL_RE.sub(bare, segment)
        return segment

    out = []
    for i, part in enumerate(_CODE_RE.split(text)):
        out.append(part if i % 2 else process(part))
    result = "".join(out)

    # 還原暫存的片段（可能巢狀，重複到沒有佔位符為止）
    while _PLACEHOLDER_RE.search(result):
        result = _PLACEHOLDER_RE.sub(lambda m: held[int(m.group(1))], result)
    return result
