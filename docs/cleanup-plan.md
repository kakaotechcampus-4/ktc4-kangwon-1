# 단일 decision 구조 정리·결함 수정 계획

기준: 사용자 지시 2026-10-14, 구조 설계 v0.4, 채점표 v0.8.
리뷰 `backend/cache/review/01-core-bugs.md`, `02-data-sql.md`,
`03-legacy-inventory.md`, `04-refactor.md` 네 개를 모두 읽었다.
리뷰의 줄 수·도달 분석은 추정이며 삭제 직전 재계산 결과를 우선한다.

## 시작 상태와 처리

- 브랜치 `feat/agentic-decision`, PR6 커밋 `9b4f7cf`.
- PR7 미커밋: 추적 파일 66개 변경, 새 파일 6개. 임의 폐기하지 않는다.
- 새 공개 API 목업 질문·답변·평가·최종 조회는 통과했던 상태다.
- 옛 API 시험은 분리 중이며 전체 검사 통과 상태는 아니다.
- B1은 새 경로 테스트를 우선 검사하여 PR7 경계를 커밋한다.
  B2의 결합 분리 중 옛 전용 테스트는 B4에서 삭제·재작성한다.
  B4 이후에는 남는 전체 unittest를 게이트로 사용한다.
- `.env`, `education_zone.py`, 프론트, 자료 DB는 수정하지 않는다.
- 추가 외부 호출 없이 임시 DB·모델 대역으로 구현한다. 실테스트는 마지막 한 번뿐이다.

## 결합 해제 순서

| 순서 | 현재 결합 | 처리 | 소비처 검증 |
| --- | --- | --- | --- |
| 1 | schemas → contracts → legacy_schemas | 공통 타입 분리 후 팀 계약 schemas에 유지, legacy 삭제 | API·도구 JSON Schema·분석 타입 동일성 |
| 2 | 새 API → routes → 옛 서비스 | jobs/errors 공개 헬퍼 추출 | wait·events·답변·오류·동시성 |
| 3 | 목업 → run_agents → 옛 그래프 | 목업 계산 자료 직접 저장·채점 | 네 평가자·외부 호출 없음 |
| 4 | 계산 import → 패키지 init → 에이전트 본체 | init 비우고 순수 함수 이동 | 앱·갱신 CLI·남는 테스트 import |

## 삭제 목록과 테스트 분류

리뷰 03의 §1·§3을 실행 목록으로 삼는다. 수집 클라이언트 세 종류와
C1 연구 스크립트·시험은 유지한다. 그래프를 다시 계산한 실제 목록은 완료 기록에 남긴다.

| 대상 | 리뷰 추정 | 처리 |
| --- | --- | --- |
| orchestration/specialists/decision/evaluators, evidence, 옛 services·storage·DB repository, 옛 분석 본체 | app 69파일·9,241줄 | 새 경로·유지 CLI 참조 없음 확인 후 삭제 |
| routes·legacy_schemas·settings·repository·혼합 계산 모듈 | 29파일·약 4,050줄 삭제 가능 | 사용하는 함수·타입을 먼저 이동 |
| 옛 전용 테스트 | 58파일·10,981줄 | 삭제 |
| legacy_app·legacy_db·orchestration_support | 3파일·108줄 | 전용 테스트와 함께 삭제 |
| 재작성 테스트 | 25파일·5,909줄 | 아래 규칙을 새 시험으로 보존 |
| 유지 테스트 | 30파일·3,546줄 + 수집 클라이언트 시험 4개 | 유지·import만 갱신 |
| collect_rubric_samples·refresh_rubric_samples·measure_payloads | 3파일·694줄 | 삭제 |
| examples | 옛 Python 8개·872줄 및 응답 자료 폴더 | run_education_zone.py만 유지 |

재작성 규칙: POST wait=false·400/502 오류·질문·답변 409/422, events 순번/상태,
작업 슬롯 용량, Site/AnalysisTask/AgentAnalysis와 새 결과 계약, 요청 ID/병렬 DB 초기화/
옛 DB 거절, 설정 경로/동시성, 질문 길이·중복, 지도 결정론 세 상태/거리,
모델 전송·완료 사유·JSON 오류, 개폐업 누락 0 보충, 주소/SHP/인구 블록/
브랜드 캐시/업종 매핑/계산/안전 로깅/부하 시험. 삭제하면서 규칙을 빠뜨리지 않는다.
fixture는 유지 테스트의 참조가 남은 것만 보존한다.

## DB

삭제: decision_results, supplement_events, map_observations, agent_briefs,
specialist_consults, evaluation_drafts, evaluations, evaluation_logs, question_sessions.
raw_*와 v_raw_*는 유지한다. agent_results는 목업 분리 후 사용처가 없을 때만 제거한다.
요청 DB 스키마 버전을 올리고 자동 이전하지 않는다. 자료 DB는 건드리지 않는다.

## 결함 수정·회귀

