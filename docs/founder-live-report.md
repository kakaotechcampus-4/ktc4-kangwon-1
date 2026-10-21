# Founder 전용 프롬프트 실호출 관찰 기록

**실행 완료·최종 계약 통과. Founder는 거절 없이 completed·conditional, 지적 한 건을 decision이 수용했다.** 한 번의 관찰이며 전후 개선이나 일반적인 품질 향상을 확인했다는 뜻이 아니다.

## 실행 조건과 비교 기록

| 항목 | 내용 |
| --- | --- |
| 날짜·브랜치 | 2026-10-19 · feat/founder · develop c7b5f9d 기반 |
| 이전 request_id | 93143a529a414f2584fdf387f4aff150 |
| 이번 request_id | c3761a60cde14a7fad0007c40a223709 |
| 비교 기록 | [이전 성공 실행](identifier-live-report.md), 양쪽 요청 DB의 agentic_reviews·tool_calls·최종 결과·모델 녹화 |
| 주소 | 서울 마포구 와우산로 94 |
| 시험 답변 | 1층 / 약 40㎡(12평) / 이전 일반 소매, 주방·배기 설비 없음 |
| 경로 | 서버 공개 API POST → events → 질문 대기 → answers → GET |
| 접수·답변 HTTP | POST 202 / answers 202 |
| 변경 | PERSONAS[founder]의 다섯 항목·조회·조건 지적·verdict 문장만 변경 |
| 유지 | COMMON·나머지 세 persona·모델/도구/예산·패킷·코드 채점·규제 코드·자료 DB |
| 측정 | 녹화 켬, 기존과 같은 measurement=True. 새 상한 추가·기존 예산 조정 없음 |
| 실제 모델 | gpt-6-luna |
| 재실행·튜닝 | 없음 |
| 커밋·푸시·PR | 없음 |

실행마다 decision 초안·L 제출·다른 평가자의 출력도 달라진다. 고정된 초안을 대상으로 한 통제 실험이 아니므로 아래 숫자 차이를 founder 프롬프트의 인과 효과로 해석하지 않는다.

## 전체 종료 결과

- 전체 벽시계 시간 **105.829초**, 모델 **26회**, 입력 **239,256**, 출력 **12,582**.
- 공개 GET 상태 completed, DecisionResult 검증 통과. 최종 submit_draft는 첫 제출의 segment 유형 오류를 수정한 뒤 성공했다. 대체 초안 종료가 아니다.
- 평가자 네 명 모두 completed, failed 영 명. 피드백 라운드 한 회.
- founder 외에는 customer 숫자 지적 한 제출, examiner 빈 근거 한 제출, landlord_advocate 숫자 지적 두 제출이 거절됐다. 모두 같은 실행 안에서 수정·완료했다.
- decision 초안은 직접 숫자 표기와 fact 숫자 형식 오류로 두 번 거절됐고 세 번째에 채택됐다. 최종 제출도 한 번 형식 거절 후 두 번째에 채택됐다.
- 이 공통 경로·다른 역할의 거절은 관찰만 남기며 수정하지 않았다.

| 역할 | 호출 | 입력 토큰 | 출력 토큰 | 모델 시간 합(초) |
| --- | ---: | ---: | ---: | ---: |
| decision | 8 | 124,206 | 8,530 | 80.328 |
| customer | 5 | 25,574 | 1,326 | 14.983 |
| founder | 2 | 10,624 | 295 | 4.405 |
| landlord_advocate | 6 | 32,551 | 1,488 | 19.217 |
| examiner | 5 | 46,301 | 943 | 13.153 |

평가자는 병렬로 실행하므로 역할별 시간 합은 전체 벽시계 시간과 다르다.

## Founder 이전 기록과 이번 관찰

