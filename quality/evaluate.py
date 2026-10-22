"""HTTPS regression runner. Explicit --live is required; passwords are never saved."""
import argparse
import base64
from datetime import datetime, timezone
from getpass import getpass
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

from quality.checks import grade, metrics
from rag.documents import fingerprint, load_chunks

ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = ROOT / "quality/cases.json"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_cases():
    cases = json.loads(CASE_PATH.read_text(encoding="utf-8-sig"))
    assert cases and len({c["id"] for c in cases}) == len(cases), "用例ID为空或重复"
    sources = {c["chunk_id"]:c for c in load_chunks()}
    for c in cases:
        if "source" in c["expected"]:
            assert c["expected"]["source"] in sources, c["id"] + " 的预期条款不存在"
    return cases, sources


def git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8", stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def valid_base(value):
    p = urlsplit(value)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.path not in ("", "/") or p.query or p.fragment or p.port not in (None,443):
        raise ValueError("仅接受HTTPS根地址，例如 https://oa.jacewood.work")
    return "https://" + p.netloc


def run(args):
    cases, sources = load_cases()
    if not args.live:
        print(f"预检查通过：{len(cases)}题，预期条款全部存在；没有发起HTTP请求。")
        print("实际评测加 --live，会调用站点的模型API并产生费用。")
        return True
    base = valid_base(args.base_url)
    if not args.user or not args.user.isascii() or ":" in args.user:
        raise ValueError("用户名须为不含冒号的ASCII字符")
    opener = build_opener(ProxyHandler({}), NoRedirect())
    token = base64.b64encode((args.user + ":" + getpass("Demo password (hidden): ")).encode("utf-8")).decode("ascii")
    auth = {"Authorization":"Basic " + token}
    # Verify login once, without a model call, and never forward credentials on redirects.
    with opener.open(Request(base + "/", headers=auth), timeout=20) as response:
        if response.status != 200:
            raise ValueError("登录检查未返回200")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    target = ROOT / "data/index/day8" / run_id
    target.mkdir(parents=True, exist_ok=False)
    write_json(target / "meta.json", {
        "run_id":run_id, "base_url":base, "created_at_utc":datetime.now(timezone.utc).isoformat(),
        "local_commit":git("rev-parse","HEAD"), "local_dirty":bool(git("status","--porcelain")),
        "server_revision_user_supplied":args.server_revision,
        "server_revision_independently_verified":False,
        "model_label_user_supplied":args.model_label,
        "local_corpus_fingerprint":fingerprint(list(sources.values())),
        "cases_sha256":hashlib.sha256(CASE_PATH.read_bytes()).hexdigest(),
        "planned":len(cases), "dataset_role":"development regression; not an independent test set",
    })
    write_json(target / "cases.json", cases)
    print("评测目录：", target, flush=True)
    with (target / "results.jsonl").open("x", encoding="utf-8") as output:
        for case in cases:
            time.sleep(3)
            data = json.dumps({"question":case["question"]}, ensure_ascii=False).encode("utf-8")
            req = Request(base + "/ask", data=data, headers={**auth,"Content-Type":"application/json"})
            started = time.perf_counter()
            code, body = None, {}
            try:
                try:
                    response = opener.open(req, timeout=190)
                except HTTPError as error:
                    response = error
                with response:
                    code = response.code
                    raw = response.read(2_000_001)
                    if len(raw) > 2_000_000:
                        raise ValueError("ResponseTooLarge")
                    try:
                        body = json.loads(raw)
                    except ValueError:
                        body = {"non_json_response":True}
            except (OSError, ValueError) as error:
                body = {"transport_error_type":type(error).__name__}
            elapsed = round(time.perf_counter() - started, 3)
            checks = grade(case, code, body, sources)
            row = {"id":case["id"], "group":case["group"], "question":case["question"],
                   "http_status":code, "elapsed_seconds":elapsed, "checks":checks,
                   "automatic_pass":all(checks.values()), "response":body}
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()  # Completed rows survive a later interruption.
            print(case["id"], "PASS" if row["automatic_pass"] else "FAIL", f"{elapsed:.2f}s", flush=True)
            if code in (401,403,429):
                print("登录/限流状态异常，停止本轮；保留已有结果。")
                break
    summary(target)
    return all(r["automatic_pass"] for r in read_rows(target)) and len(read_rows(target)) == len(cases)


