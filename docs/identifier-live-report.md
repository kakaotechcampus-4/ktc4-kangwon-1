# 숫자 식별자 제외 후 공개 API 실테스트 · 푸시 전 점검

**실테스트 통과.** 2026-10-15 · 브랜치 feat/agentic-decision · 수정 커밋 81ed55d.
주소 서울 마포구 와우산로 94, 시험 답변은 1층 / 약 40㎡ / 이전 일반 소매, 주방·배기 없음이다. 서버 공개 API POST → events → answers → GET으로 한 번 실행했다. 재실행·프롬프트·상한 변경은 없다.

## 변경과 검증

- 공통 has_digit에서 업종 코드 형식 [A-Z][0-9]{3}[A-Z]?, f_와 8자리 16진수 별칭, 독립된 20xx분기 코드를 먼저 제거한다. 카탈로그 존재 여부는 검사하지 않는다. 12만명·30%·3곳·업종 코드와 측정값이 섞인 문장, 기존 유니코드 숫자는 계속 거절한다.
- report 세 곳, evaluators, l_input의 공통 함수 사용을 유지한다. 도구 이름은 현재 숫자가 없어 별도 예외가 필요하지 않다.
- 빈 근거 지적을 레코드별로 거절한다. 유효 지적은 재제출 동안 보존하고 오류 두 회 재제출 규칙은 유지한다. 모든 오류가 정리되기 전에는 completed로 기록하지 않는다.
- 새 검사 테스트와 혼합 지적 테스트 추가. 백엔드 전체 **497개 / 104.119초 통과**, ruff check·format(198파일)·mypy(103파일)·카탈로그 검사 통과. **408/408 동일**, 추천9/조건부1/보류377/비추천21.
- 프론트 format:check·lint·build 통과. 프론트 소스 변경 없음.

## 통과 기준

| 기준 | 결과 | 판정 |
| --- | --- | --- |
| 실제 최종 DecisionResult, 최종 제출 거절 없음 | phase=final submit_draft 성공, 대체 결과 아님 | 통과 |
| 모델 직접 L 최소45개 | 51개 채택; 최종 observed47 / unknown4 | 통과 |
| 평가자 네 명 완료·유효 피드백 한 회 | completed4 / failed0, 지적12건 수용·반영, feedback_rounds=1 | 통과 |
| G·C4 관측 | G 해당 없음51, C4 observed6 / n.a.45 | 통과 |
| 소매 주방·배기 부재 불리 채점 없음 | 소매의 adverse는 G211 면적 불일치뿐; 주방·배기 불리 채점 없음 | 통과 |

초안 첫 제출 한 회는 측정 숫자 자유 문장으로 거절됐고 다음 제출에서 수정됐다. **최종 제출 거절은 영 회**다. 평가자 네 명도 각각 빈 근거 지적 하나를 제출해 해당 레코드만 거절받았고, 보존된 유효 지적 세 개씩을 확정해 전원 완료했다.

## 실측

- 요청 ID: 93143a529a414f2584fdf387f4aff150
- 전체 시간 **85.047초**, 모델 **27회**, 입력 **227,577**, 출력 **12,488**.
- 실제 모델 gpt-6-luna. 자문 영 회.
- L 등급: 0등급0 / 1등급16 / 2등급31 / 3등급0 / 4등급0 / unknown4.
- unknown 네 업종은 공간 요건 초안에서 확인된 일치·불일치 항목이 없어 신규 근거 부족이다.
- 전역 안전선 입력400k·출력60k·40회·600초 안에 끝났다. 예산 제안·변경 없음.

| 역할 | 호출 | 입력 | 출력 | 모델 시간 합(초) |
| --- | ---: | ---: | ---: | ---: |
| decision | 7 | 103,844 | 7,769 | 61.730 |
| examiner | 5 | 45,480 | 1,312 | 13.859 |
| founder | 5 | 23,617 | 1,035 | 13.387 |
| landlord_advocate | 5 | 29,912 | 1,077 | 12.655 |
| customer | 5 | 24,724 | 1,295 | 13.858 |

