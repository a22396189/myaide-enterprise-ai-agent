# config.py
# 品牌／文案設定。COMPANY_NAME 等文案可透過環境變數覆寫，套用到任何
# 部署這個平台的公司，不需要修改程式碼本身。

import os

# MyAide 是這個 AI Agent 平台本身的產品品牌名稱，不透過環境變數覆寫——
# 每個部署可以設定自己的 COMPANY_NAME（要顯示成哪家公司在用），但畫面上
# 顯示的一律是「{COMPANY_NAME} · MyAide」這種「客戶公司 + 產品品牌」的
# 組合，類似 Slack workspace 的命名方式。
PRODUCT_NAME = "MyAide"

COMPANY_NAME = os.environ.get("COMPANY_NAME", "貴公司")
APP_TITLE = os.environ.get("APP_TITLE", PRODUCT_NAME)
APP_SUBTITLE = os.environ.get(
    "APP_SUBTITLE",
    "MyAide — 整合內部文件、企業資料庫、Email 與行事曆的知識查詢與任務執行 Agent",
)

# Agent 回答裡允許保留成「可點擊連結」的網域（逗號分隔，含子網域），例如
# "example.com,intranet.example.com"。不在清單內的連結一律顯示成純文字網址，
# 避免郵件／網頁裡的釣魚連結被模型整理成助理親自遞出的可點連結。預設為空：
# 所有連結都不可點。見 ui_render.neutralize_links。
ALLOWED_LINK_DOMAINS = [
    d.strip().lower().lstrip(".")
    for d in os.environ.get("ALLOWED_LINK_DOMAINS", "").split(",")
    if d.strip()
]
