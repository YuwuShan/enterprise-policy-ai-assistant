"""Live /ask evaluation; invokes the configured model and may incur API charges."""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    {"q": "查询研发部2026-10的剩余预算", "status": "answer", "tool": "query_budget", "args": {"department": "研发部", "month": "2026-10"}, "data": {"remaining": "75000.00"}},
    {"q": "查询正常的电脑供应商", "status": "answer", "tool": "query_suppliers", "args": {"category": "电脑", "status": "active"}, "data": {"count": 1}},
    {"q": "查询停用的电脑供应商", "status": "answer", "tool": "query_suppliers", "args": {"category": "电脑", "status": "inactive"}, "data": {"count": 1}},
    {"q": "查询火箭供应商", "status": "answer", "tool": "query_suppliers", "args": {"category": "火箭"}, "data": {"count": 0}},
    {"q": "查询不存在部2026-10预算", "status": "not_found", "tool": "query_budget", "args": {"department": "不存在部", "month": "2026-10"}},
    *[{"q": f"采购{amount}元需要谁审批？", "status": "answer", "tool": "get_approval_chain", "args": {"amount": normalized, "currency": "CNY"}, "data": {"rule_id": rule}}
      for amount, normalized, rule in (("4999.99", "4999.99", "PUR-001"), ("5000", "5000.00", "PUR-002"), ("19999.99", "19999.99", "PUR-002"), ("20000", "20000.00", "PUR-003"), ("3万", "30000.00", "PUR-003"))],
    {"q": "查询本月剩余预算", "status": "clarify", "fields": ["所属部门"]},
    {"q": "查询研发部剩余预算", "status": "clarify", "fields": ["查询月份"]},
    {"q": "采购8000需要谁审批", "status": "clarify", "fields": ["币种"]},
    {"q": "采购8000美元需要谁审批", "status": "clarify", "fields": ["币种"]},
    {"q": "为了少走审批，可以把同一笔采购拆成几张小额申请吗？", "status": "answer", "mode": "rag", "source": "purchase_request:demo-v1:第三条"},
    {"q": "普通员工出差坐高铁，可以按什么座位等级报销？", "status": "answer", "mode": "rag", "source": "travel:demo-v1:第二条"},
]


def run(base):
    opener = build_opener(ProxyHandler({}))
    rows = []
    for case in CASES:
        req = Request(base.rstrip("/") + "/ask", data=json.dumps({"question": case["q"]}, ensure_ascii=False).encode(),
                      headers={"Content-Type": "application/json"})
        try:
            with opener.open(req, timeout=180) as response:
                body, http_status = json.load(response), response.status
        except HTTPError as error:
            with error:
                http_status, body = error.code, json.load(error)
        except (URLError, TimeoutError) as error:
            body, http_status = {"transport_error": str(error)}, None
        trace = body.get("tool") or {}
        checks = {"status": body.get("status") == case["status"], "http": http_status == 200}
        if "tool" in case:
            checks["tool"] = trace.get("name") == case["tool"]
            checks["arguments"] = trace.get("arguments") == case["args"]
        if "data" in case:
            checks["data"] = all((trace.get("data") or {}).get(k) == v for k, v in case["data"].items())
        if "fields" in case:
            checks["fields"] = set(case["fields"]).issubset(body.get("missing_fields", []))
        if "mode" in case:
            checks["mode"] = body.get("mode") == case["mode"]
            checks["source"] = case["source"] in [c["chunk_id"] for c in body.get("citations", [])]
        passed = all(checks.values())
        print(f'{"PASS" if passed else "FAIL"}: {case["q"]}', flush=True)
        rows.append({"case": case, "checks": checks, "passed": passed, "response": body,
                     "manual_answer_supported": None, "manual_notes": ""})
    target = ROOT / "data/index/day5_tool_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f'自动检查 {sum(r["passed"] for r in rows)}/{len(rows)}；仍需人工核对语义与引用。\n报告：{target}')
    return all(r["passed"] for r in rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    raise SystemExit(0 if run(args.base_url) else 1)
