# 평가셋 스키마 (v0.1 초안 — 사용자 승인 전)

| 파일 | 내용 |
|---|---|
| `dev.json` | 개발용 10문항 (답변 가능 8, 근거 없음 2). 튜닝·근거 부족 판정 방법 결정에 사용 |
| `test.json` | 최종 20문항 (직접 10, 변형·유사 조건 구분 7, 근거 없음 3). **튜닝 금지, 승인 후 버전 고정** |

## 필드
- `id`: D01~D10, T01~T20. `type`: `direct` / `variant_or_confusable` / `no_evidence`.
- `question`(영문, 검색에 사용) / `question_ko`(참고용 번역). 문서가 영어이므로 질문도 영어로 둔다.
- `expected_key_facts`: 정답 충족 채점용 핵심 사실. 모두 맞고 모순이 없으면 1. 근거 없음 문항은 "정보 부족 안내".
- `allowed_evidence`: `{doc_id, quote}`. `quote`는 `data/corpus/corpus.jsonl`의 `long_description`에 **그대로 존재하는 원문 발췌**이며, `src/check_eval.py`가 일치를 검사한다. 청크 ID는 청킹 확정 후 `quote`가 포함된 청크로 매핑해 `chunk_ids`를 추가한다(ID가 바뀌면 재매핑).
- `absence_reason`, `absence_checks`: 근거 없음 판정 이유와 해당 문서에 특정 패턴이 없음을 확인하는 정규식.
- `grading_note`: 혼동 방지 채점 메모(예: 지연시간 수치를 비용 절감으로 답하면 오답).

## 규칙
- 정답표(`eval/`)는 검색 색인과 프롬프트에 넣지 않는다. 검색 대상은 `data/corpus/corpus.jsonl`의 `long_description`뿐이다.
- 개발셋과 최종셋은 근거 문서가 겹치지 않는다(`check_eval.py`가 검사).
- 최종셋 결과를 본 뒤 질문을 교체·삭제하지 않는다.
- 검사: `python -I src/check_eval.py data/corpus/corpus.jsonl eval/dev.json eval/test.json`
