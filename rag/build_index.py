import json

import numpy as np

from rag.documents import INDEX_PATH, embedding_text, fingerprint, load_chunks
from rag.embeddings import DIMENSIONS, embed_texts


def load_index():
    if not INDEX_PATH.is_file():
        raise RuntimeError("索引不存在，请先执行 python -m rag.build_index")
    with np.load(INDEX_PATH, allow_pickle=False) as saved:
        vectors = saved["vectors"]
        payload = json.loads(saved["payload"].item())
    chunks = payload["chunks"]
    if vectors.shape != (len(chunks), payload["dimensions"]):
        raise ValueError("索引中的条款数、维度与向量不匹配")
    if not chunks or not np.isfinite(vectors).all():
        raise ValueError("索引为空或包含非法向量")
    if not np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5):
        raise ValueError("索引中的向量没有正确归一化")
    if fingerprint(chunks) != payload["fingerprint"]:
        raise ValueError("索引中的条款内容与指纹不一致")
    return payload, vectors


def main():
    from model_client import required_env

    model = required_env("EMBEDDING_MODEL")
    chunks = load_chunks()
    stamp = fingerprint(chunks)
    if INDEX_PATH.exists():
        old, _ = load_index()
        if (old["model"], old["dimensions"], old["fingerprint"]) == (
            model, DIMENSIONS, stamp,
        ):
            print("模型、维度和资料均未变化，复用已有索引。")
            return

    vectors = embed_texts([embedding_text(c) for c in chunks], model)
    payload = {
        "model": model,
        "dimensions": DIMENSIONS,
        "fingerprint": stamp,
        "chunks": chunks,
    }
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = INDEX_PATH.with_name("policies.pending.npz")
    np.savez_compressed(
        temp_path,
        vectors=vectors,
        payload=np.array(json.dumps(payload, ensure_ascii=False)),
    )
    temp_path.replace(INDEX_PATH)
    print(f"索引已保存：{INDEX_PATH}；向量形状：{vectors.shape}")


if __name__ == "__main__":
    main()
