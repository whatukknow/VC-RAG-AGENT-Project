"""질문 -> 검색 -> 근거 선택 -> 답변·출처 또는 근거 부족 안내.
상태 값
  answered               : 근거 인용이 유효한 답변
  insufficient_evidence  : 모델이 근거 부족이라고 판단했거나, 인용 없는 답변을 차단함(blocked_reason 기록)
  error_retrieval        : 검색 단계 예외
  error_generation       : 생성 예외 또는 출력 형식 오류 — 올바른 거절로 세지 않는다
"""
import time

from .errors import BudgetExceeded
from .generate import GEN_CONFIG, INSUFFICIENT_TEXT, SYSTEM_PROMPT, USER_TEMPLATE, build_documents, parse_output


class AnswerPipeline:
    def __init__(self, retriever, generator, cfg=None):
        self.retriever, self.generator = retriever, generator
        self.cfg = cfg or getattr(generator, "cfg", GEN_CONFIG)  # 백엔드(로컬/API)별 설정
        self.system = getattr(generator, "system_prompt", SYSTEM_PROMPT)  # 백엔드별 프롬프트

    def answer(self, question, config="C"):
        rec = {"question": question, "config": config, "status": None, "answer": "", "citations": [],
               "invalid_citations": [], "blocked_reason": None, "error": None, "raw_output": None,
               "retrieved": [], "timing_ms": {}, "generated_tokens": None}
        t0 = time.perf_counter()
        try:
            res = self.retriever.run(config, question)
        except Exception as e:  # 검색 실패는 '근거 없음'과 구분한다
            rec.update(status="error_retrieval", error=f"{type(e).__name__}: {e}")
            return rec
        rec["timing_ms"]["retrieval"] = round((time.perf_counter() - t0) * 1000, 1)  # 리라이트 사용 시 리라이트 시간 포함
        rec["rewrite"] = res.get("rewrite")  # C+R 에서만 값이 있다(원질문·변환 질의·fallback 사유)

        ids = [t["chunk_id"] for t in res["top"]][: self.cfg["context_chunks"]]
        chunks = [self.retriever.chunks[self.retriever.pos[cid]] for cid in ids]
        rec["retrieved"] = [{"n": i, "chunk_id": c["chunk_id"], "doc_id": c["doc_id"], "span": [c["start"], c["end"]],
                             "score": s["score"]} for i, (c, s) in enumerate(zip(chunks, res["top"]), start=1)]
        if not chunks:
            rec.update(status="insufficient_evidence", answer=INSUFFICIENT_TEXT, blocked_reason="no_retrieval_results")
            return rec

        user = USER_TEMPLATE.format(documents=build_documents(chunks), question=question)
        t1 = time.perf_counter()
        try:
            text, n_tok = self.generator.generate(self.system, user, self.cfg["max_new_tokens"],
                                                  prefill=self.cfg.get("prefill"))
            rec["llm_meta"] = getattr(self.generator, "last_meta", None)  # API: 응답 모델 ID·요청 ID·토큰·비용
        except BudgetExceeded:
            raise  # 비용 한도는 실행 전체를 멈춘다(개별 질문 오류로 삼키지 않는다)
        except Exception as e:
            rec.update(status="error_generation", error=f"{type(e).__name__}: {e}")
            return rec
        rec["timing_ms"]["generation"] = round((time.perf_counter() - t1) * 1000, 1)
        rec["timing_ms"]["total"] = round((time.perf_counter() - t0) * 1000, 1)
        rec["raw_output"], rec["generated_tokens"] = text, n_tok

        parsed = parse_output(text)
        if parsed["status"] is None:
            rec.update(status="error_generation", error="format: STATUS 줄 없음")
            return rec
        if parsed["status"] == "INSUFFICIENT":
            rec.update(status="insufficient_evidence", answer=parsed["answer"] or INSUFFICIENT_TEXT)
            return rec

        valid = [n for n in parsed["citations"] if 1 <= n <= len(chunks)]
        invalid = [n for n in parsed["citations"] if n not in valid]
        rec["invalid_citations"] = invalid
        if not parsed["answer"] or not valid:  # 출처 없는 답변은 내보내지 않는다
            rec.update(status="insufficient_evidence", answer=INSUFFICIENT_TEXT,
                       blocked_reason="no_valid_citation" if parsed["answer"] else "empty_answer")
            return rec
        rec.update(status="answered", answer=parsed["answer"], citations=[
            {"n": n, "chunk_id": chunks[n - 1]["chunk_id"], "doc_id": chunks[n - 1]["doc_id"],
             "span": [chunks[n - 1]["start"], chunks[n - 1]["end"]]} for n in valid])
        return rec
