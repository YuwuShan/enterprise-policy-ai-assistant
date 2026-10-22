"""Structural checks are not a substitute for human semantic review."""
from assistant.schemas import AskResponse


def grade(case, code, body, sources):
    checks = {"http_200": code == 200, "response_schema": False}
    try:
        response = AskResponse.model_validate(body)
    except (ValueError, TypeError):
        return checks
    checks["response_schema"] = True
    expected = case["expected"]
    checks["status"] = response.status == expected["status"]
    checks["question_echo"] = response.question == case["question"]
    checks["request_id"] = bool(response.request_id)
    checks["answer_nonempty"] = bool(response.answer.strip())
    if "mode" in expected:
        checks["mode"] = response.mode == expected["mode"]
    if expected.get("no_tool"):
        checks["no_tool_trace"] = response.tool is None
    if "fields" in expected:
        checks["missing_fields"] = set(expected["fields"]) <= set(response.missing_fields)
    if "tool" in expected:
        trace = response.tool
        checks["tool_name"] = trace is not None and trace.name == expected["tool"]
        checks["tool_arguments"] = trace is not None and trace.arguments == expected["arguments"]
        checks["no_policy_citations_for_tool"] = not response.citations
        data = trace.data if trace else None
        if expected.get("data_is_null"):
            checks["data_is_null"] = trace is not None and data is None
        if "data" in expected:
            checks["tool_data"] = isinstance(data, dict) and all(data.get(k) == v for k,v in expected["data"].items())
        if "supplier_ids" in expected:
            items = data.get("items") if isinstance(data, dict) else None
            checks["supplier_ids"] = isinstance(items, list) and all(isinstance(i,dict) for i in items) and sorted(i.get("id","") for i in items) == sorted(expected["supplier_ids"])
    if response.status != "answer":
        checks["non_answer_has_no_citations"] = not response.citations
    if "source" in expected:
        checks["expected_source"] = expected["source"] in [c.chunk_id for c in response.citations]
    if response.status == "answer" and response.mode == "rag":
        checks["rag_has_citations"] = bool(response.citations)
        checks["citation_integrity"] = all(
            (source := sources.get(c.chunk_id)) is not None
            and bool(c.quote.strip()) and c.quote in source["text"]
            and all(getattr(c,k) == source[k] for k in ("title","version","article","source_file","scope"))
            and f"[{c.number}]" in response.answer
            for c in response.citations
        )
    return checks


def metrics(rows):
    total = len(rows)
    reviewed = [r for r in rows if type(r.get("human_ok")) is bool]
    return {
        "total": total,
        "automatic_pass": sum(r["automatic_pass"] for r in rows),
        "reviewed": len(reviewed),
        "human_pass_among_reviewed": sum(r["human_ok"] for r in reviewed),
        "human_pass_all": sum(r["human_ok"] for r in reviewed) if len(reviewed) == total else None,
        "complete_pass_all": sum(r["automatic_pass"] and r["human_ok"] is True for r in rows) if len(reviewed) == total else None,
    }
