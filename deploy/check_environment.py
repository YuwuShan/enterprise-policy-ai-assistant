"""Run from the project root. Check prerequisites without printing secret values."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def check():
    from model_client import required_env
    from rag.build_index import load_index
    from rag.documents import fingerprint, load_chunks
    from rag.embeddings import DIMENSIONS

    for name in ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL", "CHAT_MODEL", "EMBEDDING_MODEL"):
        required_env(name)
        print(f"OK: {name} configured (value hidden)")
    chunks = load_chunks()
    payload, vectors = load_index()
    if payload["model"] != required_env("EMBEDDING_MODEL") or payload["dimensions"] != DIMENSIONS:
        raise ValueError("Index model/dimensions mismatch")
    if payload["fingerprint"] != fingerprint(chunks):
        raise ValueError("Index is stale for the current policy files")
    print(f"OK: {len(chunks)} chunks; index shape {vectors.shape}; current fingerprint matched")
    for relative in ("Dockerfile", ".dockerignore", "compose.yaml", "deploy/nginx/default.conf", "requirements.txt"):
        if not (ROOT / relative).is_file():
            raise ValueError(f"Missing file: {relative}")
    print("OK: Deployment files present. No remote model requests were made.")


if __name__ == "__main__":
    try:
        check()
    except Exception as error:
        # These local checks do not send model requests or include secret values in errors.
        print(f"FAIL: {type(error).__name__}: {error}")
        raise SystemExit(1)