| 항목 | 이전 성공 실행 | 이번 실행 |
| --- | --- | --- |
| 최종 상태 | completed | completed |
| 최종 verdict | conditional | conditional |
| 읽기 도구 호출 | get_facts 세 회 | get_facts 한 회 |
| 일반 조회 limit=51 오류 | 두 회 | 영 회 |
| submit_review 시도 | 두 회 | 한 회 |
| 서버 거절 | 빈 근거 레코드 한 건, 제출 한 회 거절 | 영 건·영 회 |
| 최종 지적 | 세 건 | 한 건 |
| target/kind | fact/scope_mismatch 두 건, claim/factual_error 한 건 | condition/action_condition 한 건 |
| 근거 개수 | 지적별 한 개·한 개·세 개 | 두 개 |
| 미관측·인용 불가 근거 거절 | 없음 | 없음 |
| 숫자 지적 거절 | 없음 | 없음 |
| 모델 호출 | 다섯 회 | 두 회 |
| 입력·출력 토큰 | 23,617 / 1,035 | 10,624 / 295 |
| 모델 시간 합 | 13.387초 | 4.405초 |
| decision 반영 | 수용 세 건 / 일부 영 / 기각 영 | 수용 한 건 / 일부 영 / 기각 영 |

이번 founder는 Top5의 G203을 industry_code로 지정하고 source=industry_profile, metrics=[space_requirements], limit=32로 조회했다. 응답은 성공했다. 다른 업종을 각각 읽거나 같은 오류를 반복하지 않았다. 인용한 두 fact는 모두 해당 G203의 observed·citable=true이며, 각각 space_fit과 space_requirements다.

읽기·거절·토큰이 이전 기록보다 적게 관측됐지만 **초안·검토 내용·지적 수가 달라졌으므로 개선으로 단정하지 않는다.** founder persona도 85자에서 695자로 늘었으며, 호출 횟수 감소와 전체 토큰 차이를 프롬프트 길이 감소로 설명해서는 안 된다.

## Founder 실제 제출과 반영

- issue_id: founder:space-check
- 업종: G203 모터사이클·운동용품·자전거 소매
- 분류: target=condition, kind=action_condition
- 근거 fact:
  - f_f58bbfa6-4006-47e8-96e7-ef5dfba501e2 — space_fit: 면적·층 일치, reviewed=false, confidence=low, 주방·배기·급배수 n.a.
  - f_9244cf6d-f535-4296-a0f5-1f6e40588ff7 — space_requirements: 미검토 공간 요건 원문. 확인된 법규나 시설 기준이 아님.

### comment 원문

> 공간 비교에서는 면적·층이 초안 가설과 일치로 표시되지만 신뢰도는 낮고 요건 초안은 미검토 운영 가설입니다. 입점 전 현장에서 실제 사용 가능 면적, 자전거 반입·보관 및 진열 동선을 확인하고, 필요한 설비·공사 범위를 임대인과 허용 여부 및 책임까지 확인한 뒤 필요하면 견적과 관할기관의 용도·인허가 사항을 확인하세요. 초안을 확정 요건으로 보거나 해당 없음 설비를 불리하게 판단하지 않습니다.

### suggested_check 원문

> 현장 확인 후 임대인과 공사 허용·비용/원상복구 책임을 서면 확인하고, 실제 계획에 필요한 사항만 견적 및 관할기관에 확인

### decision 반영

판정은 **accepted**다.

> 추가 임대인 질문 없이 현장 확인, 공사 허용·비용·원상복구 책임의 서면 확인 및 필요한 경우 관계기관 확인을 조건에 반영했습니다.

실제 최종 G203 확인 조건:

> 현장에서 사용 가능 면적, 반입·보관 및 진열 동선을 확인하고, 필요한 공사 허용·비용·원상복구 책임을 임대인과 서면 확인하세요. 실제 계획에 필요한 용도·인허가 사항은 관계기관에 확인하세요.

초안의 G203 확인 조건은 “세부 운영 방식, 필요한 시설 및 건축물 용도를 확인하세요.”였다. 최종에는 현장 반입·보관·진열 동선, 임대인과 공사 허용·비용·원상복구 책임의 서면 확인이 구체화됐다. 반영 기록뿐 아니라 최종 후보 문장에도 나타남을 대조했다. 다만 견적 단계는 최종 문장에 명시적으로 반복되지 않아, founder 제안의 모든 단어가 그대로 반영된 것은 아니다.

## 다섯 항목·중복 관찰

