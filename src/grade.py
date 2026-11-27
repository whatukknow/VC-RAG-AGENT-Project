"""채점 시트 생성과 지표 계산.
  .venv/Scripts/python src/grade.py sheet results/dev/answers_A_<run_id>.json --out results/dev/grading_dev.csv
  (CSV 의 correct·grounded·grader·note 를 기입한다. run_id 열은 수정하지 않는다)
  .venv/Scripts/python src/grade.py score results/dev/answers_A_<run_id>.json --grades results/dev/grading_dev.csv
주의: 입력은 구성당 실행(run_id) 하나만 지정한다. 같은 (질문, 구성)이 둘 이상이면 오류로 중단한다(와일드카드로
재실행·다른 백엔드 결과가 섞이는 것을 막기 위함). INCOMPLETE 파일은 자동 제외한다.
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ragagent.grading import read_grades, score, write_sheet  # noqa: E402


def load_rows(patterns):
    """글롭에 걸린 답변 기록을 읽는다. INCOMPLETE(한도 도달로 중단된 부분 기록)는 제외하고, 입력으로 쓴 파일을 출력한다."""
    rows, used = [], []
    for pat in patterns:
        for path in sorted(glob.glob(pat)):
            if "INCOMPLETE" in os.path.basename(path):
                print(f"제외(불완전 실행): {os.path.basename(path)}")
                continue
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            gc = data["summary"].get("generation_config", {})
            used.append(f"{os.path.basename(path)} (run {data['summary'].get('run_id')}, "
                        f"{gc.get('backend') or 'local'}/{gc.get('model')}, {gc.get('prompt_version')})")
            rows += data["rows"]
    if not rows:
        sys.exit("답변 기록 파일을 찾지 못했다: " + " ".join(patterns))
    print("입력 파일:\n  " + "\n  ".join(used))
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
        try:
            write_sheet(a.out, rows)
        except ValueError as e:  # 같은 (질문, 구성) 중복: 실행 하나만 골라 다시 입력해야 한다
            sys.exit(str(e))
        print(f"채점 시트 {len(rows)}행 -> {a.out}")
    else:
        try:
            res = score(rows, read_grades(a.grades))
        except ValueError as e:
            sys.exit(str(e))
        for cfg, m in res.items():
            print(f"[{cfg}] complete={m['complete']} 정답충족={m['correct']} 근거적합={m['grounded']} "
                  f"근거없음 거절={m['no_evidence_refused']}(지어냄 {m['no_evidence_answered']}) "
                  f"답변가능 잘못거절={m['answerable_refused']} 호출성공={m['call_success']} 오류={m['errors']} "
                  f"응답ms(평균/중앙/n)={m['response_ms_mean_median_n']} 채점자={m['graders']}"
                  + (f" 미채점={m['ungraded']}" if m["ungraded"] else ""))


if __name__ == "__main__":
    main()
