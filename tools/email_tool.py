# tools/email_tool.py
# Gmail 工具。
#
# 設計原則：Agent 只能「查詢」與「草擬」，實際寄送一律不開放給 Agent 自動呼叫，
# 必須由使用者在畫面上確認草稿內容後手動觸發 send_gmail()（見 app.py）。
# 這是企業場景下處理具真實副作用動作（寄信、通知外部人員）的標準做法：
# LLM 生成內容、人類核可執行。

import base64
from email.mime.text import MIMEText

from googleapiclient.discovery import build
from langchain_core.tools import tool

from tools.google_auth import get_credentials


def _gmail_service():
    return build("gmail", "v1", credentials=get_credentials())


@tool
def search_email(query: str, max_results: int = 5) -> str:
    """搜尋使用者的 Gmail 信箱。query 請使用 Gmail 搜尋語法，例如：
    'from:boss@company.com subject:報價' 或 'is:unread after:2025/01/01'。
    僅供查詢，不會修改或刪除任何郵件。
    """
    try:
        service = _gmail_service()
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        messages = resp.get("messages", [])
        if not messages:
            return "沒有找到符合條件的郵件。"

        results = []
        for m in messages:
            msg = service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            snippet = msg.get("snippet", "")
            results.append(
                f"寄件者：{headers.get('From', '未知')}\n"
                f"主旨：{headers.get('Subject', '(無主旨)')}\n"
                f"日期：{headers.get('Date', '')}\n"
                f"摘要：{snippet}"
            )
        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"搜尋郵件失敗：{e}"


@tool
def draft_email(to: str, subject: str, body: str) -> str:
    """草擬一封郵件內容（不會寄出）。當使用者要求「寄信」、「回信」、「通知某人」時，
    使用此工具產生草稿。寄送必須由使用者在畫面上確認後手動送出，你自己絕對不會、
    也不能直接把信寄出。
    """
    return (
        "已產生郵件草稿，請在畫面上確認後手動送出：\n\n"
        f"收件者：{to}\n主旨：{subject}\n內容：\n{body}"
    )


def send_gmail(to: str, subject: str, body: str) -> str:
    """實際寄出郵件。此函式刻意不包裝成 @tool，不會出現在 Agent 的工具清單中，
    只能由 app.py 在使用者明確點擊「確認寄送」按鈕後呼叫。"""
    service = _gmail_service()
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return f"郵件已寄出給 {to}"
