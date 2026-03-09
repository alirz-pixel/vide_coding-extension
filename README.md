## 아키텍처

```
[VS Code Extension]
        │
        │ code + history
        ↓
[FastAPI Backend]
        │
        ├──→ [RAG - retrieve()]
        │           │
        │           ├──→ [Ollama qwen2.5:1.5b]  ← 키워드 추출
        │           │
        │           └──→ [ChromaDB]              ← 벡터 검색 (BAAI/bge-m3)
        │
        │ system prompt 조합
        ├──→ [PromptBuilder]
        │           │
        │           └──→ [templates/teacher.yaml]
        │
        │ 조합된 messages
        ↓
[Ollama qwen2.5-coder:14b]                       ← 메인 코드 분석
        │
        │ 스트리밍 응답 (SSE)
        ↓
[VS Code - 캐릭터 말풍선 UI]
```

## TechStack
- **Data/Storage:** `Vector DB (ChromaDB)`
- **LLM Runtime:** `Ollama (Local LLM)`, `qwen2.5-coder:14b (메인)`, `qwen2.5:1.5b (경량)`
- **Backend:** `FastAPI`, `Requests / BeautifulSoup`
- **Frontend:** `VS Code Extension (TypeScript)`, `Webview Panel (HTML / CSS / JS)`
