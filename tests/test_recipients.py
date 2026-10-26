# tests/test_recipients.py
# 收件者／與會者驗證：核准表單裡填了職稱、全形逗號時，不能把整串文字
# 當成 email 送進 Google API（實際發生過：與會者「採購專員，專案工程師，品管」
# → Calendar API 400 Invalid attendee email）。

from unittest.mock import patch

import pytest

from tools import calendar_tool, email_tool
from tools.recipients import parse_emails


@pytest.mark.parametrize("text, valid, invalid", [
    ("", [], []),
    ("a@example.com", ["a@example.com"], []),
    ("a@example.com, b@example.com", ["a@example.com", "b@example.com"], []),
    ("a@example.com，b@example.com、c@example.com", ["a@example.com", "b@example.com", "c@example.com"], []),
    ("採購專員，專案工程師，品管", [], ["採購專員", "專案工程師", "品管"]),
    ("a@example.com, 品管", ["a@example.com"], ["品管"]),
    ("not-an-email", [], ["not-an-email"]),
])
def test_parse_emails(text, valid, invalid):
    assert parse_emails(text) == (valid, invalid)


def test_create_calendar_event_rejects_job_titles_before_calling_api():
    with patch.object(calendar_tool, "_calendar_service") as mock_service:
        with pytest.raises(ValueError, match="採購專員"):
            calendar_tool.create_calendar_event(
                summary="與供應商開會", start="2026-10-26T14:00:00+08:00",
                end="2026-10-26T15:00:00+08:00", attendees="採購專員，專案工程師，品管",
            )
        mock_service.assert_not_called()


def test_create_calendar_event_accepts_fullwidth_comma_emails():
    with patch.object(calendar_tool, "_calendar_service") as mock_service:
        insert = mock_service.return_value.events.return_value.insert
        insert.return_value.execute.return_value = {"htmlLink": "https://calendar.example/e1"}
        calendar_tool.create_calendar_event(
            summary="會議", start="2026-10-26T14:00:00+08:00", end="2026-10-26T15:00:00+08:00",
            attendees="a@example.com，b@example.com",
        )
        body = insert.call_args.kwargs["body"]
        assert body["attendees"] == [{"email": "a@example.com"}, {"email": "b@example.com"}]


def test_send_gmail_rejects_invalid_recipient_before_calling_api():
    with patch.object(email_tool, "_gmail_service") as mock_service:
        with pytest.raises(ValueError):
            email_tool.send_gmail(to="John", subject="s", body="b")
        mock_service.assert_not_called()
