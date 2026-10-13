# 백엔드 책임·계약·운영 구조 구현 계획

> **구현 에이전트:** 작업별로 `superpowers:executing-plans`를 사용한다. 사용자가 병렬 위임을 선택한 경우에만 `superpowers:subagent-driven-development`를 사용한다. 이 문서는 구현·커밋을 시작하라는 지시가 아니다.

**목표:** 계약을 유지하며 내부 경계와 실행 안정성을 개선하고, 운영 확장 작업을 별도 범위로 준비한다.

**구조:** 함수 주입·그래프·RunHooks·SourceIndex를 유지한다. 필요한 업무 단위 저장소 계약과 복원 검증만 추가하고 외부 큐·DB·수치 계약 변경은 후속 작업으로 분리한다.

**기술:** Python 3.12, FastAPI, asyncio, Pydantic, typing.Protocol/TypedDict, SQLite, LangGraph, httpx/AsyncOpenAI.

**설계:** [backend-design.md](../../backend-design.md), 기준 HEAD `f7aebe6`.

**실행 상태:** 사용자 승인으로 A1~A12 구현·최종 리뷰 보완 완료. 최종697개 테스트 및 전체 검사
통과. 아래 체크리스트는 작업 계획 원문이며 완료 근거·판단·제한은
[진행 기록](../../backend-refactoring-progress.md)에 남긴다. 커밋·푸시 없음, 유료0/5회.

## 공통 제약

- A1~A12 순서로 작업한다. A9는 세 개의 독립 수정으로 분리한다. 각 항목은 별도 검토 가능한 변경 단위다.
- HTTP 응답·문구·공개 시그니처·DB 형식·schemas.py 계약 유지. 확인된 버그 수정만 예외이며 회귀 테스트 필수.
- 기존 사용자 문서·프론트엔드·validation_tool·보호된 자동화·.env 수정 금지.
- 외부 호출은 비동기, SQLite·파일 처리는 to_thread. 취소·저장 실패를 fallback으로 숨기지 않는다.
- 유료 호출·외부 API·푸시·PR 금지. 커밋은 실행 요청에서 허용한 경우만 한다.
- 단위마다 전체 검사 통과 후 다음 단계로 간다. 기존 기대값은 버그 재현 외에는 바꾸지 않는다.
- 기준 코드가 다르면 새 HEAD와 차이를 기록하고, 설계 결정을 바꾸는 차이는 질문한다.

## 리뷰에서 반드시 확인할 입력

1. 옛 context와 새 필드가 함께 존재하는 복원 자료: 기존 모드별 우선순위 유지(A4).
2. 같은 ID의 중복 실행·한쪽만 종료: 살아 있는 작업과 슬롯 보존(A2~A3).
3. 저장 직전 취소·DB 실패: 중간 상태를 성공으로 반환하지 않음(A2, A5~A6).
4. 보완 후 색인 재사용: 오래된 값으로 근거를 검증하지 않음(A10).
5. 모든 모델 근거가 제외됨: fallback에도 코드 생성 경고와 호출 기록 보존(A8).

## 공통 완료 절차

각 단계는 아래 순서로 수행한다.

- [ ] 기존 테스트로 동작을 읽고, 해당 단계의 회귀/계약 테스트를 먼저 추가한다.
- [ ] 테스트가 의도한 이유로 실패하는지 확인한다. 단순 구조 이동은 기존 테스트로 기준을 고정한다.
- [ ] 최소 구현을 작성한다. 모델 호출과 외부 네트워크는 사용하지 않는다.
- [ ] 해당 테스트와 아래 전체 검사를 통과한다.
- [ ] 바뀐 계약·파일·검증·기존 기대값 조정 여부를 기록한다. 허용된 경우에만 한국어 메시지로 커밋한다.

