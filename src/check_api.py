"""API 연결 점검: 키가 있는지, 모델이 응답하는지, 비용·요청 ID가 기록되는지 최소 호출 1회로 확인한다.
키 값은 출력하지 않는다. 비용은 results/api_cost_ledger.jsonl 에 기록되고 한도(API_GEN_CONFIG.budget_usd)에 포함된다.
사용: .venv/Scripts/python src/check_api.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ragagent.envfile import load_env  # noqa: E402
from ragagent.generate import API_GEN_CONFIG  # noqa: E402
from ragagent.generate_api import ApiGenerator  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    loaded = load_env(os.path.join(ROOT, ".env"))
    print("ANTHROPIC_API_KEY:", "설정됨" if os.environ.get("ANTHROPIC_API_KEY") else "없음",
          f"(.env에서 읽은 키 이름: {loaded or '없음'})")
    gen = ApiGenerator(os.path.join(ROOT, "results", "api_cost_ledger.jsonl"))
    text, n = gen.generate("Reply with exactly: STATUS: ANSWER", "Say it.", 64)
    m = gen.last_meta
    print(f"응답: {text!r}")
    print(f"요청 모델={m['requested_model']} 실제 응답 모델={m['served_model']} stop={m['stop_reason']}")
    print(f"토큰 in/out={m['input_tokens']}/{m['output_tokens']} 비용=${m['cost_usd']} 요청ID={m['request_id']}")
    print(f"누적 비용 ${gen.ledger.spent():.6f} / 한도 ${API_GEN_CONFIG['budget_usd']:.2f}")


if __name__ == "__main__":
    main()
