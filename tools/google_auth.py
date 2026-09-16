# tools/google_auth.py
# Gmail / Google Calendar 共用的 OAuth2 認證流程。
#
# 使用前須在 Google Cloud Console 建立 OAuth 用戶端（類型：Desktop app），
# 下載 credentials.json 放到專案根目錄。首次呼叫會開啟瀏覽器要求使用者登入
# 並同意授權範圍，之後授權會快取在 token.json，不需重複登入。
# 詳細步驟見 README.md。

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]

CREDENTIALS_PATH = Path(os.environ.get("GOOGLE_OAUTH_CREDENTIALS", "./credentials.json"))
TOKEN_PATH = Path(os.environ.get("GOOGLE_OAUTH_TOKEN", "./token.json"))

_creds: Credentials | None = None


def get_credentials() -> Credentials:
    """取得使用者的 Google OAuth 憑證，並在需要時觸發登入流程或刷新 token。"""
    global _creds
    if _creds and _creds.valid:
        return _creds

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"找不到 {CREDENTIALS_PATH}。請至 Google Cloud Console 建立 OAuth 用戶端"
                    "（Desktop app），下載 credentials.json 後放到專案根目錄，詳見 README.md。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    _creds = creds
    return creds
