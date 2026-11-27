"""검색 구성(A/B/C)별 근거 기반 답변 실행과 원본 기록. 기본은 개발용 셋만.
최종셋은 --final 이 있어야 하며 eval_retrieval 과 같은 고정 검사(FREEZE + final.lock)를 통과해야 한다.
채점(정답 충족·근거 적합)은 기록의 expected_key_facts·allowed_chunk_ids·citations 를 보고 별도로 수행한다.
사용: .venv/Scripts/python src/run_answers.py --split dev --configs A B C [--limit N]
"""
import argparse
import datetime
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_retrieval import SPLIT_FILES, check_freeze  # noqa: E402
from ragagent.answer import AnswerPipeline  # noqa: E402
from ragagent.factory import build_retriever  # noqa: E402
from ragagent.envfile import load_env  # noqa: E402
from ragagent.errors import BudgetExceeded  # noqa: E402
from ragagent.generate import Generator  # noqa: E402
from ragagent.generate_api import ApiGenerator  # noqa: E402
from ragagent.rewrite import Rewriter, RewritingRetriever  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", nargs="+", default=["A", "B", "C"], choices=["A", "B", "C", "C+R"],
                    help="C+R = 쿼리 리라이트 후 C(최종 평가에서는 C와 비교)")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--split", default="dev", choices=["dev", "dev_extra"])
    ap.add_argument("--limit", type=int, default=None, help="앞에서 N문항만(시간 측정용). --final 에서는 허용하지 않는다.")
    ap.add_argument("--out", default=None)
    ap.add_argument("--backend", default="api", choices=["api", "local"],
                    help="api = Claude Haiku 5.5(기본, 비용 한도·원장), local = Qwen2.5-1.5B(이전 기록 재현용)")
    a = ap.parse_args()
    split = "test" if a.final else a.split
    if a.final:
        if a.limit:
            sys.exit("--final 에서는 --limit 을 쓸 수 없다(일부만 실행한 최종 결과 방지).")
        check_freeze()
    with open(os.path.join(ROOT, "eval", SPLIT_FILES[split]), encoding="utf-8") as f:
        qs = json.load(f)["questions"]
    if a.limit:
        qs = qs[: a.limit]
    with open(os.path.join(ROOT, "eval", "chunk_map.json"), encoding="utf-8") as f:
        cmap = json.load(f)["map"]
    retr, meta = build_retriever()
    if a.backend == "api":
        load_env(os.path.join(ROOT, ".env"))  # 키 값은 환경변수에만 들어가고 출력·기록되지 않는다
        gen = ApiGenerator(os.path.join(ROOT, "results", "api_cost_ledger.jsonl"))
    else:
        gen = Generator(os.path.join(ROOT, meta["models"]["generator"]["local_dir"]))
    pipe = AnswerPipeline(RewritingRetriever(retr, Rewriter(gen)), gen)  # 리라이트는 같은 생성 모델을 쓴다
    outdir = a.out or os.path.join(ROOT, "results", split)
    os.makedirs(outdir, exist_ok=True)
    run_id = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")

    for cfg in a.configs:
        rows = []
        for q in qs:
            try:
                rec = pipe.answer(q["question"], cfg)
            except BudgetExceeded as e:  # 한도 도달: 지금까지의 기록을 보존하고 중단한다(오류로 처리해 계속하지 않는다)
                with open(os.path.join(outdir, f"answers_{cfg}_{run_id}_INCOMPLETE.json"), "w", encoding="utf-8",
                          newline="\n") as f:
                    json.dump({"summary": {"incomplete": True, "reason": str(e), "rows_done": len(rows),
                                           "generation_config": gen.cfg}, "rows": rows}, f, indent=1, ensure_ascii=False)
                sys.exit(f"비용 한도에 도달해 중단했다: {e}")
            rec.update({"run_id": run_id, "question_id": q["id"], "type": q["type"], "answerable": q["answerable"],
                        "expected_key_facts": q["expected_key_facts"],
                        "allowed_chunk_ids": cmap[q["id"]]["allowed_chunk_ids"], "grading": None})
            rows.append(rec)
            print(f"  [{cfg}] {q['id']} {rec['status']:<22} {rec['timing_ms'].get('generation', '-')} ms", flush=True)
        ans = [r for r in rows if r["answerable"]]
        noe = [r for r in rows if not r["answerable"]]
        gen_ms = [r["timing_ms"]["generation"] for r in rows if "generation" in r["timing_ms"]]
        summary = {
            "run_id": run_id, "split": split, "config": cfg, "n": len(rows),
            "status_counts": {s: sum(1 for r in rows if r["status"] == s) for s in
                              ("answered", "insufficient_evidence", "error_retrieval", "error_generation")},
            "answerable_answered": f"{sum(r['status'] == 'answered' for r in ans)}/{len(ans)}",
            "answerable_wrongly_refused": sum(r["status"] == "insufficient_evidence" for r in ans),
            "no_evidence_refused": f"{sum(r['status'] == 'insufficient_evidence' for r in noe)}/{len(noe)}",
            "no_evidence_answered": sum(r["status"] == "answered" for r in noe),
            "errors": sum(r["status"].startswith("error") for r in rows),
            "rewrite_fallbacks": {k: sum(1 for r in rows if (r.get("rewrite") or {}).get("fallback_reason") == k)
                                  for k in ("error", "empty", "too_long", "intent_guard")},
            "generation_ms_mean_median_n": [round(statistics.mean(gen_ms), 1) if gen_ms else None,
                                            round(statistics.median(gen_ms), 1) if gen_ms else None, len(gen_ms)],
            "generation_config": gen.cfg, "models": meta["models"],
            "api_cost_usd": round(sum((r.get("llm_meta") or {}).get("cost_usd", 0.0) for r in rows), 6),
            "served_models": sorted({(r.get("llm_meta") or {}).get("served_model") for r in rows} - {None}),
        }
        with open(os.path.join(outdir, f"answers_{cfg}_{run_id}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"summary": summary, "rows": rows}, f, indent=1, ensure_ascii=False)
        print(f"[{cfg}] {split} answered(answerable)={summary['answerable_answered']} "
              f"refused(no_evidence)={summary['no_evidence_refused']} wrongly_refused={summary['answerable_wrongly_refused']} "
              f"errors={summary['errors']} gen_ms(mean/median/n)={summary['generation_ms_mean_median_n']}")


if __name__ == "__main__":
    main()
