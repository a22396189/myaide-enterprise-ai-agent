# check_models.py
# 執行：python check_models.py
# 列出你的 API key 可用的 LLM 與 embedding 模型（用 google-genai SDK，
# 舊的 google-generativeai 套件已不再使用）

import os

from google import genai

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
if not GOOGLE_API_KEY:
    print("❌ 找不到 GOOGLE_API_KEY，請先設定環境變數")
    exit(1)

client = genai.Client(api_key=GOOGLE_API_KEY)
models = list(client.models.list())

print("=== 支援 generateContent 的 LLM 模型 ===\n")
chat_models = [m.name for m in models if "generateContent" in (m.supported_actions or [])]
for name in chat_models:
    print(f"  ✅ {name}")

print(f"\n=== 支援 embedContent 的 Embedding 模型 ===\n")
embedding_models = [m.name for m in models if "embedContent" in (m.supported_actions or [])]
for name in embedding_models:
    print(f"  ✅ {name}")

print(f"\n專案目前使用：LLM = gemini-3.8-flash，Embedding = gemini-embedding-001")