backend 작업 디렉터리에서:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m unittest discover -s tests
python scripts/build_industry_catalog.py --check
```

목업 흐름은 A3·A5·A7·A10·A11·A12 뒤에 확인한다. `BRIEFING_ENABLED=true`, `EVALUATORS_ENABLED=true`를 프로세스 환경변수로만 지정한다. 질문에 모름 응답 후 완료, 평가 전 실패 재시도, 평가 후 실패 재시도를 모두 검사한다. 실제 생성기 factory는 patch로 차단한다.

## A1. 계층 의존성 정리

**파일:** 신규 `app/execution/policy.py`, `app/execution/validation.py`; 수정 `services/execution_policy.py`, `services/settings.py`, `services/mocking.py`, `api/v1/mock.py`, `mocks.py`, `agents/orchestration/deps.py`, `workflow.py`, `db/repository/{requests,deliberation,evaluations,map}.py`.

**인터페이스:** 공통 `validate_timeout(value: float) -> None`, 순수 실행 정책. 기존 services import 경로는 필요한 호환 re-export로 유지한다. 목업 함수는 `app/mocks.py`로 옮기고 API의 기존 import 경로를 유지한다.

- [ ] 신규 `tests/test_dependency_boundaries.py`: 새 프로세스에서 services.mocking 직접 import 성공, 하위 계층의 services/api import 없음.
- [ ] 정책 테스트로 기존 오류 문구 유지. SQLite 예외 변환은 어댑터에서 시행한다.
- [ ] `fix: 공통 실행 규칙과 목업의 순환 의존성 제거` 단위로 검토한다.

## A2. 작업 등록·취소 소유권

**파일:** 신규 `services/jobs.py`, `tests/test_job_registry.py`; 수정 `api/v1/routes.py`, `main.py`.

**인터페이스:** `AnalysisJobRegistry`의 `start(request_id, work)`, `is_active(request_id)`, `shutdown(timeout_seconds=10)`; work는 등록 실패 시 close한다. request app state에는 registry 하나를 둔다.

- [ ] 중복 ID 거부, 오래된 작업 콜백이 새 작업을 제거하지 않음, 실패/취소 시 제거를 검사한다.
- [ ] 종료 중 신규 접수 거부, 취소 cleanup 완료까지 대기, 10초 상한 동작을 검사한다.
- [ ] 기존 events의 접수 직후 pending·재개 중 running 판정과 헤더를 유지한다.
- [ ] `fix: 분석 작업 등록과 종료 정리의 소유권 보장` 단위로 검토한다.

## A3. 모든 실행 경로에 접수 제한

**파일:** `services/jobs.py`, `api/v1/routes.py`, `tests/test_job_registry.py`; 신규 `tests/test_admission_control.py`.

**인터페이스:** registry 내부 실행 슬롯 예약 context manager. 접수 전에 예약하며 wait=false 작업과 wait=true 실행이 같은 슬롯을 소비한다. 답변/재시도 사전 검사는 기존 시점을 유지한다.

- [ ] max_concurrency=2에서 wait=true 1건+wait=false 1건 실행 중 세 번째 신규 요청은 기존 429·헤더.
- [ ] 분석·답변·재시도 모두 제한, 오류·취소 후 슬롯 반환, 동일 작업의 슬롯 이중 계산 없음.
- [ ] 이미 제출한 답과 다른 답을 wait=false로 보내면 기존 409, 실제 시작 전에 거절된 요청은 LLM/DB claim 안 함.
- [ ] 목업 전체 흐름 후 `fix: 모든 분석 경로에 공통 실행 제한 적용`으로 검토한다.

## A4. 그래프 상태와 복원 계약

**파일:** `agents/orchestration/state.py`, `graph.py`, `nodes/*.py`, `db/types.py`, `db/repository/questions.py`, `deliberation.py`; 신규 `tests/test_resume_validation.py`; 기존 `tests/test_graph_state.py` 유지.

**인터페이스:** `GraphUpdate(TypedDict, total=False)`, `validate_resume_state(state: GraphState, *, mode: AnalysisMode, retry_only: bool) -> None`. 변환 → 검증 → initial state 순서로 적용한다.

- [ ] 옛 context 우선순위, 새 상태, 잘못된 map 문자열, 음수 라운드, ID 충돌, 불완전 평가 조합 검사.
- [ ] 실행 JSON의 잘못된 budget/time/capabilities를 복원 단계에서 거절한다.
- [ ] 기존 단계별 부재가 정상인 필드까지 필수로 만들지 않는다. 손상 경로의 기존 HTTP 변환 유지.
- [ ] `refactor: 재개 상태 검증과 그래프 변경분 계약 분리`로 검토한다.

## A5. 업무 저장소 계약과 조회 타입

**파일:** 신규 `storage/{__init__,contracts,models}.py`, `db/analysis_repository.py`, `tests/test_repository_contract.py`; 수정 `services/{analysis,views}.py`, `db/repository/requests.py`.

**인터페이스:** 설계 4장의 동기 AnalysisRepositoryProtocol/get_detail/complete/claim_answers/claim_retry/load_resume. claim_answers는 bool로 선점 여부를 반환하고 load_resume는 자료를 읽는다(사용자 확정). 서비스 내부에서 기본 SQLite 어댑터를 구성하고 공개 서비스 시그니처를 바꾸지 않는다. 내부 실행 함수에만 저장소를 전달한다.

- [ ] 동일 contract 테스트를 SQLite와 기록형 대역에 적용한다. 대역이 트랜잭션 검증을 대신하지 않는다.
- [ ] 기존 상세 결과 fixture의 응답 구조·값 동일, 옛 JSON은 현재 스키마로 강제 변환하지 않음.
- [ ] 완료 저장 실패 롤백, 두 claim 중 한 건만 성공, 기존 문구와 source_attempts 보존.
- [ ] 첫 다섯 업무 외 CRUD를 미리 만들지 않는다. 나머지 직접 DB 호출은 명시적인 후속 경계로 기록한다.
- [ ] 목업 흐름 후 `refactor: 업무 단위 저장소 계약과 상세 조회 타입 정의`로 검토한다.

## A6. 서비스 책임과 진단 계약

**파일:** 신규 `services/generators.py`, `services/persistence.py`, `execution/errors.py`; 수정 `services/analysis.py`, `agents/decision/agent.py`; 신규 `tests/test_execution_diagnostics.py`.

**인터페이스:** 기존 생성기 factory의 호환 경로 유지; `DecisionExecutionError`의 원인·정제된 failures 필드. 저장 hooks는 A5 계약을 사용하며 필요한 이벤트/예산 업무 메서드만 추가한다.

- [ ] 교정 성공/실패·저장 실패·취소 모두 원래 공개 코드·문구와 진단 보존.
- [ ] 일반 예외에 동적 failures를 붙이지 않는다. CancelledError는 재포장하지 않는다.
- [ ] `_settle`·누적 활성 시간·평가 후 재시도 재사용 검증을 유지한다.
- [ ] `refactor: 실행 서비스 구성과 실패 진단 책임 분리`로 검토한다.

## A7. 전문가 실행과 도구 책임

**파일:** `agents/specialists/agent.py`, 신규 `agents/specialists/response.py`, `agents/orchestration/map_tools.py`; 수정 `orchestration/consult.py`; 신규 `tests/test_specialist_response.py`.

**인터페이스:** 모델 도구 응답을 해석하는 순수 함수, finish 내용의 부분 검증 함수. 지도 도구 구성은 map_tools로 이동하되 기존 callable/반환 계약 유지.

- [ ] 잘못된 tool-call 수·JSON 인자·finish 일부 형식 오류·등록 안 된 도구·호출 상한 검사.
- [ ] 보완/지도 채택은 변경분으로 반환, 병렬 자기 자료 소유권과 이전 동종 장소 보존 규칙 유지.
- [ ] 비교 도구 alias 제거는 모델 입력이 바뀌므로 이 단계에서 하지 않는다. 별도 효율 작업으로 기록한다.
- [ ] 목업 흐름 후 `refactor: 전문가 응답 검증과 지도 도구 구성 분리`로 검토한다.

## A8. 근거 검증과 경고 보존

**파일:** `evidence/findings.py`, `agents/specialists/agent.py`; 기존 `tests/test_specialist_context.py`, `test_specialist_agent.py`, `test_specialist_payload.py`.

**인터페이스:** validate_findings 공개 계약 유지. 내부 경로·수치·단위 검사와 경고 형식 생성 분리.

- [ ] 원자료7에 시설999대는 제외, 정상 연령30대·기간·지도 반경 허용 회귀 검사.
- [ ] 기존 형식/없음/업종 및 지도 원인·맞지 않는 수 최대3개 유지.
- [ ] 모든 근거 제외 후 fallback에도 제외 경고 전문과 tool_calls 유지.
- [ ] `_radii` 테스트를 SourceIndex.radii 기대값으로 옮기고 실행에서 미사용인 헬퍼만 삭제한다.
- [ ] 지표 의미의 뒤바뀜은 제한사항으로 기록하고 B1로 넘긴다.
- [ ] `fix: 전문가 수치 오인과 대체 브리핑 경고 누락 수정`으로 검토한다.

## A9. 계산·결측·외부 실패 회귀 수정 (세 작업)

**파일:** `agents/business_lifecycle/area_resolver.py`, `floating_population/{models,client,population,classify}.py`; 신규 `tests/test_geometry_holes.py`, `test_population_missingness.py`, `test_population_fetch_lifecycle.py`.

- [ ] A9a: 실제 SHP 방향·중첩 규칙을 확인하고 외곽·구멍·독립 폴리곤·중첩 섬 fixture로 면적을 검사한다. 단순 ring 순서 가정 금지. 채택 범위 변화는 버그 수정으로 기록.
- [ ] A9b: 사용자 확정에 따라 인구 내부 자료의 숫자 필드를 nullable로 변경한다. 빈 숫자만 JSON null로 보존하고 정상 수치는 유지한다. 집계에 해당 수치의 결측이 섞이면 합계·파생 비율은 null, 필요한 입력이 결측인 유형 판정은 보류. partial/no_data·경고·분류·실제0·문자열 null 정규화·JSON 왕복을 검사한다. 공통 schemas.py 변경 없음.
- [ ] A9c: top INFO-200 빈 응답 정상 처리, 한 병렬 fetch 실패 시 나머지 종료/정리와 client close 순서 검사. 가짜 transport만 사용.
- [ ] 각 작업을 전체 검사 후 `fix: 상권 폴리곤 구멍 면적 계산 수정`, `fix: 인구 결측과 실제 영값 구분`, `fix: 인구 자료 빈 응답과 병렬 조회 종료 처리`로 각각 검토한다.

## A10. 변경되지 않는 색인·평가 입력 재사용

**파일:** `agents/evaluators/agent.py`, `orchestration/nodes/evaluation.py`, `specialists/tools.py`, `evidence/index.py`; 신규 `tests/test_evaluation_index_reuse.py`.

**인터페이스:** 내부 PreparedEvaluationInputs에 공통 payload·sources·indexes 보관. 공개 evaluate_draft 계약은 유지하고 내부 prepared 실행을 사용한다.

- [ ] 기존 평가 입력과 채택 결과의 내용 동일; 네 평가자에 원자료별 색인 한 번.
- [ ] 보완/지도 채택 후 새 입력 생성, 오래된 값 사용 안 함; fallback도 같은 자료 색인 재사용.
- [ ] 기존 specialist_index_baseline 결과 그대로, 호출 수·토큰 내용 변화 없음.
- [ ] 목업 흐름 후 `perf: 평가 공통 입력과 근거 색인 재사용`으로 검토한다.

## A11. LLM 클라이언트 수명 관리

**파일:** `llm/client.py`, 신규 `llm/session.py`; 수정 `services/analysis.py`, `main.py`; 신규 `tests/test_llm_session.py`.

**인터페이스:** 실행 수명에 바인딩된 내부 client session. A부는 요청 실행 범위에서 같은 설정의 클라이언트를 재사용하고 종료 시 닫는다. API 서버·CLI·직접 함수 호출 모두 기존 외부 동작 유지.

- [ ] 같은 설정 호출은 재사용, 다른 키/base_url 분리, 예외·취소 시 close, 서로 다른 loop 사이 공유 금지.
- [ ] stream_options, usage 수집, budget.finish, SDK 재시도 설정·오류 코드 유지.
- [ ] 실제 네트워크 생성기를 차단한 목업 흐름 확인.
- [ ] `perf: 분석 실행 안에서 LLM 연결 재사용`으로 검토한다.

## A12. 오프라인 부하 측정과 정리 보고

**파일:** 신규 `scripts/measure_backend_load.py`, `tests/test_load_harness.py`; 수정 설계 문서에 결과 부록 추가, `backend/README.md` 단일 프로세스 제약 기록.

**인터페이스:** CLI `--scenario execution|events --concurrency 10|50|100 --db-path <임시파일>`. 실행은 ASGI+가짜 모델/API만 사용한다. 대역임을 출력에 명시한다.

- [ ] scenario는 느린 모델·외부 실패·DB 지연·취소를 포함. 이벤트 시나리오는 완료/진행 자료를 준비한다.
- [ ] 접수/완료/거절 수, 시간 분포, CPU/RSS·loop 지연·DB 잠금·가짜 호출 수를 기록한다. 임시 DB만 사용.
- [ ] 전후 같은 머신·같은 fixture·같은 환경으로 3회 실행하고 중간값 보고. 단일 ASGI 결과를 배포 처리량으로 오인하지 않음.
- [ ] 전체 검사·목업 흐름 후 파일 목록·테스트 수·계약 보존·변경 위험·남은 B부를 보고한다.
- [ ] `test: 백엔드 오프라인 부하 측정과 실행 제약 기록`으로 검토하고 멈춘다.

## B부: 별도 설계·승인 후 실행

아래는 A부에서 구현하지 않는다. 제품/계약 결정과 실측이 필요한 독립 작업이다.

| 작업 | 선행 결정 | 완료 조건 |
| --- | --- | --- |
| B1 구조화 근거·Figure | report-plan 합의, 스키마·옛 기록 호환, 실제 서버 Structured Outputs 지원 | 모델이 근거 선택, 코드가 값/단위 렌더링; 기존 경로 검증 유지; 자유 문장 숫자 우회 방지 |
| B2 영속 큐·워커·서버 DB | 신규 분석률/SLO/외부 한도, 비용·운영 담당, 제품 선택 | 전역 접수 제한·lease·원자 claim·중복 배달·워커 종료/재시도·토큰 제한·롤백 검증 |
| B3 진행 이벤트 전달 | FE 별도 범위, SSE/폴링 선택, 커서·보관기간·페이지 계약 | 재접속 누락/중복 처리, 느린 소비자·공유 pub/sub·접속 종료·폴링 부하 검증 |
| B4 공개 운영·호환 | 인증/조직 소유권·할당량·보관/삭제·캐시 버전·마이그레이션 정책 | 사용자 간 정보 격리, 비용 제한, 기존 기록 읽기, 점진 배포·복구 시험 |

B부는 이 문서의 순서표만으로 구현하지 않는다. 측정과 선택 결과를 개별 설계에 적고 실행 계획을 작성한다. 유료 비교는 사용자 별도 승인 후 1회 등 명시된 상한만 수행한다.