평가자는 병렬이므로 역할별 모델 시간 합은 전체 벽시계 시간과 다르다. 아래 순번은 녹화 배열 순서다.

| 순번 | 역할 | 도구 | 입력 | 출력 | 초 | 결과 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| 1 | decision | ask_user | 7,238 | 184 | 7.045 | 성공 |
| 2 | decision | get_facts | 6,327 | 29 | 1.686 | 성공 |
| 3 | decision | get_scorecard | 12,114 | 41 | 1.844 | 성공 |
| 4 | decision | submit_l | 12,566 | 1,170 | 6.828 | 성공 |
| 5 | decision | submit_draft | 20,063 | 1,671 | 13.89 | 초안 숫자 거절 |
| 6 | decision | submit_draft | 18,307 | 1,666 | 10.75 | 성공 |
| 7 | examiner | get_scorecard | 5,018 | 22 | 1.11 | 성공 |
| 8 | founder | get_facts | 5,018 | 36 | 1.219 | 성공 |
| 9 | landlord_advocate | get_facts | 5,020 | 39 | 1.39 | 성공 |
| 10 | customer | get_facts | 5,008 | 36 | 1.53 | 성공 |
| 11 | examiner | get_facts | 10,327 | 36 | 1.186 | 성공 |
| 12 | founder | get_facts | 4,181 | 36 | 1.077 | 성공 |
| 13 | landlord_advocate | get_facts | 5,225 | 39 | 1.28 | 성공 |
| 14 | customer | get_facts | 4,564 | 36 | 1.25 | 성공 |
| 15 | examiner | get_facts | 9,602 | 36 | 1.219 | 성공 |
| 16 | founder | get_facts | 4,294 | 37 | 1.296 | 성공 |
| 17 | landlord_advocate | get_facts | 6,160 | 39 | 1.204 | 성공 |
| 18 | customer | get_facts | 4,994 | 36 | 1.094 | 성공 |
| 19 | founder | submit_review | 5,145 | 509 | 4.265 | 빈 근거 지적만 거절 |
| 20 | landlord_advocate | submit_review | 7,008 | 529 | 5.078 | 빈 근거 지적만 거절 |
| 21 | customer | submit_review | 5,060 | 655 | 5.704 | 빈 근거 지적만 거절 |
| 22 | examiner | submit_review | 10,803 | 688 | 6.235 | 빈 근거 지적만 거절 |
| 23 | landlord_advocate | submit_review | 6,499 | 431 | 3.703 | 성공 |
| 24 | founder | submit_review | 4,979 | 417 | 5.53 | 성공 |
| 25 | examiner | submit_review | 9,730 | 530 | 4.109 | 성공 |
| 26 | customer | submit_review | 5,098 | 532 | 4.28 | 성공 |
| 27 | decision | submit_draft | 27,229 | 3,008 | 19.687 | 성공 |

## Top 5 변화

L 반영 전:

| 순위 | 업종 | 하한/적용 배점 | 배지 |
| --- | --- | ---: | --- |
| 1 | G203 모터사이클·운동용품·자전거 소매 | 63.125/90 | 추천 |
| 2 | G213 문화·오락·여가용품 소매 | 57.5/100 | 보류 |
| 3 | G208 가전·정보통신장비 소매 | 55.625/90 | 보류 |
| 4 | R104 오락 서비스 | 55.625/90 | 보류 |
| 5 | R102 독서실·유사 여가시설 | 51.25/100 | 보류 |

최종:

| 순위 | 업종 | 코드 /90 | L /10 | 하한/적용 배점 | 배지 |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | G203 모터사이클·운동용품·자전거 소매 | 63.125 | 5 | 68.125/90 | 추천 |
| 2 | G213 문화·오락·여가용품 소매 | 57.5 | 5 | 62.5/100 | 보류 |
| 3 | G208 가전·정보통신장비 소매 | 55.625 | 5 | 60.625/90 | 추천 |
| 4 | R104 오락 서비스 | 55.625 | unknown | 55.625/90 | 보류 |
| 5 | G204 종합 소매 | 48.75 | 5 | 53.75/80 | 추천 |

