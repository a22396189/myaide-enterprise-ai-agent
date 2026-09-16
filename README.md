# MyAide — 企業內部 AI Agent 平台

**MyAide** 是以 LangGraph + Gemini + Streamlit 打造的企業內部 Agent 平台，
把「知識查詢」與「任務執行」整合在同一個對話介面裡：

- **知識查詢**——檢索內部文件（RAG）、查詢企業 SQL 資料庫、必要時搜尋外部公開資訊
- **任務執行**——查詢與草擬 Email、查詢與草擬 Google Calendar 行程

部署到哪家公司，公司名稱、標題等文案透過環境變數設定即可（見
[config.py](config.py)），MyAide 本身的品牌不綁定特定公司。

## 這個專案想證明什麼

比起一般的 RAG 聊天機器人，這裡的重點是「Agent 真的去做事」之後，
系統設計要怎麼跟著長大：

- **會產生真實外部副作用的動作，一定要人核准**——而且是 graph 結構上
  保證做不到繞過，不是靠 prompt 拜託 LLM 自律
- **權限判斷在伺服器端強制執行**，不是寫在 system prompt 裡
- **接的是真實資料**，不是為了 demo 生成的假資料
- **有自動化測試與評測套件**，不是「demo 當下能動就好」
- **可觀測**——每個動作都有結構化 log、可選的 Prometheus 指標

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

Agent 的推理／工具呼叫／人工核准／執行，是一個明確的 `StateGraph`
（見 [`graph/`](graph/)），不是隱藏在框架裡的黑盒迴圈：

```
START → agent ⇄ tools（LLM 持續要求呼叫工具就一直迴圈）
          │
          ├─ 沒有工具呼叫、沒有待核准草稿 → END（純粹回答）
          └─ 沒有工具呼叫、有待核准草稿   → approval
                                              │
                                     interrupt() 在這裡真正暫停整個 graph
                                              │
                               ┌────── reject → END
                               └────── approve → execute → END
```

**安全不變量**：`execute` 節點（唯一會呼叫 `send_gmail()` /
`create_calendar_event()` 的地方）在整個 graph 裡只有一條入邊，來自
`approval` 節點的 approve 分支；而 `approval` 節點一定會先呼叫
`interrupt()` 把整個 graph 暫停，等待 `app.py` 呼叫 `agent.confirm()`
才會恢復。圖上不存在任何一條「Agent 自己就能抵達 execute」的路徑——
`app.py` 本身完全沒有 import `send_gmail` / `create_calendar_event`，
UI 唯一能做的就是呼叫 `agent.confirm()` 要求 graph 恢復執行。這不只是
程式碼審查時的默契，而是自動化測試實際驗證的結構性質：

```bash
pytest tests/test_graph_safety.py -v
```

短期對話記憶（同一個瀏覽器 session 內的上下文）由 LangGraph 的
`InMemorySaver` checkpointer 依 `thread_id` 自動保存；「清除對話記錄」
會連同 `thread_id` 一起重置。

## 安全設計

**權限控管（RBAC）**：側邊欄有一個「使用者」下拉選單
（[`auth/users.py`](auth/users.py)），對應 employee／sales／hr／
finance／manager／admin 六種角色（[`auth/policy.py`](auth/policy.py)）。
這不是真正的身分驗證——沒有密碼，純粹是示範用，讓 RBAC 的效果能在 UI 上
被操作、被測試；正式環境要接公司真正的 IdP，換掉 `auth/users.py` 拿到的
身分結果即可，後面所有依賴 role 的程式碼完全不用改。真正重要的是權限
「在哪裡」被檢查：[`graph/nodes.py`](graph/nodes.py) 的 `tools_node`
在**真正呼叫工具之前**檢查 `is_tool_allowed(role, tool_name)`，被拒絕
的呼叫連工具本身都不會執行，LLM 只會收到一則「權限不足」的
`ToolMessage`：

```bash
pytest tests/test_rbac.py -v
```

