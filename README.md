# MyAide — 企業內部 AI Agent 平台

**MyAide** 是以 LangGraph、Gemini 與 Streamlit 打造的企業內部 Agent 平台，
將「知識查詢」與「任務執行」整合於單一對話介面：

- **知識查詢**——檢索內部文件（RAG）、查詢企業 SQL 資料庫，並於必要時
  搜尋外部公開資訊
- **任務執行**——查詢與草擬 Email、查詢與草擬 Google Calendar 行程

無論部署於哪一家公司，公司名稱、標題等文案均可透過環境變數設定
（見 [config.py](config.py)），MyAide 本身的品牌識別不綁定特定客戶。

## 設計原則

相較於一般的 RAG 聊天機器人，本專案聚焦於 Agent 具備任務執行能力後，
系統應具備的對應防護與治理機制：

- **具真實外部副作用的動作，皆須經人工核准**，且此限制由 graph 結構
  保證，而非仰賴系統提示詞要求 LLM 自律
- **權限判斷於伺服器端強制執行**，而非僅記載於系統提示詞中
- **串接真實資料**，而非為展示目的產生的模擬資料
- **具備自動化測試與評測套件**，確保行為可重現、可驗證
- **具備可觀測性**：每個動作皆有結構化日誌，並可選擇性啟用
  Prometheus 指標

## 功能一覽

| 能力 | 工具 | 說明 | 角色限制 |
|---|---|---|---|
| 內部文件檢索 | `search_knowledge_base` | Chroma 向量檢索 + reranking，依角色過濾機密文件 | 全部角色，機密文件另外限縮 |
| 企業資料庫查詢 | `list_database_tables`、`run_sql_query` | AST 驗證過的唯讀 SQL，預設資料為真實公開資料集，可換成正式內部資料庫 | employee 不可用 |
| Email | `search_email`、`draft_email` | 查詢 Gmail、草擬郵件（寄送需人工確認） | 全部角色 |
| 行事曆 | `list_calendar_events`、`draft_calendar_event` | 查詢／草擬 Google Calendar 行程（建立需人工確認） | 全部角色 |
| 外部搜尋 | `web_search` | DuckDuckGo 公開資訊搜尋 | 全部角色 |
| 數值計算 | `calculate` | 基本數學運算 | 全部角色 |

## 架構

Agent 的推理、工具呼叫、人工核准與執行流程，實作為明確的
`StateGraph`（見 [`graph/`](graph/)），而非框架內部隱含的迴圈邏輯：

```
START → agent ⇄ tools（LLM 持續請求呼叫工具時反覆執行）
          │
          ├─ 無工具呼叫、無待核准草稿 → END（直接回覆）
          └─ 無工具呼叫、有待核准草稿  → approval
                                              │
                                     interrupt() 於此處暫停整個 graph
                                              │
                               ┌────── reject → END
                               └────── approve → execute → END
```

**安全不變量**：`execute` 節點（唯一呼叫 `send_gmail()` /
`create_calendar_event()` 的節點）在整個 graph 中僅有一條入邊，來自
`approval` 節點的 approve 分支；而 `approval` 節點必定先呼叫
`interrupt()` 暫停整個 graph，等待 `app.py` 呼叫 `agent.confirm()`
才會恢復執行。圖上不存在任何一條「Agent 可自行抵達 execute」的路徑——
`app.py` 本身完全未 import `send_gmail` / `create_calendar_event`，
UI 僅能呼叫 `agent.confirm()` 請求 graph 恢復執行。此設計並非僅依賴
程式碼審查的共識，而是透過自動化測試驗證的結構性保證：

```bash
pytest tests/test_graph_safety.py -v
```

短期對話記憶（同一瀏覽器 session 內的上下文）由 LangGraph 的
`InMemorySaver` checkpointer 依 `thread_id` 自動保存；「清除對話記錄」
會連同 `thread_id` 一併重置。

## 安全設計

