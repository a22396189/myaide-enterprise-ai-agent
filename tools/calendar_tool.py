# tools/calendar_tool.py
# Google Calendar 工具。
#
# 與 email_tool.py 相同的安全設計：Agent 只能查詢與草擬事件，實際建立事件
# 必須由使用者在畫面上確認後手動觸發 create_calendar_event()（見 app.py）。

from googleapiclient.discovery import build
from langchain_core.tools import tool

from tools.google_auth import get_credentials


def _calendar_service():
    return build("calendar", "v3", credentials=get_credentials())


@tool
def list_calendar_events(time_min: str, time_max: str) -> str:
    """查詢使用者 Google 日曆在指定時間範圍內的行程。
    time_min、time_max 請使用 ISO 8601 格式，例如 '2025-06-01T00:00:00Z'。
    僅供查詢，不會修改行事曆。
    """
    try:
        service = _calendar_service()
        resp = service.events().list(
            calendarId="primary", timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy="startTime",
        ).execute()
        events = resp.get("items", [])
        if not events:
            return "此時間範圍內沒有行程。"

        results = []
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date"))
            results.append(f"{start}｜{e.get('summary', '(無標題)')}")
        return "\n".join(results)
    except Exception as e:
        return f"查詢行事曆失敗：{e}"


@tool
def draft_calendar_event(summary: str, start: str, end: str, attendees: str = "") -> str:
    """草擬一個行事曆事件（尚未建立）。當使用者要求「排會議」、「安排行程」時使用此工具。
    start/end 請使用 ISO 8601 格式（例如 '2025-06-01T14:00:00+08:00'），
    attendees 為以逗號分隔的 email 清單（可留空）。
    實際建立事件必須由使用者在畫面上確認後手動觸發，你自己絕對不會、也不能直接建立。
    """
    return (
        "已產生行事曆事件草稿，請在畫面上確認後手動建立：\n\n"
        f"標題：{summary}\n開始：{start}\n結束：{end}\n與會者：{attendees or '（無）'}"
    )


def create_calendar_event(summary: str, start: str, end: str, attendees: str = "") -> str:
    """實際建立日曆事件。此函式刻意不包裝成 @tool，不會出現在 Agent 的工具清單中，
    只能由 app.py 在使用者明確點擊「確認建立」按鈕後呼叫。"""
    service = _calendar_service()
    event = {
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    if attendees:
        event["attendees"] = [{"email": a.strip()} for a in attendees.split(",") if a.strip()]
    created = service.events().insert(
        calendarId="primary", body=event, sendUpdates="all"
    ).execute()
    return f"行事曆事件已建立：{created.get('htmlLink')}"