一般員工不能查 SQL 資料庫，業務／人資／財務／主管／管理員可以。每一次
工具呼叫（允許或拒絕）都會寫進 `logs/audit.jsonl`
（[`security/audit.py`](security/audit.py)）。

**SQL 唯讀防護**：[`security/sql_ast.py`](security/sql_ast.py) 用
`sqlglot` 把 SQL 剖析成 AST，確認「恰好是一句 SELECT」，取代關鍵字
黑名單——黑名單抓不到的多語句夾帶（`SELECT ...; DROP TABLE ...`）會被
正確擋下。查詢額外包在唯讀交易裡執行、結束強制 rollback，並有 10 秒
逾時（`ThreadPoolExecutor`，Windows 沒有 `signal.alarm` 可用）：

```bash
pytest tests/test_sql_ast_validation.py -v
```

**Prompt injection 防禦**：system prompt 明確告訴 Agent，工具回傳的
內容（郵件內文、網頁、檢索到的文件）一律是資料，不是指令。更重要的是
不只靠這句話——就算 Agent 真的被騙去呼叫 `draft_email`，graph 的結構
仍然保證 `execute` 只能透過 `approval` 的 `interrupt()` 抵達：

```bash
pytest tests/test_prompt_injection.py -v
```

**API Key 是部署密鑰，不是使用者輸入**：側邊欄的 API Key 輸入框只在
沒有設定 `.streamlit/secrets.toml` 或環境變數時才會出現，並標示「本機
開發模式」。原因：輸入框寫入的是 `os.environ`，是整個伺服器行程共用的
全域狀態，不是各自獨立的瀏覽器 session——多人共用時第一個輸入的人所填
的 key 會被所有後續使用者沿用。正式部署一律走 `secrets.toml` 或環境
變數，一般使用者完全看不到這個欄位。

**稽核紀錄**：[`security/audit.py`](security/audit.py) 記錄
`user`／`role`／`tool`／`decision`／時間戳記，寫進 `logs/audit.jsonl`；
內容欄位截斷到 200 字元，不整段記錄郵件內文或 SQL 結果——稽核紀錄本身
外洩也是風險。

## 知識檢索（RAG）

**引用來源**：`search_knowledge_base` 的回答一律附上來源文件名稱，UI
上會顯示「引用來源」標籤。

**角色過濾檢索**：[`data/hr_confidential_salary_bands.txt`](data/hr_confidential_salary_bands.txt)
是一份標成 `allowed_roles: hr,finance,manager,admin` 的機密範例文件
（`ingest.py` 寫進 metadata），`search_knowledge_base` 會依目前角色過濾
Chroma 檢索結果——一般員工問薪資職等對照表，這份文件不會出現在候選
名單裡；人資問一樣的問題則看得到。

**Reranking**：[`tools/reranker.py`](tools/reranker.py) 用本機
cross-encoder（`cross-encoder/ms-marco-MiniLM-L-6-v2`，透過
`sentence-transformers`）把候選文件重新排序，取代單純依賴向量相似度
排序。這個依賴帶了 `torch`，是目前專案最重的一個套件；第一次使用會
下載模型，若下載/載入失敗，`rerank()` 會記警告後直接回傳原始排序，
不會讓 app 掛掉。（混合檢索／向量+BM25 目前沒有做——沒有量測數據顯示
純語意檢索不夠用，見下方 Roadmap。）

## 可觀測性

每個 graph 節點、每次工具呼叫都會寫結構化 JSON log
（[`observability/logging_config.py`](observability/logging_config.py)），
輸出到 stdout 與 `logs/agent.jsonl`。

Prometheus 指標（[`observability/metrics.py`](observability/metrics.py)）
預設**完全關閉**，設定 `ENABLE_METRICS=true` 再啟動 app，才會在本機開
一個 `/metrics` endpoint（預設 port 8000，可用 `METRICS_PORT` 調整）：

```bash
set ENABLE_METRICS=true
streamlit run app.py
```

