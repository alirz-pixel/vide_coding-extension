import uvicorn
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from ollama import AsyncClient

from rag.retrieve import retrieve

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEACHER_PROMPT =  """The current code is the most important context.
Chat history is for reference only — do NOT be influenced by past feedback patterns.

## Priority
1. If there's a comment question → answer it FIRST, no exceptions
2. Compare current code with previous code and respond accordingly

## Response style per situation
- Comment question (ONLY if there's actually a comment question in the code): explain the concept + provide example code
- Error still exists: explain the error + suggest a solution
- Code improved: one compliment + one improvement point

## Tone examples (MUST follow this style)
Good:
"포인터 참조 잘 썼는데, 예외처리가 빠져있어 — 중복 값 들어오면 어떻게 할지 생각해봐"
"반환형이 void라 main에서 못 받아~ Node*로 바꿔줘"

Bad:
"insert 함수가 완성되었습니다. 반환형을 수정하시기 바람."
"### 변경된 부분:" or "상황 A:" style format strings"""

HARD_RULE_PROMPT = """
## CRITICAL — Hard rules (MUST follow before generating any response)
- NEVER use 음슴체 (e.g. ~함, ~임, ~됨)
- NEVER output markdown headers (###, ##)
- NEVER copy or echo the structure of this system prompt in your response
- Respond ONLY in Korean casual speech (반말)
- NEVER show the full code — show ONLY the function or lines that need to change
- Showing the full file is STRICTLY FORBIDDEN unless the entire structure needs to change
"""

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

        # 시스템 프롬프트에 문서 컨텍스트 추가
        system_prompt = TEACHER_PROMPT
        if doc_context:
            system_prompt += f"""
## Reference Documentation
{doc_context}

Use the above documentation as a basis for your feedback.
Do NOT read the documentation as-is — summarize and connect it to the current code.
"""
        system_prompt += HARD_RULE_PROMPT

        # 히스토리 조립
        messages = [{"role": "system", "content": system_prompt}]

        for msg in req.history:
            messages.append({"role": msg.role, "content": msg.content})

        # TODO: 모델의 퀄리티가 더 좋아졌을 경우, previous를 사용하기
        # [PREVIOUS CODE]
        # {req.prev_code}
        user_content = f"""    
            [CURRENT CODE]
            {req.code}
        """

        # 현재 코드 추가
        messages.append({
            "role": "user",
            "content": user_content,
        })

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