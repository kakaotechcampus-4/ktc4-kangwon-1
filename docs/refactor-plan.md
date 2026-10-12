# 리팩터링 계획 — 리포트 개편 전에 정리할 것

작성: 2026-10-02 · 상태: 계획(사용자 검토 전) · 기준 커밋: `f4352c9`
출처: PR `696df81` 멘토 리뷰 7건 + 코드 점검 3갈래(그래프·서비스 / 근거·판정관 / DB·API)
관련: `docs/report-plan.md`(리포트 개편 — 이 계획 **다음**에 진행)

## 0. 원칙

1. **동작은 바꾸지 않습니다.** 리팩터링 PR은 기존 테스트(596개)가 그대로 통과해야 하고, 테스트 기대값을 고치지 않습니다. 버그 수정(1장)만 예외이며 회귀 테스트를 새로 넣습니다.
2. **계약은 건드리지 않습니다.** `schemas.py`의 공통 계약, API 응답 형태, DB 표는 그대로입니다. 바꿔야 하는 것은 리포트 개편(`report-plan.md`)에서 한 번에 합니다.
3. **PR은 작게 나눕니다.** 한 PR에 한 갈래만. 리뷰어가 "동작이 같은가"만 보면 되게 합니다.
4. **멘토가 "지금 안 해도 된다"고 한 것은 미룹니다**(Repository Protocol, SSE). 계획만 남깁니다.

---

## 1. 지금 코드에서 문제가 되는 부분 (버그·위험, 먼저 고침)

| # | 위치 | 문제 | 영향 |
| --- | --- | --- | --- |
| B1 | `db/repository.py` `fail_request`(200 vs 207), `append_event`(978 vs 983), `claim_decision_retry`(234) | 요청 ID를 UPDATE에서는 `_text()`로 정규화하고 INSERT에서는 그대로 씀 / 아예 안 씀 | 공백 섞인 ID에서 실패 기록·이벤트가 다른 키로 저장될 수 있음 |
| B2 | `db/repository.py` 756 vs 811 | `execution_json` 저장 방식이 두 곳에서 다름(`allow_nan=False` 유무) | NaN이 한쪽 경로로만 저장될 수 있음 |
| B3 | `orchestration/graph.py:387-403` vs `consult.py:279-293` | 지도 조회 실패 처리가 두 벌이고 서로 다름. 그래프는 시간 초과를 `MAP_TIMEOUT`으로 바꾸고 저장 오류를 다시 올리지 않음. 전문가 경로는 반대 | 같은 실패가 모드에 따라 다르게 기록됨. 저장 오류가 숨겨질 수 있음(AGENTS.md 3번 위반 소지) |
| B4 | `api/v1/routes.py` 200-207, 392-395, 440-445 | 예상 못 한 예외를 500으로 바꾸면서 로그를 남기지 않음(`from None`) | 운영에서 500의 원인을 알 수 없음 |
| B5 | `decision/agent.py:399` | 지도 자료를 `model_dump()`로 변환(다른 곳은 `mode="json"`) | 자료형 차이로 근거 판정이 갈릴 수 있음 |
| B6 | `orchestration/graph.py:575` | 단독 판정 모드에서 GraphState에 없는 `map_queries`를 조회 | 지금은 빈 값으로 넘어가지만, 의도와 다른 우연한 동작 |
| B7 | `services/analysis.py:165`, `routes.py:363-378` | 목업 답변 재개에 **실제** 평가자 생성기를 넘김. 재개에서는 평가자를 부르지 않아 지금은 호출 없음(확인함) | 재개 흐름이 바뀌면 목업에서 유료 호출이 나갈 수 있는 잠재 위험. 결정: `resume_analysis`에 선택적 키워드 인자 `generate_evaluators` 추가를 공개 시그니처 유지의 예외로 허용. `services/mocking.py`에서 대역을 구성하고, `retry_decision`에는 지원하는 `generate`·`generate_evaluators`만 전달하며 시그니처는 유지 |
| B8 | `db/connection.py:117` | 마이그레이션이 `schema.sql`을 `;`로 잘라 첫 문장을 `analysis_requests`로 가정 | 파일 순서·주석이 바뀌면 기존 DB 마이그레이션이 깨짐 |
| B9 | `routes.py:299` | GET 조회가 모든 예외를 500으로 바꿈(자료 불일치 `ValueError` 포함) | 손상 자료와 서버 오류가 구분되지 않음. 결정: HTTP 500·기존 응답 문구 유지, 저장 자료 손상(`ValueError`·검증·JSON 오류)은 `logger.error`, 그 외는 `logger.exception`으로 요청 ID와 함께 구분하며 예외 원문은 기록하지 않음 |

