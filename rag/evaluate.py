import json

from rag.documents import ROOT
from rag.search import search


def main():
    cases = json.loads((ROOT / "data" / "retrieval_cases.json").read_text(encoding="utf-8-sig"))
    top1 = top5 = 0
    records = []
    for case in cases:
        hits = search(case["question"], top_k=5)
        expected = set(case["expected_chunk_ids"])
        ids = [hit["chunk_id"] for hit in hits]
        hit1 = ids[0] in expected
        hit5 = bool(expected.intersection(ids))
        top1 += hit1
        top5 += hit5
        records.append({**case, "retrieved_ids": ids, "hit_at_1": hit1, "hit_at_5": hit5})
        print(f"Top-1={hit1} Top-5={hit5}：{case['question']}")
    report = {
        "note": "开发用小样本检索测试，不是回答正确率，也不是独立测试集。",
        "total": len(cases), "hit_at_1": top1 / len(cases),
        "hit_at_5": top5 / len(cases), "cases": records,
    }
    target = ROOT / "data" / "index" / "retrieval_report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Top-1 命中 {top1}/{len(cases)}；Top-5 命中 {top5}/{len(cases)}")
    print(f"报告：{target}")


if __name__ == "__main__":
    main()
