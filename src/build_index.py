"""코퍼스 -> 청크 색인(chunks.jsonl) + 설정 기록(index_meta.json) + 근거->청크 매핑.
사용: python src/build_index.py
근거 인용을 원문에서 찾지 못하거나, 답변 가능 문항의 허용 청크가 비면 비정상 종료한다(조용한 0점 방지).
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ragagent.bm25 import BM25_CONFIG  # noqa: E402
from ragagent.chunking import CHUNK_CONFIG, chunk_document  # noqa: E402
from ragagent.fusion import RRF_CONFIG  # noqa: E402
from ragagent.textnorm import find_span  # noqa: E402  (check_eval 과 같은 정규화)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPLIT_FILES = {"dev": "dev.json", "dev_extra": "dev_extra.json", "test": "test.json"}


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def map_evidence(questions, by_doc, text_of):
    """문항 목록 -> ({qid: 매핑}, 치명적 문제, 경고). 순수 함수라 테스트할 수 있다."""
    cmap, fatal, warn = {}, [], []
    for q in questions:
        entries = []
        for ev in q["allowed_evidence"]:
            s, e = find_span(text_of[ev["doc_id"]], ev["quote"])
            if s < 0:
                fatal.append((q["id"], f"인용 위치 없음: [{ev['doc_id']}] {ev['quote'][:50]}"))
                continue
            full = [c.chunk_id for c in by_doc[ev["doc_id"]] if c.start <= s and e <= c.end]
            part = [c.chunk_id for c in by_doc[ev["doc_id"]] if c.start < e and s < c.end]
            if not full:
                warn.append((q["id"], f"인용이 청크 경계에 걸침 {ev['doc_id']} {part}"))
            entries.append({"doc_id": ev["doc_id"], "span": [s, e], "chunk_ids_full": full,
                            "chunk_ids_overlap": part, "chunk_ids": full or part})
        allowed = sorted({cid for en in entries for cid in en["chunk_ids"]})
        if q["answerable"] and not allowed:
            fatal.append((q["id"], "답변 가능 문항의 허용 청크가 비어 있다"))
        cmap[q["id"]] = {"evidence": entries, "allowed_chunk_ids": allowed,
                         "evidence_groups": [en["chunk_ids"] for en in entries]}
    return cmap, fatal, warn


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    corpus = os.path.join(ROOT, "data", "corpus", "corpus.jsonl")
    with open(corpus, encoding="utf-8") as f:
        docs = [json.loads(l) for l in f]
    chunks = [c for d in docs for c in chunk_document(d)]
    outdir = os.path.join(ROOT, "data", "index")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "chunks.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        for c in chunks:
            f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    meta = {"chunk": CHUNK_CONFIG, "bm25": BM25_CONFIG, "fusion": RRF_CONFIG,
            "corpus_sha256": sha(corpus), "n_docs": len(docs), "n_chunks": len(chunks)}
    with open(os.path.join(outdir, "index_meta.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    by_doc = {}
    for c in chunks:
        by_doc.setdefault(c.doc_id, []).append(c)
    text_of = {d["doc_id"]: d["long_description"] for d in docs}
    cmap, fatal, warn = {}, [], []
    for split, fname in SPLIT_FILES.items():
        path = os.path.join(ROOT, "eval", fname)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            qs = json.load(f)["questions"]
        m, ft, wn = map_evidence(qs, by_doc, text_of)
        for qid in m:
            m[qid]["split"] = split
        cmap.update(m)
        fatal += ft
        warn += wn

    sizes = [len(c.body) for c in chunks]
    per_doc = [len(v) for v in by_doc.values()]
    print(f"docs={len(docs)} chunks={len(chunks)} chunk_len median={sorted(sizes)[len(sizes)//2]} max={max(sizes)} "
          f"(max_chars={CHUNK_CONFIG['max_chars']})")
    print(f"chunks/doc: 1개={sum(1 for n in per_doc if n == 1)} 2개={sum(1 for n in per_doc if n == 2)} 3개+={sum(1 for n in per_doc if n >= 3)}")
    print("경고(청크 경계):", warn or "없음")
    if fatal:
        print("치명적 문제:", *fatal, sep="\n  ")
        sys.exit("근거 매핑 실패 — chunk_map.json 을 쓰지 않고 종료한다.")
    with open(os.path.join(ROOT, "eval", "chunk_map.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"index_meta": meta, "map": cmap}, f, indent=2, ensure_ascii=False)
    print("매핑 문제: 없음")


if __name__ == "__main__":
    main()