**權限控管（RBAC）**：側邊欄提供「使用者」下拉選單
（[`auth/users.py`](auth/users.py)），對應 employee／sales／hr／
finance／manager／admin 六種角色（[`auth/policy.py`](auth/policy.py)）。
此機制並非正式的身分驗證（不含密碼），僅作為展示 RBAC 效果之用；
正式環境串接公司既有的身分系統（IdP）時，僅需替換 `auth/users.py`
取得身分結果的方式，後續依賴 role 的程式碼無須變更。權限檢查的
執行位置是本設計的關鍵：[`graph/nodes.py`](graph/nodes.py) 的
`tools_node` 在**實際呼叫工具之前**檢查
`is_tool_allowed(role, tool_name)`，遭拒絕的請求連工具本身都不會
執行，LLM 僅會收到一則「權限不足」的 `ToolMessage`：

```bash
pytest tests/test_rbac.py -v
```

一般員工帳號無法查詢 SQL 資料庫，業務、人資、財務、主管及管理員帳號
則可。每一次工具呼叫（無論允許或拒絕）皆會寫入 `logs/audit.jsonl`
（[`security/audit.py`](security/audit.py)）。

**SQL 唯讀防護**：[`security/sql_ast.py`](security/sql_ast.py) 使用
`sqlglot` 將 SQL 解析為 AST，驗證其為單一 SELECT 陳述式，取代原先的
關鍵字黑名單機制——黑名單機制難以偵測的多語句注入
（`SELECT ...; DROP TABLE ...`）可被正確攔截。查詢額外於唯讀交易中
執行、結束後強制 rollback，並設有 10 秒逾時限制
（`ThreadPoolExecutor`；Windows 平台無法使用 `signal.alarm`）：

```bash
pytest tests/test_sql_ast_validation.py -v
```

**Prompt injection 防禦**：系統提示詞明確告知 Agent，工具回傳的內容
（郵件內文、網頁、檢索到的文件）一律視為資料，而非指令。此防禦機制
不僅依賴提示詞——即使 Agent 受注入內容誤導而呼叫 `draft_email`，
graph 結構仍保證 `execute` 僅能透過 `approval` 的 `interrupt()`
抵達：

```bash
pytest tests/test_prompt_injection.py -v
```

**API Key 屬部署層級密鑰，非使用者輸入**：側邊欄的 API Key 輸入框
僅於未設定 `.streamlit/secrets.toml` 或環境變數時才會顯示，並標示
「本機開發模式」。原因在於此輸入框將金鑰寫入 `os.environ`，屬整個
伺服器行程共用的全域狀態，並非各自獨立的瀏覽器 session——若部署於
多人共用的網址，第一位輸入者的金鑰將被所有後續使用者沿用。正式部署
一律採用 `secrets.toml` 或環境變數，一般使用者完全不會看到此欄位。

**稽核紀錄**：[`security/audit.py`](security/audit.py) 記錄
`user`／`role`／`tool`／`decision`／時間戳記，寫入
`logs/audit.jsonl`；內容欄位截斷至 200 字元，避免完整記錄郵件內文或
SQL 查詢結果——稽核紀錄本身外洩亦屬資安風險之一。

## 知識檢索（RAG）

**引用來源**：`search_knowledge_base` 回傳的答案均附上來源文件名稱，
介面上會顯示「引用來源」標籤。

**角色過濾檢索**：
[`data/hr_confidential_salary_bands.txt`](data/hr_confidential_salary_bands.txt)
為標註 `allowed_roles: hr,finance,manager,admin` 的機密範例文件
（由 `ingest.py` 寫入 metadata），`search_knowledge_base` 依據目前
使用者角色過濾 Chroma 檢索結果：一般員工查詢薪資職等對照表時，該
文件不會出現於候選結果中；人資角色查詢相同問題則可正常取得。

**Reranking**：[`tools/reranker.py`](tools/reranker.py) 採用本機
多語 cross-encoder（`BAAI/bge-reranker-base`，透過
`sentence-transformers`）對候選文件重新排序，取代單純依賴向量相似度
的排序方式。此依賴套件包含 `torch`，為目前專案中體積最大的相依套件；
首次執行時會下載模型（約 1 GB），若下載或載入失敗，`rerank()` 會記錄
警告訊息並回傳原始排序，不影響應用程式運作。可用環境變數
`RERANKER_MODEL` 更換模型，設為 `none` 則關閉 rerank。

