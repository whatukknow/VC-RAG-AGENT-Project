"""API 연결 점검: 키가 있는지, 모델이 응답하는지, 비용·요청 ID가 기록되는지 최소 호출 1회로 확인한다.
키 값은 출력하지 않는다. 비용은 백엔드별 원장(results/*_cost_ledger.jsonl)에 기록되고 한도에 포함된다.
사용: .venv/Scripts/python src/check_api.py [--backend openai|anthropic]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ragagent.envfile import load_env  # noqa: E402
from ragagent.generate_api import ApiGenerator  # noqa: E402
from ragagent.generate_openai import OpenAIGenerator  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKENDS = {
    "openai": ("OPENAI_API_KEY", OpenAIGenerator, "openai_cost_ledger.jsonl"),
    "anthropic": ("ANTHROPIC_API_KEY", ApiGenerator, "api_cost_ledger.jsonl"),
}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="openai", choices=list(BACKENDS))
    a = ap.parse_args()
    key_name, cls, ledger = BACKENDS[a.backend]
    loaded = load_env(os.path.join(ROOT, ".env"))
    print(f"{key_name}:", "설정됨" if os.environ.get(key_name) else "없음", f"(.env에서 읽은 키 이름: {loaded or '없음'})")
    gen = cls(os.path.join(ROOT, "results", ledger))
    text, n = gen.generate("Reply with exactly: STATUS: ANSWER", "Say it.", 64)
    m = gen.last_meta
    print(f"응답: {text!r}")
    print(f"요청 모델={m['requested_model']} 실제 응답 모델={m['served_model']}")
    print(f"토큰 in/out={m['input_tokens']}/{m['output_tokens']} (추론 토큰: {m.get('reasoning_tokens')}) "
          f"비용=${m['cost_usd']} 요청ID={m['request_id']} 응답ID={m.get('response_id')}")
    print(f"누적 비용 ${gen.ledger.spent():.6f} / 한도 ${gen.cfg['budget_usd']:.2f}")


if __name__ == "__main__":
    main()