指標涵蓋：`agent_requests_total`、`tool_calls_total{tool}`、
`tool_errors_total{tool}`、`tool_latency_seconds{tool}`、
`approval_requested_total`、`approval_decisions_total{decision}`、
`permission_denied_total{tool,role}`。

想看視覺化的話，`docker-compose.yml` 會另外起 Prometheus + Grafana
兩個容器（app 本身仍然直接跑在主機上，沒有被容器化）：

```bash
docker compose up
```

- Prometheus targets：http://localhost:9090/targets （要看到 `myaide` 是 up，前提是 app 有設 `ENABLE_METRICS=true` 且正在跑）
- Grafana（匿名檢視即可，不需登入）：http://localhost:3000，已經 provision 好一個 dashboard

LangSmith 追蹤不用寫程式碼，LangChain/LangGraph 原生支援，設定
`LANGCHAIN_TRACING_V2=true` 與 `LANGCHAIN_API_KEY`（需要自己申請
LangSmith 帳號）即可。

## 測試與評測

```bash
pytest tests/ -v              # 23 個單元測試：graph 安全性、RBAC、SQL AST 驗證、prompt injection
python -m evals.run_evals     # 評測套件（預設 --fake-llm）
```

兩者都不需要真的 Google API Key——LLM 節點被替換成固定腳本回應，因為
要驗證的是 graph 的路線、權限檢查、SQL 驗證邏輯正不正確，不是 LLM
選工具選得準不準。

評測資料集在 [`evals/datasets/core_cases.py`](evals/datasets/core_cases.py)
（知識問答、Text-to-SQL、寄信/排行程、RBAC 拒絕、prompt injection、
RAG 角色過濾，共 8 個案例），評分邏輯在
[`evals/evaluators.py`](evals/evaluators.py)。`--fake-llm` 模式用腳本化
回應跑過全部 8 個案例，用來驗證評測套件本身的機制；`--live` 模式
（`python -m evals.run_evals --live`）改跑真正的 Gemini，量測真實模型
「選對工具、沒選錯誤工具、該停在核准就真的停在核准、RAG 有引用對的
來源」，需要有效的 Gemini API 額度才能執行。兩種模式都會把
`send_gmail` / `create_calendar_event` mock 掉，評測不會真的寄出郵件。
輸出 `evals/report.json`（機器可讀）+ console 摘要表。

## 安裝

**兩段式安裝，順序不能反：**

```bash
pip install -r requirements.txt
pip install --no-deps -r requirements-langgraph.txt
```

<details>
<summary>為什麼 LangGraph 要分開裝（已知的 pip 相依性問題）</summary>

`langgraph` 1.x 系列的子套件 `langgraph-prebuilt` 在 PyPI 上宣告需要
`langchain-core>=1.0.0`，但這個專案其餘的 `langchain-core` /
`langchain-community` / `langchain-text-splitters` / `langchain-google-genai`
都還固定在 0.2.x（升級到 langchain 1.x 是更大、獨立的遷移，這裡先不
做）。兩邊放進同一次 `pip install -r requirements.txt` 解析，pip 會
直接判定 `ResolutionImpossible`，拒絕安裝整個檔案。

但這只是 metadata 宣告過度保守，不是程式碼真的不相容：這個專案的核心
human-in-the-loop 機制（`interrupt()` / `Command` / checkpointer）、
23 個單元測試、真實瀏覽器操作、真的呼叫過 Gmail API，全部都是在
`langgraph==1.1.3` + `langchain-core==0.2.43` 這個確切組合下驗證的
（包含在一個全新虛擬環境裡重跑過一次，確認兩段式安裝本身也沒問題）。
`--no-deps` 讓 pip 跳過它自己對 `requirements-langgraph.txt` 這幾個
套件的相依性檢查，直接裝這幾個釘死的版本，不會因為「宣告不相容」就讓
整個安裝失敗。（也評估過改用 metadata 上真的解得開的
`langgraph==0.3.34`，但它的 `invoke()` 回傳值不會帶 `__interrupt__`
這個 key，偵測暫停狀態的邏輯得整個改用 `get_state()`，屬於沒驗證過的
改動，風險比目前的做法更高，所以沒有採用。）

