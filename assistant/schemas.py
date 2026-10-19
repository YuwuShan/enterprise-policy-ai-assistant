from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MissingField = Literal["出差城市", "员工身份", "金额", "币种", "所属部门", "查询月份", "业务场景"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AskRequest(StrictModel):
    question: str = Field(min_length=1, max_length=1000)


class Evidence(StrictModel):
    chunk_id: str = Field(min_length=1)
    quote: str = Field(min_length=4, max_length=1800)


class Claim(StrictModel):
    text: str = Field(min_length=1, max_length=500)
    evidence: list[Evidence] = Field(min_length=1, max_length=3)


class Draft(StrictModel):
    status: Literal["answer", "clarify", "refuse", "needs_tool"]
    claims: list[Claim] = Field(default_factory=list, max_length=5)
    missing_fields: list[MissingField] = Field(default_factory=list, max_length=7)
    refusal_reason: Literal["insufficient_evidence", "conflict"] = "insufficient_evidence"

    @model_validator(mode="after")
    def check_status(self):
        if self.status == "answer" and (not self.claims or self.missing_fields):
            raise ValueError("回答必须有带证据的结论，且不能同时要求补充条件")
        if self.status != "answer" and self.claims:
            raise ValueError("非回答状态不能携带结论")
        if (self.status == "clarify") != bool(self.missing_fields):
            raise ValueError("只有追问状态可以且必须包含待补充条件")
        return self


class Review(StrictModel):
    verdict: Literal["supported", "unsupported", "missing_context", "conflict"]
    missing_fields: list[MissingField] = Field(default_factory=list, max_length=7)

    @model_validator(mode="after")
    def check_fields(self):
        if (self.verdict == "missing_context") != bool(self.missing_fields):
            raise ValueError("缺少上下文时必须指出待补充条件")
        return self


class Citation(StrictModel):
    number: int
    chunk_id: str
    title: str
    version: str
    article: str
    source_file: str
    scope: str
    quote: str


class AskResponse(StrictModel):
    request_id: str = ""
    question: str
    status: Literal["answer", "clarify", "refuse", "needs_tool"]
    answer: str
    reason: str
    citations: list[Citation] = Field(default_factory=list)
    missing_fields: list[MissingField] = Field(default_factory=list)
    mode: Literal["rag"] = "rag"
