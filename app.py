# app.py
import os
import uuid
import streamlit as st
from agent import ask, confirm
from auth.users import DEFAULT_USER, DEMO_USERS
from config import APP_SUBTITLE, APP_TITLE, COMPANY_NAME
from observability.metrics import start_metrics_server
from tools.recipients import parse_emails
# 注意：這裡刻意不 import send_gmail / create_calendar_event。
# 這兩個具有真實副作用的函式只存在於 graph/nodes.py 的 execute 節點裡，
# 只有 graph 本身在人工核准後才會呼叫；UI 只透過 agent.confirm() 觸發 graph
# 恢復執行，UI 自己完全沒有能力直接寄信或建立行程。

# 只有設定 ENABLE_METRICS=true 才會真的開 /metrics endpoint（P4）
start_metrics_server()

st.set_page_config(
    page_title=f"{COMPANY_NAME} · {APP_TITLE}",
    page_icon="🏢",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────
st.markdown("""
<style>
/* ── 全域字型與背景 ── */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans TC', -apple-system, BlinkMacSystemFont, sans-serif;
}

.stApp {
    background-color: #F7F8FA;
}

/* ── 隱藏 Streamlit 預設元素 ── */
/* 注意：不能用 `header { visibility: hidden }` 整個隱藏 header——
   側邊欄收合後的「展開」按鈕（stExpandSidebarButton）就長在 header 裡，
   visibility 會被子元素繼承，隱藏 header 等於使用者一旦收合側邊欄
   就再也點不到展開按鈕。改成只隱藏選單／Deploy 按鈕，header 本身
   保留（只是背景透明），讓收合/展開按鈕維持可見可點。 */
#MainMenu, footer, [data-testid="stAppDeployButton"] { visibility: hidden; }
[data-testid="stHeader"] { background: transparent; }
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 780px !important;
}

/* ── 主區塊文字放大 ── */
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] span {
    font-size: 1.05rem !important;
    line-height: 1.85 !important;
}
[data-testid="stMarkdownContainer"] p {
    font-size: 1.05rem;
    line-height: 1.85;
}

/* ── 頂部 Header ── */
.app-header {
    background: linear-gradient(135deg, #0F3460 0%, #1A6B9A 100%);
    color: white;
    padding: 1.2rem 2rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 1rem;
}
.app-header-title {
    font-size: 1.4rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    margin: 0;
}
.app-header-sub {
    font-size: 0.78rem;
    opacity: 0.75;
    margin: 0.2rem 0 0 0;
    letter-spacing: 0.03em;
}
.header-badge {
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.3);
    border-radius: 6px;
    padding: 0.2rem 0.6rem;
    font-size: 0.7rem;
    font-weight: 500;
    letter-spacing: 0.05em;
    white-space: nowrap;
}

/* ── 歡迎卡片 ── */
.welcome-card {
    background: white;
    border: 1px solid #E2E8F0;
    border-left: 4px solid #1A6B9A;
    border-radius: 10px;
    padding: 1.2rem 1.5rem;
    color: #334155;
    font-size: 0.92rem;
    line-height: 1.7;
    margin-bottom: 1rem;
}

/* ── 對話泡泡 ── */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    padding: 0.3rem 0 !important;
}

/* user 訊息 */
[data-testid="stChatMessage"][data-testid*="user"],
.stChatMessage:has([data-testid="chatAvatarIcon-user"]) {
    background: transparent !important;
}

/* ── 來源標籤 ── */
.source-tag {
    display: inline-block;
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    color: #1D4ED8;
    border-radius: 20px;
    padding: 0.15rem 0.65rem;
    font-size: 0.72rem;
    font-weight: 500;
    margin: 0 0.25rem 0.25rem 0;
}
.source-row {
    margin-top: 0.5rem;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.1rem;
}
.source-label {
    font-size: 0.72rem;
    color: #94A3B8;
    margin-right: 0.3rem;
}

/* ── Agent 步驟 ── */
.step-card {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.6rem;
    font-size: 0.82rem;
}
.step-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
    font-weight: 600;
    color: #334155;
}
.step-tool-badge {
    background: #0F3460;
    color: white;
    border-radius: 4px;
    padding: 0.1rem 0.5rem;
    font-size: 0.68rem;
    font-family: monospace;
    letter-spacing: 0.02em;
}
.step-tool-badge.web {
    background: #0D6E3B;
}
.step-tool-badge.calc {
    background: #7C3AED;
}
.step-tool-badge.sql {
    background: #B45309;
}
.step-tool-badge.mail {
    background: #0E7490;
}
.step-tool-badge.cal {
    background: #BE185D;
}

/* ── 待確認動作卡片 ── */
.pending-action-card {
    background: #FFFBEB;
    border: 1px solid #FCD34D;
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin: 0.6rem 0;
}
.pending-action-title {
    font-weight: 600;
    color: #92400E;
    margin-bottom: 0.5rem;
    font-size: 0.9rem;
}
.step-io {
    color: #64748B;
    line-height: 1.5;
}
.step-io-label {
    font-weight: 600;
    color: #475569;
}

/* ── Sidebar 樣式 ── */
[data-testid="stSidebar"] {
    background-color: #FFFFFF !important;
    border-right: 1px solid #E2E8F0 !important;
}
[data-testid="stSidebar"] .block-container {
    padding-top: 1rem;
}
.sidebar-logo {
    font-size: 0.95rem;
    font-weight: 600;
    color: #0F3460;
    padding: 0.5rem 0;
    border-bottom: 2px solid #0F3460;
    margin-bottom: 1.2rem;
    letter-spacing: 0.02em;
}
.sidebar-section-title {
    font-size: 0.72rem;
    font-weight: 600;
    color: #94A3B8;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 1.2rem 0 0.6rem 0;
}
.kb-item {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 0.6rem 0.8rem;
    margin-bottom: 0.4rem;
    font-size: 0.82rem;
    color: #334155;
}
.kb-item-title {
    font-weight: 600;
    color: #0F3460;
    margin-bottom: 0.2rem;
    font-size: 0.83rem;
}
.kb-item-sub {
    color: #64748B;
    font-size: 0.75rem;
    line-height: 1.5;
}

/* ── 範例問題按鈕 ── */
.stButton > button {
    background: #F8FAFC !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    color: #334155 !important;
    font-size: 0.8rem !important;
    text-align: left !important;
    padding: 0.5rem 0.8rem !important;
    transition: all 0.15s ease !important;
    font-family: 'Noto Sans TC', sans-serif !important;
}
.stButton > button:hover {
    background: #EFF6FF !important;
    border-color: #93C5FD !important;
    color: #1D4ED8 !important;
    transform: translateX(2px) !important;
}

/* ── 清除按鈕特殊樣式 ── */
.clear-btn > button {
    background: transparent !important;
    border: 1px solid #FCA5A5 !important;
    color: #DC2626 !important;
    font-size: 0.78rem !important;
}
.clear-btn > button:hover {
    background: #FEF2F2 !important;
    border-color: #F87171 !important;
    color: #B91C1C !important;
    transform: none !important;
}

/* ── API Key 輸入 ── */
.api-section {
    background: #FFFBEB;
    border: 1px solid #FCD34D;
    border-radius: 8px;
    padding: 0.8rem;
    margin-bottom: 1rem;
    font-size: 0.8rem;
    color: #92400E;
}

/* ── Chat input ── */
[data-testid="stChatInput"] textarea {
    border-radius: 10px !important;
    border: 1.5px solid #CBD5E1 !important;
    font-family: 'Noto Sans TC', sans-serif !important;
    font-size: 0.9rem !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: #1A6B9A !important;
    box-shadow: 0 0 0 3px rgba(26, 107, 154, 0.1) !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    background: #FAFBFC !important;
}
[data-testid="stExpander"] summary {
    font-size: 0.82rem !important;
    color: #64748B !important;
    font-weight: 500 !important;
}

/* ── Spinner ── */
.stSpinner > div {
    border-top-color: #1A6B9A !important;
}
</style>
""", unsafe_allow_html=True)

# ── API Key ───────────────────────────────────────────
# API Key 屬於部署層級的基礎設施密鑰，正式環境應由管理員透過
# .streamlit/secrets.toml 或環境變數設定，一般使用者完全不需要、
# 也不應該看到輸入框。只有在兩者都沒設定時，才顯示手動輸入框，
# 且明確標示僅供本機個人測試使用——避免有人誤把這個輸入框部署給
# 多人共用（os.environ 是整個伺服器行程共用的全域狀態，不是
# per-user session，多人共用時第一個輸入的 key 會被所有人沿用）。
def _get_configured_api_key() -> str | None:
    try:
        if "GOOGLE_API_KEY" in st.secrets:
            return st.secrets["GOOGLE_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GOOGLE_API_KEY") or None


_configured_api_key = _get_configured_api_key()
if _configured_api_key:
    os.environ["GOOGLE_API_KEY"] = _configured_api_key
else:
    with st.sidebar:
        st.markdown(
            '<div class="api-section">⚠️ 本機開發模式：尚未由管理員設定 API Key<br>'
            '<span style="font-weight:400;opacity:0.85">'
            '正式部署請改用 .streamlit/secrets.toml 或環境變數設定，'
            '此輸入框僅供個人測試，不應部署給多人共用</span></div>',
            unsafe_allow_html=True,
        )
        api_key = st.text_input("Google API Key", type="password", placeholder="AIza...", label_visibility="collapsed")
        if api_key:
            os.environ["GOOGLE_API_KEY"] = api_key
            st.success("已設定完成（僅本機測試用）")

# ── 使用者／角色（P2，Demo 登入）──────────────────────
# 不是真的身分驗證（沒有密碼），只是讓 RBAC 的「權限依角色而定」能在
# UI 上被示範與測試。真正的權限判斷在 graph/nodes.py 的 tools_node 裡
# 伺服器端強制執行，換角色不是「換個說法騙過提示詞」就能繞過的。
if "current_user" not in st.session_state:
    st.session_state.current_user = DEFAULT_USER

with st.sidebar:
    st.markdown('<div class="sidebar-section-title">使用者（Demo 登入）</div>', unsafe_allow_html=True)
    selected_user = st.selectbox(
        "使用者", options=list(DEMO_USERS.keys()),
        index=list(DEMO_USERS.keys()).index(st.session_state.current_user),
        label_visibility="collapsed",
    )
    if selected_user != st.session_state.current_user:
        # 換人＝換身分，連同對話狀態一起重置，避免把上一位使用者的
        # 對話上下文／待核准草稿帶到新的角色底下
        st.session_state.current_user = selected_user
        st.session_state.messages = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()
    st.markdown(
        f'<div class="kb-item-sub" style="margin:-6px 0 8px">目前角色：<strong>{DEMO_USERS[st.session_state.current_user]}</strong></div>',
        unsafe_allow_html=True,
    )

# ── Sidebar ───────────────────────────────────────────
with st.sidebar:
    st.markdown(f'<div class="sidebar-logo">{COMPANY_NAME} · {APP_TITLE}</div>', unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section-title">知識庫範圍</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="kb-item">
        <div class="kb-item-title">公司規章手冊</div>
        <div class="kb-item-sub">請假、薪資績效、資安規範<br>差旅報銷、廠區安全與品質</div>
    </div>
    <div class="kb-item">
        <div class="kb-item-title">MES 操作手冊（範例）</div>
        <div class="kb-item-sub">工單與首件檢驗、批號追溯<br>品質異常處理、設備保養</div>
    </div>
    <div class="kb-item">
        <div class="kb-item-title">常見問題集</div>
        <div class="kb-item-sub">員工福利、IT 支援<br>獎金計算、採購請購</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section-title">企業資料庫</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="kb-item">
        <div class="kb-item-title">訂單／客戶／產品</div>
        <div class="kb-item-sub">SQL 唯讀查詢，預設接真實公開交易資料集<br>正式環境可用 DATABASE_URL 接內部資料庫</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section-title">任務執行工具</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="kb-item">
        <div class="kb-item-title">Gmail ／ Google 日曆</div>
        <div class="kb-item-sub">可查詢信箱與行程、草擬郵件與會議<br>寄送／建立一律需手動確認</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section-title">範例問題</div>', unsafe_allow_html=True)

    example_qs = [
        "病假一年有幾天？薪資如何計算？",
        "品質異常 Critical 等級要多久內通報？",
        "測試儀器多久要校正一次？",
        "績效 A、月薪 60000、年資 3 年，年終獎金多少？",
        "請購單超過 10 萬元要多久核准？",
        "銷售額最高的前五個國家是哪些？",
        "客戶編號 17850 買過哪些產品？",
        "幫我查一下這週的行事曆行程",
    ]
    for q in example_qs:
        if st.button(q, use_container_width=True, key=f"btn_{q[:10]}"):
            st.session_state.pending_question = q

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="clear-btn">', unsafe_allow_html=True)
    if st.button("清除對話記錄", use_container_width=True):
        st.session_state.messages = []
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────
st.markdown(f"""
<div class="app-header">
    <div style="flex:1">
        <p class="app-header-title">{APP_TITLE}</p>
        <p class="app-header-sub">{APP_SUBTITLE}</p>
    </div>
    <span class="header-badge">RAG + Agent</span>
</div>
""", unsafe_allow_html=True)

# ── Session State ─────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None
if "thread_id" not in st.session_state:
    # LangGraph 的 checkpointer 用這個 id 記住這個 session 的對話狀態
    # （包含尚未核准的草稿），取代舊版手動重建 chat_history 的做法。
    st.session_state.thread_id = str(uuid.uuid4())

# ── 歡迎訊息 ──────────────────────────────────────────
if not st.session_state.messages:
    st.markdown(f"""
    <div class="welcome-card">
        您好，我是{COMPANY_NAME}的 {APP_TITLE}。<br>
        可協助查詢<strong>公司規章</strong>、<strong>製造與品質作業程序</strong>及<strong>企業資料庫</strong>（訂單、客戶、產品），
        也能查詢與草擬 <strong>Email／行事曆</strong>任務，寄送與建立一律需要您手動確認。
        若內部資料無法回答，將自動搜尋外部公開資訊。<br>
        請在下方輸入問題，或從左側點選範例。
    </div>
    """, unsafe_allow_html=True)

# ── 對話歷史 ──────────────────────────────────────────
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


def render_tool_badge(tool_name):
    cls = _TOOL_BADGE_CLASS.get(tool_name, "")
    return f'<span class="step-tool-badge {cls}">{tool_name}</span>'

def render_sources(sources):
    if not sources:
        return ""
    tags = "".join(f'<span class="source-tag">{s}</span>' for s in sources)
    return f'<div class="source-row"><span class="source-label">引用來源</span>{tags}</div>'

def render_steps(steps):
    if not steps:
        return
    items = ""
    for i, step in enumerate(steps, 1):
        badge = render_tool_badge(step["tool"])
        items += f"""
        <div class="step-card">
            <div class="step-header">步驟 {i} &nbsp; {badge}</div>
            <div class="step-io">
                <span class="step-io-label">輸入：</span>{step['input']}<br>
                <span class="step-io-label">輸出：</span>{step['output']}
            </div>
        </div>"""
    return items

def _resolve_interrupt(msg_idx, approve, edited_params):
    """呼叫 agent.confirm() 恢復被 interrupt() 暫停的 graph。
    真正的 send_gmail / create_calendar_event 呼叫只會發生在 graph 的
    execute 節點裡（approve=True 且經過 approval 節點之後）。"""
    try:
        result = confirm(
            st.session_state.thread_id, approve=approve, edited_params=edited_params,
            user=st.session_state.current_user, role=DEMO_USERS[st.session_state.current_user],
        )
        interrupt = st.session_state.messages[msg_idx]["interrupt"]
        interrupt["resolved"] = True
        interrupt["approval_decision"] = result.get("approval_decision")
        interrupt["execution_result"] = result.get("execution_result")
        st.rerun()
    except Exception as e:
        st.error(f"處理失敗：{e}")


def render_interrupt(msg_idx, interrupt):
    """渲染寄信／建立行程的草稿確認卡片。這張卡片本身沒有能力寄信或建立
    行程——按鈕只會呼叫 agent.confirm()，由 graph 的 execute 節點（唯一
    持有 send_gmail / create_calendar_event 的地方）在核准後才真正執行。"""
    if not interrupt:
        return

    if interrupt.get("resolved"):
        if interrupt.get("approval_decision") == "reject":
            st.info("❌ 已拒絕，未執行")
        else:
            execution_result = interrupt.get("execution_result") or ""
            if execution_result.startswith("執行失敗"):
                st.error(f"⚠️ {execution_result}")
            else:
                label = "郵件已寄出" if interrupt["type"] == "draft_email" else "行事曆事件已建立"
                st.success(f"✅ {execution_result or label}")
        return

    params = interrupt.get("params") or {}
    key = f"interrupt_{msg_idx}"

    if interrupt["type"] == "draft_email":
        with st.container(border=True):
            st.markdown('<div class="pending-action-title">📧 郵件草稿待確認</div>', unsafe_allow_html=True)
            to = st.text_input("收件者", value=params.get("to", ""), key=f"{key}_to")
            subject = st.text_input("主旨", value=params.get("subject", ""), key=f"{key}_subject")
            body = st.text_area("內容", value=params.get("body", ""), key=f"{key}_body")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 確認寄送", key=f"{key}_confirm", use_container_width=True):
                    valid, invalid = parse_emails(to)
                    if invalid or not valid:
                        # 不呼叫 confirm()：graph 維持暫停，使用者修正後可再按確認
                        st.error(f"收件者需為有效的 email，請修正：{'、'.join(invalid) or '（空白）'}")
                    else:
                        _resolve_interrupt(msg_idx, approve=True, edited_params={"to": ", ".join(valid), "subject": subject, "body": body})
            with col2:
                if st.button("❌ 拒絕", key=f"{key}_reject", use_container_width=True):
                    _resolve_interrupt(msg_idx, approve=False, edited_params=None)

    elif interrupt["type"] == "draft_calendar_event":
        with st.container(border=True):
            st.markdown('<div class="pending-action-title">📅 行事曆事件待確認</div>', unsafe_allow_html=True)
            summary = st.text_input("標題", value=params.get("summary", ""), key=f"{key}_summary")
            start = st.text_input("開始時間（ISO 8601）", value=params.get("start", ""), key=f"{key}_start")
            end = st.text_input("結束時間（ISO 8601）", value=params.get("end", ""), key=f"{key}_end")
            attendees = st.text_input("與會者 email（逗號分隔，可留空；填入後 Google 會寄邀請）", value=params.get("attendees", ""), key=f"{key}_attendees")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 確認建立", key=f"{key}_confirm", use_container_width=True):
                    valid, invalid = parse_emails(attendees)
                    if invalid:
                        # 不呼叫 confirm()：graph 維持暫停，使用者修正後可再按確認
                        st.error(f"與會者需填 email（不能填職稱或姓名），請修正或清空：{'、'.join(invalid)}")
                    else:
                        _resolve_interrupt(
                            msg_idx, approve=True,
                            edited_params={"summary": summary, "start": start, "end": end, "attendees": ", ".join(valid)},
                        )
            with col2:
                if st.button("❌ 拒絕", key=f"{key}_reject", use_container_width=True):
                    _resolve_interrupt(msg_idx, approve=False, edited_params=None)

for msg_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            st.markdown(render_sources(msg["sources"]), unsafe_allow_html=True)
        if msg.get("steps"):
            with st.expander("查看 Agent 思考過程"):
                st.markdown(render_steps(msg["steps"]), unsafe_allow_html=True)
        if msg.get("interrupt"):
            render_interrupt(msg_idx, msg["interrupt"])

# ── 問題處理 ──────────────────────────────────────────
question = st.chat_input("輸入您的問題…")
if st.session_state.pending_question:
    question = st.session_state.pending_question
    st.session_state.pending_question = None

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("查詢中…"):
            try:
                result    = ask(
                    question, thread_id=st.session_state.thread_id,
                    user=st.session_state.current_user, role=DEMO_USERS[st.session_state.current_user],
                )
                answer    = result["answer"] or ""
                sources   = result["sources"]
                steps     = result["steps"]
                interrupt = result["interrupt"]
            except Exception as e:
                answer    = f"發生錯誤：{e}\n\n請確認 Google API Key 已設定且 `ingest.py` 已執行。"
                sources   = []
                steps     = []
                interrupt = None

        st.markdown(answer)
        if sources:
            st.markdown(render_sources(sources), unsafe_allow_html=True)
        if steps:
            with st.expander("查看 Agent 思考過程"):
                st.markdown(render_steps(steps), unsafe_allow_html=True)

    st.session_state.messages.append({
        "role":      "assistant",
        "content":   answer,
        "sources":   sources,
        "steps":     steps,
        "interrupt": interrupt,
    })
    st.rerun()
