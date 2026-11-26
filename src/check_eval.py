"""평가셋 무결성 검사: 구성·인용 원문 일치·근거 없음 부재·개발/최종 분리.
사용: python -I src/check_eval.py data/corpus/corpus.jsonl eval/dev.json eval/test.json
"""
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -I 에서도 공유 모듈을 찾는다
from ragagent.textnorm import norm  # noqa: E402  (build_index 와 같은 정규화)


def main(corpus_path, dev_path, test_path, extra_path=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    docs = {}
    for l in open(corpus_path, encoding="utf-8"):
        d = json.loads(l)
        docs[d["doc_id"]] = norm(d["long_description"])
    dev = json.load(open(dev_path, encoding="utf-8"))["questions"]
    test = json.load(open(test_path, encoding="utf-8"))["questions"]
    extra = json.load(open(extra_path, encoding="utf-8"))["questions"] if extra_path else []
    errors = []

    def err(msg):
        errors.append(msg)

    # 1) 구성
    c_dev = Counter((q["type"], q["answerable"]) for q in dev)
    c_test = Counter(q["type"] for q in test)
    if len(dev) != 10 or sum(q["answerable"] for q in dev) != 8:
        err(f"dev 구성 오류: {len(dev)}문항, 답변가능 {sum(q['answerable'] for q in dev)}")
    if len(test) != 20 or sum(q["answerable"] for q in test) != 17:
        err(f"test 구성 오류: {len(test)}문항, 답변가능 {sum(q['answerable'] for q in test)}")
    if (c_test["direct"], c_test["variant_or_confusable"], c_test["no_evidence"]) != (10, 7, 3):
        err(f"test 유형 오류: {dict(c_test)}")

    if extra and (len(extra) != 10 or sum(q["answerable"] for q in extra) != 8):
        err(f"dev_extra 구성 오류: {len(extra)}문항, 답변가능 {sum(q['answerable'] for q in extra)}")

    # 2) ID·질문 중복
    ids = [q["id"] for q in dev + test + extra]
    if len(set(ids)) != len(ids):
        err("질문 ID 중복")
    qs = [norm(q["question"]).lower() for q in dev + test + extra]
    if len(set(qs)) != len(qs):
        err("질문 문장 중복")

    # 3) 인용 원문 일치
    n_quotes = 0
    for q in dev + test + extra:
        if q["answerable"] and not q["allowed_evidence"]:
            err(f"{q['id']}: 답변가능인데 근거 없음")
        if not q["answerable"] and q["allowed_evidence"]:
            err(f"{q['id']}: 근거없음인데 근거가 채워짐")
        for ev in q["allowed_evidence"]:
            n_quotes += 1
            text = docs.get(ev["doc_id"])
            if text is None:
                err(f"{q['id']}: 존재하지 않는 doc_id {ev['doc_id']}")
            elif norm(ev["quote"]) not in text:
                err(f"{q['id']}: 인용이 원문과 불일치 [{ev['doc_id']}] {ev['quote'][:60]}")

    # 4) 근거 없음 부재 확인(지정 문서)
    for q in dev + test + extra:
        if q["answerable"]:
            continue
        if not q.get("absence_checks"):
            err(f"{q['id']}: 근거 없음 문항에 absence_checks가 없다(부재 확인 불가)")
        for chk in q.get("absence_checks", []):
            if chk["doc_id"] not in docs:
                err(f"{q['id']}: absence_checks의 doc_id가 코퍼스에 없다 {chk['doc_id']}")
                continue
            m = re.search(chk["must_not_match"], docs[chk["doc_id"]], re.I)
            if m:
                err(f"{q['id']}: 부재 가정 위반 [{chk['doc_id']}] '{m.group(0)}'")

    # 5) 개발/최종 문서 분리
    dev_docs = {e["doc_id"] for q in dev for e in q["allowed_evidence"]} | {
        c["doc_id"] for q in dev for c in q.get("absence_checks", [])}
    test_docs = {e["doc_id"] for q in test for e in q["allowed_evidence"]} | {
        c["doc_id"] for q in test for c in q.get("absence_checks", [])}
    overlap = dev_docs & test_docs
    if overlap:
        err(f"개발·최종 문서 겹침: {sorted(overlap)}")
    if extra:
        extra_docs = {e["doc_id"] for q in extra for e in q["allowed_evidence"]} | {
            c["doc_id"] for q in extra for c in q.get("absence_checks", [])}
        for name, other in (("test", test_docs), ("dev", dev_docs)):
            if extra_docs & other:
                err(f"dev_extra·{name} 문서 겹침: {sorted(extra_docs & other)}")
        print(f"dev_extra: {dict(Counter((q['type'], q['answerable']) for q in extra))}, 문서 {len(extra_docs)}개")

    # 6) 근거 없음 질문 주제 이름이 다른 문서에 언급되는지(참고용)
    print("--- 참고: 근거 없음 주제 회사명이 다른 문서에 언급되는지 ---")
    for name, doc in [("unify", "yc-unify"), ("wafer", "yc-wafer"), ("runanywhere", "yc-runanywhere")]:
        others = [k for k, v in docs.items() if k != doc and name in v.lower()]
        print(f"{name}: 다른 문서 언급 {others}")

    print(f"dev: {dict(c_dev)}")
    print(f"test: {dict(c_test)}")
    print(f"인용 {n_quotes}건 검사, 문서 수 dev {len(dev_docs)} / test {len(test_docs)}")
    print("오류 없음" if not errors else "오류:\n" + "\n".join(" - " + e for e in errors))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