升級任何一個套件前，建議先在乾淨的虛擬環境裡照這兩個指令跑一次，確認
新組合真的裝得起來、`pytest tests/ -v` 也真的全過。

</details>

### 1. 設定品牌文案（選用）

不設定則使用預設中性文案（「貴公司」）。

```bash
set COMPANY_NAME=您的公司名稱
set APP_TITLE=企業內部 AI 助理
set APP_SUBTITLE=您的一句話說明
```

### 2. 設定 Google API Key（RAG / LLM 必要）

API Key 是部署層級的基礎設施密鑰，設定的優先順序是：
`.streamlit/secrets.toml` → 環境變數 `GOOGLE_API_KEY` → 側邊欄手動輸入。

**正式部署**（多人共用同一個服務網址時）：

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# 編輯 secrets.toml，填入正式的 GOOGLE_API_KEY
```

由管理員在部署前設定好，一般使用者完全不會、也不需要在畫面上看到或
輸入 API Key。`secrets.toml` 已列在 `.gitignore`，不會被提交進版控。

**本機個人測試**：若都沒有設定，側邊欄才會顯示手動輸入框（畫面上會
標示「本機開發模式」，僅適合單人本機開發，見上方「安全設計」）。

### 3. 建立內部文件知識庫

把您自己的內部文件（`.txt` / `.pdf`）放進 `data/`，取代裡面的範例
文件，然後：

```bash
python ingest.py
```

`data/` 底下有一份 `hr_confidential_salary_bands.txt` 範例機密文件，
用來示範角色過濾檢索（見上方「知識檢索」一節）。

### 4. 建立企業 SQL 資料庫

**快速體驗（預設）：真實公開資料集**

```bash
python sql_ingest.py
```

會從 UCI Machine Learning Repository 下載 **Online Retail II**
（一間英國網路零售商 2009–2011 年間的真實交易紀錄，CC BY 4.0 授權，
非模擬／非 LLM 生成資料），整理成 `customers` / `products` / `orders` /
`order_items` 四張表，存進 `enterprise_data/enterprise.db`，供 SQL 工具
唯讀查詢，模擬「訂單／客戶／產品」這類典型企業資料庫。

**接上正式的企業內部資料庫**：不需要修改任何程式碼，設定
`DATABASE_URL` 環境變數即可，`tools/sql_query.py` 會透過 SQLAlchemy
自動改連正式資料庫：

```bash
# PostgreSQL（需另外 pip install psycopg2-binary）
set DATABASE_URL=postgresql+psycopg2://readonly_user:***@db.internal:5432/erp

# MySQL（需另外 pip install pymysql）
set DATABASE_URL=mysql+pymysql://readonly_user:***@db.internal:3306/erp

