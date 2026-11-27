"""쿼리 리라이트(선택한 최적화). 원질문과 변환 질의를 모두 기록하고, 변환 질의로 검색한다.
- 정답·허용 근거는 리라이터 입력에 절대 넣지 않는다(질문 문장만 입력).
- 안전장치: 오류·빈 출력·너무 긴 출력·의도 손실(원질문의 숫자·고유명사 누락)이면 원질문으로 fallback 한다.
- 답변 생성에는 항상 원질문을 쓴다(변환 질의는 검색에만 사용).
프롬프트를 바꾸면 PROMPT_SHA256 이 바뀌어 최종 설정 고정(final.lock) 검사에서 걸린다."""
import hashlib
import re
import time

from .errors import BudgetExceeded

SYSTEM_PROMPT = """Rewrite the user's question into a short search query for finding YC company profiles.
Rules:
- Keep every company name, product name, number and technical term from the question unchanged.
- Do not answer the question. Do not add facts that are not in the question.
- Output only the query on one line, no quotes and no explanation."""

REWRITE_CONFIG = {
    "max_new_tokens": 48,
    "max_chars": 200,
    "prompt_version": "rewrite-v1",
    "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
}

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9.\-+]*")


def must_keep(question):
    """원질문에서 변환 후에도 남아야 하는 토큰: 숫자, 첫 단어를 제외한 대문자 포함 단어(고유명사·약어)."""
    keep = [n for n in _NUMBER.findall(question)]
    words = _WORD.findall(question)
    for w in words[1:]:
        if any(ch.isupper() for ch in w):
            keep.append(w.strip(".-"))
    seen, out = set(), []
    for t in keep:
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def intent_guard(original, rewritten):
    """누락된 필수 토큰 목록(비어 있으면 통과)."""
    low = rewritten.lower()
    return [t for t in must_keep(original) if t.lower() not in low]


class Rewriter:
    def __init__(self, generator, cfg=None):
        self.generator, self.cfg = generator, cfg or REWRITE_CONFIG

    def rewrite(self, question):
        rec = {"original": question, "rewritten": None, "used": question, "fallback_reason": None,
               "missing_tokens": [], "generated_tokens": None, "ms": None, "error": None, "llm_meta": None}
        t0 = time.perf_counter()
        try:
            text, n = self.generator.generate(SYSTEM_PROMPT, question, self.cfg["max_new_tokens"])
        except BudgetExceeded:
            raise  # 비용 한도는 실행 전체를 멈춘다
        except Exception as e:  # 리라이트 실패는 검색 실패가 아니다: 원질문으로 계속한다
            rec.update(fallback_reason="error", error=f"{type(e).__name__}: {e}")
            rec["llm_meta"] = getattr(self.generator, "last_meta", None)  # 실패해도 청구된 비용은 기록
            rec["ms"] = round((time.perf_counter() - t0) * 1000, 1)
            return rec
        rec["llm_meta"] = getattr(self.generator, "last_meta", None)  # 리라이트 호출의 모델·토큰·비용
        rec["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        rec["generated_tokens"] = n
        line = text.strip().splitlines()[0].strip().strip('"').strip("'") if text.strip() else ""
        rec["rewritten"] = line
        if not line:
            rec["fallback_reason"] = "empty"
        elif len(line) > self.cfg["max_chars"]:
            rec["fallback_reason"] = "too_long"
        else:
            missing = intent_guard(question, line)
            if missing:
                rec.update(fallback_reason="intent_guard", missing_tokens=missing)
        if rec["fallback_reason"] is None:
            rec["used"] = line
        return rec


class RewritingRetriever:
    """Retriever 를 감싸 'C+R' 구성(리라이트 -> C)을 추가한다. 다른 구성은 그대로 위임한다."""

    def __init__(self, base, rewriter):
        self.base, self.rewriter = base, rewriter

    @property
    def chunks(self):
        return self.base.chunks

    @property
    def pos(self):
        return self.base.pos

    def run(self, config, q):
        if config != "C+R":
            return self.base.run(config, q)
        rw = self.rewriter.rewrite(q)
        res = self.base.run("C", rw["used"])
        res["rewrite"] = rw
        res["config"] = "C+R"
        return res
