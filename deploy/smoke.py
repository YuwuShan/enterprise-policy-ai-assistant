"""Check the deployed entrypoint; --live adds three paid-model questions."""
import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


def run(base, live=False):
    opener = build_opener(ProxyHandler({}))

    def request(path, body=None):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = Request(base.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with opener.open(req, timeout=190) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                raw = error.read()
                try:
                    payload = json.loads(raw)
                except ValueError:
                    payload = {"non_json_error": raw[:200].decode("utf-8", errors="replace")}
                return error.code, payload

    code, body = request("/health")
    assert code == 200 and body.get("service") == "assistant", (code, body)
    print("PASS: /health reached assistant through the supplied entrypoint")
    code, body = request("/ask", {"question": ""})
    assert code == 422, (code, body)
    print("PASS: invalid input rejected with 422 before invoking a model")
    if not live:
        print("No model request made. Use --live for business-path checks.")
        return
    cases = [
        ("采购8000元谁审批？", "get_approval_chain", "rule_id", "PUR-002"),
        ("查询研发部2026-10预算", "query_budget", "remaining", "75000.00"),
        ("查询停用的电脑供应商", "query_suppliers", "count", 1),
    ]
    for question, tool, key, value in cases:
        code, body = request("/ask", {"question": question})
        trace = body.get("tool") or {}
        assert code == 200 and body.get("status") == "answer" and trace.get("name") == tool, (code, body)
        assert (trace.get("data") or {}).get(key) == value, body
        print(f"PASS: {question}")
    print("Live checks passed for Day 2 seed data. RAG coverage needs the Day 5 evaluation too.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        run(args.base_url, args.live)
    except (AssertionError, URLError, TimeoutError, ValueError) as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
