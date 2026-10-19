import argparse
import numpy as np

from rag.documents import embedding_text, fingerprint, load_chunks, split_document
from rag.embeddings import normalize
from rag.search import rank


def must_fail(function, *args):
    try:
        function(*args)
    except ValueError:
        return
    raise AssertionError(f"预期应拒绝输入：{function.__name__}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-docs", type=int, default=10)
    parser.add_argument("--expected-chunks", type=int, default=30)
    args = parser.parse_args()
    chunks = load_chunks()
    assert len({c["doc_id"] for c in chunks}) == args.expected_docs, "制度文件数与指定预期不一致"
    assert len(chunks) == args.expected_chunks, "条款数与指定预期不一致"
    assert len({c["chunk_id"] for c in chunks}) == len(chunks)
    assert all(c["text"] and c["scope"] and c["source_file"] for c in chunks)
    assert all(c["title"] in embedding_text(c) for c in chunks)

    meta = {"doc_id": "test", "title": "测试制度", "version": "v1", "scope": "测试", "source_file": "test.md"}
    sample = "# 测试\n第一条 保留以下两项：\n（一）采购申请。\n（二）部门确认。\n第 2 条 保存凭证。"
    parts = split_document(sample, meta)
    assert len(parts) == 2 and parts[1]["article"] == "第2条"
    assert "（一）" in parts[0]["text"] and "（二）" in parts[0]["text"]
    must_fail(split_document, "没有条款标题", meta)
    must_fail(split_document, "第一条\n第二条 内容", meta)
    must_fail(split_document, "第一条 内容\n第一条 重复", meta)
    must_fail(split_document, "第一条 " + "长" * 1801, meta)
    changed = [{**chunks[0], "text": chunks[0]["text"] + "修改"}, *chunks[1:]]
    assert fingerprint(changed) != fingerprint(chunks)

    matrix = normalize([[3, 4], [1, 0], [-1, 0]])
    query = normalize([[1, 0]])[0]
    assert np.allclose(np.linalg.norm(matrix, axis=1), 1)
    hits = rank([{"chunk_id": "a"}, {"chunk_id": "b"}, {"chunk_id": "c"}], matrix, query, 3)
    assert [h["chunk_id"] for h in hits] == ["b", "a", "c"]
    assert np.allclose([h["score"] for h in hits], [1, 0.6, -1])
    must_fail(normalize, [[0, 0]])
    must_fail(normalize, [[float("nan"), 1]])
    print(f"离线检查通过：{args.expected_docs} 份制度、{args.expected_chunks} 条条款、元数据、分块、归一化与排序。")
    print("此检查未调用模型 API，不代表真实语义检索效果已经通过。")


if __name__ == "__main__":
    main()