| 묶음 | 수정 | 회귀 기준 |
| --- | --- | --- |
| 재개 실패 | 사전 검증 밖 ValueError도 failed, DataValidationError 분리 | 질문 전 검증 오류/재개 후 오류/자료 버전 없음 |
| 병렬·예산 | 평가자 출력 예약 축소, TaskGroup, 최종 모델 두 호출 보장 | 네 명 동시 완료/저장 실패 후 잔여 취소/누적 한도 |
| 도구 경계 | SQL 큰 정수·NaN 거절/정제 감사, 제출 호출은 읽기 몫 제외, 질문 권한·단계 검사 | 잘못된 인자도 요청 유지/제출 가능/질문 금지 |
| L·반영 근거 | 공통 has_digit, 자유 문장 전수, 겹치는 요인·다른 업종 근거 거절 | 숫자·부분 중복·업종 불일치 |
| 자료 갱신 | 필수 원천·분기 묶음 검증, 체크포인트 reset/불일치 재수집, staged 정리 | 임시 자료 DB에서 이전 활성 유지·정리 |
| 공간·SQL·저장 | 비교 반경 경계, 조회 64KB, 셀 업종/분기, 뷰 대소문자/안전 함수, 인덱스/불변 트리거/초기화 버전 | 경계·격리·계보·EXPLAIN·불변 |
| 낮은 위험 결함 | 일시 오류 캐시 제외·decision 한 번 재시도, 비밀 수집/키 이름 보완, v0.8 문구 | 네트워크 없는 대역·비밀 검사 |

## 리팩토링과 이름

| 현재 | 변경 |
| --- | --- |
| storage.raw._write/_json/_hash/_now | run_in_thread/canonical_json/canonical_hash/utc_now_iso 공개 중립 함수 |
| _overlapping_areas/_aggregate/_benchmark/_age_share/_check_header/_extract_items/_aggregate_rows | 공개 계산·파싱 이름 |
| registry.py | facts.py + snapshot.py |
| runtime.py | runtime.py + advisor.py + questions.py |
| observations/reads/reviews/formatter/raw_query | map_regulation/read_tools/evaluators/inputs/sql_tool |
| services/agentic_analysis·agentic_mock | services/analysis·mock |
| api/v1/agentic | api/v1/analyses |
| agents/agentic | app/agentic, 마지막 별도 커밋 |

시각·JSON·해시·비밀 정제·읽기 전용 연결·분기 이동·백분위는 기존 규칙을 유지하며 합친다.
순환은 snapshot_config/register_fact 분리로 풀고 지연 import를 상단으로 올린다.
SQL 정규식은 추가 검사로 명시하며 AST/구조화 SQL 계약 변경은 하지 않는다.
주소 길이 가드/토큰 상수, 밀도 기준선 CSV 분리 후 408건 재현을 다시 확인한다.
미사용 필드는 API 계약·프론트 참조 확인 후에만 제거한다.

## 목표 폴더

```text
app/
  schemas.py address.py geo.py clock.py config.py seoul.py
  api/v1/analyses.py jobs.py errors.py responses.py
  services/analysis.py mock.py jobs.py settings.py
  agentic/runtime.py advisor.py questions.py evaluators.py contracts.py
          facts.py snapshot.py tools.py sql_tool.py read_tools.py
          map_regulation.py inputs.py scoring.py report.py budget.py recording.py
  local_data/  agents/계산·수집 모듈/  industries/data/  llm/  db/  storage/
  education_zone.py
```

## 프롬프트·검증·커밋

공간 요건 51업종 CSV는 reviewed=false 초안이다. fact 출처와 초안 여부를 표시한다.
L 상위 열 업종 전수 확인·unknown 이유, 소매의 설비 부재 오판 방지, 자료 조회 조건,
처음 한 번 묶음 질문, 자문 기준, 숫자 fact 슬롯, 평가자 읽기 세 번+제출을 짧게 명시한다.

| 단계 | 검증 | 커밋 |
| --- | --- | --- |
| A | git diff --check, 리뷰 전수 확인 | docs 계획 1 |
| B1 | lint/format/mypy/새 경로 unittest/catalog | PR7 1 |
| B2 | 새 경로·유지 CLI import/대역 계약·API | 결합 분리 1~2 |
| B3 | 결함별 회귀·새 경로 게이트 | 결함 1~3 |
| B4 | 재계산 import 목록, 남는 전체 게이트, 408건 | 삭제·문서 2~3 |
| B5 | 전체 게이트·408건, 명칭 마지막 커밋 별도 | 리팩토링 2~4 |
| B6 | 전체 게이트·CSV 51행·프롬프트 규칙 | 프롬프트 1 |
| 실테스트 | 홍대 공개 API 한 실행·녹화·모든 통과 기준 | 기록 1 |

운영 예산 400k/60k/40회/600초/출력16k를 유지하며 실측×1.5는 제안만 한다.
유료 실행은 모든 게이트가 끝난 뒤 한 번. 품질 미달이면 원인만 기록하고 재실행하지 않는다.
기존 로컬 build/egg-info/cache는 삭제 안내만 한다. push하지 않는다.