G208은 L 반영으로 보류→추천, G204는 Top 5 진입, R102는 제외됐다. R104는 L unknown을 유지해 보류다.

## 평가 피드백과 남은 품질 한계

| 역할 | 완료 | 지적 | 유효 반영 |
| --- | --- | ---: | --- |
| examiner | completed | 3 | 공간 초안의 저신뢰도·범위, 전체 후보의 현장 확인, R104 근거 부족 설명 |
| founder | completed | 3 | 초안을 확정 요건으로 단정하지 않음, 소매 주방·배기 n.a. 유지, 운영 형태 확인 |
| customer | completed | 3 | 반입·보관·진열·상담·재고와 실제 동선 확인 조건 |
| landlord_advocate | completed | 3 | 가설과 현장 조건 구분, 층·면적 일치를 확정 적합성으로 단정하지 않음 |

반영 기록 열두 개 모두 accepted이며 실제 최종 보고서의 한계·후보별 확인 조건에 반영됐다. 다만 **R104의 저장 상태는 unknown인데 보고서·반영 설명에서 “중립 처리”라고 부른다.** 중립 observed2로 채점한 것은 아니다. 계약 통과와 별개인 표현 품질 문제로 기록하며 추가 수정·재실행하지 않았다. 공간 요건 CSV는 사람 미검토 초안이고 일반화된 추천 정확도는 이번 한 주소로 검증하지 않았다.

## 푸시 전 점검

| 항목 | 결과 |
| --- | --- |
| a 작업 트리·실데이터 | 수정 커밋 뒤 clean; 기록 문서 커밋 후 다시 확인. cache·storage 실데이터·DB·녹화 추적0 |
| b 비밀 | 실제 .env 추적0, 환경변수의 키·토큰·비밀·암호 값 추적 파일 발견0; 값 출력 없음 |
| c 금지 GitHub 파일 | origin/develop 대비 .github diff0 |
| d education_zone.py | origin/develop 대비 diff0 |
| e 프론트·대용량 | frontend diff0; 새5MiB 초과 파일0 |
| f CI·회귀 | 백엔드 전체497개 및 정적 검사·카탈로그·408건 재현 통과; 프론트 세 검사 통과 |
| g 원격·충돌 | fetch 후 origin/develop 뒤0 / 수정 커밋 시점 앞61, develop은 조상; 병합·리베이스 없음 |

기록 커밋까지 **원격에 없는62개 커밋**이 올라갈 예정이다. perf/decision의 develop 이후15개 커밋을 포함한다. 앞쪽 커밋은 6818746(문서 정리), 50855ab(유동 기준선), f9e326f(51업종), 2e45967(누락0), 6aa2f64(develop merge)이다.

문서의 feature/* 규칙 대신 사용자가 지정한 feat/agentic-decision을 유지한다. 과거 커밋 6aa2f64의 merge:는 허용 type 목록 밖이며 재작성하지 않았다. 다른 업로드 대상의 커밋 유형은 허용 목록 안이다.

푸시는 모든 점검 통과 뒤 **git push -u origin feat/agentic-decision** 한 번만 수행한다. 다른 브랜치·강제 푸시·PR 생성·병합은 하지 않는다. 실제 원격 해시 일치는 푸시 후 채팅에 보고한다.

## 커밋 제외 자료

- backend/cache/identifier-live-hongdae/public-result.json
- backend/cache/identifier-live-hongdae/requests.sqlite3
- backend/cache/identifier-live-hongdae/93143a529a414f2584fdf387f4aff150-model-calls.json
- backend/cache/identifier-live-hongdae/summary.json
- backend/cache/identifier-unittest.log
- backend/cache/identifier-push-audit.json

녹화·원자료·일회성 실행 및 점검 스크립트는 커밋하지 않는다.

