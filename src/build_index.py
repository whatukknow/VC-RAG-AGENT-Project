"""코퍼스 -> 청크 색인(chunks.jsonl) + 설정 기록(index_meta.json) + 근거->청크 매핑.
사용: python src/build_index.py
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ragagent.bm25 import BM25_CONFIG  # noqa: E402
from ragagent.chunking import CHUNK_CONFIG, chunk_document  # noqa: E402
from ragagent.fusion import RRF_CONFIG  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def norm_pos(text, quote):
    """공백을 정규화하지 않고 원문 위치를 찾는다. 개행이 섞인 인용은 공백 무시 매칭으로 보완."""
    i = text.find(quote)
    if i >= 0:
        return i, i + len(quote)
    import re
    pat = r"\s+".join(re.escape(w) for w in quote.split())
    m = re.search(pat, text)
    return (m.start(), m.end()) if m else (-1, -1)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    corpus = os.path.join(ROOT, "data", "corpus", "corpus.jsonl")
    docs = [json.loads(l) for l in open(corpus, encoding="utf-8")]
    chunks = [c for d in docs for c in chunk_document(d)]
    outdir = os.path.join(ROOT, "data", "index")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "chunks.jsonl"), "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    meta = {"chunk": CHUNK_CONFIG, "bm25": BM25_CONFIG, "fusion": RRF_CONFIG,
            "corpus_sha256": sha(corpus), "n_docs": len(docs), "n_chunks": len(chunks)}
    json.dump(meta, open(os.path.join(outdir, "index_meta.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    # 근거 인용 -> 청크 ID 매핑(청킹이 바뀌면 재생성). 평가셋 원본 파일은 수정하지 않는다.
    by_doc = {}
    for c in chunks:
        by_doc.setdefault(c.doc_id, []).append(c)
    text_of = {d["doc_id"]: d["long_description"] for d in docs}
    cmap, problems = {}, []
    for split in ("dev", "dev_extra", "test"):
        path = os.path.join(ROOT, "eval", "dev_extra.json" if split == "dev_extra" else f"{split}.json")
        if not os.path.exists(path):
            continue
        for q in json.load(open(path, encoding="utf-8"))["questions"]:
            entries = []
            for ev in q["allowed_evidence"]:
                s, e = norm_pos(text_of[ev["doc_id"]], ev["quote"])
                if s < 0:
                    problems.append((q["id"], "인용 위치 없음"))
                    continue
                full = [c.chunk_id for c in by_doc[ev["doc_id"]] if c.start <= s and e <= c.end]
                part = [c.chunk_id for c in by_doc[ev["doc_id"]] if c.start < e and s < c.end]
                if not full:
                    problems.append((q["id"], f"인용이 청크 경계에 걸침 {ev['doc_id']} {part}"))
                entries.append({"doc_id": ev["doc_id"], "span": [s, e], "chunk_ids_full": full, "chunk_ids_overlap": part})
            cmap[q["id"]] = {"split": split, "evidence": entries,
                             "allowed_chunk_ids": sorted({cid for en in entries for cid in (en["chunk_ids_full"] or en["chunk_ids_overlap"])})}
    json.dump({"index_meta": meta, "map": cmap}, open(os.path.join(ROOT, "eval", "chunk_map.json"), "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    sizes = [len(c.body) for c in chunks]
    per_doc = [len(v) for v in by_doc.values()]
    print(f"docs={len(docs)} chunks={len(chunks)} chunk_len median={sorted(sizes)[len(sizes)//2]} max={max(sizes)}")
    print(f"chunks/doc: 1개={sum(1 for n in per_doc if n == 1)} 2개={sum(1 for n in per_doc if n == 2)} 3개+={sum(1 for n in per_doc if n >= 3)}")
    print("매핑 문제:", problems or "없음")


if __name__ == "__main__":
    main()