| 항목 | 이번 출력에서 관찰한 내용 |
| --- | --- |
| F1 공간·운영 | 실제 면적·반입·보관·진열 확인 |
| F2 설비·공사·초기 준비 | 공사 범위·허용·비용/원상복구 책임 확인. 금액이나 손익 추정 없음 |
| F3 영업 지속성 | 개폐업 지표에 대한 별도 조회·지적 없음 |
| F4 경쟁 속 실행 전제 | 경쟁 지표에 대한 별도 조회·지적 없음 |
| F5 직접 확인 순서 | 현장 → 임대인 허용·책임 → 필요한 경우 견적·관할기관 순서 제시 |

이번에는 하나의 G203 조건 지적으로 묶어 제출했다. 나머지 후보와 F3·F4를 충분히 검토했다고 출력만으로 확인할 수 없다. 모든 문항에서 지적을 내도록 요구한 것은 아니므로, 지적이 없다는 사실 자체를 누락이나 실패로 판정하지 않는다.

중복은 공유 핵심 fact·동일 원인·동일 확인 행동을 사람이 대조했다. 이전 founder의 공간 초안 일반론과 여러 소매 후보의 초안 경고 두 건은 examiner/customer/landlord_advocate의 공간 초안·현장/용도 확인과 겹쳤다. 이번 한 건도 같은 G203 공간 초안을 출발점으로 하므로 **주제 중복은 한 건 남는다.** 다만 다른 역할은 초안의 확정 해석 금지·수요 근거 부족 등에 집중했고, founder의 현장→공사 허용·책임의 서면 확인→필요 시 견적 순서와 완전히 같은 행동 묶음은 없었다. 이는 수작업 내용 분류이며 정량 품질 척도나 일반적인 중복 감소의 증거가 아니다.

보이지 않는 초안 문장의 단정·누락을 주장하지 않았고 지적은 condition/action_condition이었다. 미확인·n.a.를 불리 요인으로 삼지 않았으며 소매업 주방·배기 부재를 불리하게 쓰지 않았다.

## Founder verdict 분포

최종 저장된 founder 평가만 센다. 수정 제출을 독립 표본으로 세지 않는다.

| verdict | 이전 실행 n=1 | 이번 실행 n=1 |
| --- | ---: | ---: |
| agree | 0 | 0 |
| conditional | 1 | 1 |
| oppose | 0 | 0 |
| failed 슬롯 | 0 | 0 |

이번 한 건은 conditional이며 결과 비율은 100%지만 표본이 하나다. action_condition만 허용한 이번 구조에서 조건 확인 지적이 제출됐다는 사실을 기록할 뿐, 조건부 쏠림을 결함이나 개선으로 판단하지 않는다.

**사용자 결정 사항:** founder를 현재처럼 입점 전 확인 조건을 만드는 역할로 유지할지, 향후 사실관계를 충분히 읽고 확인 과제가 없는 별도 표본으로 agree 경로도 관찰할지 결정할 수 있다. 이번 실행만으로 verdict 기준·상한·패킷·프롬프트는 추가 변경하지 않는다.

## 호출별 측정

순서는 모델 녹화 배열 순서이며, 결과는 대응 도구 검증 기록을 대조했다.