# SQL Server（需另外 pip install pyodbc）
set DATABASE_URL=mssql+pyodbc://readonly_user:***@db.internal/erp?driver=ODBC+Driver+17+for+SQL+Server
```

**強烈建議**：連線帳號使用資料庫層級唯讀權限（例如 PostgreSQL 的
`GRANT SELECT`），不要只依賴程式碼裡的 SQL 驗證。

### 5. 設定 Gmail / Google Calendar（選用，任務執行功能需要）

1. 到 [Google Cloud Console](https://console.cloud.google.com/) 建立
   專案，啟用 **Gmail API** 與 **Google Calendar API**
2. 「憑證」→「建立憑證」→「OAuth 用戶端 ID」，應用程式類型選
   **Desktop app**
3. 下載憑證 JSON，重新命名為 `credentials.json`，放到專案根目錄
4. 第一次呼叫 Email／行事曆工具時會自動開啟瀏覽器要求登入並同意授權，
   授權結果會快取到 `token.json`，之後不需重複登入
5. `credentials.json` / `token.json` 已列在 `.gitignore`，切勿提交進
   版控

### 執行

```bash
streamlit run app.py
```

## 專案結構

```
agent.py                對外公開介面：ask() / confirm()，把 graph 的結果整理成 UI 要的形狀
app.py                  Streamlit UI，含使用者/角色選擇、任務確認（人工核可）介面
config.py               品牌文案設定（環境變數）
ingest.py               內部文件 → Chroma 向量索引（含 allowed_roles metadata）
sql_ingest.py            真實公開資料集 → 企業 SQL 範例資料庫
data/                    內部文件（RAG 來源，含一份 RBAC 範例機密文件）
graph/
  state.py                AgentState（messages / pending_action / approval_decision / execution_result）
  nodes.py                 agent／tools／approval／execute 四個節點（RBAC 檢查、log／metrics／稽核都在這裡）
  build.py                  組出 StateGraph 並編譯
auth/
  users.py                 Demo 使用者清單（username → role）
  policy.py                 權限矩陣：is_tool_allowed(role, tool_name)
security/
  sql_ast.py                SQL AST 驗證，取代關鍵字黑名單
  audit.py                   稽核紀錄（user/role/tool/decision → logs/audit.jsonl）
observability/
  logging_config.py          結構化 JSON log
  metrics.py                  Prometheus 指標（預設關閉，ENABLE_METRICS=true 才開）
  prometheus.yml               docker-compose 用的 scrape 設定
  grafana/                      provisioning + 一個現成 dashboard
evals/
  datasets/core_cases.py     版本控制的評測案例
  evaluators.py                評分邏輯（純函式）
  run_evals.py                  CLI：--fake-llm（預設）/ --live
tools/
  knowledge_base.py         RAG 檢索工具（角色過濾 + rerank）
  reranker.py                 本機 cross-encoder
  sql_query.py                 企業資料庫唯讀查詢工具（可切換正式資料庫）
  google_auth.py               Gmail / Calendar 共用 OAuth2
  email_tool.py                  Gmail 查詢／草擬／寄送
  calendar_tool.py               Calendar 查詢／草擬／建立
  web_search.py                   外部搜尋
  calculate.py                      數值計算
tests/
  test_graph_safety.py      graph 結構 + 核准流程
  test_rbac.py                權限在工具呼叫前被擋下
  test_sql_ast_validation.py   AST 驗證擋掉黑名單漏抓的案例
  test_prompt_injection.py      注入指令仍無法繞過 approval
docker-compose.yml          Prometheus + Grafana（app 本身仍跑在主機上）
```

## Roadmap

幾個地方是刻意保持輕量、還沒做到「完整企業部署」的程度，記錄下來避免
誤以為是遺漏：

- **真正的 SSO/IdP**：目前是側邊欄選角色的 Demo 登入，換成公司真正的
  身分系統只需要換掉 `auth/users.py`，RBAC 判斷邏輯不用動
- **FastAPI 後端拆分**：Streamlit 進程本身就是「伺服器端」，RBAC／
  稽核已經是伺服器端強制執行；拆出獨立 API 層是更大的重構，等真的需要
  多種前端（不只 Streamlit）再做
- **把整個 app 容器化**：`docker-compose.yml` 目前只跑 Prometheus/
  Grafana，Streamlit app 仍然直接在主機執行
- **`--live` 評測報告**：`evals/run_evals.py --live` 的機制已驗證可動
  （`--fake-llm` 8/8 通過），但還沒有產出一份對真實模型跑的評測報告
- **混合檢索**：向量 + BM25 的混合檢索沒有做——目前沒有量測數據顯示
  純語意檢索不夠用
- **資料庫層 `statement_timeout`**：目前的查詢逾時是應用層
  （`ThreadPoolExecutor`），不是資料庫本身的設定；接上正式 PostgreSQL
  時建議額外設定
