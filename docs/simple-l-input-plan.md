# L 입력 단순화·사전 관측 구현 계획

목표: 전체 51업종 L은 유지하고 등급·상태·원문 ID·제출 묶음 규칙을 코드로 옮긴다.
구조: 로컬 자료와 코드 사전 관측 → 코드90점 → 공간 비교 → 단순 L 입력 → 보고서
→ 작은 검토 패킷으로 평가 네 명 → 피드백 한 번. 기존 계산·저장·계보 검증을 재사용한다.
기준: 사용자 2026-10-14 지시 및 whole-industry-l-live-report.md.

## 먼저 확인한 실제 경로

| 경로 | 확인 | 영향 |
| --- | --- | --- |
| services/analysis.py execute_agentic_analysis → persist_local | education_scan을 전달하지 않음 | G는 현재 전51개 unknown. 직접 제한 관련 업종 I101/I102/R104/I211 네 개 |
| local_data/persistence.py persist_local → evaluate | 로컬 입력만 전달. 시설 조회 단계 없음 | C4 적용 G213/G215/G218/I101/P105/R102 여섯 개 unknown, 나머지45개 n.a. |
| agentic/scoring.py C4 | facilities.data.queries/places의 카테고리·최근접 거리 필요 | HP8/SC4/CT1/AT4/SW8 다섯 카테고리, 최대500m(HP8 요구300m) |

## 고정 결정·변경 범위

- .env·education_zone.py·자료 DB·프론트·보호 GitHub 파일을 수정하지 않는다. push하지 않는다.
- 외부 호출은 실제 테스트 한 회에서만. 기본자료 API·LLM 사전 시험은 없다.
- 전역400k입력/60k출력/40모델/600초/호출출력16k는 유지한다.
- 이번 측정에서 역할·단계 입력 추정 검사만 끈다. 새 상한 제안을 하지 않는다.
- 공간 요건은 추정 초안(reviewed=false/낮은 확신도)으로 채운다. 법규로 표현하지 않는다.
- 도구 계약3·요청 DB5. 기존 요청 DB는 명확한 초기화 안내, 자료 DB는 그대로 둔다.

## 설계

| 단위 | 코드·입출력 | 검증 |
| --- | --- | --- |
| 사전 조회 | services/analysis + 새 preflight 모듈. 기존 regulation/map 관측 저장 재사용. V-World1·카카오≤8. 결과를 persist_local의 data에 주입하고 같은 관측/캐시를 decision에 전달 | 성공이면 G/C4 채점에 반영, 실패 원천만 unknown/limitation. 저장 오류는 전파 |
| 공간 표 | industry_space_requirements.csv의 면적은 최소~최대㎡, 급배수 boolean. 기존 space.compare_space 재사용·필요한 명시 답변 파싱만 보완 | 범위 안 포함 일치, 범위 밖 불일치. 답변 없음 미확인. 불필요 설비 해당 없음 |
| 별칭 | 요청 DB fact_aliases에 요청·8자리 별칭·원래 fact_id 저장. 충돌 검출 후 새8자리 배정. 모델 경계에서만 별칭 노출/해석 | 다른 요청·미존재 별칭 차단. 저장·계보·최종 응답은 원래ID |
| submit_l | 업종·factors(fact_id/direction/severe)·neutral/fact_ids·note≤80. 등급·상태·LSelection·조회 기록은 코드가 구성. 상한 없이 row별 검증 | 유효 row만 채택, 중복 무시, 숫자 note 버리고 코드 설명. 거절 row별 수정법·미제출 코드 반환 |
| L 등급 | 기존 report 등급 계산을 단일 함수로 추출. 유리≥2/불리없음4, 유리1/불리없음3, 상쇄·neutral2, 불리1은1, 불리≥2/큰제약0 | 업종·새 근거·DCS중복·같은 요인 중복 검증 유지. 공간 aggregate는 방향에 맞는 확인된 component를 코드가 선택 |
| 보고서 | 입력의 별칭을 셀·문장 단위로 해석. 없는 fact 문장만 제거하고 오류/수정 알림 반환, 유효 문장은 보존 | 가짜 근거가 최종 보고서에 들어가지 않음. 숫자는 기존 renderer |
| 평가 | Top5·후보 L 요인·전체 등급분포·한계·핵심 fact(별칭)의 코드 패킷. 대화 전체/51개 L 원문 제외. 문자12k 내로 구성(토큰 추정≤6k) | 필요한 사실은 읽기 도구로 추가 조회. 세 번 후 제출 안내 |
| 평가 제출 | submit_review에는 도구/역할 예산 제한 없음. 전역 모델 안전선은 유지. fact 최대5, 잘못된 제출은 추가 두 번 수정 | 한 명 실패해도 네 슬롯. 재제출 오류가 제출 몫을 소진하지 않음 |

neutral은 확인한 새 fact가 반드시 필요하며 코드 지표만으로 중립을 만들지 않는다.
공간 전체 fact를 인용하면 favorable은 확인된 일치 항목, adverse는 확인된 불일치 항목만
선택한다. 해당 없음·미확인은 가감점 대상이 아니다. 코드가 생성한 설명은 숫자 note를 대체한다.
입력 구조 오류도 row별로 보고하기 위해 submit_l의 각 row는 handler에서 개별 모델 검증한다.
도구 JSON Schema는 정상 단순 row의 형태를 명시한다.

## 구현 순서·파일

1. [ ] 사전 관측: app/agentic/preflight.py, services/analysis.py, local_data/persistence.py 및 성공/실패 대역 시험.
2. [ ] 공간 표: industries/data/industry_space_requirements.csv, space.py, snapshot.py 및 51업종 분포 시험.
3. [ ] 계약·별칭·L: contracts.py, schemas.py, schema.sql/connection.py, aliases.py, runtime.py/report.py, tools.py 모델 경계 및 개별 채택/거절/별칭 시험.
4. [ ] 평가: evaluators.py/budget.py/tools.py, 패킷·무조건 제출·두 번 오류 수정 시험.
5. [ ] 기존 fixtures/녹화 대역을 새 입력으로 맞춘다. 전체ruff/format/mypy/unittest/catalog,408건 일치 후 구현2~4커밋.
6. [ ] 새 DB·새 녹화로 홍대 공개 API 한 회. 질문 답변 자동 재개. 실패·품질 부족이면 원인만 기록하고 수정/재실행하지 않는다.

검토 초점: 미존재 별칭·scope혼입, 원천 실패와 저장 실패 구분, 공간 요건 없음 감점 방지,
새 L 중복 요인, 평가 패킷에서 핵심 fact 누락. 각 단위 대역 시험으로 고정한다.
실테스트는 계약/최종보고서 거절0/직접L≥45/평가완료4/유효피드백1/G·C4 관측/소매설비감점0을 각각 보고한다.
