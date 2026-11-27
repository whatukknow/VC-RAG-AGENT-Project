"""OpenAI 생성기(gpt-6-luna, Responses API). 같은 generate() 인터페이스를 쓰므로 AnswerPipeline·Rewriter 는 그대로 동작한다.
- 비용 한도: 호출 전에 '누적 + 최악 비용'이 한도를 넘으면 BudgetExceeded 로 실행 전체를 멈춘다(원장 JSONL, 추론 토큰 포함 출력 기준).
- 재현성: temperature/top_p/seed 를 보내지 않으므로 결정성을 강제할 수 없다. 응답 모델 ID·요청 ID·응답 ID·토큰을 기록한다.
- prefill 은 쓰지 않는다. store=False 로 Responses 의 기본 상태 보관(30일)을 막는다.
- 외부로 보내는 것은 질문과 검색된 공개 프로필 문구뿐이다(사용자 식별 정보 없음). 키 값은 출력·기록하지 않는다."""
import datetime

from .envfile import require_key
from .generate import OPENAI_GEN_CONFIG, SYSTEM_PROMPT_API
from .generate_api import CostLedger


class OpenAIGenerator:
    cfg = OPENAI_GEN_CONFIG
    system_prompt = SYSTEM_PROMPT_API

    def __init__(self, ledger_path, client=None, cfg=None):
        self.cfg = cfg or OPENAI_GEN_CONFIG
        if client is None:
            require_key("OPENAI_API_KEY")
            from openai import OpenAI
            client = OpenAI(timeout=60.0, max_retries=2)  # 키는 환경변수에서만 읽는다
        self.client = client
        self.ledger = CostLedger(ledger_path, self.cfg["budget_usd"], self.cfg["prices_usd_per_mtok"])
        self.last_meta = None

    def generate(self, system, user, max_new_tokens=None, prefill=None):
        """반환: (텍스트, 출력 토큰 수[추론 토큰 포함]). 정상 완료(status=completed)가 아니면 예외를 던진다."""
        if prefill:
            raise ValueError("응답 prefill 은 쓰지 않는다")
        max_out = max(max_new_tokens or self.cfg["max_new_tokens"], self.cfg["min_max_tokens"])
        self.ledger.check((len(system) + len(user)) // 3 + 64, max_out)  # 글자 수/3 = 보수적 토큰 추정
        resp = self.client.responses.create(
            model=self.cfg["model"], instructions=system, input=user, max_output_tokens=max_out,
            reasoning={"effort": self.cfg["effort"]}, store=self.cfg["store"],
        )
        usage = resp.usage
        in_tok, out_tok = int(usage.input_tokens), int(usage.output_tokens)
        details = getattr(usage, "output_tokens_details", None)
        incomplete = getattr(resp, "incomplete_details", None)
        meta = {"requested_model": self.cfg["model"], "served_model": getattr(resp, "model", None),
                "request_id": getattr(resp, "_request_id", None), "response_id": getattr(resp, "id", None),
                "input_tokens": in_tok, "output_tokens": out_tok,
                "reasoning_tokens": getattr(details, "reasoning_tokens", None),
                "status": getattr(resp, "status", None), "incomplete_reason": getattr(incomplete, "reason", None),
                "cost_usd": round(self.ledger.cost(in_tok, out_tok), 6)}
        self.ledger.record(dict(meta, ts=datetime.datetime.now().isoformat(timespec="seconds")))
        self.last_meta = meta
        text = (getattr(resp, "output_text", "") or "").strip()
        if meta["status"] != "completed":  # incomplete(토큰 한도)·failed·cancelled: 잘린 답을 정상 답변으로 쓰지 않는다
            raise RuntimeError(f"status={meta['status']} incomplete_reason={meta['incomplete_reason']}")
        if not text:
            raise RuntimeError("empty output_text (거절 또는 추론만 생성)")
        return text, out_tok
