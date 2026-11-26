# VC-RAG-AGENT-Project

VC 딜소싱 심사역이 **YC 공개 프로필(AI 추론 인프라 회사)** 문서에서 근거 있는 답을 찾도록 돕는 Knowledge Agent.
BM25 + Vector 하이브리드 검색, re-ranking, 근거 인용/근거 부족 안내, 고정 평가셋 비교 실험을 1인으로 수행한다.

> 상태: **Day 1~2 진행 중.** 문제 정의·문서·평가셋 고정, 청킹·BM25·RRF 구현 완료. 벡터 검색·re-ranking·답변·최적화·최종 평가는 미구현.
> 과제 요건은 팀 과제이나 1인 수행이다. 편차는 `docs/problem.md` 6절에 기록한다.

## 구조
| 경로 | 내용 |
|---|---|
| `docs/problem.md` | 문제 정의, 범위, 성공 기준(사전 확정), 데이터 점검 결과 |
| `docs/doc_list.csv` | 문서 68개 목록(ID·출처 URL·이용 조건·수집일·원문 위치) |
| `eval/dev.json`, `eval/test.json` | 개발 10문항, **최종 20문항(v1.0 고정)**. 스키마는 `eval/README.md` |
| `eval/FREEZE.json` | 고정 시점 SHA-256. `src/eval_retrieval.py --final`이 검증 |
| `eval/chunk_map.json` | 근거 인용 → 청크 ID 매핑(청킹 변경 시 재생성) |
| `src/` | 코퍼스 구성, 청킹·BM25·RRF, 색인 빌드, 검색 평가 |
| `tests/` | 단위 테스트 |

## 데이터와 이용 조건
- 원천: `yc-oss/api` 일괄 JSON(`https://yc-oss.github.io/api/companies/all.json`), 수집일 2026-11-26. 저장소에 **라이선스가 명시되어 있지 않은 비공식 데이터**다.
- 원문 JSON과 가공 코퍼스(`data/`)는 **저장소에 올리지 않는다.** 문서 ID·원본 URL·재수집 스크립트만 공개한다. 평가셋의 근거 인용은 문항 검증을 위한 짧은 발췌다.
- 외부 모델로 보내는 텍스트는 공개 프로필 문구뿐이다. API 키는 `.env`(미커밋)에 둔다. 예시는 `.env.example`.

## 재현 (현재까지)
Python 3.13. 외부 의존성 없음.
```powershell
# 1) 데이터 수집 (data/raw/all.json) — 수동 다운로드 후 경로 고정
curl -L -o data/raw/all.json https://yc-oss.github.io/api/companies/all.json
# 2) 후보 추출 -> 수동 검토 목록 반영 -> 코퍼스·문서 목록
python -I src/build_corpus.py data/raw/all.json data/corpus/candidates.jsonl
python -I src/curate_corpus.py data/raw/all.json data/corpus/candidates.jsonl data/corpus/corpus.jsonl docs/doc_list.csv
# 3) 평가셋 무결성 검사
python -I src/check_eval.py data/corpus/corpus.jsonl eval/dev.json eval/test.json
# 4) 청킹·색인·근거 매핑, 개발셋 BM25 평가, 테스트
python src/build_index.py
python src/eval_retrieval.py --config bm25
python -m unittest discover -s tests -v
```

## 규칙
- 최종 평가셋(`eval/test.json`)은 개발·튜닝에 쓰지 않는다. 변경은 새 버전과 사유를 `docs/problem.md` 변경 기록에 남긴다.
- 평가용 정답표는 검색 색인·프롬프트에 넣지 않는다.
- 최종 결과의 오답·실패를 삭제하거나 좋은 재실행만 고르지 않는다.
- 작은 평가셋(최종 20문항)과 제한된 문서 범위(68개, 영문 소개문)의 검증이며, 서비스 수준·통계적 유의성을 주장하지 않는다.

## 작업 방식
`main`에는 초기 커밋만 직접 올리고, 이후 기능 브랜치 → PR → 리뷰 → 머지로 진행한다.
