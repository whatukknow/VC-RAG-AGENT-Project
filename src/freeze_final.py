"""최종 평가 직전에 검색 설정을 고정한다(Day 3 종료 시점). 이후 --final 은 이 고정과 일치할 때만 실행된다.
사용: .venv/Scripts/python src/freeze_final.py
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ragagent.freeze import FINAL_LOCK, build_final_lock, verify_files  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    with open(os.path.join(ROOT, "eval", "FREEZE.json"), encoding="utf-8") as f:
        errors = verify_files(ROOT, json.load(f)["files"])
    if errors:
        sys.exit("평가셋 고정(eval/FREEZE.json) 검사 실패: " + "; ".join(errors))
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or None
    except OSError:
        commit = None
    lock = build_final_lock(ROOT, commit)
    out = os.path.join(ROOT, FINAL_LOCK)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(lock, f, indent=2, ensure_ascii=False)
    print(f"고정 완료: {FINAL_LOCK} (파일 {len(lock['files'])}개, git {commit})")


if __name__ == "__main__":
    main()
