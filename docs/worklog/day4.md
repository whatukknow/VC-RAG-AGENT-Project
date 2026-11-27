# Day 4 작업일지: 최종 평가 실행, 채점, 보고서, 재현 점검

- 프로젝트: VC-RAG-AGENT-Project (VC 딜소싱 RAG Agent)
- 수행 형태: 1인 수행, 코드는 Claude가 작성하고 결정·승인은 본인이 수행
- 일자: 2026-11-27
- 관련 저장소: https://github.com/whatukknow/VC-RAG-AGENT-Project
- 상태: PR #3 병합 완료(main `9664032`), 제출 태그 `ax1-project3-submit`

## Notion 입력용 요약

**막힌 점, 고민**
- 모든 구성이 최종셋 천장(17/17)에 걸려 구성 우열을 가릴 수 없었고, 규칙 기반 채점은 문구 차이를 오탐(10~12/17)해 정확도로 쓸 수 없었음
- 새 폴더 재현 점검에서 깊은 임시 폴더의 경로 길이(260자)로 torch 설치가 실패했고, README에 로컬 생성기 3GB 다운로드·PowerShell 비호환 명령이 있었음

**해결방안**
- 정답 충족을 의미로 1차 판정(Claude)한 뒤 17문항 전체를 본인이 직접 확인해 유지하고, 한계(천장 효과, 소표본, 같은 쪽이 만든 정답표)를 보고서에 그대로 기록
- 짧은 경로에서 재설치해 해시·잠금·테스트·개발셋 검색 10/10·OpenAI 답변 상태·인용 10/10 일치를 확인하고 README 결함 3건 수정

**산출물 링크**
[PR #3](https://github.com/whatukknow/VC-RAG-AGENT-Project/pull/3) · [report.md](https://github.com/whatukknow/VC-RAG-AGENT-Project/blob/main/report.md) · [contributions.md](https://github.com/whatukknow/VC-RAG-AGENT-Project/blob/main/contributions.md) · [results/test](https://github.com/whatukknow/VC-RAG-AGENT-Project/tree/main/results/test) · [problem.md](https://github.com/whatukknow/VC-RAG-AGENT-Project/blob/main/docs/problem.md)

## 1. 한 일
| 순서 | 작업 | 결과 |
|---|---|---|
| 1 | 최종 평가 실행(구성별 1회) | A/B/C/C+R 답변 + A/B/C 검색, 오류 0, 비용 $0.00795 |
| 2 | 1차 채점 | Claude 의미 판정 → 17문항 전체 직접 확인, 판정 유지 |
| 3 | report.md 초안, contributions.md | 12절 체크리스트로 남은 항목 관리 |
| 4 | 새 폴더 재현 점검 | 해시·잠금·테스트·검색·답변 일치, README 결함 3건 수정 |
| 5 | 발표 자료 10장 | 비공개 아티팩트, 시연 시나리오 포함 |
| 6 | 시연 실행 확인 | T11 정상 답변, T18 근거 없음 거절, C와 C+R 답변 동일(검색 상위 5개만 다름) |
| 7 | PR #3 병합, 제출 태그 | main `9664032` |

## 2. 핵심 결과(최종셋 20문항)
- 모든 구성이 사전 성공 기준 충족: Hit@5 17/17, 근거 없음 거절 3/3, 오류 0
- MRR A 0.819 < B 0.971 < C 1.0, 정답 충족 A·B·C 16/17, C+R 17/17(T03 한 문항)
- C+R은 비용 +56%, 지연 +125%에 품질 이득 미입증 → 최종 선택은 C

## 3. 한계와 미해결
- 천장 효과로 구성 우열을 통계적으로 가릴 수 없음, 20문항 소표본
- 근거 적합(인용 대조)은 직접 대조하지 않음
- 출력 변동 미측정, 평가셋은 단일 문서 사실 질문 중심
- 재현 점검은 같은 사람·같은 PC에서 한 것(타인 재현 아님), 1단계 원본 데이터는 매일 갱신되어 시간이 지나면 같은 파일을 못 받을 수 있음
- 미수정 nit 7건과 리라이트 상투어