原本使用的英文模型 `cross-encoder/ms-marco-MiniLM-L-6-v2` 經量測不適合
中文文件：以 8 題中文查詢檢查正確段落是否進入前 4 名，向量檢索本身
8/8，英文模型重排後只剩 5/8（例如把年終獎金公式 FAQ Q10 擠出前 4 名），
`bge-reranker-base` 8/8（CPU 約 4 秒/題），`bge-reranker-v2-m3` 8/8
（約 15 秒/題）。在目前僅 17 個 chunk 的範例知識庫上，rerank 尚未顯示
優於純向量檢索；文件量增加後才是它發揮作用的地方。（混合檢索／
向量 + BM25 尚未實作，詳見下方 Roadmap。）

## 可觀測性

每個 graph 節點、每次工具呼叫皆會寫入結構化 JSON 日誌
（[`observability/logging_config.py`](observability/logging_config.py)），
輸出至 stdout 與 `logs/agent.jsonl`。

Prometheus 指標（[`observability/metrics.py`](observability/metrics.py)）
預設**完全關閉**，需設定 `ENABLE_METRICS=true` 後再啟動應用程式，
才會於本機開啟 `/metrics` endpoint（預設 port 8000，可透過
`METRICS_PORT` 調整）：

```bash
set ENABLE_METRICS=true
streamlit run app.py
```

指標涵蓋：`agent_requests_total`、`tool_calls_total{tool}`、
`tool_errors_total{tool}`、`tool_latency_seconds{tool}`、
`approval_requested_total`、`approval_decisions_total{decision}`、
`permission_denied_total{tool,role}`。

如需視覺化呈現，`docker-compose.yml` 可另行啟動 Prometheus 與
Grafana 兩個容器（應用程式本身仍直接執行於主機上，未容器化）：

```bash
docker compose up
```

- Prometheus targets：http://localhost:9090/targets （前提是應用程式已設定 `ENABLE_METRICS=true` 並正在執行，方能看到 `myaide` 為 up 狀態）
- Grafana（可匿名檢視，無須登入）：http://localhost:3000，已預先 provision 一個 dashboard

LangSmith 追蹤無須額外撰寫程式碼，LangChain/LangGraph 原生支援，
設定 `LANGCHAIN_TRACING_V2=true` 與 `LANGCHAIN_API_KEY`（需自行申請
LangSmith 帳號）即可啟用。

### LangGraph Studio（視覺化與逐步除錯）

