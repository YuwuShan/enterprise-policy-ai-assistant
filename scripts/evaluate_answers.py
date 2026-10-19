import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from rag.documents import ROOT, load_chunks


def call_api(question):
    base = os.getenv("ASSISTANT_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    request = Request(base + "/ask", method="POST",
                      data=json.dumps({"question": question}, ensure_ascii=False).encode("utf-8"),
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=180) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        with error:
            return error.code, json.load(error)
    except (URLError, TimeoutError) as error:
        return 0, {"error": type(error).__name__}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["base", "expanded", "all"], default="all")
    args = parser.parse_args()
    cases = json.loads((ROOT / "data" / "day4_cases.json").read_text(encoding="utf-8-sig"))
    cases = [c for c in cases if args.stage == "all" or c["stage"] == args.stage]
    corpus = {c["chunk_id"]: c for c in load_chunks()}
    results = []
    for case in cases:
        code, response = call_api(case["question"])
        citations = response.get("citations", [])
        structure_ok = bool(citations) and all(
            c.get("chunk_id") in corpus
            and bool(c.get("quote"))
            and c["quote"] in corpus[c["chunk_id"]]["text"]
            and all(c.get(k) == corpus[c["chunk_id"]][k]
                    for k in ("title", "version", "article", "source_file", "scope"))
            for c in citations
        )
        status_ok = code == 200 and response.get("status") == case["expected_status"]
        expected_ids = set(case["expected_chunk_ids"])
        target_hit = expected_ids.issubset({c.get("chunk_id") for c in citations}) if expected_ids else None
        results.append({**case, "http_status": code, "response": response,
                        "status_matches": status_ok, "expected_citations_present": target_hit,
                        "citation_structure_valid": structure_ok if response.get("status") == "answer" else None,
                        "human_review": {"content_correct": None, "citations_support": None, "conditions_preserved": None}})
        print(f"{case['id']} HTTP={code} status={response.get('status')} expected={case['expected_status']} match={status_ok}")

    report = {
        "note": "状态匹配和引用结构检查不等于回答正确率；必须逐题填写人工评估。",
        "total": len(results), "status_matches": sum(x["status_matches"] for x in results),
        "http_errors": sum(x["http_status"] != 200 for x in results),
        "refused_answerable": sum(x["expected_status"] == "answer" and x["response"].get("status") == "refuse" for x in results),
        "results": results,
    }
    target = ROOT / "data" / "index" / f"day4_{args.stage}_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"状态匹配 {report['status_matches']}/{report['total']}；HTTP错误 {report['http_errors']}；报告：{target}")
    print("请人工检查内容、适用条件和引用支持关系；不要把状态匹配率写成准确率。")


if __name__ == "__main__":
    main()
