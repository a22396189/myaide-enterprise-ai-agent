# check_models.py
# 執行：python check_models.py
# 列出你的 API key 可用的所有 embedding 模型

import os
import google.generativeai as genai

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
if not GOOGLE_API_KEY:
    print("❌ 找不到 GOOGLE_API_KEY，請先設定環境變數")
    exit(1)

genai.configure(api_key=GOOGLE_API_KEY)

print("=== 支援 generateContent 的 LLM 模型 ===\n")
chat_models = []
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(f"  ✅ {m.name}")
        chat_models.append(m.name)

print(f"\n=== 支援 embedContent 的 Embedding 模型 ===\n")
embedding_models = []
for m in genai.list_models():
    if "embedContent" in m.supported_generation_methods:
        print(f"  ✅ {m.name}")
        embedding_models.append(m.name)

print(f"\n建議 LLM 使用：    {chat_models[0] if chat_models else '無'}")
print(f"建議 Embedding 使用：{embedding_models[0] if embedding_models else '無'}")
