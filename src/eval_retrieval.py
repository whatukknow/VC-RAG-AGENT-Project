"""검색 구성(A/B/C)별 Hit@5·MRR 계산과 원본 기록. 기본은 개발용 셋만.
최종셋은 --final 이 있어야 하고 다음이 모두 통과해야 한다(최종 평가는 Day 4에 한 번만 수행).
  1) eval/FREEZE.json : 평가셋·코퍼스·문서목록 해시(누락·불일치 모두 오류)
  2) configs/final.lock.json : chunk_map·모델 리비전·청크 색인·모든 설정 고정(없으면 거부)
사용: .venv/Scripts/python src/eval_retrieval.py --configs A B C
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ragagent.factory import build_retriever  # noqa: E402
from ragagent.freeze import verify_files, verify_final_lock  # noqa: E402
from ragagent.pipeline import PIPELINE_CONFIG  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPLIT_FILES = {"dev": "dev.json", "dev_extra": "dev_extra.json", "test": "test.json"}


def check_freeze():
    with open(os.path.join(ROOT, "eval", "FREEZE.json"), encoding="utf-8") as f:
        errors = verify_files(ROOT, json.load(f)["files"])
    errors += verify_final_lock(ROOT)
    if errors:
        sys.exit("최종 평가를 중단한다:\n - " + "\n - ".join(errors))


def score_question(cmap_entry, top):
    """허용 청크 기준 채점. rank/hit 는 '하나 이상', full_evidence 는 모든 근거 인용의 청크가 상위에 있는지."""
    allowed = set(cmap_entry["allowed_chunk_ids"])
    rank = next((i + 1 for i, c in enumerate(top) if c in allowed), None)
    groups = cmap_entry.get("evidence_groups") or []
    full = int(bool(groups) and all(set(g) & set(top) for g in groups))
    return {"allowed_chunk_ids": sorted(allowed), "hit_at_5": int(rank is not None), "rank": rank,
            "full_evidence_at_5": full}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="+", default=["A", "B", "C"], choices=["A", "B", "C"])
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--split", default="dev", choices=["dev", "dev_extra"], help="--final 이 없을 때 대상(개발용만)")
    ap.add_argument("--out", default=None, help="결과 디렉터리(기본 results/<split>)")
    a = ap.parse_args()
    split = "test" if a.final else a.split
    if a.final:
        check_freeze()
    with open(os.path.join(ROOT, "eval", SPLIT_FILES[split]), encoding="utf-8") as f:
        qs = json.load(f)["questions"]
    with open(os.path.join(ROOT, "eval", "chunk_map.json"), encoding="utf-8") as f:
        cmap = json.load(f)["map"]
    retr, meta = build_retriever()
    outdir = a.out or os.path.join(ROOT, "results", split)
    os.makedirs(outdir, exist_ok=True)
    run_id = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    k = PIPELINE_CONFIG["top_k"]

    for cfg in a.configs:
        rows, hits, full_hits, rr_sum, n = [], 0, 0, 0.0, 0
        for q in qs:
            res = retr.run(cfg, q["question"])
            top = [t["chunk_id"] for t in res["top"]]
            row = {"run_id": run_id, "question_id": q["id"], "type": q["type"], "config": cfg,
                   "question": q["question"], "top": res["top"], "candidates": res["candidates"], "status": "ok"}
            if q["answerable"]:
                row.update(score_question(cmap[q["id"]], top))
                hits += row["hit_at_5"]
                full_hits += row["full_evidence_at_5"]
                rr_sum += 1.0 / row["rank"] if row["rank"] else 0.0
                n += 1
            rows.append(row)
        summary = {"run_id": run_id, "split": split, "config": cfg, "hit_at_5": f"{hits}/{n}",
                   "full_evidence_at_5": f"{full_hits}/{n}", "mrr": round(rr_sum / n, 4) if n else None,
                   "n_answerable": n, "pipeline": PIPELINE_CONFIG, "models": meta["models"],
                   "embedding_cache": meta["embedding_cache"]}
        with open(os.path.join(outdir, f"retrieval_{cfg}_{run_id}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"summary": summary, "rows": rows}, f, indent=1, ensure_ascii=False)
        by_type = {}
        for r in rows:
            if "hit_at_5" in r:
                by_type.setdefault(r["type"], []).append(r["hit_at_5"])
        misses = [(r["question_id"], r["rank"]) for r in rows if r.get("hit_at_5") == 0]
        print(f"[{cfg}] {split} Hit@{k}={hits}/{n}  full-evidence={full_hits}/{n}  MRR={summary['mrr']}  "
              + " ".join(f"{t}:{sum(v)}/{len(v)}" for t, v in by_type.items()) + f"  miss={misses}")
        for r in rows:
            if "rank" in r and r["rank"] != 1:
                print(f"     {r['question_id']} rank={r['rank']} top={[t['chunk_id'] for t in r['top'][:3]]}")


if __name__ == "__main__":
    main()
