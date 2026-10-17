from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="OA 智能助手", version="0.1.0")


class AskRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    question: str = Field(min_length=1, max_length=1000)


class AskResponse(BaseModel):
    question: str
    answer: str
    mode: str


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "assistant",
    }


@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest):
    return AskResponse(
        question=body.question,
        answer="问题已收到。当前仅验证接口，尚未接入制度检索。",
        mode="echo",
    )