---

## 2. 멘토 리뷰 반영 항목

| 리뷰 | 판단 | 이 계획의 대응 |
| --- | --- | --- |
| ① 분석 3종 파이썬 전환 | 칭찬 | 없음 |
| ② `run_graph` 책임 과다·클로저 | **반영** | R2 |
| ③ Repository 계약 없음 | 참고 | R6에서 헬퍼 정리만, Protocol은 보류(구현이 SQLite 하나) |
| ④ `context` dict | **반영** | R1 |
| ⑤ `path.split`·`row.get` | **일부 반영** | R4(포인터 처리 한 곳으로, 지도는 모델로 검사). 분석 자료 타입화는 리포트 개편 때 |
| ⑥ 정규식 → 구조화 출력 | **리포트 개편에서 반영** | `report-plan.md` 3장 `Figure`. 지금 정규식만 걷어 내면 두 번 일함 |
| ⑦ 1초 폴링 부하 | 참고 | R8(가벼운 조치만), SSE는 보류 |

---

## 3. 리팩터링 항목

### R1. 그래프 상태 정리 (`context` dict → 타입, 이중 저장 제거) — 멘토 ④
**지금**
- `GraphState.context: dict`에 `map_observation`·`map_queries`·`feedback`·`supplement_context` 4개 키가 문자열로 쓰입니다.
- 그런데 `map_observation`·`feedback`·`supplement_context`는 GraphState 최상위 필드에도 따로 있습니다. 단독 판정은 최상위를, 멀티는 `context`를 써서 `if mode == "multi_agent"` 분기가 생깁니다(graph.py 423-425, 575).
- 전문가 도구가 `context`와 `state["analyses"]`를 **제자리에서 바꿔서**(consult.py 208-211, 278, 301), 노드가 같은 객체를 다시 돌려줘야 LangGraph가 변경을 압니다.

**바꿀 것**
- 네 값은 **GraphState 최상위 필드 한 곳에만** 둡니다. `context` 필드를 없애고 모드 분기를 지웁니다. (TypedDict로 감싸는 것보다 한 단계 더 나아가 저장 위치를 하나로)
- 저장된 재개 상태(`resume_state`)는 읽을 때 옛 `context` 키를 최상위로 옮기는 변환 함수 하나로 호환합니다.
- 전문가 도구는 상태를 직접 바꾸지 않고 **변경분을 돌려주고**, consult 노드가 그 변경분을 합쳐 반환합니다.
- 검사: mypy, 기존 테스트. `test_specialist_tools.py`·`test_map_matching.py`가 plain dict로 넘기는 부분만 새 형태로 맞춥니다.

### R2. `run_graph` 분해 — 멘토 ②
**지금**: `graph.py:130-704`, 575줄, 인자 19개, 내부 함수 19개. 노드를 단위 테스트할 수 없습니다.

**바꿀 것**
- `GraphDeps`(frozen dataclass): `address, request_id, radius_m, resolve, agents, generate, generate_specialists, generate_evaluators, supplements, map_lookup, hooks, budget, agent_timeout, mode, allow_questions, evaluators_enabled, retry_only, user_answers`.
  - 의존성 검사는 `GraphDeps.__post_init__`로 옮기고 재개 상태 검사는 `run_graph`에 둡니다. 서비스와 조건·문구가 같은 검사만 공유합니다. 문구 차이로 유지, 계약 변경 때 통일.
  - `step`, `expert_calls`, `registered`는 GraphDeps 메서드로.
