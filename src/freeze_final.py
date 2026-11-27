"""최종 평가 직전에 검색·답변 설정과 코드를 고정한다(Day 3 종료 시점). 이후 --final 은 이 고정과 일치할 때만 실행된다.
- 작업 폴더에 커밋되지 않은 변경이 있으면 거부한다(고정이 특정 커밋과 대응하도록).
- 이미 고정되어 있으면 `--force --reason "사유"` 가 필요하고, 사유·이전 커밋·이전 고정 파일 해시가 lock 의 history 에 남는다.
- 최종 결과(results/test)가 이미 있으면 `--after-final` 로 '결과를 본 뒤의 재고정'임을 명시해야 하며 이것도 history 에 남는다.
사용: .venv/Scripts/python src/freeze_final.py [--backend openai]
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ragagent.freeze import FINAL_LOCK, build_final_lock, plan_refreeze, verify_files  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="openai", choices=["openai", "anthropic", "local"])
    ap.add_argument("--force", action="store_true", help="이미 있는 고정 파일을 다시 만든다(--reason 필수)")
    ap.add_argument("--reason", default=None, help="재고정 사유(history 에 기록)")
    ap.add_argument("--after-final", action="store_true", help="최종 결과가 이미 있는 상태의 재고정임을 명시")
    a = ap.parse_args()
    history, error = plan_refreeze(ROOT, a.force, a.reason, a.after_final)
    if error:
        sys.exit(error)
    with open(os.path.join(ROOT, "eval", "FREEZE.json"), encoding="utf-8") as f:
        errors = verify_files(ROOT, json.load(f)["files"])
    if errors:
        sys.exit("평가셋 고정(eval/FREEZE.json) 검사 실패: " + "; ".join(errors))
    dirty = git("status", "--porcelain")
    if dirty:
        sys.exit("커밋되지 않은 변경이 있어 고정하지 않는다:\n" + dirty)
    commit = git("rev-parse", "HEAD") or None
    lock = build_final_lock(ROOT, commit, a.backend, history)
    out = os.path.join(ROOT, FINAL_LOCK)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(lock, f, indent=2, ensure_ascii=False)
    print(f"고정 완료: {FINAL_LOCK} | 백엔드 {a.backend} | 파일 {len(lock['files'])}개 · 코드 {len(lock['code'])}개 | git {commit} "
          f"| 재고정 이력 {len(lock['history'])}건")
    if history:
        print("마지막 이력:", json.dumps(history[-1], ensure_ascii=False))


if __name__ == "__main__":
    main()
