"""채점 시트 생성과 지표 계산.
  .venv/Scripts/python src/grade.py sheet results/dev/answers_A_*.json --out results/dev/grading_dev.csv
  (CSV 의 correct·grounded·grader·note 를 기입한다)
  .venv/Scripts/python src/grade.py score results/dev/answers_A_*.json --grades results/dev/grading_dev.csv
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ragagent.grading import read_grades, score, write_sheet  # noqa: E402


def load_rows(patterns):
    rows = []
    for pat in patterns:
        for path in sorted(glob.glob(pat)):
            with open(path, encoding="utf-8") as f:
                rows += json.load(f)["rows"]
    if not rows:
        sys.exit("답변 기록 파일을 찾지 못했다: " + " ".join(patterns))
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet")
    s.add_argument("answers", nargs="+")
    s.add_argument("--out", required=True)
    c = sub.add_parser("score")
    c.add_argument("answers", nargs="+")
    c.add_argument("--grades", required=True)
    a = ap.parse_args()
    rows = load_rows(a.answers)
    if a.cmd == "sheet":
        if os.path.exists(a.out):
            sys.exit(f"이미 있는 파일을 덮어쓰지 않는다(채점 기록 보호): {a.out}")
        write_sheet(a.out, rows)
        print(f"채점 시트 {len(rows)}행 -> {a.out}")
    else:
        res = score(rows, read_grades(a.grades))
        for cfg, m in res.items():
            print(f"[{cfg}] complete={m['complete']} 정답충족={m['correct']} 근거적합={m['grounded']} "
                  f"근거없음 거절={m['no_evidence_refused']}(지어냄 {m['no_evidence_answered']}) "
                  f"답변가능 잘못거절={m['answerable_refused']} 호출성공={m['call_success']} 오류={m['errors']} "
                  f"응답ms(평균/중앙/n)={m['response_ms_mean_median_n']} 채점자={m['graders']}"
                  + (f" 미채점={m['ungraded']}" if m["ungraded"] else ""))


if __name__ == "__main__":
    main()
