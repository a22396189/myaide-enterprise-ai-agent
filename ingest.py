# ingest.py
# 執行一次：python ingest.py
# 會在 ./chroma_db 目錄建立向量索引

import os
from pathlib import Path
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma

# ── 設定 ──────────────────────────────────────────────
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "your-api-key-here")
DATA_DIR       = Path("./data")
CHROMA_DIR     = "./chroma_db"
COLLECTION     = "company_knowledge"

# ── 載入文件 ──────────────────────────────────────────
def load_documents(data_dir: Path):
    docs = []
    for file in sorted(data_dir.iterdir()):
        # langchain-community 已停止維護，文件載入直接用 pypdf／讀檔，
        # 不再依賴它的 TextLoader / PyPDFLoader
        if file.suffix == ".txt":
            loaded = [Document(page_content=file.read_text(encoding="utf-8"))]
            # 在 metadata 記錄來源檔名，方便引用
            for doc in loaded:
                doc.metadata["source"] = file.name
                doc.metadata["display_name"] = {
                    "company_policy.txt": "公司規章手冊",
                    "MES_Ops_Manual_v1.0.txt": "MES 操作手冊",
                    "faq.txt":            "常見問題集",
                    "hr_confidential_salary_bands.txt": "薪資職等對照表（機密）",
                }.get(file.name, file.name)
                # allowed_roles："*" 代表所有角色都能查到；否則是逗號分隔的
                # 角色清單，由 tools/knowledge_base.py 依目前使用者角色過濾。
                # Chroma 的 metadata 值只能是純量，所以存成字串而不是 list。
                doc.metadata["allowed_roles"] = {
                    "hr_confidential_salary_bands.txt": "hr,finance,manager,admin",
                }.get(file.name, "*")
            docs.extend(loaded)
        elif file.suffix == ".pdf":
            # 與 PyPDFLoader 相同：一頁一個 Document，metadata 帶頁碼
            loaded = [
                Document(page_content=page.extract_text() or "", metadata={"page": i})
                for i, page in enumerate(PdfReader(str(file)).pages)
            ]
            for doc in loaded:
                doc.metadata["source"]       = file.name
                doc.metadata["display_name"] = file.stem
                doc.metadata["allowed_roles"] = "*"
            docs.extend(loaded)

    print(f"載入 {len(docs)} 份文件")
    return docs

# ── 切塊 ──────────────────────────────────────────────
def split_documents(docs):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,        # 每塊最多 500 字元
        chunk_overlap=80,      # 重疊 80 字元，避免語意被截斷
        separators=["\n\n", "\n", "。", "，", " ", ""],
    )
    chunks = splitter.split_documents(docs)
    print(f"切成 {len(chunks)} 個 chunks")
    return chunks

# ── 建立向量索引 ──────────────────────────────────────
def build_index(chunks):
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",  # Gemini 嵌入模型
        google_api_key=GOOGLE_API_KEY,
    )
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=COLLECTION,
        persist_directory=CHROMA_DIR,
    )
    print(f"索引建立完成，儲存於 {CHROMA_DIR}")
    return vectorstore

if __name__ == "__main__":
    docs   = load_documents(DATA_DIR)
    chunks = split_documents(docs)
    build_index(chunks)