- 노드는 파일을 나눠 모듈 함수로: `orchestration/nodes/`에 `analysis.py`(prepare_address, run_analyses), `decision.py`(evaluate_decision, judge, _evaluate, route), `tools.py`(execute_map, supplement_node, ask_user), `deliberation.py`(write_briefs, consult), `evaluation.py`(evaluate_draft_node). 형태는 `async def node(state, deps) -> GraphState`.
- `build_graph(deps)`가 `functools.partial(node, deps=deps)`로 연결합니다. `run_graph`는 예산 준비 → deps 생성 → 실행 → 결과 확인만 남깁니다(목표 60줄 이하). **공개 시그니처는 그대로.**
- 상수로 뺄 숫자: `EVALUATOR_RESERVE(4)`, 라운드 상한(2, +4), `< 3`, 질문 요약 길이(300), `recursion_limit(32)`, 기본 시간 초과 `180.0`(graph·consult·workflow 세 곳).
- 중복 제거: `collect`(graph 456-461) ↔ `workflow.py:187-193`, `judge`(graph 279-294) ↔ `analysis.py:529-537`, 지도 조회 실패 처리(B3에서 하나로 만든 함수 사용).
- 새 테스트: 노드 2~3개를 대역 deps로 직접 부르는 단위 테스트(이제 가능해짐).

### R3. 서비스 계층 정리 (`services/analysis.py`)
**지금**
- `execute_analysis` 173줄(인자 16개, 오버로드 2개가 시그니처 반복), `resume_analysis` 122줄, `retry_decision` 92줄. 들여쓰기 6단.
- 재개 묶음 `bundle`(키 13개)과 `execution` JSON(키 10여 개)을 문자열 키로 읽습니다.
- `resume_state` 리터럴을 두 곳(175-188, 486-502)에서 만듭니다. `execution_json`을 두 번 파싱(760, 771, 두 번째는 죽은 코드).

**바꿀 것**
- `ResumeBundle`, `ExecutionState`를 TypedDict(또는 dataclass)로 정의하고 저장소가 그 타입을 돌려주게 합니다(R6과 함께).
- `build_resume_state(bundle)` 함수 하나로 두 곳을 합칩니다.
- 세 함수의 공통 뼈대(DB 상태 확인 → 그래프 실행 → 저장 → 실패 기록)를 내부 함수로 뽑아 각 함수를 80줄 이하로.
- 목업 연결(어떤 대역을 넣을지)을 `services/mocking.py` 한 곳으로 모읍니다. 지금은 라우트 세 곳에 복사돼 있고 엔드포인트마다 넣는 대역이 다릅니다(B7 원인).

### R4. 근거 경로 처리 한 곳으로 (`evidence.py` 주변) — 멘토 ⑤ 일부
**지금**
- JSON Pointer 해석이 두 벌(`evidence.py:127` ↔ `decision/agent.py:361-374`), 이스케이프가 네 곳, "경로가 있고 업종이 맞는가" 검사가 세 곳(`evidence.py:270`, `decision/agent.py:383-389`, `evaluators/agent.py:104-105`).
- 지도 근거는 이미 `MapData` 모델이 있는데 매번 dict로 바꾼 뒤 `.get` 사슬로 검사합니다.
- `status in {"ok","partial"}` 거르기가 6곳.

**바꿀 것**
- `app/evidence/` 패키지로 나눕니다: `pointer.py`(parse·escape·resolve — 유일한 구현), `index.py`(index_paths, scalar_records, industry_catalog), `map.py`(지도 근거: **`MapData` 모델을 받아** 검사, dict 변환 없음), `findings.py`(validate_findings — 정규식은 리포트 개편 전까지 그대로 두되 이 파일에 격리).
- 공통 함수 `can_cite(source, path, industry_code) -> Reason | None` 하나를 판정관·평가자·전문가가 함께 씁니다.
- `usable_analyses(analyses)`로 상태 거르기를 한 곳에.
- 매직 문자열 상수화: `"map_analysis"`, 경고 접두어 `"전문가 근거 제외"`, 업종 행 구역 이름(`industries`·`by_middle`·`industry_results`·`industry_counts`).
- 검사: 지금 근거 관련 테스트 전부 + `can_cite` 단위 테스트.

### R5. API 라우트를 얇게 (`api/v1/routes.py`)
- `get_analysis`의 화면용 조립(평가·브리핑·JSON 해석, 252-320)을 `services/views.py`로 옮깁니다.
- 오류 변환을 `_run_or_http(work)` 헬퍼 하나로: `(RuntimeError, TimeoutError) → 502`, 그 외 → 500 + **`logger.exception`**(B4). `X-Request-ID` 헤더 생성도 여기서.
- 답변 사전 검사는 유지: wait=false에서 202 접수 전에 잘못된 답변을 409로 거르는 역할. claim_question_resume 검사와 겹쳐 보이지만 시점이 다름.
- 응답 모델 추가: events, GET 상세, 202 `{request_id, status}`. OpenAPI 문서가 실제 응답과 맞게 됩니다(프론트 타입 생성에도 도움).
- `/api/v1/health`와 `/health` 중복은 하나를 다른 하나로 위임.

