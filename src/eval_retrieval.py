"""검색 구성별 Hit@5 계산. 기본은 개발셋만. 최종셋은 --final 이 있어야 하고 FREEZE 해시가 일치해야 한다.
사용: python src/eval_retrieval.py --config bm25
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ragagent.bm25 import BM25  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_chunks():
    return [json.loads(l) for l in open(os.path.join(ROOT, "data", "index", "chunks.jsonl"), encoding="utf-8")]


def bm25_ranker(chunks):
    idx = BM25([c["text"] for c in chunks])
    ids = [c["chunk_id"] for c in chunks]
    return lambda q, k=5: [(ids[i], s) for i, s in idx.search(q, k)]


def check_freeze():
    fr = json.load(open(os.path.join(ROOT, "eval", "FREEZE.json"), encoding="utf-8"))
    for p, h in fr["files"].items():
        if hashlib.sha256(open(os.path.join(ROOT, p), "rb").read()).hexdigest() != h:
            sys.exit(f"고정 해시 불일치: {p} — 최종 평가를 중단한다.")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="bm25", choices=["bm25"])
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--k", type=int, default=5)
    a = ap.parse_args()
    split = "test" if a.final else "dev"
    if a.final:
        check_freeze()
    qs = json.load(open(os.path.join(ROOT, "eval", f"{split}.json"), encoding="utf-8"))["questions"]
    cmap = json.load(open(os.path.join(ROOT, "eval", "chunk_map.json"), encoding="utf-8"))["map"]
    rank = bm25_ranker(load_chunks())
    hits, n = 0, 0
    for q in qs:
        res = rank(q["question"], a.k)
        top = [c for c, _ in res]
        if not q["answerable"]:
            print(f"{q['id']} [근거없음] 상위: {[(c, round(s, 2)) for c, s in res[:3]]}")
            continue
        allowed = set(cmap[q["id"]]["allowed_chunk_ids"])
        hit = int(bool(allowed & set(top)))
        hits += hit
        n += 1
        pos = next((i + 1 for i, c in enumerate(top) if c in allowed), None)
        print(f"{q['id']} hit={hit} rank={pos} allowed={sorted(allowed)}")
    print(f"[{a.config}] split={split} Hit@{a.k} = {hits}/{n}")


if __name__ == "__main__":
    main()
