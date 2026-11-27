"""화면 표시용 순수 함수(Streamlit 에 의존하지 않아 단위 테스트 가능).
원칙: 오류(error_*)와 정상적인 '근거 부족' 거절을 시각적으로 구분하고, 인용은 실제 검색된 청크만 보여준다."""
import csv
import json
import os

STATUS_VIEW = {
    "answered": ("정상 답변", "success"),
    "insufficient_evidence": ("근거 부족 — 문서에 없는 내용이라 답하지 않음", "warning"),
    "error_retrieval": ("오류 — 검색 단계 실패(근거 부족이 아님)", "error"),
    "error_generation": ("오류 — 생성 단계 실패(근거 부족이 아님)", "error"),
}


def status_view(status):
    """(표시 문구, 수준) 수준은 success|warning|error."""
    return STATUS_VIEW.get(status, (f"알 수 없는 상태: {status}", "error"))


def chunk_index(chunks):
    return {c["chunk_id"]: c for c in chunks}


def load_doc_links(csv_path):
    """docs/doc_list.csv -> {doc_id: source_url}. 파일이 없으면 빈 dict."""
    if not os.path.exists(csv_path):
        return {}
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        return {r["doc_id"]: r.get("source_url") or "" for r in csv.DictReader(f)}


def _name(by_id, chunk_id):
    c = by_id.get(chunk_id)
    return c["name"] if c else "(알 수 없음)"


def citation_rows(rec, by_id, links):
    """답변이 인용한 청크 표. 인용은 검색된 컨텍스트 안의 번호만 들어 있다."""
    return [{"번호": f"[{c['n']}]", "회사": _name(by_id, c["chunk_id"]), "청크 ID": c["chunk_id"],
             "원문 위치": f"{c['span'][0]}–{c['span'][1]}", "출처": links.get(c["doc_id"], "")}
            for c in rec.get("citations", [])]


def evidence_blocks(rec, by_id):
    """인용된 청크의 원문 발췌: [(번호, 회사, 청크 ID, 본문)]."""
    out = []
    for c in rec.get("citations", []):
        chunk = by_id.get(c["chunk_id"])
        out.append((c["n"], _name(by_id, c["chunk_id"]), c["chunk_id"], chunk["body"] if chunk else ""))
    return out


def retrieved_rows(retrieved, by_id, links, cited_ids=()):
    """검색된 상위 청크 표. cited_ids 에 있는 청크는 '인용됨' 으로 표시한다."""
    rows = []
    for i, r in enumerate(retrieved, start=1):
        rows.append({"순위": i, "회사": _name(by_id, r["chunk_id"]), "청크 ID": r["chunk_id"],
                     "점수": round(float(r["score"]), 4), "인용됨": "예" if r["chunk_id"] in cited_ids else "",
                     "출처": links.get(r.get("doc_id") or by_id.get(r["chunk_id"], {}).get("doc_id", ""), "")})
    return rows


def retrieval_only_record(res, by_id):
    """Retriever.run 결과를 화면용 retrieved 목록으로 변환한다(생성 없음)."""
    return [{"n": i, "chunk_id": t["chunk_id"], "doc_id": by_id[t["chunk_id"]]["doc_id"], "score": t["score"]}
            for i, t in enumerate(res["top"], start=1)]


def rewrite_view(rec):
    """C+R 일 때 원질문·변환 질의·fallback 사유. 해당 없으면 None."""
    rw = rec.get("rewrite")
    if not rw:
        return None
    return {"원질문": rw["original"], "변환 질의": rw["rewritten"] or "(없음)",
            "검색에 사용한 질의": rw["used"],
            "fallback": rw["fallback_reason"] or "없음(변환 질의 사용)",
            "누락된 필수 토큰": ", ".join(rw["missing_tokens"]) or "없음", "오류": rw["error"] or ""}


def timing_text(rec):
    t = rec.get("timing_ms") or {}
    parts = []
    if "retrieval" in t:
        parts.append(f"검색{'(리라이트 포함)' if rec.get('rewrite') else ''} {t['retrieval'] / 1000:.2f}초")
    if "generation" in t:
        parts.append(f"생성 {t['generation'] / 1000:.2f}초")
    if "total" in t:
        parts.append(f"전체 {t['total'] / 1000:.2f}초")
    return " · ".join(parts) or "측정 없음"


def llm_text(rec):
    m = rec.get("llm_meta")
    if not m:
        return ""
    return (f"모델 {m.get('served_model') or m.get('requested_model')} · 토큰 입력 {m['input_tokens']} / 출력 {m['output_tokens']} · "
            f"이번 호출 비용 ${m['cost_usd']:.6f} · 요청 ID {m.get('request_id')}")


def spent_text(ledger_path, cap):
    """누적 API 비용 표시. 원장이 없으면 0."""
    total = 0.0
    if ledger_path and os.path.exists(ledger_path):
        with open(ledger_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    total += json.loads(line).get("cost_usd", 0.0)
    return f"누적 ${total:.4f} / 한도 ${cap:.2f}", total
