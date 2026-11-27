# Day 3 작업일지: 근거 기반 답변·최적화·인터페이스 연결, 최종 설정 고정

- 프로젝트: VC-RAG-AGENT-Project (VC 딜소싱 RAG Agent)
- 수행 형태: 1인 수행, 코드는 Claude가 작성하고 결정·승인은 본인이 수행(바이브 코딩)
- 일자: 2026-11-27 (프로젝트 3일차 범위 기준)
- 관련 저장소: https://github.com/whatukknow/VC-RAG-AGENT-Project
- 작성 시점 기준 상태: PR #2 병합 완료(main 545c625, 2026-11-27). 병합 후 최종 고정 검증 통과. **최종 평가는 아직 실행하지 않음** (이 일지는 작성 시점 기준이며, 이후 최종 평가가 실행됐다 → [day4.md](day4.md))

## Notion 입력용 요약

**막힌 점, 고민**
- 로컬 소형 모델(Qwen2.5-1.5B)이 약속한 답변 형식을 못 지켜 정상 답변이 0건이었고(프롬프트 v1), 형식을 강제한 v2에서는 프롬프트 예시 속 가상 회사를 정답처럼 베낀 오답이 나왔으며, 4B 모델 다운로드는 20분 가까이 정체됐음
- API로 전환하려니 5.5 세대 모델은 응답 prefill과 temperature 지정이 막혀 있어 로컬처럼 결정성을 강제할 수 없고, 사전 등록한 판정 기준 (b)는 어느 구성에 적용하는지 공백이 있었음
- 개발셋이 포화되어 구성 비교가 안 되고, 코드 리뷰(고정 후 실시)에서 채점 중복 집계·비용 누락·재고정 우회가 발견됨

**해결방안**
- 모델 선택 기준을 실행 전에 problem.md에 사전 등록하고 로컬 → API(OpenAI gpt-6-luna)로 전환, 비용 한도 $5 원장과 응답 모델·요청 ID 기록으로 재현성을 보완했으며 개발셋 20문항에서 오류 0·C 16/16·근거 없음 4/4 확인
- 쿼리 리라이트(C+R)는 의도 보존 검사와 원질문 fallback을 넣어 시험(fallback 0/20, 순위 동일, 지연 +89%, 비용 +50%)하고, 리뷰 지적 important 3건을 수정한 뒤 사유·이전 해시를 남기며 재고정

