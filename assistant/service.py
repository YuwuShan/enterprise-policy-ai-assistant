import json

from pydantic import ValidationError

from assistant.prompts import ANSWER_PROMPT, REVIEW_PROMPT
from assistant.schemas import AskResponse, Citation, Draft, Review
from rag.search import search


class ModelOutputError(RuntimeError):
    pass


class KnowledgeUnavailable(RuntimeError):
    pass


def parse_output(text, schema):
    try:
        return schema.model_validate_json(text)
    except (ValidationError, TypeError) as error:
        raise ModelOutputError("模型输出不符合约定结构") from error


def ask_model(prompt, schema, data):
    from model_client import create_client, required_env

    with create_client() as client:
        response = client.chat.completions.create(
            model=required_env("CHAT_MODEL"),
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps({
                    "schema": schema.model_json_schema(), "data": data,
                }, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            extra_body={"enable_thinking": False},
            temperature=0,
            max_tokens=1800,
        )
    if not response.choices or response.choices[0].finish_reason != "stop":
        raise ModelOutputError("模型输出未完整结束")
    return parse_output(response.choices[0].message.content or "", schema)

def non_answer(question, status, reason, fields=None):
    fields = list(dict.fromkeys(fields or []))
    messages = {
        "needs_tool": "本次制度问答流程判断需要查询 OA。请把部门、月份或采购金额和币种写完整，再单独提交查询。",
        "clarify": "还需要补充以下条件，才能确定适用规定：" + "、".join(fields) + "。请补齐后重新提交完整问题。",
        "insufficient_evidence": "现有检索材料不足以确定答案，请补充相关制度或咨询制度负责人。",
        "conflict": "检索材料存在无法确定优先级的冲突，暂时不能给出确定结论，请确认适用版本。",
        "citation_check_failed": "候选回答的引用未通过核验，暂时不能据此作答。",
        "unsupported": "候选回答未得到检索材料的充分支持，暂时不能据此作答。",
    }
    key = status if status in ("clarify", "needs_tool") else reason
    return AskResponse(question=question, status=status, answer=messages[key],
                       reason=reason, missing_fields=fields)


def valid_citations(draft, hits):
    available = {hit["chunk_id"]: hit for hit in hits}
    for claim in draft.claims:
        for item in claim.evidence:
            source = available.get(item.chunk_id)
            if source is None or item.quote not in source["text"]:
                return False
    return True


def render_answer(question, draft, hits):
    available = {hit["chunk_id"]: hit for hit in hits}
    citations, numbers, lines = [], {}, []
    for claim in draft.claims:
        refs = []
        for item in claim.evidence:
            key = (item.chunk_id, item.quote)
            if key not in numbers:
                source = available[item.chunk_id]
                number = len(citations) + 1
                numbers[key] = number
                citations.append(Citation(
                    number=number, chunk_id=item.chunk_id, quote=item.quote,
                    **{k: source[k] for k in ("title", "version", "article", "source_file", "scope")},
                ))
            refs.append(f"[{numbers[key]}]")
        lines.append(claim.text + " " + "".join(dict.fromkeys(refs)))
    return AskResponse(question=question, status="answer", answer="\n".join(lines),
                       reason="supported", citations=citations)


def answer_question(question):
    try:
        hits = search(question, top_k=5)
    except (RuntimeError, ValueError, OSError, KeyError) as error:
        raise KnowledgeUnavailable("知识库不可用，请检查资料与索引") from error
    if not hits:
        return non_answer(question, "refuse", "insufficient_evidence")

    evidence = [{k: h[k] for k in (
        "chunk_id", "title", "version", "article", "scope", "text",
    )} for h in hits]
    draft = ask_model(ANSWER_PROMPT, Draft, {"question": question, "evidence": evidence})
    if draft.status == "needs_tool":
        return non_answer(question, "needs_tool", "requires_oa")
    if draft.status == "clarify":
        return non_answer(question, "clarify", "missing_context", draft.missing_fields)
    if draft.status == "refuse":
        return non_answer(question, "refuse", draft.refusal_reason)

    if not valid_citations(draft, hits):
        return non_answer(question, "refuse", "citation_check_failed")
    review = ask_model(REVIEW_PROMPT, Review, {
        "question": question, "evidence": evidence, "draft": draft.model_dump(),
    })
    if review.verdict == "missing_context":
        return non_answer(question, "clarify", "missing_context", review.missing_fields)
    if review.verdict != "supported":
        return non_answer(question, "refuse", review.verdict)
    return render_answer(question, draft, hits)
