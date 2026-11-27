"""API 생성기(Claude Haiku 5.5). 같은 generate() 인터페이스를 쓰므로 AnswerPipeline·Rewriter 는 그대로 동작한다.
- 비용 한도: 호출 전에 '누적 + 최악 비용'이 한도를 넘으면 BudgetExceeded 로 실행 전체를 멈춘다. 원장은 JSONL.
- 재현성: 이 모델은 temperature 등 샘플링 값을 설정할 수 없어 결정성을 강제할 수 없다. 대신 응답 모델 ID·요청 ID·토큰 수를 기록한다.
- prefill 은 5.5 세대에서 400 이므로 거부한다.
- 외부로 보내는 것은 질문과 검색된 공개 프로필 문구뿐이다(사용자 식별 정보 없음). 키 값은 출력·기록하지 않는다."""
import datetime
import json
import os

from .envfile import require_key
from .errors import BudgetExceeded
from .generate import API_GEN_CONFIG, SYSTEM_PROMPT_API


class CostLedger:
    def __init__(self, path, cap_usd, prices):
        self.path, self.cap, self.prices = path, cap_usd, prices

    def cost(self, in_tok, out_tok):
        return in_tok * self.prices["input"] / 1e6 + out_tok * self.prices["output"] / 1e6

    def spent(self):
        total = 0.0
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        total += json.loads(line).get("cost_usd", 0.0)
        return total

    def check(self, est_in_tokens, max_out_tokens):
        """이번 호출의 최악 비용을 더해도 한도 이내인지 확인한다."""
        spent, worst = self.spent(), self.cost(est_in_tokens, max_out_tokens)
        if spent + worst > self.cap:
            raise BudgetExceeded(f"비용 한도 ${self.cap:.2f} 도달 직전: 누적 ${spent:.4f} + 이번 최악 ${worst:.4f}")

    def record(self, entry):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class ApiGenerator:
    cfg = API_GEN_CONFIG
    system_prompt = SYSTEM_PROMPT_API

    def __init__(self, ledger_path, client=None, cfg=None):
        self.cfg = cfg or API_GEN_CONFIG
        if client is None:
            require_key("ANTHROPIC_API_KEY")
            import anthropic
            client = anthropic.Anthropic(timeout=60.0, max_retries=2)  # 키는 환경변수에서만 읽는다
        self.client = client
        self.ledger = CostLedger(ledger_path, self.cfg["budget_usd"], self.cfg["prices_usd_per_mtok"])
        self.last_meta = None

    def generate(self, system, user, max_new_tokens=None, prefill=None):
        """반환: (텍스트, 출력 토큰 수). 사고 토큰도 max_tokens 에 포함되므로 최소 여유(min_max_tokens)를 둔다."""
        if prefill:
            raise ValueError("응답 prefill 은 이 모델(5.5 세대)에서 지원되지 않는다")
        max_tokens = max(max_new_tokens or self.cfg["max_new_tokens"], self.cfg["min_max_tokens"])
        self.ledger.check((len(system) + len(user)) // 3 + 64, max_tokens)  # 글자 수/3 = 보수적 토큰 추정
        resp = self.client.messages.create(
            model=self.cfg["model"], max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.cfg["effort"]},
        )
        usage = resp.usage
        in_tok, out_tok = int(usage.input_tokens), int(usage.output_tokens)
        meta = {"requested_model": self.cfg["model"], "served_model": getattr(resp, "model", None),
                "request_id": getattr(resp, "_request_id", None), "input_tokens": in_tok, "output_tokens": out_tok,
                "stop_reason": getattr(resp, "stop_reason", None),
                "cost_usd": round(self.ledger.cost(in_tok, out_tok), 6)}
        self.ledger.record(dict(meta, ts=datetime.datetime.now().isoformat(timespec="seconds")))
        self.last_meta = meta
        if meta["stop_reason"] == "refusal":
            details = getattr(resp, "stop_details", None)
            raise RuntimeError(f"refusal category={getattr(details, 'category', None)}")  # 올바른 거절이 아닌 오류로 취급
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        return text.strip(), out_tok
