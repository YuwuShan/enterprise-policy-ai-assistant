import json
from pathlib import Path

from rag.documents import ROOT, POLICY_DIR, load_chunks


def main():
    manifest_path = POLICY_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    extras = json.loads((ROOT / "data" / "day4_extra_policies.json").read_text(encoding="utf-8-sig"))
    load_chunks()  # 写文件之前先验证已有制度。
    by_id = {item["doc_id"]: item for item in manifest}
    by_file = {item["source_file"]: item["doc_id"] for item in manifest}
    pending_files, additions = [], []
    for item in extras:
        meta = {key: item[key] for key in ("doc_id", "title", "version", "scope", "source_file")}
        name = meta["source_file"]
        if Path(name).name != name or not name.endswith(".md"):
            raise ValueError("制度文件名不合法")
        if meta["doc_id"] in by_id and by_id[meta["doc_id"]] != meta:
            raise ValueError(f"已有制度元数据不同，请人工核对：{meta['doc_id']}")
        if name in by_file and by_file[name] != meta["doc_id"]:
            raise ValueError(f"已有文件名被其他制度使用：{name}")
        if len(item["articles"]) != 3:
            raise ValueError("每份扩充资料应有三条")
        text = f"# {meta['title']}\n\n本文件为个人项目模拟制度，不代表真实企业规定。\n适用范围：{meta['scope']}。\n\n"
        text += "\n\n".join(f"第{n}条 {body}" for n, body in zip("一二三", item["articles"])) + "\n"
        target = POLICY_DIR / name
        if target.exists():
            if target.read_text(encoding="utf-8-sig") != text:
                raise ValueError(f"已有文件包含不同内容，请人工核对：{name}")
        else:
            pending_files.append((target, text))
        if meta["doc_id"] not in by_id:
            additions.append(meta)
        by_id[meta["doc_id"]] = meta
        by_file[name] = meta["doc_id"]

    for path, text in pending_files:
        path.write_text(text, encoding="utf-8")
    if additions:
        updated = manifest + additions
        temporary = POLICY_DIR / "manifest.pending.json"
        temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(manifest_path)
    chunks = load_chunks()
    print(f"新增 {len(additions)} 份；当前 {len({c['doc_id'] for c in chunks})} 份，{len(chunks)} 条。")
    print("原有制度未被覆盖；资料变化后请重建向量索引。")


if __name__ == "__main__":
    main()
