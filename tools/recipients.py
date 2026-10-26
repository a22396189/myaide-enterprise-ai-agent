# tools/recipients.py
# 收件者／與會者 email 清單的解析與驗證。
#
# 使用者在核准表單裡常會打全形逗號「，」、頓號「、」，或直接填職稱、人名
# （例如「採購專員，品管」）。原本只用半形逗號切割，整串文字被當成一個
# email 送到 Google API，回 400 Invalid attendee email，而且是在「核准之後、
# 執行當下」才失敗，草稿也跟著消失。這裡統一在送出前驗證：app.py 在使用者
# 按下確認前先檢查，不合法就留在核准畫面讓使用者修正；send_gmail /
# create_calendar_event 也再檢查一次（縱深防禦）。

import re

# 半形／全形逗號、頓號、分號、空白都視為分隔符
_SEPARATORS = re.compile(r"[,，、;；\s]+")
# 實務上夠用的 email 格式檢查（不追求完整 RFC 5322）
_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def parse_emails(text: str) -> tuple[list[str], list[str]]:
    """把一串收件者文字切成 email 清單。回傳 (合法的 email, 不合法的項目)。"""
    items = [s for s in _SEPARATORS.split(text or "") if s]
    valid = [s for s in items if _EMAIL.match(s)]
    invalid = [s for s in items if not _EMAIL.match(s)]
    return valid, invalid
