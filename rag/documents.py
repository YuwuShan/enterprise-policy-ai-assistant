import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_DIR = ROOT / "data" / "policies"
INDEX_PATH = ROOT / "data" / "index" / "policies.npz"
ARTICLE = re.compile(
    r"^[ \t]*(第[ \t]*[零〇一二三四五六七八九十百千两0-9]+[ \t]*条)[ \t]*",
    re.MULTILINE,
)


def split_document(text: str, meta: dict) -> list[dict]:
    matches = list(ARTICLE.finditer(text))
    if not matches:
        raise ValueError(f"没有识别到条款：{meta['source_file']}")

    chunks, seen = [], set()
    source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    for i, match in enumerate(matches):
        article = re.sub(r"\s+", "", match.group(1))
        if article in seen:
            raise ValueError(f"同一文件条款号重复：{article}")
        seen.add(article)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.start():end].strip()
        if not text[match.end():end].strip():
            raise ValueError(f"条款没有正文：{article}")
        if len(body) > 1800:
            raise ValueError(f"条款超过本教程长度上限，请检查拆分方式：{article}")
        chunks.append({
            **meta,
            "chunk_id": f"{meta['doc_id']}:{meta['version']}:{article}",
            "article": article,
            "text": body,
            "source_sha256": source_hash,
        })
    return chunks


def load_chunks() -> list[dict]:
    manifest = json.loads((POLICY_DIR / "manifest.json").read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("manifest.json 必须是非空列表")
    chunks, ids = [], set()
    for meta in manifest:
        for key in ("doc_id", "title", "version", "scope", "source_file"):
            if not isinstance(meta.get(key), str) or not meta[key].strip():
                raise ValueError(f"制度清单缺少有效字段：{key}")
        if meta["doc_id"] in ids:
            raise ValueError("制度 doc_id 重复")
        ids.add(meta["doc_id"])
        filename = meta["source_file"]
        if Path(filename).name != filename or Path(filename).suffix != ".md":
            raise ValueError("source_file 必须是 policies 目录内的 Markdown 文件名")
        text = (POLICY_DIR / filename).read_text(encoding="utf-8-sig")
        chunks.extend(split_document(text, meta))
    return chunks


def fingerprint(chunks: list[dict]) -> str:
    content = json.dumps(chunks, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def embedding_text(chunk: dict) -> str:
    return (
        f"制度：{chunk['title']}\n版本：{chunk['version']}\n"
        f"适用范围：{chunk['scope']}\n{chunk['text']}"
    )


if __name__ == "__main__":
    chunks = load_chunks()
    print(f"文件数：{len({c['doc_id'] for c in chunks})}；条款数：{len(chunks)}")
    print(json.dumps(chunks[0], ensure_ascii=False, indent=2))