### R6. 저장소 정리 (`db/repository.py`, 1026줄) — 멘토 ③ 참고
- 반복 헬퍼 추출: 요청 행 조회(5곳), "실행 중인가" 확인(6곳 + rowcount 검사), 분석 결과 차수 조회(3곳), `INSERT INTO agent_results`(2곳), JSON 저장(`_dumps` 하나로, B2), 평가자 4명 검사(2곳).
- 반환을 dict 대신 타입으로: 실패 기록·이벤트·지도 조회 상태·재개 묶음(R3).
- 비즈니스 규칙을 서비스로 이동: 재시도 가능 오류 코드(242-247), 예산·시간 검사(717-753), 라운드당 전문가 3명(894-901), 평가자 4명(771), 단독 판정 지도 1회(506-507).
- 타입 힌트가 없는 `db_path=None` 인자 정리.
- **파일 분할**: `repository/requests.py`, `results.py`, `questions.py`, `map.py`, `deliberation.py`, `evaluations.py`, `events.py`. 바깥에서는 지금처럼 `from app.db import repository`로 쓰도록 `__init__`에서 다시 내보냅니다.
- Protocol은 만들지 않습니다(③ 보류). 분할된 파일 경계가 나중에 Protocol의 단위가 됩니다.

### R7. 죽은 코드·작은 정리
- 삭제: `agents/map_analysis/schemas.py`(참조 0, 없는 `search()`를 설명), `workflow.py:143`의 안 쓰는 `_exc`, `consult.py:295`의 `getattr(hooks, "on_map_result")`(항상 있음), `analysis.py:771` 두 번째 파싱, `decision/agent.py:477-485`에서 만들고 버리는 payload.
- 테스트에서만 쓰는 저장소 함수 5개(`list_decision_results` 등)는 테스트 도우미로 옮기거나 유지 사유를 주석으로.
- 함수 안의 지연 import(`graph.py:377`, `decision/agent.py:394,487,489,512`)는 순환 참조가 아니면 위로.
- 광범위 `except Exception`(약 12곳): 외부 경계(에이전트 실행·지도·LLM)는 유지하되 `logger.exception` 추가, 내부 로직은 구체 예외로.

### R8. 폴링 부담 가볍게 — 멘토 ⑦ 참고
- events 엔드포인트가 연결을 두 번 엶(220, 232) → 한 번으로. GET 상세는 약 8번 → 한 연결에서 읽기.
- `supplement_events(request_id)` 인덱스 추가(`schema.sql`, 기존 DB는 `CREATE INDEX IF NOT EXISTS`).
- 프론트 권장값을 `API_CONTRACT.md`에 명시: 처음 1초, 10초 뒤부터 2초, 1분 뒤부터 3초. 같은 문서에 "사용자 증가 시 SSE로 전환, 이벤트는 이미 DB에 순번으로 쌓임"을 적어 둡니다.

---

## 4. 이번에 하지 않는 것 (리포트 개편 또는 이후)

| 항목 | 언제 |
| --- | --- |
| 숫자 정규식 → 구조화 수치(`Figure`) — 멘토 ⑥ | 리포트 개편 R-3 |
| 분석 3종 `data`를 타입 모델로 검사(개폐업은 모델이 없음, 상권은 `citable` 추가 키 정책 필요) | 리포트 개편과 함께 |
| Repository Protocol — 멘토 ③ | 저장소 교체·테스트 대역이 필요해질 때 |
| SSE 푸시 — 멘토 ⑦ | 동시 사용자가 늘 때 |
| 마이그레이션 버전 관리(`PRAGMA user_version`) | B8 수정 후 다음 스키마 변경 때 |
| 목업 지도에 장소 추가 | 프론트 지도 섹션 작업 때(작은 일, 언제든) |
| 분석 에이전트 오류 코드 이름 통일(`SeoulOpenAPIError` 등) | 리포트 개편 때 `API_CONTRACT` 오류 코드 표와 함께 |

