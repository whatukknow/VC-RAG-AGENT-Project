# Day 2 작업일지: 전처리·색인, Vector와 Hybrid 구현

- 프로젝트: VC-RAG-AGENT-Project (VC 딜소싱 RAG Agent)
- 수행 형태: 1인 수행, 코드는 Claude가 작성하고 결정·승인은 본인이 수행(바이브 코딩)
- 일자: 2026-11-26 (프로젝트 2일차 범위 기준)
- 관련 저장소: https://github.com/whatukknow/VC-RAG-AGENT-Project
- 작성 시점 기준 상태: PR #1 등록됨(Open, 미병합). 코드 리뷰 지적 9건은 모두 수정해 PR 브랜치에 반영함(머지는 본인 승인 대기)

## Notion 입력용 요약

**막힌 점, 고민**
- 개발셋에서 A/B/C가 모두 8/8이라 구성을 비교할 신호가 없었음(개발 8문항이 전부 직접형)
- 개발셋 결과(문항 하나 차이, 분모 8)로 "하이브리드·reranker가 낫다"고 말해도 되는지 판단이 필요했음
- 청크 색인에 소개문 전문이 있어 원문 데이터가 커밋될 뻔했고, Windows 줄바꿈 변환으로 고정 해시가 다른 환경에서 깨질 뻔했음
- GitHub에 로그인돼 있지 않아 PR을 만들 수 없었음(gh CLI·브라우저 모두 미로그인)
- 코드 리뷰에서 9건 지적(important 4): 새 clone에서 재현 실패, freeze 검사 범위 부족, 인용 정규화 불일치 등

**해결방안**
- 최종셋과 겹치지 않는 문서로 보조 개발셋 dev_extra 10문항(변형·혼동 포함) 추가. dev.json은 매뉴얼의 10문항을 유지하고 하이퍼파라미터는 바꾸지 않음
- 개발 결과는 우열의 근거가 아니라 방향성 힌트로만 해석하고, 최종셋은 Day 4에 한 번만 실행
- .gitignore에 data/index·data/models 추가, .gitattributes로 LF 고정, 커밋될 파일 해시가 고정값과 일치함을 확인
- 브라우저에서 직접 로그인한 뒤 브랜치를 SSH로 푸시하고 PR #1 등록
- 리뷰 지적 9건은 공유 정규화, 최종 설정 고정(final.lock) 추가, 재현 경로(폴더 생성·원본 스냅샷 해시) 보강, 청킹 한도 수정, 테스트 16건 추가로 모두 수정(테스트 33건 통과)(작성 시점 기준 미반영)