[LangGraph Studio](https://docs.langchain.com/langsmith/quick-start-studio)
會讀取 [`graph/build.py`](graph/build.py) 的 nodes 與 edges，自動畫出
`__start__ → agent ⇄ tools → approval → execute → __end__` 的流程圖，並可
逐步檢視每個節點的輸入、輸出與 State，也能直接看到 `approval` 節點的
`interrupt()` 暫停。Studio 與 Streamlit 共用同一份 graph 定義
（`build_state_graph()`），進入點是 [`graph/studio.py`](graph/studio.py)，
設定檔是 [`langgraph.json`](langgraph.json)。

```bash
set PYTHONUTF8=1
langgraph dev
```

啟動後以瀏覽器開啟
https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
（需登入 LangSmith 帳號，免費方案即可）。

- `PYTHONUTF8=1` 在繁體中文 Windows 上是必要的：`langgraph-api` 讀取
  內部 schema 檔時未指定編碼，預設 cp950 會在啟動時 `UnicodeDecodeError`。
- API Key 沿用 `.streamlit/secrets.toml`，不需另建 `.env`。
- 角色與使用者由 run 的 `config.configurable` 傳入，例如
  `{"user": "ben", "role": "sales"}`；未指定時預設為 `employee`
  （最低權限，SQL 工具會被拒絕）。
- 在 `approval` 暫停時，以 resume 值 `{"decision": "reject", "params": null}`
  拒絕；`"approve"` **會真的寄出郵件／建立行程**。

## 測試與評測

```bash
pytest tests/ -v              # 23 個單元測試：graph 安全性、RBAC、SQL AST 驗證、prompt injection
python -m evals.run_evals     # 評測套件（預設 --fake-llm）
```

兩者皆不需要有效的 Google API Key——測試中 LLM 節點以固定腳本回應
取代，因驗證重點在於 graph 路線、權限檢查與 SQL 驗證邏輯的正確性，
而非 LLM 的工具選擇準確度。

評測資料集位於
[`evals/datasets/core_cases.py`](evals/datasets/core_cases.py)
（知識問答、Text-to-SQL、寄信／排行程、RBAC 拒絕、prompt injection、
RAG 角色過濾、品質異常規範查詢，共 9 個案例），評分邏輯位於
[`evals/evaluators.py`](evals/evaluators.py)。`--fake-llm` 模式以
腳本化回應執行全部 9 個案例，用於驗證評測套件本身的執行機制；
`--live` 模式（`python -m evals.run_evals --live`）改為執行真正的
Gemini 模型，用以量測真實模型「是否選對工具、是否避免選用不當工具、
應停留於核准節點時是否確實停留、RAG 是否引用正確來源」，執行前需
具備有效的 Gemini API 額度。兩種模式皆會將 `send_gmail` /
`create_calendar_event` mock 化，確保評測過程不會真正寄出郵件。
執行結果輸出至 `evals/report.json`（機器可讀）並於主控台顯示摘要
表格。

**首次 `--live` 結果（2026-10-24，Gemini 3.8 Flash）**：第一次執行
5/8。三個未通過案例檢查後都是**評測預期本身有誤**，而非模型行為錯誤：
年終獎金案例原本禁止查知識庫，但公式在 FAQ Q10，正確答案應為
108,000（原腳本只算 90,000，漏掉年資係數）；RBAC 案例預期模型先呼叫
`run_sql_query`，但系統提示詞規定先呼叫 `list_database_tables`；
注入案例預期模型「被騙去草擬」，實際上模型識破注入、完全沒有草擬。
修正預期後連續兩次 8/8。所有案例的 `no_unsafe_action` 檢查（未經核准
不得寄信／建立行程）在修正前後皆通過。

**改為真實檢索後（2026-10-25）**：原本 `fake_tool_stub` 在 `--live`
模式也會頂替工具輸出，RAG 案例其實沒有查詢向量庫。修正為只在
`--fake-llm` 頂替（注入案例的惡意郵件改用兩種模式都頂替的
`tool_stub`）後，年終獎金案例失敗——追查發現英文 reranker 把正確的
FAQ 段落擠出前 4 名（見上方 Reranking 量測）。改用 `bge-reranker-base`
後連續兩次 9/9。

## 安裝

```bash
pip install -r requirements.txt
```

<details>
<summary>模型與套件版本（2026-10 遷移至 langchain 1.x）</summary>

LLM 使用 **Gemini 3.8 Flash**（`gemini-3.8-flash`）。原本的
`gemini-2.5-flash` 已不開放給新使用者（新專案呼叫會回 404），而
Gemini 3.x 的 function calling 需要把 thought signature 帶回下一輪
請求，舊版 `langchain-google-genai==1.0.10` 不支援（回 400
`missing a thought_signature`）。因此整組升級至 `langchain-core` 1.x
／`langchain-google-genai` 4.x／`langgraph` 1.2，並改用
`langchain-chroma`。升級後各套件版本宣告一致，先前的
`pip install --no-deps` 兩階段安裝已不再需要。

依官方 Gemini 3 指引，`temperature` 維持 1.0（調低可能導致迴圈或推理
變差）；思考深度以 `thinking_level` 控制，預設 `low`。兩者可用環境
變數 `GEMINI_MODEL`、`GEMINI_THINKING_LEVEL` 覆寫。`chromadb` 維持
1.5.5，既有的 `chroma_db/` 索引不需重建（embedding 仍為
`gemini-embedding-001`，官方停用日為 2028-05-14）。

遷移後驗證結果：23 個單元測試全數通過、`--fake-llm` 評測 9/9、
`--live` 評測（含真實向量檢索）連續兩次 9/9。

</details>

### 1. 設定品牌文案（選用）

未設定時使用預設中性文案（「貴公司」）。

```bash
set COMPANY_NAME=您的公司名稱
set APP_TITLE=企業內部 AI 助理
set APP_SUBTITLE=您的一句話說明
```

### 2. 設定 Google API Key（RAG / LLM 必要）

API Key 屬部署層級的基礎設施密鑰，設定優先順序為：
`.streamlit/secrets.toml` → 環境變數 `GOOGLE_API_KEY` → 側邊欄手動
輸入。

**正式部署**（多人共用同一服務網址時）：

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# 編輯 secrets.toml，填入正式的 GOOGLE_API_KEY
```

由管理員於部署前完成設定，一般使用者完全不會、也無須於畫面上看到或
輸入 API Key。`secrets.toml` 已列於 `.gitignore`，不會被提交至版控。

**本機測試**：若上述兩者皆未設定，側邊欄才會顯示手動輸入框（畫面上
會標示「本機開發模式」，僅適用於單人本機開發，詳見上方「安全設計」）。

### 3. 建立內部文件知識庫

將自有內部文件（`.txt` / `.pdf`）放入 `data/`，取代其中的範例文件，
接著執行：

```bash
python ingest.py
```

`data/` 目錄下的範例文件皆為通用內容，不代表任何特定公司：員工手冊
（含廠區安全與品質規範）、常見問題集、製造執行系統（MES）操作手冊
（工單、首件檢驗、批號追溯、品質異常處理、設備保養），以及一份
`hr_confidential_salary_bands.txt` 範例機密文件，用於示範角色過濾檢索
（詳見上方「知識檢索」）。重新匯入前請先刪除 `chroma_db/`，
`ingest.py` 會將文件附加到既有索引而非覆寫。

### 4. 建立企業 SQL 資料庫

**快速體驗（預設）：真實公開資料集**

```bash
python sql_ingest.py
```

將從 UCI Machine Learning Repository 下載 **Online Retail II**
（一間英國網路零售商 2009–2011 年間的真實交易紀錄，CC BY 4.0
授權，非模擬或 LLM 生成資料），整理為 `customers` / `products` /
`orders` / `order_items` 四張資料表，存入
`enterprise_data/enterprise.db`，供 SQL 工具進行唯讀查詢，模擬
「訂單／客戶／產品」此類典型企業資料庫。

**串接正式的企業內部資料庫**：無須修改任何程式碼，設定
`DATABASE_URL` 環境變數即可，`tools/sql_query.py` 將透過
SQLAlchemy 自動改連正式資料庫：

```bash
# PostgreSQL（需額外安裝 pip install psycopg2-binary）
set DATABASE_URL=postgresql+psycopg2://readonly_user:***@db.internal:5432/erp

# MySQL（需額外安裝 pip install pymysql）
set DATABASE_URL=mysql+pymysql://readonly_user:***@db.internal:3306/erp

# SQL Server（需額外安裝 pip install pyodbc）
set DATABASE_URL=mssql+pyodbc://readonly_user:***@db.internal/erp?driver=ODBC+Driver+17+for+SQL+Server
```

**強烈建議**：連線帳號採用資料庫層級的唯讀權限（例如 PostgreSQL 的
`GRANT SELECT`），不應僅依賴程式碼層級的 SQL 驗證。

### 5. 設定 Gmail / Google Calendar（選用，任務執行功能所需）

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
   建立專案，啟用 **Gmail API** 與 **Google Calendar API**
2. 於「憑證」頁面點選「建立憑證」→「OAuth 用戶端 ID」，應用程式
   類型選擇 **Desktop app**
3. 下載憑證 JSON，重新命名為 `credentials.json`，放置於專案根目錄
4. 首次呼叫 Email／行事曆工具時，將自動開啟瀏覽器要求登入並同意
   授權，授權結果會快取於 `token.json`，之後無須重複登入
5. `credentials.json` / `token.json` 已列於 `.gitignore`，切勿提交
   至版控

### 執行

```bash
streamlit run app.py
```

## 專案結構

```
agent.py                對外公開介面：ask() / confirm()，將 graph 執行結果整理為 UI 所需的格式
app.py                  Streamlit UI，含使用者／角色選擇、任務確認（人工核可）介面
config.py               品牌文案設定（環境變數）
ingest.py               內部文件 → Chroma 向量索引（含 allowed_roles metadata）
sql_ingest.py            真實公開資料集 → 企業 SQL 範例資料庫
data/                    內部文件（RAG 來源，含一份 RBAC 範例機密文件）
graph/
  state.py                AgentState（messages / pending_action / approval_decision / execution_result）
  nodes.py                 agent／tools／approval／execute 四個節點（RBAC 檢查、log／metrics／稽核皆於此處理）
  build.py                  組裝 StateGraph 並編譯（build_state_graph／build_graph）
  studio.py                 LangGraph Studio 進入點（langgraph.json 指向這裡）
auth/
  users.py                 Demo 使用者清單（username → role）
  policy.py                 權限矩陣：is_tool_allowed(role, tool_name)
security/
  sql_ast.py                SQL AST 驗證，取代關鍵字黑名單
  audit.py                   稽核紀錄（user/role/tool/decision → logs/audit.jsonl）
observability/
  logging_config.py          結構化 JSON 日誌
  metrics.py                  Prometheus 指標（預設關閉，需設定 ENABLE_METRICS=true 啟用）
  prometheus.yml               docker-compose 使用的 scrape 設定
  grafana/                      provisioning 設定與一份現成 dashboard
evals/
  datasets/core_cases.py     版本控制的評測案例
  evaluators.py                評分邏輯（純函式）
  run_evals.py                  CLI：--fake-llm（預設）/ --live
tools/
  knowledge_base.py         RAG 檢索工具（角色過濾 + rerank）
  reranker.py                 本機多語 cross-encoder（bge-reranker-base）
  sql_query.py                 企業資料庫唯讀查詢工具（可切換正式資料庫）
  google_auth.py               Gmail / Calendar 共用 OAuth2
  email_tool.py                  Gmail 查詢／草擬／寄送
  calendar_tool.py               Calendar 查詢／草擬／建立
  web_search.py                   外部搜尋
  calculate.py                      數值計算
tests/
  test_graph_safety.py      graph 結構與核准流程驗證
  test_rbac.py                權限於工具呼叫前遭正確攔截
  test_sql_ast_validation.py   AST 驗證攔截黑名單機制未能偵測的案例
  test_prompt_injection.py      注入指令仍無法繞過核准流程
docker-compose.yml          Prometheus + Grafana（應用程式本身仍執行於主機）
```

## Roadmap

以下項目為刻意保持輕量、尚未達到完整企業部署程度的部分，特此說明以
避免誤解為疏漏：

- **正式 SSO / IdP 整合**：目前採用側邊欄選擇角色的展示用登入方式，
  串接公司既有身分系統僅需替換 `auth/users.py`，RBAC 判斷邏輯無須
  變更
- **FastAPI 後端拆分**：Streamlit 行程本身即扮演伺服器端角色，
  RBAC 與稽核已於伺服器端強制執行；拆分獨立 API 層屬於更大規模的
  重構，待實際需要支援多種前端（不限於 Streamlit）時再行評估
- **應用程式容器化**：`docker-compose.yml` 目前僅啟動 Prometheus
  與 Grafana，Streamlit 應用程式本身仍直接執行於主機
- **擴充評測集**：`--live` 已對 Gemini 3.8 Flash 連續兩次 9/9，但 9 個
  案例的樣本數太小，尚不足以宣稱整體工具選擇準確率；下一步是擴充至
  30–50 題並加入檢索指標（Recall@k）
- **混合檢索**：向量 + BM25 之混合檢索尚未實作——目前無量測數據
  顯示純語意檢索效果不足
- **資料庫層級 `statement_timeout`**：目前的查詢逾時機制為應用層
  實作（`ThreadPoolExecutor`），非資料庫本身設定；串接正式
  PostgreSQL 時建議額外設定