---

## 5. 커밋 순서

브랜치 하나(`refactor/pre-report`, 현재 `feature/multiagent_evaluator`에서 분기)에 **아래 순서대로 커밋을 하나씩** 쌓습니다.
커밋 하나는 한 가지 일만 하고, **커밋마다 전체 검사가 통과**해야 다음으로 넘어갑니다(중간에 깨진 커밋 없음).

| # | 커밋 메시지(예) | 내용 | 위험 |
| --- | --- | --- | --- |
| C1 | `fix: 요청 ID 정규화와 실행 상태 JSON 저장 통일` | B1, B2 | 낮음 |
| C2 | `fix: 지도 조회 실패 처리를 한 함수로 통일` | B3 (그래프·전문가가 같은 함수 사용, 저장 오류는 다시 올림, 시간 초과는 `MAP_TIMEOUT`) | 낮음 |
| C3 | `fix: 예상 못 한 API 오류 로그와 조회 오류 구분` | B4, B9 | 낮음 |
| C4 | `fix: 지도 근거 변환과 단독 판정 상태 조회 정리` | B5, B6 | 낮음 |
| C5 | `fix: 목업 실행에 실제 생성기가 섞이지 않게 대역 주입 통일` | B7 + R3의 목업 연결 모음(`services/mocking.py`) | 낮음 |
| C6 | `fix: 마이그레이션이 schema.sql 문장 순서에 의존하지 않게` | B8 | 낮음 |
| C7 | `refactor: 죽은 코드와 중복 파싱 제거` | R7 | 낮음 |
| C8 | `refactor: 근거 경로 처리를 evidence 패키지로 모음` | R4 | 낮음 — 테스트가 촘촘함 |
| C9 | `refactor: 그래프 상태의 context를 최상위 필드로 합침` | R1 (옛 재개 상태 변환 함수 + 호환 테스트 필수) | **중간** |
| C10 | `refactor: run_graph 노드를 모듈 함수와 GraphDeps로 분리` | R2 (공개 시그니처 유지, 노드 단위 테스트 추가) | **중간** |
| C11 | `refactor: 재개 묶음·실행 상태 타입과 서비스 함수 분해` | R3 나머지 | 중간 |
| C12 | `refactor: 라우트 오류 변환·조회 조립을 서비스로 이동` | R5 | 낮음 |
| C13 | `refactor: 저장소 반복 헬퍼 추출과 업무 규칙 이동` | R6 앞부분(헬퍼·타입·규칙 이동) | 낮음 |
| C14 | `refactor: 저장소를 관심사별 파일로 분할` | R6 뒷부분(파일 분할, 기존 import 경로 유지) | 낮음 |
| C15 | `perf: 폴링 조회 연결 수 줄이기와 인덱스 추가` | R8 + `API_CONTRACT.md` 폴링 간격 권장 | 낮음 |

순서 이유: 버그(C1~C6)를 먼저 고쳐 회귀 테스트를 깔아 두고, 파일 이동이 적은 정리(C7·C8) → 가장 위험한 그래프(C9·C10) → 그 위의 서비스·라우트(C11·C12) → 저장소(C13·C14) 순으로 바깥쪽으로 넓힙니다.

**커밋마다 돌릴 검사**: `ruff check`, `ruff format --check`, `mypy`, `unittest discover`(596개 + 추가분), `scripts/build_industry_catalog.py --check`.
**C6·C10·C11·C14 뒤에는 추가로**: 목업 끝까지 흐름(분석 → 질문 → 답변 → 완료, 평가자·브리핑 켬) 1회.
유료 실행은 전부 끝난 뒤 한 번만(사용자 승인 후): 오금로 404로 결과·호출 수가 리팩터링 전과 같은 범위인지.

## 6. 결정 (기본값 — 바꾸려면 구현 전에 알려 주세요)
1. R1은 `context`를 없애고 최상위 필드로 합칩니다(TypedDict로 감싸기만 하지 않음).
2. R6은 헬퍼 정리(C13)와 파일 분할(C14)을 둘 다 합니다. 분할 후에도 `from app.db import repository` 사용법은 그대로입니다.
3. 구현은 다른 에이전트가 이 문서대로 합니다. 문서와 코드가 다르거나 문서가 정하지 않은 결정이 필요하면 멈추고 질문합니다.
