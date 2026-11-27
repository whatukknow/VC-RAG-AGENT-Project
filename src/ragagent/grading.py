"""채점 시트 생성과 지표 계산(매뉴얼 STEP 6 규칙).
- 정답 충족: 필수 핵심 사실이 모두 맞고 모순이 없으면 1(사람이 0/1 기입)
- 근거 적합: 인용이 실제 검색 결과에 있고 답변의 주요 주장을 뒷받침하면 1(사람이 0/1 기입)
- 근거 없음: 무근거 단정 없이 정보 부족을 안내했으면 1 -> 상태(insufficient_evidence)로 자동 판정. 호출 오류는 0
- 답변 가능 문항에서 답을 내지 않은 경우(거절·오류)는 정답 충족·근거 적합 모두 0
- 채점자(grader)를 기록한다: LLM 판정과 사람 검토를 구분하기 위함
"""
import csv
import statistics

SHEET_FIELDS = ["question_id", "config", "type", "answerable", "status", "question", "expected_key_facts", "answer",
                "citations", "allowed_chunk_ids", "correct", "grounded", "grader", "note"]


def make_sheet_rows(rows):
    out = []
    for r in rows:
        out.append({
            "question_id": r["question_id"], "config": r["config"], "type": r["type"],
            "answerable": int(bool(r["answerable"])), "status": r["status"], "question": r["question"],
            "expected_key_facts": " | ".join(r["expected_key_facts"]), "answer": r["answer"],
            "citations": " | ".join(f"[{c['n']}] {c['chunk_id']}" for c in r["citations"]),
            "allowed_chunk_ids": " | ".join(r["allowed_chunk_ids"]),
            "correct": "", "grounded": "", "grader": "", "note": "",
        })
    return out


def write_sheet(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_FIELDS)
        w.writeheader()
        w.writerows(make_sheet_rows(rows))


def _bit(v):
    v = (v or "").strip()
    if v == "":
        return None
    if v not in ("0", "1"):
        raise ValueError(f"채점 값은 0 또는 1 이어야 한다: {v!r}")
    return int(v)


def read_grades(path):
    grades = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            grades[(r["question_id"], r["config"])] = {
                "correct": _bit(r.get("correct")), "grounded": _bit(r.get("grounded")),
                "grader": (r.get("grader") or "").strip(), "note": r.get("note", "")}
    return grades


def score(rows, grades):
    """구성별 지표. 채점이 비어 있는 '답변한' 문항이 있으면 ungraded 에 담고 complete=False 로 표시한다."""
    result = {}
    for cfg in sorted({r["config"] for r in rows}):
        rs = [r for r in rows if r["config"] == cfg]
        ans = [r for r in rs if r["answerable"]]
        noe = [r for r in rs if not r["answerable"]]
        correct = grounded = 0
        ungraded, graders = [], {}
        for r in ans:
            if r["status"] != "answered":
                continue  # 답을 내지 않았으므로 0점
            g = grades.get((r["question_id"], cfg))
            if g is None or g["correct"] is None or g["grounded"] is None:
                ungraded.append(r["question_id"])
                continue
            correct += g["correct"]
            grounded += g["grounded"]
            graders[g["grader"] or "(미기입)"] = graders.get(g["grader"] or "(미기입)", 0) + 1
        ok = [r for r in rs if not r["status"].startswith("error")]
        times = [r["timing_ms"]["total"] for r in ok if "total" in r["timing_ms"]]
        result[cfg] = {
            "complete": not ungraded, "ungraded": ungraded,
            "correct": f"{correct}/{len(ans)}", "grounded": f"{grounded}/{len(ans)}",
            "no_evidence_refused": f"{sum(r['status'] == 'insufficient_evidence' for r in noe)}/{len(noe)}",
            "no_evidence_answered": sum(r["status"] == "answered" for r in noe),
            "answerable_refused": sum(r["status"] == "insufficient_evidence" for r in ans),
            "call_success": f"{len(ok)}/{len(rs)}",
            "errors": {s: sum(1 for r in rs if r["status"] == s) for s in ("error_retrieval", "error_generation")},
            "response_ms_mean_median_n": [round(statistics.mean(times), 1) if times else None,
                                          round(statistics.median(times), 1) if times else None, len(times)],
            "graders": graders,
        }
    return result
