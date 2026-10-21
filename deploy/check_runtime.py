"""Run inside the application image. Read-only, no remote model request."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from rag.build_index import load_index
    from rag.documents import fingerprint, load_chunks
    from rag.embeddings import DIMENSIONS
    for key in ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL", "CHAT_MODEL", "EMBEDDING_MODEL"):
        if not os.getenv(key, "").strip():
            raise ValueError(f"Missing configuration: {key}")
    chunks = load_chunks()
    payload, vectors = load_index()
    if payload["model"] != os.environ["EMBEDDING_MODEL"] or payload["dimensions"] != DIMENSIONS:
        raise ValueError("Index model or dimensions mismatch")
    if payload["fingerprint"] != fingerprint(chunks):
        raise ValueError("Index is stale; rebuild from the current corpus on your workstation")
    print(json.dumps({"documents": len({c["doc_id"] for c in chunks}), "chunks": len(chunks),
                      "shape": list(vectors.shape), "index_current": True, "remote_model_calls": 0}))


if __name__ == "__main__":
    main()