**산출물 링크**
[PR #1](https://github.com/whatukknow/VC-RAG-AGENT-Project/pull/1) · [src/ragagent](https://github.com/whatukknow/VC-RAG-AGENT-Project/tree/feat/vector-search/src/ragagent) · [dev_extra.json](https://github.com/whatukknow/VC-RAG-AGENT-Project/blob/feat/vector-search/eval/dev_extra.json) · [results](https://github.com/whatukknow/VC-RAG-AGENT-Project/tree/feat/vector-search/results) · [models.lock.json](https://github.com/whatukknow/VC-RAG-AGENT-Project/blob/feat/vector-search/configs/models.lock.json)

## 1. 오늘의 목표 (매뉴얼 2일차)
전처리·색인, Vector와 Hybrid 구현. 중간 결과물은 청크·메타데이터, A/B 검색 기록, 개발셋 동작.
(매뉴얼상 3일차 항목인 re-ranking(C)까지 앞당겨 구현했고, 개발셋에서만 평가함)

## 2. 한 일
| 순서 | 작업 | 결과 |
|---|---|---|
| 1 | 최종셋 고정 | test-v1.0 SHA-256을 eval/FREEZE.json에 기록. --final 옵션은 해시가 맞지 않으면 중단 |
| 2 | 청킹·색인 | 문장 단위 청킹, 안정적 청크 ID(문서ID#c00)와 원문 위치 기록. 문서 68개 -> 청크 120개(리뷰 반영 후 500자 하드 한도로 122개) |
| 3 | 근거 인용 -> 청크 ID 매핑 | eval/chunk_map.json 생성. 매핑 문제 0건 |
| 4 | BM25, RRF 구현 | 외부 의존성 없이 직접 구현. 단위 테스트 포함 |
| 5 | 로컬 모델 설치 | 임베딩 bge-small-en-v1.5(133MB, MIT), reranker ms-marco-MiniLM-L6-v2(91MB, Apache-2.0). 리비전 고정 |
| 6 | 벡터 검색(A), 하이브리드(B), re-ranking(C) 구현 | 하이퍼파라미터는 결과를 보기 전에 코드에 고정 |
| 7 | 개발셋 평가 | dev, dev_extra 각각 A/B/C 실행, 원본 기록을 results/에 저장 |
| 8 | 보조 개발셋 추가 | dev_extra 10문항(직접 4, 변형·혼동 4, 근거 없음 2) |
| 9 | Git 정리 | 초기 커밋을 main에 푸시, 기능 브랜치에서 PR #1 등록 |
| 10 | 코드 리뷰 | 지적 9건(important 4, nit 5) 보고 후 전부 수정, 테스트 17 -> 33건 |

## 3. 핵심 의사결정
| 결정 | 내용 | 이유 |
|---|---|---|
| 모델 실행 방식 | 로컬 CPU 모델 | 외부 API는 비용, 키 관리, 모델 버전 변동이 생기고 재현성이 떨어짐. GPU 빌드는 수 GB라 불필요(청크 120개 규모) |
| 결합 방식 | 점수 합산 대신 RRF(k=60, 가중치 1:1) | BM25와 벡터 점수는 척도가 달라 단순 합산하지 않음(매뉴얼 요건) |
| 구성 | A 벡터 상위 5 / B BM25 20 + 벡터 20을 RRF 후 상위 5 / C B의 상위 10을 cross-encoder로 재정렬 후 상위 5 | 단계별 효과를 분리해서 비교 |
| 보조 개발셋 | dev.json은 매뉴얼의 10문항을 유지하고 dev_extra.json을 별도로 추가 | 공식 개발셋이 전부 직접형이라 A/B/C가 모두 만점이어서 구성 비교 신호가 없었음 |
| 설정 변경 금지 | dev_extra 결과를 본 뒤에도 하이퍼파라미터를 조정하지 않음 | 개발셋에 맞춘 튜닝을 피하고 변경 기록에 남김 |
| PR 방식 | main에는 초기 커밋만 직접 푸시, 이후 기능 브랜치와 PR | 매뉴얼의 PR 리뷰 요건 충족 |

## 4. 결과 (개발셋만, 최종셋은 실행하지 않음)
| 구성 | dev Hit@5 | dev MRR | dev_extra Hit@5 | dev_extra MRR |
|---|---|---|---|---|
| A (Vector) | 8/8 | 0.906 | 7/8 | 0.8125 |
| B (BM25+RRF) | 8/8 | 1.0 | 8/8 | 0.9062 |
| C (+reranker) | 8/8 | 1.0 | 8/8 | 1.0 |

해석: dev_extra의 Hit@5 차이는 문항 하나(X02)에서 나왔고 분모가 8이라 구성 우열의 근거가 아니라 방향성 힌트로만 본다. 순서는 A < B < C이다.

리뷰 반영 후 추가 지표(여러 근거가 필요한 문항에서 모든 근거 청크를 상위 5개에 회수했는지, full-evidence@5)
| 구성 | dev | dev_extra |
|---|---|---|
| A | 7/8 | 5/8 |
| B | 8/8 | 7/8 |
| C | 8/8 | 7/8 |

Hit@5(하나 이상)는 A가 dev_extra에서 7/8이지만 필요한 근거를 모두 가져온 문항은 5/8이다. Hit@5만 보면 검색 성능을 과대평가할 수 있다는 리뷰 지적이 수치로 확인됨. 청킹 수정 후에도 Hit@5·MRR은 변하지 않았다.

## 5. 산출물과 근거
| 경로 | 내용 |
|---|---|
| src/ragagent/chunking.py | 청킹과 청크 ID, 원문 위치 |
| src/ragagent/bm25.py, fusion.py | BM25, RRF |
| src/ragagent/embed.py, rerank.py, pipeline.py, factory.py | 임베딩(캐시 포함), reranker, A/B/C 파이프라인, 조립 |
| src/build_index.py, src/eval_retrieval.py, src/download_models.py | 색인·매핑, 구성별 평가, 모델 다운로드 |
| eval/dev_extra.json, eval/chunk_map.json | 보조 개발셋, 근거->청크 매핑 |
| configs/models.lock.json, requirements.txt | 모델 리비전과 패키지 버전 고정 |
| results/dev, results/dev_extra | 구성별 원본 기록(질문, 상위 청크, 점수, 순위, 재정렬 전후) |
| tests/ | 단위 테스트 33건 통과(리뷰 반영 후) |

커밋과 PR
| 근거 | 내용 |
|---|---|
| 0ee17da | 문제 정의, 고정 평가셋, BM25/RRF 기본 구현 (main) |
| c612737 | 벡터 검색, 하이브리드, reranker |
| db9c0a7 | 보조 개발셋 dev_extra |
| 7097c12 | README 의존성 문구 정정 |
| PR #1 | https://github.com/whatukknow/VC-RAG-AGENT-Project/pull/1 (feat/vector-search -> main, Open) |

## 6. 문제와 해결 (시행착오)
| 문제 | 원인 | 해결 |
|---|---|---|
| 개발셋에서 세 구성이 모두 8/8 | 개발 8문항이 전부 직접형 | 변형·혼동 문항을 담은 보조 개발셋 추가 |
| 평가셋 검증에서 근거 없음 문항(X09)이 두 번 걸림 | 처음엔 "latency"라는 단어, 다음엔 투자사명 a16z의 숫자가 걸림 | 문항이 묻는 것은 측정 수치이므로 검사 패턴을 숫자+단위 형태로 좁힘(문항 내용은 변경 안 함) |
| 원문 데이터가 커밋될 뻔함 | data/index/chunks.jsonl에 소개문 전문이 있는데 gitignore에 없었음 | data/index/, data/models/를 gitignore에 추가하고 커밋 전 확인 |
| 고정 해시가 다른 환경에서 깨질 뻔함 | Windows 줄바꿈(LF->CRLF) 변환 | .gitattributes로 LF 고정, csv는 바이트 그대로 보존. 커밋될 파일의 해시가 고정값과 일치함을 확인 |
| gh CLI와 브라우저에 GitHub 로그인 없음 | 인증을 대신할 수 없음 | 브랜치는 SSH로 푸시하고, 내장 브라우저에서 직접 로그인한 뒤 PR 등록 |
| 앱의 PR 추적 연결 실패 | gh 미로그인 | PR 상태는 브라우저로 확인. CI가 없어 체크 결과 없음 |

## 7. 코드 리뷰 결과 (PR #1, 지적 9건)
| 구분 | 내용 |
|---|---|
| important 1 | 새로 clone하면 재현 절차가 폴더 없음으로 실패(build_corpus, curate_corpus, README의 curl) |
| important 2 | 재실행 시 doc_list.csv의 수집일(date.today())과 비고정 원본 때문에 고정 해시가 달라질 수 있음 |
| important 3 | freeze 검사가 chunk_map.json, 모델 잠금, 설정을 포함하지 않고 누락 파일을 조용히 건너뜀 |
| important 4 | build_index와 check_eval의 따옴표 정규화가 달라 인용이 조용히 누락될 수 있음 |
| nit 5건 | max_chars 한도가 긴 문장에서 안 지켜짐(실측 최대 917자), reranker 없이 C 실행 시 불명확한 오류, 전이 의존성 미고정, 다중 근거 문항의 Hit 과대 계산, 새 안전장치(freeze·매핑)에 테스트 없음 |

수정 결과: 9건 모두 반영함.
| 지적 | 조치 |
|---|---|
| 재현 절차 폴더 없음 | build_corpus·curate_corpus가 출력 폴더를 만들고, README 1단계에 mkdir 추가 |
| 재실행 시 해시 불일치 | 수집일과 원본 sha256을 configs/data_snapshot.json에 고정. 다른 원본이면 curate_corpus가 중단. corpus.jsonl 줄바꿈을 CRLF로 명시해 같은 바이트 재생성(고정 해시 4건 일치 확인) |
| freeze 범위 부족 | configs/final.lock.json(chunk_map, 모델 리비전, 청크 색인, 모든 설정) 추가. --final은 FREEZE와 final.lock을 모두 검증하고 파일 누락도 오류 |
| 인용 정규화 불일치 | textnorm.py 하나를 check_eval과 build_index가 공유. 매핑 실패는 비정상 종료 |
| 청킹 한도 | 공백 기준 하드 분할(chunk-v2), 최대 500자. 청크 120 -> 122개 |
| C 가드, 의존성, 다중 근거 지표, 테스트 | reranker 없으면 명확한 오류, requirements.lock.txt, full-evidence@5 추가, 안전장치 테스트 16건 추가 |

## 8. 한계와 미해결
- 개발셋 결과로 "하이브리드와 reranker가 낫다"고 결론 낼 수 없음(표본 작음). 최종셋은 한 번도 실행하지 않았고 Day 4에 한 번만 수행
- 근거 없음 문항은 검색 단계에서 걸러지지 않음. 정보 부족 판정은 Day 3 답변 단계에서 개발셋으로 정해야 함
- 문서가 짧아 기업당 청크가 1~2개 수준이라 청킹·재정렬 효과는 작을 수 있음
- 1인 수행이라 교차 채점·타인 재현·팀원 PR 리뷰는 대체 방식으로만 충족(problem.md 6절)
- PR #1은 미병합. 머지는 본인 승인 후에만 진행

## 9. 다음 단계 (Day 3)
1. PR #1 머지 승인(본인 확인 후)
2. 근거 기반 답변 흐름(근거 부족 판정을 개발셋으로 결정)과 출처 인용
3. 캐싱 또는 쿼리 리라이트 중 1개 선택·구현, 실행 인터페이스(Streamlit)
4. 최종 설정 고정(src/freeze_final.py) 후 Day 4에 고정 평가 실행