def read_rows(target):
    path = target / "results.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def with_reviews(target):
    rows = read_rows(target)
    review_path = target / "reviews.json"
    reviews = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
    for row in rows:
        item = reviews.get(row["id"], {})
        row["human_ok"] = item.get("human_ok")
        row["human_notes"] = item.get("notes", "")
    return rows, reviews


def review(target):
    rows, reviews = with_reviews(target)
    cases = {c["id"]:c for c in json.loads((target / "cases.json").read_text(encoding="utf-8"))}
    for row in rows:
        if type(row["human_ok"]) is bool:
            continue
        case = cases[row["id"]]
        print("\n", row["id"], row["question"])
        print("人工判定标准：", case["rubric"])
        print("自动检查：", row["checks"])
        print(json.dumps(row["response"], ensure_ascii=False, indent=2))
        while True:
            value = input("业务结论、适用条件、来源均正确？y=是 n=否 s=暂不判断 q=退出：").strip().lower()
            if value in ("y","n","s","q"):
                break
        if value == "q":
            break
        if value == "s":
            continue
        notes = input("记录判断理由（失败必须填写）：").strip()
        while value == "n" and not notes:
            notes = input("请记录错误或缺失的具体事实：").strip()
        reviews[row["id"]] = {"human_ok":value == "y", "notes":notes}
        write_json(target / "reviews.json", reviews)
    summary(target)


def summary(target):
    rows, _ = with_reviews(target)
    meta = json.loads((target / "meta.json").read_text(encoding="utf-8"))
    m = metrics(rows)
    complete = len(rows) == meta["planned"]
    times = sorted(r["elapsed_seconds"] for r in rows if r["http_status"] == 200)
    def count(value, n):
        return "未完成，不出总通过率" if value is None else f"{value}/{n}"
    lines = ["# Day 8 评测报告", "", f"运行：{meta['run_id']}",
             f"计划/实际执行：{meta['planned']}/{len(rows)}", f"本地代码：{meta['local_commit']}",
             f"本地有未提交修改：{meta['local_dirty']}",
             f"服务器版本（用户记录，脚本未核验）：{meta['server_revision_user_supplied']}",
             f"模型标签（用户记录）：{meta['model_label_user_supplied']}", "",
             f"自动检查通过（已执行题）：{m['automatic_pass']}/{len(rows)}",
             f"人工完成：{m['reviewed']}/{len(rows)}",
             f"人工判对（已复核题）：{m['human_pass_among_reviewed']}/{m['reviewed']}",
             "全部计划题人工判对：" + count(m['human_pass_all'] if complete else None, meta['planned']),
             "全部计划题自动与人工同时通过：" + count(m['complete_pass_all'] if complete else None, meta['planned']), ""]
    if times:
        lines += [f"HTTP 200 请求延迟中位数：{statistics.median(times):.3f}s；P95（最近秩）：{times[math.ceil(.95*len(times))-1]:.3f}s；样本{len(times)}。",
                  "延迟仅是本轮串行客户端观测，HTTP 200包括拒答和追问，不代表并发能力。", ""]
    lines += ["本题集用于开发回归；自动结构检查、同模型复核及单人评审均不能证明生产准确率。", "",
              "| ID | 自动 | 人工 | HTTP | 秒 |", "|---|---|---|---|---|"]
    for r in rows:
        human = "待复核" if type(r["human_ok"]) is not bool else ("通过" if r["human_ok"] else "失败")
        lines.append(f"| {r['id']} | {'通过' if r['automatic_pass'] else '失败'} | {human} | {r['http_status']} | {r['elapsed_seconds']} |")
    for group in sorted({r["group"] for r in rows}):
        part = [r for r in rows if r["group"] == group]
        lines.append(f"\n{group} 自动通过：{sum(r['automatic_pass'] for r in part)}/{len(part)}。")
    text = "\n".join(lines) + "\n"
    (target / "SUMMARY.md").write_text(text, encoding="utf-8")
    print(text)
    print("报告：", target / "SUMMARY.md")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--base-url", default="https://oa.jacewood.work")
    run_parser.add_argument("--user", default="demo")
    run_parser.add_argument("--server-revision", default="unknown")
    run_parser.add_argument("--model-label", default="unknown")
    run_parser.add_argument("--live", action="store_true")
    for name in ("review","summary"):
        sub.add_parser(name).add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        return run(args)
    if args.command == "review":
        review(args.directory)
    else:
        summary(args.directory)
    return True


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