| 순번 | 역할 | 도구 | 입력 | 출력 | 초 | 결과 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| 1 | decision | ask_user | 7,226 | 152 | 3.125 | 성공 |
| 2 | decision | get_facts | 6,263 | 29 | 1.141 | 성공 |
| 3 | decision | submit_l | 12,058 | 1,136 | 7.75 | 성공 |
| 4 | decision | submit_draft | 18,328 | 1,012 | 11.188 | 초안 숫자 직접 표기 거절 |
| 5 | decision | submit_draft | 16,095 | 994 | 9.358 | 초안 fact 숫자 형식 거절 |
| 6 | decision | submit_draft | 17,198 | 875 | 8.625 | 성공 |
| 7 | customer | get_facts | 5,214 | 36 | 1.204 | 성공 |
| 8 | founder | get_facts | 5,591 | 36 | 1.358 | 성공 |
| 9 | landlord_advocate | get_facts | 5,226 | 36 | 1.5 | 성공 |
| 10 | examiner | get_scorecard | 5,224 | 22 | 1.593 | 성공 |
| 11 | customer | get_facts | 4,731 | 36 | 1.25 | 성공 |
| 12 | landlord_advocate | get_facts | 4,741 | 36 | 1.422 | 성공 |
| 13 | examiner | get_facts | 10,493 | 30 | 1.436 | 성공 |
| 14 | customer | get_facts | 5,151 | 36 | 1.093 | 성공 |
| 15 | examiner | get_facts | 9,369 | 39 | 1.375 | 성공 |
| 16 | founder | submit_review | 5,033 | 259 | 3.047 | 성공 |
| 17 | landlord_advocate | get_facts | 5,161 | 40 | 2.03 | 성공 |
| 18 | customer | submit_review | 5,235 | 628 | 6.077 | customer 숫자 지적 거절 |
| 19 | examiner | submit_review | 11,250 | 576 | 5.672 | examiner 빈 근거 지적 거절 |
| 20 | landlord_advocate | submit_review | 5,804 | 517 | 5.483 | landlord 숫자 지적 거절 |
| 21 | examiner | submit_review | 9,965 | 276 | 3.077 | 성공 |
| 22 | customer | submit_review | 5,243 | 590 | 5.359 | 성공 |
| 23 | landlord_advocate | submit_review | 5,505 | 469 | 4.704 | landlord 숫자 지적 재거절 |
| 24 | landlord_advocate | submit_review | 6,114 | 390 | 4.078 | 성공 |
| 25 | decision | submit_draft | 24,536 | 2,162 | 20.75 | 최종 segment 유형 거절 |
| 26 | decision | submit_draft | 22,502 | 2,170 | 18.391 | 성공 |

## 이번 최종 Top 5 — 참고

| 순위 | 업종 | L 점수 | 배지 |
| --- | --- | ---: | --- |
| 1 | G203 모터사이클·운동용품·자전거 소매 | 5 | 추천 |
| 2 | G213 문화·오락·여가용품 소매 | 5 | 보류 |
| 3 | G208 가전·정보통신장비 소매 | 5 | 추천 |
| 4 | R104 오락 서비스 | 5 | 추천 |
| 5 | G204 종합 소매 | 5 | 추천 |

이전 실행에서 R104는 L unknown·보류였고 이번에는 L observed·추천이다. founder는 점수·L을 재채점하지 않았으며, 실행마다 decision 판단이 다르므로 이 변화를 founder 프롬프트의 효과로 해석하지 않는다.

## 검증·파일·후속 범위

- 실호출 전 ruff check·format·mypy·카탈로그 검사 통과, 전체 대역 회귀498개 통과, 코드 채점408/408 동일성을 확인했다. 실호출 후 제품 코드를 바꾸지 않았다.
- 이번 결과 문서는 docs/founder-live-report.md다. 기존 변경 파일은 evaluators.py의 founder 문자열, founder-evaluator-rubric.md, prompt-change-notes.md, decision-prompt-rubric.md다.
- COMMON·다른 세 persona·계약·예산·교육환경보호구역 코드·프론트·자료 DB는 수정하지 않았다.
- 후속 과제: 검토 패킷에 초안 본문을 전달할지 결정. 현재 문장 오류·이미 있던 확인 조건의 완전한 대조는 불가능하다.
- 후속 과제: F3·F4와 나머지 Top5에 대한 검토 범위를 어떻게 드러낼지 결정. 이번에 검토 완료했다고 가정하지 않는다.
- 기존 설계 문서의 근거≤3과 현재 코드≤5, 과거 상위 열 업종 설명 등은 이번 범위에서 수정하지 않았다.
- 커밋·푸시·PR 및 추가 실행은 하지 않았다. 키·URL 원문은 보고서에 포함하지 않았다.

## 커밋 제외 실행 자료

- backend/cache/founder-live-hongdae-20261019/public-result.json
- backend/cache/founder-live-hongdae-20261019/requests.sqlite3
- backend/cache/founder-live-hongdae-20261019/c3761a60cde14a7fad0007c40a223709-model-calls.json
- backend/cache/founder-live-hongdae-20261019/summary.json
- backend/cache/founder-live-console.log

요청 DB·녹화·로그·일회성 실행/요약 스크립트는 cache 경로에만 있으며 Git 추적 대상이 아니다.

