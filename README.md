# VC-RAG-AGENT-Project

VC 딜소싱 심사역이 **YC 공개 프로필(AI 추론 인프라 회사)** 문서에서 근거 있는 답을 찾도록 돕는 Knowledge Agent.
BM25 + Vector 하이브리드 검색, re-ranking, 근거 인용/근거 부족 안내, 고정 평가셋 비교 실험을 1인으로 수행한다.

> 상태: **Day 3 진행 중.** 검색(A/B/C), 근거 기반 답변(출처 인용·근거 부족 안내), 쿼리 리라이트(C+R), 생성기(OpenAI `gpt-6-luna` 기본), Streamlit 인터페이스 구현 완료. 평가는 개발용 20문항만 수행했고 **최종 평가(최종셋 20문항)는 아직 실행하지 않았다.**
> 과제 요건은 팀 과제이나 1인 수행이다. 편차는 `docs/problem.md` 6절에 기록한다.

## 구조
| 경로 | 내용 |
|---|---|
| `docs/problem.md` | 문제 정의, 범위, 성공 기준(사전 확정), 데이터 점검 결과 |
| `docs/doc_list.csv` | 문서 68개 목록(ID·출처 URL·이용 조건·수집일·원문 위치) |
| `eval/dev.json`, `eval/dev_extra.json`, `eval/test.json` | 개발 10문항, 보조 개발 10문항, **최종 20문항(v1.0 고정)**. 스키마는 `eval/README.md` |
| `eval/FREEZE.json`, `configs/final.lock.json` | 평가셋 고정(현재), 검색 설정 고정(최종 평가 직전 생성). `--final`이 둘 다 검증 |
| `configs/` | 모델 리비전 고정(`models.lock.json`), 원본 스냅샷 해시(`data_snapshot.json`) |
| `eval/chunk_map.json` | 근거 인용 → 청크 ID 매핑(청킹 변경 시 재생성) |
| `src/` | 코퍼스 구성, 청킹·BM25·RRF, 색인 빌드, 검색·답변 평가(`eval_retrieval.py`, `run_answers.py`), 채점(`grade.py`), 인터페이스(`app.py`) |
| `tests/` | 단위 테스트 |

## 데이터와 이용 조건
- 원천: `yc-oss/api` 일괄 JSON(`https://yc-oss.github.io/api/companies/all.json`), 수집일 2026-11-26. 저장소에 **라이선스가 명시되어 있지 않은 비공식 데이터**다.
- 원문 JSON과 가공 코퍼스(`data/`)는 **저장소에 올리지 않는다.** 문서 ID·원본 URL·재수집 스크립트만 공개한다. 평가셋의 근거 인용은 문항 검증을 위한 짧은 발췌다.
- 외부 모델로 보내는 텍스트는 공개 프로필 문구뿐이다. API 키는 `.env`(미커밋)에 둔다. 예시는 `.env.example`.

## 재현 (현재까지)
Python 3.13. 1~4단계는 표준 라이브러리만 쓴다. 5단계부터(벡터 검색·reranker) `requirements.txt`의 패키지와 모델 다운로드가 필요하다(전이 의존성까지 고정한 `requirements.lock.txt` 제공).

> **주의(원본 스냅샷):** yc-oss 일괄 JSON은 매일 갱신된다. 고정된 코퍼스·평가셋은 `configs/data_snapshot.json`의 해시(2026-11-26 수집본)와 같은 파일에서만 재현된다. 다른 날 받은 파일이면 2단계의 `curate_corpus.py`가 중단된다. 원문은 재배포하지 않으므로 같은 스냅샷을 얻을 수 없으면 평가셋을 새로 설계해야 한다.
```powershell
# 1) 데이터 수집 (data/raw/all.json)
mkdir -p data/raw
curl -L -o data/raw/all.json https://yc-oss.github.io/api/companies/all.json
# 2) 후보 추출 -> 수동 검토 목록 반영 -> 코퍼스·문서 목록
python -I src/build_corpus.py data/raw/all.json data/corpus/candidates.jsonl
python -I src/curate_corpus.py data/raw/all.json data/corpus/candidates.jsonl data/corpus/corpus.jsonl docs/doc_list.csv
# 3) 평가셋 무결성 검사
python -I src/check_eval.py data/corpus/corpus.jsonl eval/dev.json eval/test.json eval/dev_extra.json
# 4) 청킹·색인·근거 매핑
python src/build_index.py
# 5) 격리 환경과 모델(리비전 고정: configs/models.lock.json, CPU)
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.lock.txt
.venv/Scripts/python src/download_models.py     # bge-small-en-v1.5(133MB, MIT), ms-marco-MiniLM-L6-v2(91MB, Apache-2.0)
# 6) 개발용 셋에서 A(Vector)·B(BM25+RRF)·C(+reranker) 검색 평가, 테스트
.venv/Scripts/python src/eval_retrieval.py --configs A B C
.venv/Scripts/python src/eval_retrieval.py --split dev_extra --configs A B C
.venv/Scripts/python -m unittest discover -s tests
```