**산출물 링크**
[PR #2](https://github.com/whatukknow/VC-RAG-AGENT-Project/pull/2) · [problem.md](https://github.com/whatukknow/VC-RAG-AGENT-Project/blob/main/docs/problem.md) · [src/ragagent](https://github.com/whatukknow/VC-RAG-AGENT-Project/tree/main/src/ragagent) · [app.py](https://github.com/whatukknow/VC-RAG-AGENT-Project/blob/main/src/app.py) · [final.lock.json](https://github.com/whatukknow/VC-RAG-AGENT-Project/blob/main/configs/final.lock.json) · [results](https://github.com/whatukknow/VC-RAG-AGENT-Project/tree/main/results)

## 1. 오늘의 목표 (매뉴얼 3일차)
re-ranking·답변·최적화·인터페이스 연결. 중간 결과물은 A/B/C 실행, 근거 출력, 선택한 최적화의 개발 검증, 최종 설정 고정.
(re-ranking(C)은 Day 2에 앞당겨 구현함)

## 2. 한 일
| 순서 | 작업 | 결과 |
|---|---|---|
| 1 | 근거 기반 답변 흐름 | 번호 문서 프롬프트, STATUS/ANSWER 프로토콜, 인용 검증(없는 번호 무시, 인용 없는 답 차단), 오류와 정상 "근거 부족" 분리 |
| 2 | 로컬 1.5B 실측 | v1: 60건 중 정상 답변 0 (형식 오류 41). v2: C 14/16, 근거 없음 12/12 거절, 단 예시 베끼기 오답 3건 |
| 3 | 생성 모델 API 전환 | 사전 등록 → Claude Haiku 5.5 구현(호출 안 함) → **OpenAI gpt-6-luna 확정**. 개발셋 오류 0, C 16/16, 근거 없음 4/4 |
| 4 | 쿼리 리라이트(C+R) | 구현과 개발셋 시험: 오류 0, fallback 0/20, 의도 손실 0, 허용 근거 순위 동일 |
| 5 | 채점 도구·Streamlit | 채점 시트·지표 계산, 오류와 근거 부족을 구분 표시하는 화면(검색만 보기 모드 포함) |
| 6 | 최종 설정 고정 | final.lock: 파일 해시 7, 코드 해시 17(이후 19), 설정·프롬프트 해시, 최종 백엔드 |
| 7 | 코드 리뷰 → 수정 → 재고정 | 지적 10건(important 3, nit 7), important 3건 수정, 이력 기록 후 재고정 1회 |
| 8 | 푸시·PR | feat/answer-flow 푸시, PR #2 등록(커밋 8개, 54개 파일) |

## 3. 핵심 의사결정
| 결정 | 내용 | 이유 |
|---|---|---|
| 로컬 → API | 1.5B 대신 API 생성기 | v2에서도 사전 등록 기준 (b)가 A·B에서 해당, 인용 누락 7건, 예시 베끼기 오답. 같은 생성기로 A/B/C를 비교하므로 생성기 잡음이 비교를 흐림 |
| OpenAI 선택 | Claude Haiku 대신 gpt-6-luna | 사용자가 보유한 키가 OpenAI이고, 평가셋·정답·1차 채점을 만든 쪽(Claude)과 생성 모델을 분리해 채점 편향을 줄임 |
| 사전 등록 | 모델 선택·판정 기준·C+R 시험 계획을 실행 전에 problem.md에 기록 | 결과를 본 뒤 기준을 바꾸지 않기 위함. 기준 (b)의 적용 구성 공백은 API 결과를 보기 전에 "C 기준"으로 보완 |
| 최적화 | 캐싱 대신 쿼리 리라이트 | 최종셋 20문항 C vs C+R 비교가 검색 성능과 직접 연결됨 |
| 재고정 정책 | `--force`는 `--reason` 필수, 최종 결과가 있으면 `--after-final` 필수, 이력 누적 | 결과를 본 뒤 코드를 바꾸고 다시 고정하는 우회를 막음 |
| 리뷰 범위 | important 3건만 수정, nit 7건은 제외 | 사용자 결정. 제외 항목은 problem.md에 목록으로 기록 |

## 4. 측정값 (개발용 20문항, 최종셋 미실행)
| 생성기 (프롬프트) | C 정상 답변 / 답변 가능 16 | 근거 없음 거절 | 오류 | 비고 |
|---|---|---|---|---|
| 로컬 1.5B (v1) | 0 (60건 전체) | - | 형식 오류 41 | STATUS 줄·인용 미준수 |
| 로컬 1.5B (v2) | 14 | 12/12 | 0 | 예시 속 회사 베낀 오답 3건, 인용 누락 차단 7건 |
| OpenAI gpt-6-luna (v3) | **16** | **4/4** (구성별) | 0 | 예시 베끼기 0건 |

- gpt-6-luna: 생성 시간 평균 1.20초(최대 3.0초), 요청 ID 60/60 기록, 응답 모델 ID `gpt-6-luna`
- C+R: 전체 응답 평균 C 1.31초 → C+R 2.49초(+89%), 20문항 비용 C $0.00173 → C+R $0.00261(약 +50%), 변환 질의 16/20에 "YC company" 상투어
- API 호출 102건, 누적 비용 $0.00785 / $5.00
- 테스트 141건 통과

## 5. 산출물과 근거
| 경로 | 내용 |
|---|---|
| src/ragagent/answer.py, generate.py | 답변 흐름, 프롬프트·파서 |
| src/ragagent/generate_openai.py, generate_api.py | OpenAI·Claude 생성기(비용 한도 원장) |
| src/ragagent/rewrite.py | 쿼리 리라이트와 fallback |
| src/ragagent/grading.py, src/grade.py | 채점 시트·지표, 중복 방지 |
| src/app.py, src/ragagent/view.py | Streamlit 인터페이스, 화면 로직 |
| src/freeze_final.py, src/ragagent/freeze.py, configs/final.lock.json | 최종 설정 고정과 가드 |
| results/dev, results/dev_extra | 로컬·OpenAI·C+R 실행 원본 기록, results/openai_cost_ledger.jsonl(비용 원장) |
| docs/problem.md | 사전 등록과 결과·판정 변경 기록 |

커밋: 85b2a68(답변 흐름·리라이트·채점·API), 97d1a07(OpenAI 백엔드), eeed2ba(C+R 시험), 0cff957(Streamlit), 83a6a0a(고정 강화), 107b952(최종 고정), 3928e86(리뷰 수정), acb2e54(재고정). PR: https://github.com/whatukknow/VC-RAG-AGENT-Project/pull/2

## 6. 문제와 해결 (시행착오)
| 문제 | 원인 | 해결 |
|---|---|---|
| 4B 모델 다운로드 정체 | 256MB에서 20분 가까이 진행 없음, 네트워크는 정상(다운로드 방식 쪽 정체로 추정) | 일반 HTTP로 이어받기 → 속도 1~2MB/s로 1~2시간 예상 → 1.5B로 전환 |
| 1.5B가 형식을 못 지킴 | STATUS 줄·`[n]` 인용 생략 | 프롬프트 v2(응답 미리 채우기+예시 1회 한정 개선) |
| 예시 속 가상 회사를 정답으로 출력 | few-shot 예시 베끼기(D04), 인용이 유효해 자동 검사로 못 잡음 | 사람이 내용을 읽어야 함을 확인, API 프롬프트에서 예시 제거 |
| 시간 측정 이상치 181.7분 | 27토큰 호출이 불가능한 시간, 노트북 절전으로 추정 | 원본 보존, 이상치 제외 후 평균 4.37초로 보고, 최종 평가 때 절전 방지 |
| API 제약 | 5.5 세대는 prefill·temperature가 막힘 | prefill 제거, 샘플링 값 미전송, 원본·요청 ID 기록으로 재현성 보완 |
| 사전 등록 기준의 공백 | (b)를 어느 구성에 적용하는지 불명확 | API 결과를 보기 전에 C 기준으로 보완하고 기록 |
| 코드 리뷰에서 3건 발견 | 채점 중복 집계, 리라이트·실패 호출 비용 누락, 재고정 우회 | 수정 후 재고정(이력에 사유·이전 해시), 테스트로 박제 |
| 작업 순서 실수 | 코드 리뷰를 최종 설정 고정 전에 하지 않고 고정 후에 실시함 | 최종 평가 전이라 재고정으로 처리했고 사유를 이력에 기록 |

## 7. 한계와 미해결
- 개발셋이 포화되어 구성 간 변별력이 낮고, 쿼리 리라이트의 품질 개선은 입증하지 못함(안전성·비용·지연만 확인)
- 샘플링 값을 보내지 않아 같은 입력의 출력 변동을 강제·측정하지 못함
- 정답 충족·근거 적합 채점은 아직 하지 않음(1차 채점 후 사람 확인 필요, 인용이 맞아도 내용이 틀릴 수 있음)
- 미수정 nit 7건: 비용 한도의 고정 포함, 차단된 지어냄의 거절 집계, 예외 문자열 미가공 저장, 공유 생성기 last_meta 혼선, 리라이트 첫 단어 검사 제외, 검증기 자기 잠금 불가, 스크립트 흐름 테스트 부재
- 재고정 이전의 개발셋 C+R 결과 행에는 리라이트 호출 비용이 없음(원장 기준 값이 정확)
- **최종 평가는 아직 실행하지 않음**

## 8. 다음 단계 (Day 4)
1. (완료) PR #2 병합. 병합 후에도 final.lock 검증·평가셋 해시·실행 가드 통과, 테스트 141건 통과
2. 절전 방지를 켠 뒤 최종 평가 실행(한 번만): `run_answers.py --final --backend openai --configs A B C C+R`, `eval_retrieval.py --final`. 호출 약 100건, 예상 비용 1~2센트
3. 정답 충족·근거 적합 채점(사람 확인 포함), 실패 분석(검색 누락·순위·생성·잘못된 인용·근거 없음 대응)
4. 비교 보고서, 재현 문서·발표 준비
