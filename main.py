import uvicorn
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from ollama import AsyncClient

from rag.retrieve import retrieve
from prompts.builder import PromptBuilder

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

builder = PromptBuilder()

class Message(BaseModel):
    role: str
    content: str

class CodeRequest(BaseModel):
    code: str
    language: str = "python"
    history: list[Message] = []  # ← 추가
    prev_code: str = ""

@app.post("/analyze")
async def analyze(req: CodeRequest):
    async def generator():
        # 관련 문서 검색
        doc_context = retrieve(req.code, req.language)

        # system prompt 로드
        system_prompt = builder.build_system(doc_context)
        messages = [{"role": "system", "content": system_prompt}]

        # 히스토리 조립
        messages += builder.build_message(req.history, req.code)

        client = AsyncClient()
        full_response = ""

        async for chunk in await client.chat(
            model="qwen2.5-coder:14b",
            messages=messages,
            stream=True
        ):
            token = chunk["message"]["content"]
            full_response += token
            yield {"data": json.dumps({"content": token})}

        # 완성된 응답 전체를 마지막에 같이 전송 (Extension에서 히스토리에 추가용)
        yield {"data": json.dumps({"done": True, "full": full_response})}

    return EventSourceResponse(generator())


if __name__ == "__main__":
    print("서버 시작: http://localhost:8765")
    uvicorn.run(app, host="localhost", port=8765)