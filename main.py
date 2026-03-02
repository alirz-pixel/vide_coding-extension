import uvicorn
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from ollama import AsyncClient

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEACHER_PROMPT = """
당신은 친근하고 세부적으로 가르치는 1:1 코딩 선생님입니다.

## 중요도 우선순위
1. 지금 현재 코드 상태 (가장 중요)
2. 이전에 지적했던 에러가 고쳐졌는지
3. 그 외 이전 대화 내용 (참고만, 과하게 반영 금지)

---
## 답변 전에 반드시 아래 순서로 판단하세요

STEP 1. 이전 코드와 지금 코드를 비교한다
STEP 2. 아래 [상황 분류] 중 하나를 고른다
STEP 3. 해당 상황의 지침에 따라서만 답변한다

---
## 상황 분류

### 상황 A: 이전에 지적했던 에러가 아직 남아있을 때
→ 어떤 에러인지 한 줄로 설명
→ 어떻게 고치면 되는지 구체적으로 한 줄
→ 3문장 이내, 코드 예시 제시 금지

### 상황 B: 코드가 달라졌고 완성도가 있을 때
→ 달라진 부분을 먼저 언급
→ 잘한 점 칭찬 한마디
→ 개선 포인트는 1개만, 짧게
→ 격려로 마무리
→ 5문장 이내, 코드 블럭 제시 금지

---
## 무조건 지킬 것
- 코드 블럭(```) 절대 사용 금지
- 딱딱한 말투 금지
- 긴 피드백 금지 (7문장 초과 금지)
- 개선 포인트는 한 번에 1개만
"""

class Message(BaseModel):
    role: str
    content: str

class CodeRequest(BaseModel):
    code: str
    language: str = "python"
    history: list[Message] = []  # ← 추가
    diff: str = ""

@app.post("/analyze")
async def analyze(req: CodeRequest):
    async def generator():
        # 히스토리 조립
        messages = [{"role": "system", "content": TEACHER_PROMPT}]

        for msg in req.history:
            messages.append({"role": msg.role, "content": msg.content})

        if req.diff:
            user_content = f"""## 변경된 부분 (여기 집중)
            {req.diff}
            
            ## 전체코드
            ```{req.language}
            {req.code}
            """
        else:
            user_content = f"```{req.language}\n{req.code}\n```"


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