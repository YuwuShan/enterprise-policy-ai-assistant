"""Run from Windows against the HTTPS domain. Credentials are entered interactively."""
import argparse
import base64
from getpass import getpass
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def evaluate_case(case, code, body):
    trace = body.get("tool") or {}
    checks = {"http": code == 200, "status": body.get("status") == case["status"]}
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
    return checks


def run(base, username, live):
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("请输入HTTPS站点根地址，例如https://oa.example.com，不带账号、路径和参数")
    if not username or ":" in username or not username.isascii():
        raise ValueError("演示用户名请使用不含冒号的ASCII字符")
    base = "https://" + parsed.netloc
    opener = build_opener(ProxyHandler({}), NoRedirect())
    rows = []

    def request(url, body=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Basic " + token
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = Request(url, data=data, headers=headers)
        try:
            response = opener.open(req, timeout=190)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            try:
                content = json.loads(raw)
            except ValueError:
                content = {"non_json_response": True}
            return response.code, content, response.headers

    code, _, headers = request("http://" + parsed.hostname + "/")
    expected_location = base + "/"
    if code != 308 or headers.get("Location") != expected_location:
        raise ValueError("HTTP没有重定向到预期HTTPS域名")
    rows.append({"check": "http_redirect", "passed": True})
    code, _, _ = request(base + "/")
    if code != 401:
        raise ValueError("未登录访问演示页未返回401，请检查访问控制")
    code, _, _ = request(base + "/ask", {"question": ""})
    if code != 401:
        raise ValueError("未登录访问/ask未返回401，请检查访问控制")
    rows.append({"check": "unauthenticated_root_and_ask", "passed": True})
    # No redirects are followed, so credentials cannot be forwarded to a redirect target.
    token = base64.b64encode((username + ":" + getpass("Demo password (hidden): ")).encode("utf-8")).decode("ascii")
    code, _, _ = request(base + "/", token=token)
    if code != 200:
        raise ValueError("登录后仍无法访问演示页，请核对账号")
    code, body, _ = request(base + "/health")
    if code != 200 or body.get("service") != "assistant":
        raise ValueError("HTTPS健康检查未到达assistant")
    code, _, _ = request(base + "/ask", {"question": ""}, token)
    if code != 422:
        raise ValueError("非法输入未返回422")
    rows.append({"check": "authenticated_page_health_validation", "passed": True})
    print("PASS: HTTPS certificate verification, redirect, login, health and input checks")
    if live:
        from scripts.evaluate_tools import CASES
        cases = list(CASES) + [{"q": "我们公司允许员工带宠物来办公室吗？", "status": "refuse"}]
        for case in cases:
            time.sleep(3)
            code, body, _ = request(base + "/ask", {"question": case["q"]}, token)
            checks = evaluate_case(case, code, body)
            passed = all(checks.values())
            print(f'{"PASS" if passed else "FAIL"}: {case["q"]}', flush=True)
            rows.append({"case": case, "checks": checks, "passed": passed, "response": body,
                         "manual_answer_supported": None, "manual_notes": ""})
    target = ROOT / "data/index/day7_acceptance.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {target}. Password and Authorization header are not saved.")
    return all(row["passed"] for row in rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--user", default="demo")
    parser.add_argument("--live", action="store_true", help="Also send 17 real questions; model usage is billable")
    args = parser.parse_args()
    try:
        ok = run(args.base_url, args.user, args.live)
    except Exception as error:
        print(f"FAIL: {type(error).__name__}: {error}")
        raise SystemExit(1)
    raise SystemExit(0 if ok else 1)
