# auth/users.py
# Demo 使用者清單（username → role）。這不是真正的身分驗證（沒有密碼、
# 沒有 SSO），只是為了讓 RBAC 的「權限依角色而定」這件事在 Streamlit UI
# 上可以被示範、被測試。正式環境要接公司真正的 IdP（AD／Okta／Google
# Workspace SSO 等），把這個模組換成真正驗證身分的結果即可——後面所有
# 依賴 role 的程式碼（auth/policy.py、graph/nodes.py 的權限檢查）完全
# 不需要改。

DEMO_USERS: dict[str, str] = {
    "alice（一般員工）": "employee",
    "ben（業務）": "sales",
    "carol（人資）": "hr",
    "david（財務）": "finance",
    "emma（主管）": "manager",
    "frank（系統管理員）": "admin",
}

DEFAULT_USER = "alice（一般員工）"
