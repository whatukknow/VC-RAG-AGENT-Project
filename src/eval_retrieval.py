"""검색 구성(A/B/C)별 Hit@5·MRR 계산과 원본 기록. 기본은 개발셋만.
최종셋은 --final 이 있어야 하고 FREEZE 해시가 모두 일치해야 한다(최종 평가는 Day 4에 한 번만 수행).
사용: .venv/Scripts/python src/eval_retrieval.py --configs A B C
"""
import argparse
import datetime
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ragagent.factory import build_retriever  # noqa: E402
from ragagent.pipeline import PIPELINE_CONFIG  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_freeze():
    fr = json.load(open(os.path.join(ROOT, "eval", "FREEZE.json"), encoding="utf-8"))
    for p, h in fr["files"].items():
        path = os.path.join(ROOT, p)
        if not os.path.exists(path):
            continue  # data/* 는 저장소에 없다. 로컬에 있으면 검증한다.
        if hashlib.sha256(open(path, "rb").read()).hexdigest() != h:
            sys.exit(f"고정 해시 불일치: {p} — 최종 평가를 중단한다.")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="+", default=["A", "B", "C"], choices=["A", "B", "C"])
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--out", default=None, help="결과 디렉터리(기본 results/<split>)")
    a = ap.parse_args()
    split = "test" if a.final else "dev"
    if a.final:
        check_freeze()
    qs = json.load(open(os.path.join(ROOT, "eval", f"{split}.json"), encoding="utf-8"))["questions"]
    cmap = json.load(open(os.path.join(ROOT, "eval", "chunk_map.json"), encoding="utf-8"))["map"]
    retr, meta = build_retriever()
    outdir = a.out or os.path.join(ROOT, "results", split)
    os.makedirs(outdir, exist_ok=True)
    run_id = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    k = PIPELINE_CONFIG["top_k"]

    for cfg in a.configs:
        rows, hits, rr_sum, n = [], 0, 0.0, 0
        for q in qs:
            res = retr.run(cfg, q["question"])
            top = [t["chunk_id"] for t in res["top"]]
            row = {"run_id": run_id, "question_id": q["id"], "type": q["type"], "config": cfg,
                   "question": q["question"], "top": res["top"], "candidates": res["candidates"], "status": "ok"}
            if q["answerable"]:
                allowed = set(cmap[q["id"]]["allowed_chunk_ids"])
                rank = next((i + 1 for i, c in enumerate(top) if c in allowed), None)
                row.update({"allowed_chunk_ids": sorted(allowed), "hit_at_5": int(rank is not None), "rank": rank})
                hits += row["hit_at_5"]
                rr_sum += 1.0 / rank if rank else 0.0
                n += 1
            rows.append(row)
        summary = {"run_id": run_id, "split": split, "config": cfg, "hit_at_5": f"{hits}/{n}",
                   "mrr": round(rr_sum / n, 4) if n else None, "n_answerable": n,
                   "pipeline": PIPELINE_CONFIG, "models": meta["models"], "embedding_cache": meta["embedding_cache"]}
        json.dump({"summary": summary, "rows": rows}, open(os.path.join(outdir, f"retrieval_{cfg}_{run_id}.json"), "w",
                  encoding="utf-8"), indent=1, ensure_ascii=False)
        by_type = {}
        for r in rows:
            if "hit_at_5" in r:
                by_type.setdefault(r["type"], []).append(r["hit_at_5"])
        misses = [(r["question_id"], r["rank"]) for r in rows if r.get("hit_at_5") == 0]
        print(f"[{cfg}] {split} Hit@{k}={hits}/{n}  MRR={summary['mrr']}  "
              + " ".join(f"{t}:{sum(v)}/{len(v)}" for t, v in by_type.items()) + f"  miss={misses}")
        for r in rows:
            if "rank" in r and r["rank"] != 1:
                print(f"     {r['question_id']} rank={r['rank']} top={[t['chunk_id'] for t in r['top'][:3]]}")


if __name__ == "__main__":
    main()
