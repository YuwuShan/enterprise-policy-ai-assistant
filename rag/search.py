import argparse

import numpy as np

from rag.build_index import load_index
from rag.documents import fingerprint, load_chunks
from rag.embeddings import DIMENSIONS, embed_texts


def rank(chunks, vectors, query_vector, top_k=5):
    if not 1 <= top_k <= 20:
        raise ValueError("top_k 必须在 1 到 20 之间")
    scores = vectors @ query_vector
    positions = np.argsort(-scores, kind="stable")[:top_k]
    return [
        {**chunks[int(i)], "score": float(scores[i])}
        for i in positions
    ]


def search(question: str, top_k=5):
    from model_client import required_env

    question = question.strip()
    if not 1 <= len(question) <= 1000:
        raise ValueError("问题长度必须在 1 到 1000 字之间")
    if not 1 <= top_k <= 20:
        raise ValueError("top_k 必须在 1 到 20 之间")

    payload, vectors = load_index()
    model = required_env("EMBEDDING_MODEL")
    if (payload["model"], payload["dimensions"]) != (model, DIMENSIONS):
        raise RuntimeError("模型或维度已变化，请重新构建索引")
    if payload["fingerprint"] != fingerprint(load_chunks()):
        raise RuntimeError("制度资料已变化，请重新构建索引")

    query_vector = embed_texts([question], model)[0]
    return rank(payload["chunks"], vectors, query_vector, top_k)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    for i, hit in enumerate(search(args.question, args.top_k), start=1):
        print(f"\n[{i}] 相似度：{hit['score']:.4f}")
        print(f"出处：{hit['title']} / {hit['version']} / {hit['article']}")
        print(f"文件：{hit['source_file']}；条款 ID：{hit['chunk_id']}")
        print(f"适用范围：{hit['scope']}")
        print(hit["text"])


if __name__ == "__main__":
    main()