### 최종 평가의 고정 절차 (Day 3 종료 시점 → Day 4)
1. `eval/FREEZE.json`: 평가셋·코퍼스·문서목록 해시. 누락·불일치는 모두 오류다.
2. `.venv/Scripts/python src/freeze_final.py`: chunk_map·모델 리비전·청크 색인·모든 검색·답변 설정(프롬프트 해시 포함)·**평가 결과를 만드는 코드의 해시**·최종 생성 백엔드를 `configs/final.lock.json`에 고정한다(커밋되지 않은 변경이 있으면 거부). **이 파일이 없으면 `--final`은 거부된다.** 현재 고정됨(`openai`, `gpt-6-luna`).
3. `--final` 실행(Day 4에 한 번만): `.venv/Scripts/python src/run_answers.py --final --backend openai --configs A B C C+R`, `.venv/Scripts/python src/eval_retrieval.py --final --configs A B C`. FREEZE와 final.lock을 모두 통과해야 하고, 고정 이후 코드·설정이 바뀌었거나 다른 백엔드이면 거부된다.
4. 같은 구성의 최종 결과가 이미 있으면 `--rerun-reason "사유"` 없이는 실행되지 않으며, 재실행해도 기존 결과는 삭제하지 않는다(좋은 결과만 고르지 않기 위함).

## 실행 인터페이스(Streamlit)
```powershell
.venv/Scripts/streamlit run src/app.py
```
질문을 입력하면 답변, 인용한 근거 청크의 원문 발췌와 출처 링크, 검색 상위 5개, 쿼리 리라이트(C+R), 응답 시간·토큰·비용을 볼 수 있다.
오류(생성·검색 실패)는 정상적인 '근거 부족' 거절과 다르게 표시한다. 사이드바에서 검색 구성(A/B/C/C+R)과 생성 백엔드를 고르고,
**'검색만 보기'**를 켜면 API 호출 없이 검색 결과만 확인한다.
- 생성 단계는 질문과 검색된 공개 프로필 문구를 선택한 외부 API(기본 OpenAI)로 보낸다. 키는 프로젝트 루트 `.env`의 `OPENAI_API_KEY`(예시: `.env.example`) 또는 환경변수에 두며 화면·기록에 나오지 않는다.
- API 비용은 원장(`results/openai_cost_ledger.jsonl`)에 기록되고 한도($5)에 도달하면 실행을 멈춘다.
- 화면 테스트(AppTest)는 로컬 색인·모델(`data/`)이 있을 때만 실행된다.

## 규칙
- 최종 평가셋(`eval/test.json`)은 개발·튜닝에 쓰지 않는다. 변경은 새 버전과 사유를 `docs/problem.md` 변경 기록에 남긴다.
- 평가용 정답표는 검색 색인·프롬프트에 넣지 않는다.
- 최종 결과의 오답·실패를 삭제하거나 좋은 재실행만 고르지 않는다.
- 작은 평가셋(최종 20문항)과 제한된 문서 범위(68개, 영문 소개문)의 검증이며, 서비스 수준·통계적 유의성을 주장하지 않는다.

## 작업 방식
`main`에는 초기 커밋만 직접 올리고, 이후 기능 브랜치 → PR → 리뷰 → 머지로 진행한다.
