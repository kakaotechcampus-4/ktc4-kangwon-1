# Agentic decision 구조 설계안 v0.3

작성: 2026-10-13 · 개정: 2026-10-14 · 설계 작업: perf/decision · 구현 통합 브랜치: feat/agentic-decision · 상태: 단일 모드 전환 결정, 코드 미적용.
기준: [채점표 v0.8](decision-prompt-rubric.md)의 **확정 규칙**. 로드맵: 51업종 완료 → 채점표 완료 → **3 구조 설계** → 4 구조 구현 → 5 decision 프롬프트 → 6 평가자 4명 → 7 실테스트·효율화.

사용자가 확정한 흐름·SQL 방식·fact_id·L 역할은 고정한다. schemas.py의 팀 공통 계약 교체는 PR1에서 팀 합의한다. 도구 계약은 app/agents/agentic/contracts.py로 분리한다. 초기 예산·CSV 원천·평가 실패 제공 정책은 사용자 결정으로 확정했으며 실테스트 후 조정한다. v0.3 개정은 문서만 수정하며 외부 API·LLM 호출은 없다. 5절 연결 확인은 과거 실행 기록이다.

## 1. 한 장 요약

```text
주소 → 주소 변환 → 분석 3종 병렬 수집 [상권 / 개폐업 / 인구(유동·직장·상주)]
                  ↓ 수집 직후, 정규화·업종 매핑으로 버리기 전에 저장
             SQLite 원문 응답·원문 행·출처/범위/기간
                  ↓ 결정론적 계산·formatter·v0.8 코드 채점 90점
             SQLite 계산 facts·scores·스냅샷
                  ↓ 요청/스냅샷 참조만 전달
             decision: 고정 시스템 프롬프트 + 조회 도구
                ├ 계산 자료 먼저 → 필요 시 읽기 전용 원문 SQL
                ├ 지도·규제 읽기 / 임대인 질문
                └ 애매할 때만 보조 LLM 자문(다른 계열 권장)
                  ↓ decision 단독 L 10점 판단 + 초안 저장
             평가자 4명 병렬: 심사관 / 창업자 / 고객 / 임대인 편
                  ↓ 같은 읽기 도구로 독립 검토 → 구조화 피드백
             decision: 수용·일부·기각 기록 → 최종 제출
                  ↓ 코드가 점수·숫자·배지·Top 5 검증/렌더링
             SQLite 최종 저장 → 새 DecisionResult GET/진행 이벤트 → 새 리포트 화면
```

| 지금 | 목표 | 현재 근거 |
| --- | --- | --- |
| single_decision은 분석 JSON, multi_agent는 digest·브리핑·되묻기를 입력에 포함 | 처음에는 요청·스냅샷·예산만, 사실은 도구로 조회 | `backend/app/agents/decision/agent.py:508`, `context.py:50`(같은 decision 디렉터리) |
| 3개 브리핑 → 분야별 전문가 되묻기 | 자동 브리핑 제거, decision 주도 도구 + 선택적 자문 1역할 | `backend/app/agents/orchestration/graph.py:40`, `nodes/deliberation.py:43` |
| 평가자는 초안·digest·원자료 경로를 받음 | 초안·인용 fact_id 목록만 받고 같은 조회 도구로 확인 | `backend/app/agents/evaluators/agent.py:62`, `agent.py:89` |
| SQLite agent_results는 계산된 AgentAnalysis JSON 저장 | API 업무 원문과 계산 결과·계보를 분리 | `backend/app/db/schema.sql:43`, `backend/app/services/persistence.py:50` |
| {i} 자리표시자·agent/path 검증·원본 값 렌더링 | 구조화 fact 슬롯과 불변 fact_id, 같은 요청·버전 검증 | `backend/app/evidence/citations.py:36`, `backend/app/agents/decision/agent.py:383` |

현재 실행 상한은 그래프 재귀 32·분석별 timeout 180초, 전문가 초기 2라운드/평가 후 4라운드, 모델 호출 24회 또는 평가 포함 64회·최종 예약 2회다(`backend/app/agents/orchestration/constants.py:3`, `backend/app/llm/budget.py:16`). 서비스 전체 timeout 기본은 평가 없음 600초·있음 1,200초이며 기존 질문 대기 제외 누적을 재사용한다(`backend/app/execution/settings.py:50`, `backend/app/services/analysis.py:466`). 새 제안 상한과 현재 값을 혼동하지 않는다.

### 현재 코드 분류

새 구조는 유일한 실행 경로다. PR7 전환 시 기존 모드·근거·저장 결과를 폐기하며 과거 결과·질문 세션을 읽는 코드는 만들지 않는다. 평가자 4명은 항상 실행한다. 개발 비용은 MOCK_MODE와 예산 상한으로 관리한다.

| 구분 | 현재 코드·위치 | 단일 모드 전환 범위 |
| --- | --- | --- |
| 재사용 | `backend/app/agents/orchestration/graph.py:40` | LangGraph·주소·분석 3종 병렬·질문 대기/재개 기반. 새 단계로 연결 |
| 교체 | `backend/app/agents/orchestration/deps.py:50`, `state.py:43` | 모드별 deps/state를 snapshot·draft·review 참조 및 actor별 예산으로 교체 |
| 재사용/확장 | `backend/app/execution/policy.py:38`, `backend/app/llm/budget.py:16` | 예약 호출·실패 전파·저장 오류 유지, 도구/토큰/HTTP 상한 추가. 모드·평가 활성 스위치 제거 |
| 교체 | `backend/app/agents/decision/agent.py:113`, `orchestration/nodes/decision.py:33` | 행동 JSON(final/ask_specialists/supplement/map_lookup/ask_user) 판정을 도구 루프로 교체. 질문 기능은 ask_user 도구로 재사용 |
| 삭제 | `backend/app/agents/decision/context.py:64`, `agent.py:508` | 전체 분석·digest·브리핑 context 삽입 제거. 고정 지시문·도구 스키마·최소 참조만 입력 |
| 삭제 | `backend/app/agents/specialists/` 전체, `orchestration/nodes/deliberation.py:43`, `orchestration/consult.py` | 브리핑·전문가 자문·ask_specialists·브리핑 그래프 분기 제거. 보조 에이전트는 별도 자문 도구로 구현 |
| 재사용/교체 | `backend/app/agents/map_analysis/client.py:52`, `agent.py:254` | PlaceClient·비동기 카테고리 검색·거리 계산 재사용. 지도 판단 agent 경로를 결정론적 map_search로 교체 |
| 삭제 | `backend/app/agents/map_analysis/mapping.py:64`, `prompt.md` | judge_matches·GenerateMapping·LLM 판정·모델별 mappings 캐시 제거. 장소 API 응답 캐시는 재사용 가능 |
| 교체/재사용 | `backend/app/agents/orchestration/supplement.py:39` | 기존 supplement 행동 분기 제거. 부분 자료·실패 상태·재계산 처리는 서비스에서 재사용 |
| 교체/재사용 | `backend/app/agents/evaluators/agent.py:175`, `orchestration/nodes/evaluation.py:18` | 4역할·병렬·실패 격리 유지. digest/path 입력·추가 행동 요청 대신 fact 기반 읽기 도구 검토, 항상 실행 |
| 삭제/이관 | `backend/app/evidence/citations.py:36`, `index.py:58`, `pointer.py` | agent/path 인용·{i} 렌더링 삭제. 업종 소유·citable·단위 검증 원칙만 fact registry로 이관. 원문 내부 계보 field_pointer는 인용 계약이 아님 |
| 교체/재사용 | `backend/app/db/schema.sql:3`, `repository/results.py:27`, `questions.py:162`, `evaluations.py:21` | 요청·저장 트랜잭션 기반 유지, 새 스키마로 생성. 구 결과·질문 reader와 보존 마이그레이션 없음 |
| 교체/재사용 | `backend/app/services/analysis.py:215`, `persistence.py:50`, `views.py:16`, `mocking.py:18` | 재개·목업·GET 조립을 새 계약으로 교체. 모드 dispatch·과거 응답 분기 제거 |
| 재사용/이관 | `backend/scripts/rubric_dryrun.py:72`, `:322`, `:404` | 순수 채점 엔진 운영 이관. CLI·민감도·표본 수집은 scripts 유지 |
| 재사용 | `backend/app/agents/commercial_area/industries.py:23`, `metrics.py:92`, `business_lifecycle/formatter.py:163` | 51업종 매핑·결정론적 지표·한국어 formatter 유지 |
| 유지/교체 | `backend/app/schemas.py:80`, `:94`, `:257`, `:486`, `:504`, `:570`, `:680` | AnalysisTask/AgentAnalysis 유지. DecisionRequest/DecisionResult/Evidence/QuestionSnapshot 교체, V2 접미사 없음 |
| 교체 | `docs/API_CONTRACT.md:224`, `backend/app/api/v1/responses.py:29` | URL·폴링 seq 기반 재사용, 새 결과·질문·stage 계약만 제공 |

현재 상주·직장은 동봉 CSV를 사용한다(`backend/app/agents/floating_population/population.py`). source_type=file·파일 해시·시점을 원문에 보존한다.

### 삭제 목록과 설정 정리

| 대상 | 전환 작업 |
| --- | --- |
| 모드·브리핑 | graph.py의 mode 분기, execution/settings.py:69~76의 스위치, specialists 호출 포트·서비스 생성기·브리핑 DB 저장/조회·목업 삭제 |
| 옛 근거·결과 | agent/path Evidence·EvidenceRef, {i} 렌더러와 관련 fixtures·검증 tests, 기존 질문 snapshot V2 및 구 결과 reader 삭제/교체 |
| 지도 숨은 LLM | mapping.py·prompt.md·generate_mapping/mapping_cache_path 주입, cache/map_mappings.sqlite3의 mappings 캐시 사용 경로 제거. 파일 정리 방법은 PR7 초기화 안내에 포함 |
| 지도 테스트 | test_map_mapping.py의 LLM·모델/프롬프트 캐시 테스트 제거/대체. test_map_matching.py의 유효한 검색·거리 테스트는 유지하고 category_match/name_match/unknown 회귀 검증으로 교체 |
| 환경변수 삭제 | ANALYSIS_MODE, BRIEFING_ENABLED, EVALUATORS_ENABLED, SPECIALIST_*_LLM_*, MAP_MAPPING_LLM_* |
| 모델 설정 유지 | ELICE_* 공통, DECISION_LLM_*, EVALUATOR_LLM_*, ADVISOR_LLM_*. 공통 옵션 LLM_*와 MOCK_MODE·API 인증·비용 상한은 유지 |

실제 파일·환경변수 삭제는 PR4/PR7에서 수행한다. 이번 문서 개정은 코드·.env·schemas.py를 수정하지 않는다.

## 2. 데이터 저장 설계(SQLite)

PR2에서는 기존 테이블을 유지하며 원문 테이블·뷰만 추가한다. 실행 결과·decision 입력은 바꾸지 않는다. PR7에서는 기존 DB를 자동 변환하지 않고 스키마 버전 검사·명시적 초기화 안내로 새 구조에 전환한다. 1차는 요청당 원문 snapshot_id **1개**를 유지한다. run_id·분석/판단 attempt는 실행·재개 기록이며 새 원문 스냅샷을 만들지 않는다. 부모 스냅샷·기초 자료 재수집은 2차로 미룬다. 원문은 매 페이지 수집 직후 저장하고 모든 수집이 끝나야 계산하는 강제 장벽 대신, 수집 완료/부분 스냅샷을 명시한 뒤 계산한다.

| 테이블 | 핵심 필드·키 | 규칙 |
| --- | --- | --- |
| raw_responses | response_id PK, request_id, run_id, snapshot_id, source, source_type(api/file/user), request_args_json, page, http_status, response_json, collected_at, payload_hash | 업무 응답 원문 보존. 인증 키·Authorization·Referer 인증 설정은 저장하지 않음. 캐시 원천·수집/캐시 시각 구분 |
| raw_rows | raw_row_id PK, response_id FK, row_index, natural_key, raw_json | 매핑 제외 업종·소분류도 원문에는 보존. 자연키 중복·수집 누락을 표시하고 임의 합산 금지 |
| snapshots | snapshot_id PK, request_id, run_id, base_source_manifest, completeness, source_periods, created_at | 요청당 1개. 기초 수집 완료 후 기준선·프로필·catalog·원천 해시 고정. 지도·규제·답변 관측은 같은 snapshot에 append-only 추가, 기존 행·fact는 덮지 않음 |
| facts | fact_id PK, request_id, snapshot_id, source, metric, value_json, unit, period, spatial_scope_json, industry_code(nullable), citable, status, calc_version, baseline_version, lineage_hash, created_at | 숫자·문자·관측 여부도 typed fact. unknown은 null·citable=false, 관측 0과 구분 |
| fact_sources | fact_id FK, raw_row_id FK, field_pointer | 원문 행/열 계보. 집계는 여러 행을 연결, 출력에는 개수·해시·조회 참조만 보내 토큰 절약 |
| scores | score_id PK, request_id, score_snapshot_id, rubric_version, industry_code, item, status, grade(nullable), points(nullable), fact_ids, created_at | 코드 90점은 불변 snapshot. L은 draft/revision별 별도 score_snapshot으로 추가. 이전 결과 UPDATE 금지. score_snapshot_id는 논리 점수 revision이며 새 원문 snapshot이 아님 |
| tool_calls | call_id PK, request_id, run_id, actor, phase, tool, normalized_args_hash, snapshot_ids, outcome_ref, status, error_code, duration_ms, http_calls, model_calls, input/output_tokens | 결과 본문은 참조 저장, 키·원시 인증 오류 URL 로깅 금지. 동일 조회 감지·실제 예산 근거 |
| advisor_consults | consult_id PK, call_id FK, question, fact_ids, advisor_model/family, answer_json, reflected, reason | 자문은 새 사실이나 L 점수로 간주하지 않음 |
| evaluator_reviews | review_id PK, draft_id FK, actor, status, review_json, tool_call_ids, created_at | 4명 각각 보존. 실패는 동의가 아님 |
| reports | report_id PK, request_id, run_id, kind(draft/final), revision, parent_id, report_json, fact_ids, score_snapshot_id, validation_status, rendered_json | 초안·최종과 번호별 피드백 반영 로그 연결. final만 완료 응답으로 채택 |

analysis_mode 열·CHECK·모드 dispatch는 새 스키마에 두지 않는다. DB 스키마 버전을 올리고 기존 파일의 버전이 다르면 시작을 중단해 파일 경로·기대/실제 버전·초기화 방법을 안내한다. 실행기가 자동 삭제·변환하지 않는다. 운영자가 서버를 멈추고 SQLITE_PATH 파일을 명시적으로 삭제 또는 이동한 뒤 재시작하면 새 DB를 생성한다. 옛 결과·질문 세션은 폐기하며 구 파일을 읽는 reader를 구현하지 않는다.

analysis_requests·agent_results·decision_results·question_sessions·analysis_events의 역할은 새 스키마에서 재사용하되 옛 행을 복사하지 않는다(`backend/app/db/schema.sql:3`, `:27`, `:43`, `:145`, `:163`). 사실 저장·호출 감사·최종 채택 실패는 서비스 오류로 전파한다. 진행 화면 이벤트의 저장 실패만 기존처럼 격리한다(`backend/app/services/persistence.py:36`).

| 조회용 뷰 | 원천·핵심 열 | 공간·기간 |
| --- | --- | --- |
| v_raw_stores | raw_row_id, response_id, store_id, 소진공 원 대/중/소분류, lat/lon, 주소 | 수집 반경·시점 유지, 서비스 업종 코드는 매핑 버전과 함께 별도 노출 |
| v_raw_lifecycle | raw_row_id, 상권 코드, quarter, 서울 업종 코드, 점포/개업/폐업 수 | 선택 상권 포함/최근접·거리 유지. 누락 행을 원문 0행으로 생성하지 않음 |
| v_raw_floating | raw_row_id, 상권 코드, quarter, 시간대/요일/연령 원값 | 반경 선택된 공식 상권 집합 명시 |
| v_raw_resident / v_raw_worker | raw_row_id, 상권 코드, quarter, 연령 원값 | 현재 CSV source_type=file·파일 해시 명시 |
| v_raw_map / v_raw_regulation / v_raw_answers | raw_row_id, 관측/구역/답변 필드 | 실제 조회 시각·출처·사용자 진술 구분 |

fact_id는 `f_<UUID>`이며 값·계보가 바뀌면 새 ID다. 1차의 추가 관측은 같은 원문 snapshot 안에서 새 fact로 등록한다. 보고서·호출마다 fact_ids와 observation cutoff seq를 기록해 당시 사용 범위를 재현하며, 스냅샷 부모 체인은 만들지 않는다. request·snapshot·metric·단위·기간·범위·업종·계산 버전·lineage가 같은 경우만 중복 등록을 피한다. 모델이 ID를 정하거나 값·citable을 쓰지 않는다. 요청 밖 fact, 현재 보고서의 비채택 관측 fact, 폐기된 draft fact는 제출 시 거절한다. 코드 점수의 fact_ids와 L 새 근거의 중복은 기계 검사하고, 의미상 같은 요인의 중복은 평가자가 검토한다.

기초 API 응답 수집 hook은 파싱·필드 축소 전 transport 계층에 추가해야 한다. 현재 상권 캐시는 items를 추리고 SQLite에는 formatter 결과를 저장하므로 이를 원문 저장으로 간주하지 않는다(`backend/app/agents/commercial_area/client.py:82`, `backend/app/services/persistence.py:50`). API·파일은 asyncio 기반, SQLite·SHP·CSV는 asyncio.to_thread. 현재 rw 연결(`backend/app/db/connection.py:23`)을 query_raw에 그대로 노출하지 않는다.

## 3. 도구 계약

### 공통 입출력·권한

도구 버전은 `agentic-tools/1`(1차 단일 SELECT, CTE 미지원). 시스템 프롬프트와 도구 스키마는 버전별 고정한다. request_id·run_id·actor·허용 snapshot은 실행기가 바인딩하며 모델 인자에는 없다. 모델은 허용 업종 enum(service-51)·metric enum·시설 코드만 사용한다. 입력은 추가 필드 금지·Pydantic 검증이다. 표의 타입은 향후 schemas.py에서 같은 이름의 모델/JSON Schema로 생성한다.

| 공통 타입 | 필드 |
| --- | --- |
| ToolReply<T> | status=ok/partial/error, data:T 또는 null, fact_ids:[FactId], snapshot_ids:[SnapshotId], truncated:bool, next_cursor:string|null, warnings:[string], error:ToolError|null |
| ToolError | code:enum, message:키 없는 짧은 문장, retryable:bool, failed_fields:[string]. 오류는 유효 값 0·빈 점포 관측과 별개 |
| FactView | fact_id, source, metric, value, unit, period, spatial_scope, industry_code, status, citable, calc_version, provenance_ref |
| Scorecard | industry_code, items[{item,status,grade,points,fact_ids}], code_points/90, L 상태/10, A,B,H, lower_ratio,upper_ratio,coverage,D/C coverage,G,badge,confirmation_conditions |

### 개별 도구

아래 도구별 상한은 요청 전체 또는 actor별 상한이며, 4절의 총합 한도가 먼저 적용된다. 예: 여러 도구의 최대치를 모두 동시에 쓸 수 있다는 보장은 없다.

| 도구 | 목적·입력 스키마 | 출력 스키마 | 오류 | 상한(초기 권고) | 주체 |
| --- | --- | --- | --- | --- | --- |
| get_scorecard | 계산 점수 우선. {industry_codes?:[Code]≤51, mode:summary/detail, limit:int≤32(summary)/5(detail), cursor?:string} | summary는 코드·B/H/A·coverage·배지·누락 상태, detail은 Scorecard·fact_ids. 전체 51업종은 페이지 조회 | common + VERSION_MISMATCH | decision 6회, 평가자 각 2회. 응답≤2,000토큰 | decision·평가자 |
| get_facts | {fact_ids:[FactId]≤32} **또는** {industry_code?:Code, source:Source, metrics:[Metric]≤8, limit≤32,cursor?}. 둘 중 하나 | {facts:[FactView],provenance_refs}. raw 행 참조·단위·기간 제공 | common + UNKNOWN_FACT/UNCITABLE | decision 8회, 평가자 각 3회, 보조 각 1회(받은 ID만) | decision·평가자·보조 |
| query_raw | {sql:string≤4,000자, params:object/array, max_rows:int≤50}. 승인된 뷰 단일 SELECT만(1차) | {columns,rows[{raw_row_refs,values,fact_ids}],uncitable_columns}; 직접 필드는 원문 재대조 후 자동 fact 등록 | common + SQL_DENIED/SQL_TIMEOUT/LINEAGE_UNAVAILABLE | decision 4회, 평가자 각 2회, SQL≤2초·50행·응답≤2,000토큰 | decision·평가자 |
| map_search | {industry_code:Code **또는** facility_code:KakaoEnum, radius_m:int 50~500, limit≤20}. 좌표는 현재 Site 고정 | {observation_id,places[{place_id,name,kakao_category,distance_fact_id,match_status:category_match/name_match/unknown,match_rule_id,fact_ids}],coverage,has_more}. 이름·카테고리·거리도 fact_id로 등록 | common + MAP_UNAVAILABLE | 요청 전체 서로 다른 검색 6개·지도 HTTP 20회·각 검색 15초 | decision·평가자 |
| check_regulation | {}. 현재 좌표·저장된 구역 snapshot 사용 | {status,queried_at,contains_verified,zones,fact_ids,industry_restrictions,limitations}. 건축물대장은 현재 unavailable | common + REGULATION_UNAVAILABLE | 실제 구역 조회 요청당 1회, actor 호출 각 1회·캐시 공유 | decision·평가자 |
| ask_advisor | {question:string≤800자,fact_ids:[FactId]≤12,industry_codes?:[Code]≤3} | {consult_id,status,interpretations[{claim,fact_ids,conditions,confidence}],missing_facts,limitations}. 점수 없음 | common + ADVISOR_UNAVAILABLE | 요청당 최대 2회·각 45초·출력≤1,000토큰 | decision만 |
| ask_user | {questions:[{field:기존 QuestionField,question:string≤200자,reason:string≤200자}]≤3} | {question_session_id,status:waiting_for_input}. 답변은 재개 시 typed user facts | common + QUESTION_NOT_ALLOWED/ALREADY_ANSWERED | 요청당 1세션·질문≤3. 기존 답변 항목 재질문 금지 | decision만 |
| submit_draft | {phase:draft/final,report:ReportProposal,review_resolutions?:[Resolution]}. 점수 숫자 없음 | {report_id,validation_status,rendered_preview_ref,score_snapshot_id}. final도 같은 구조화 제출 도구 | common + REPORT_INVALID/L_EVIDENCE_INVALID/REVIEW_UNRESOLVED | draft 1회·final 1회, 스키마 오류 교정 총 1회(예산에 포함) | decision만 |
| submit_review | {draft_id:ID,verdict:agree/conditional/oppose,issues:[ReviewIssue]≤4} | {review_id,status}. actor는 실행기가 고정 | common + DRAFT_MISMATCH/INVALID_REFERENCE | 평가자 각 1회·지적별 근거 fact_id≤3 | 평가자만 |

common 오류는 INVALID_ARGUMENT / SOURCE_UNAVAILABLE / SNAPSHOT_MISMATCH / BUDGET_EXCEEDED / TIMEOUT / DUPLICATE_CALL이다. 부분 결과는 partial·truncated·누락 필드를 표시하고, '조회 범위 내 확인한 수'만 인용한다. 계약 검증·fact 저장·호출 감사 저장 실패는 일반 error ToolReply로 숨기지 않고 실행 실패로 전파한다(AGENTS.md 3).

map_search는 PlaceClient·카카오 카테고리·거리 계산을 재사용하며 LLM 호출은 0회다. 코드 규칙의 category_match를 우선 적용하고, 명시적인 업종 검색어 규칙이 맞으면 name_match, 그 밖에는 unknown을 반환한다. 일치 상태는 검색 규칙의 결과이며 실제 경쟁점 여부의 확정 판정이 아니다. 애매한 장소의 해석은 decision이 새 fact_id를 근거로 L에서 판단한다. judge_matches·GenerateMapping·모델 프롬프트·모델별 mappings 캐시 및 설정을 제거한다(`backend/app/agents/map_analysis/mapping.py:64`, `agent.py:254`). 검색 응답 캐시를 유지할 때는 좌표·반경·검색어·규칙 버전·조회 시점을 키/출처로 남긴다. 0건·has_more를 실제 동종 가게 없음으로 확대하지 않는다. 모델 클라이언트 생성 시 실패하는 대역으로 지도 LLM 0회를 검증한다.

### query_raw와 자동 사실 등록의 경계

**register_fact는 모델 도구로 만들지 않는다.** query_raw가 원문 ID·허용 필드·metric 대응·단위·기간·업종·scope를 코드로 검증해 단순 원문 셀을 자동 등록한다. 모델이 값·수식을 제출해 사실로 승인받는 경로는 없다. 평가자의 조회도 서버가 기계적으로 등록하며, 모델은 raw·계산·점수에 쓰기 권한이 없다. submit_review는 자신의 검토 출력 저장만 허용하는 예외다.

| SQL 조건 | 실행·인용 규칙 |
| --- | --- |
| 연결 | mode=ro 별도 연결. query_only는 실행기가 설정. 현재 요청의 단일 snapshot·허용 observation cutoff에 한정된 승인 뷰만 노출 |
| 격리 | 뷰 WHERE 조건은 실행기가 바인딩한 current_request_id/current_snapshot 범위로 고정. 모델 조건을 빼도 다른 요청은 안 보임. 연결은 actor별 독립 |
| 허용 | 단일 SELECT, 승인 뷰·안전 함수 목록, 파라미터 바인딩. SQLite authorizer로 기반 테이블 직접 읽기·sqlite_master·미승인 함수 차단. 뷰를 통한 허용 기반 접근만 승인. 범용 SQL AST 검사는 2차 |
| 금지 | INSERT/UPDATE/DELETE, DDL, PRAGMA, ATTACH/DETACH, 다중 문장, load_extension·외부 파일 함수. 방어의 중심은 읽기 전용 연결·SQLite authorizer·행/시간 상한이다. AST 없는 1차에서는 WITH/CTE를 보수적으로 거절해 승인 뷰 이름 가림을 차단한다. 범용 CTE 허용·AST는 2차 |
| 중단 | LIMIT은 최종 51행 검사로 초과 탐지. progress_handler·monotonic deadline·cancel 시 connection.interrupt로 실제 쿼리 중단. to_thread await만 취소하고 백그라운드 SQL을 방치하지 않음 |
| 원문 셀 | raw_row_id + 허용 원 필드를 서버 원문에서 다시 읽어 값·단위·metric을 대조한 경우만 fact_id 생성. 등록 값은 SQL 수식 결과가 아니라 그 원문 셀이다. 불일치·계보 불명은 citable=false. alias로 의미·단위를 바꾸지 못함 |
| SQL 집계·임의 식·계보 불명 | 결과는 탐색용 citable=false, fact_id 미부여. 숫자를 보고서에 복사 금지. 집계는 get_facts/get_scorecard의 승인 계산 지표를 쓰고, 필요한 새 metric은 코드 PR로 추가 |

운영 쓰기 연결은 서비스 전용이며 모델 SQL 연결과 분리한다. 자동 fact 등록은 읽기 연결 밖의 서버 검증/트랜잭션으로 한다. 이를 원자료 쓰기 권한으로 해석하지 않는다.

## 4. decision 루프

| 단계 | 행동·종료 조건 | 저장 |
| --- | --- | --- |
| 시작 | 고정 시스템 지시문·도구 스키마 + request/run/snapshot 참조·Site 최소 문맥·rubric_version·예산. 전체 분석/원문/브리핑 주입 안 함 | run 설정·모델·도구 버전 |
| 코드 확인 | get_scorecard로 51업종 코드 하한 B_code·누락 확인 → B_code 상위 10개 선정. decision은 근거를 붙인 추가 업종 최대 2개까지 | selection score version·순위·추가 이유·fact_ids |
| 해석 | 상충/누락이 결론을 바꿀 때만 SQL·지도·규제. 불확실하면 선택적 자문. 숫자를 직접 재계산하지 않음 | tool_calls·새 facts·자문 |
| L·초안 | 선정된 10~12개를 최대 3업종씩 묶어 검토. 보조 실패 시 advisor_unavailable 기록 후 decision 단독 채점. 코드 90점은 수정 못 함. submit_draft(draft) | 대상 선정·질문·근거·grade/unknown·자문 상태를 LRecord에 기록 |
| 평가·수정 | 4명 review 완료/실패 → 각 지적 수용·일부·기각. 필요한 조회만 추가하고 L/문장 변경 | review_resolutions·새 L revision |
| 최종 | submit_draft(final), 서버가 전체 51업종 최신 채택 점수로 배지·정렬·fact 인용 재검증 | final·적용 스냅샷·완료 |
| 질문 | ask_user 후 waiting_for_input·state 참조 저장, 실행 종료. 재개 시 같은 원문/코드 점수 사용·답변 fact 추가 | 기존 질문/답변 흐름 |

LRecord={industry_code,selection{basis:code_lower_top10/decision_extra/outside_scope,code_score_snapshot_id,code_lower_rank,code_lower_B,reason,reason_fact_ids},review_state:reviewed/unreviewed,advisor_unavailable:bool,status,grade|null,new_factors[{direction:favorable/adverse/neutral,claim,fact_ids}],checked_questions,tool_call_ids,advisor_consult_ids,limitations}. points는 코드가 계산한다. 코드 문항 fact_ids만으로 채점한 L은 거절하고, C2/C3·지도·상가 조건의 새 근거가 있어야 한다. 새 요인 없음을 실제 조회로 확인한 등급 2와 미조회 unknown을 구분한다. 보호구역 금지는 L로 상쇄하지 않는다. 최종 후보 선택도 모델이 점수 순서를 임의로 바꾸지 못한다.

**L 검토 범위는 코드 하한 B_code 상위 10개 + decision의 근거 있는 추가 최대 2개(중복 없이 최대 12개)**다. 동점은 v0.8과 같이 coverage→업종 코드로 결정한다. L을 더한 최종 B로 검토 대상을 계속 재선정하지 않는다. 추가 사유·fact_ids를 LRecord에 기록한다. selection.reason_fact_ids는 검토 선정용이라 코드 자료도 사용할 수 있지만, 실제 L 점수의 new_factors.fact_ids와 분리해 중복 채점하지 않는다. 대상 밖은 L unknown·review_state=unreviewed이며 리포트에 **판단 미검토**를 표시한다. 대상 안도 근거/도구 부족이면 unknown(판단 미확인)이다. 보조 모델 미설정·실패만으로 L을 unknown으로 만들지 않는다. 최종 정렬·배지는 v0.8의 B=코드 기여점수+L 기여점수 기준 그대로다.

| 예산 | 초기 확정값·집행 |
| --- | --- |
| decision 모델 호출 | 초안 8 이하: 코드 확인·대상 선정 2 + L 묶음 검토 4(최대 3업종×4묶음) + 초안 제출 1 + 교정 여유 1. 피드백/최종 4 이하: 반영·추가 확인 2 + 최종 제출 1 + 교정 여유 1. final용 2회 예약 |
| 도구 | decision 20회(초안 14·최종 6), 평가자 각 4회, 보조 사실 읽기 각 1회. 전체 40회. 시도·거절·중복도 카운트 |
| 모델 전체 | decision 12 + 평가자 4×3 + 보조 2 = 최대 26회. 실행 상한 28회이며 여유 2회도 자동 소비하지 않음 |
| 입력/출력 토큰 | 모델 호출당 입력≤12,000·출력≤3,000, 전체 누적 입력≤160,000·출력≤24,000. 각 role·provider 사용량 실제 기록 |
| 활성 시간 | 수집/계산 120초 목표 한도 + 추론/평가/최종 180초 한도, 전체≤300초. 임대인 답변 대기 제외, 재개 때 예산 초기화 금지 |
| 병렬 | 독립 read 도구는 1턴 최대 3개 병렬. 평가자 최대 4명 병렬. 동일 SQL 연결 공유 안 함 |
| 반복 | tool+정규화 인자+snapshot/허용 observation cutoff 해시 동일은 DUPLICATE_CALL·이전 fact/call 참조만 반환. 새 사실 없는 2연속 턴이면 draft/final로 이동 |
| 문맥 | 전체 기록은 DB에 보관. 모델 작업집합은 필요한 typed facts 최대 64개·4,000토큰, 최근 도구 응답만. 인용/현재 L에 쓰는 fact는 요약 제거 금지 |

토큰은 반복 전송된 시스템·대화 이력까지 누적하며 캐시 할인이 있어도 원 토큰 사용량을 기록한다. 남은 토큰은 사전 추정과 provider usage로 조정한다. 같은 재개·판단 재시도는 저장된 사용량을 이어받는다. API 재시도도 실제 HTTP 한도를 소비한다.

상한·도구 실패는 해당 근거 unknown과 제한 문구로 남겨 부분 보고서 제출을 시도한다. 제출된 초안이 유효하고 최종 정리가 실패하면 '초안·평가 미완료'로 저장하며 final로 가장하지 않는다. 새 schemas/API에 draft_available 실행 결과를 제안한다. 제출 자체·저장·계약 검증이 실패하면 failed다. 임의 성공/중립값·가짜 L을 생성하지 않는다.

## 5. 보조 에이전트와 모델 설정

| 항목 | 계약 |
| --- | --- |
| 초기 모델 | **anthropic/claude-sonnet-5**, 엘리스 게이트웨이. decision의 실제 역할 설정은 openai/gpt-6-luna로 확인했다. 다른 계열 권장 조건에 맞음 |
| 계열 정책 | 다른 계열 **권장**, 같은 계열을 금지하지 않음. 실제 사용 model·family·endpoint 설정 출처를 자문 기록에 남김 |
| 변경 | Opus 계열 등 모델 교체는 ADVISOR 환경변수로만. 프롬프트·도구 계약 변경 없이 설정에서 선택. 실제 설정 코드는 PR5 |
| 미설정/실패 | 자문만 unavailable. LRecord에 advisor_unavailable을 기록하고 decision이 단독으로 근거 기반 L 채점. L unknown 여부는 근거·도구 확보 여부로만 결정 |
| 입력 | 질문≤800자 + fact_id≤12 + 최소 값·단위·기간·범위. 전체 분석·decision 대화·초안은 전달하지 않음 |
| 권한 | 받은 fact_id만 get_facts. SQL·지도·규제·사용자 질문·추가 보조 호출 불가 |
| 출력 | 대안 해석·근거 IDs·성립 조건·confidence·누락 사실·한계. 등급·points 없음 |
| 상한 | 전체 2회·각 45초·출력1,000토큰. 실패·재시도 포함 |
| 반영 | decision이 호출 이유·질문·자문 요지·반영 여부·이유 기록. 자문 자체를 새 fact로 등록하지 않음 |

설정은 `backend/app/llm/config.py:30`의 `LLMSettings.from_env("ADVISOR")` 형식을 따른다.

| 환경변수(.env.example에는 이름만) | 비었을 때 실제 기존 fallback |
| --- | --- |
| ADVISOR_LLM_MODEL | ELICE_MODEL |
| ADVISOR_LLM_BASE_URL | ELICE_BASE_URL |
| ADVISOR_LLM_API_KEY | ELICE_API_KEY |
| ADVISOR_LLM_MAX_TOKENS | LLM_MAX_TOKENS, 없으면 기존 기본값 |
| ADVISOR_LLM_TIMEOUT_SECONDS | LLM_TIMEOUT_SECONDS, 없으면 기존 기본값 |

모델·인증·주소는 ELICE_*를, 길이·시간은 기존 LLM_*를 사용한다. 실제 .env나 운영 설정은 이번에 바꾸지 않았다. Sonnet로 시작하려면 운영자가 ADVISOR 역할 설정에 원하는 모델과 그 모델 접근 가능한 연결을 지정해야 한다. 같은 계열 fallback도 기록하며 임의로 다른 모델을 재호출하지 않는다.

### 과거 게이트웨이 확인 기록 (2026-10-14)

기존 `app/llm/client.py:131` 경로의 stream=True·include_usage=True를 사용했다. 기본 json_object만으로 스키마 지원을 주장하지 않도록 일회성 메모리 wrapper에서 response_format=json_schema(strict=True)를 지정하고 {ok:true}를 요청했다. max_completion_tokens=200·timeout45초·SDK 자동 재시도0. 확인 코드는 저장소에 남기지 않았다.

| 확인 | 결과 |
| --- | --- |
| 모델 응답 성공 | 실패: 최초·허용 재시도 모두 LLM_REQUEST_ERROR |
| 스트리밍 | 재시도 HTTP200·text/event-stream 도착, 정상 chunk 0개. 스트리밍 추론 성공 아님 |
| usage | 반환 없음. 입력·출력 토큰/과금 미확인 |
| JSON Schema | 요청했으나 모델 접근이 거절돼 응답 지원 여부 미확인 |
| 시간 | 최초 0.859초·재시도 0.640초 |
| 서버 오류 | Model 'anthropic/claude-sonnet-5' is not allowed. Allowed: ['gpt-5.6-terra', 'openai/gpt-5.6-terra'] |

ADVISOR 역할의 별도 endpoint/key가 없어 공통 ELICE 연결로 확인했다. 이 연결의 모델 허용 목록 문제이며 Sonnet 자체의 JSON/스트리밍 비호환으로 단정하지 않는다. 별도 Sonnet용 ADVISOR_LLM_BASE_URL/API_KEY 설정 후 다음 승인된 시험에서 재확인해야 한다. 키·URL 원문은 출력·문서에 남기지 않았다. 해당 시험의 재시도 한도를 소진했으므로 그 실행에서 추가 호출하지 않았다. 이후 별도 승인된 기본 ELICE 확인은 HTTP200·스트리밍 8청크·usage 입력38/출력25·JSON 객체 검증 성공(2.86초)이었다. 당시 ADVISOR 모델·키 미설정으로 Sonnet 확인은 실행하지 않았다. v0.3 개정에서는 호출하지 않았다.

## 6. 평가자 4명 — 항상 실행

| 역할(현재 ID 유지) | 중점 | 권한 |
| --- | --- | --- |
| examiner | 숫자/단위/기간/범위·원문 계보·L 중복·상충 | 같은 score/fact/raw/map/reg 읽기 + submit_review |
| founder | 폐업·경쟁·작은 표본·업종 일부의 실행 위험 | 동일 |
| customer | 인구·시간·실제 고객 행동·수요 해석 누락 | 동일 |
| landlord_advocate | 임대인 답변·층/면적/설비·확인 조건 | 동일. 규제를 독자 법률 판정하지 않고 조회 상태/누락 확인 |

각 평가자는 고정 페르소나 시스템 프롬프트, draft_id·버전·인용 fact_id 목록·LRecord·확인 조건만 받는다. 다른 평가자의 의견·보조 의견은 초기에 주지 않아 독립 검토한다. 기존 4 ID·지적 최대 4개·실패 격리를 재사용한다(`backend/app/schemas.py:696`, `:702`, `:710`, `backend/app/agents/evaluators/agent.py:175`).

ReviewIssue={issue_id,industry_code|null,target:fact/score/L/claim/condition,kind:factual_error/duplicate_score/missing_evidence/scope_mismatch/action_condition,comment,fact_ids≤3,suggested_check,blocking:bool}. 모델이 점수나 배지를 직접 고치는 출력은 없다. 저장된 사실을 임의 삭제하거나 외부 메시지를 보내는 권한도 없다.

| 반영 규칙 | 처리 |
| --- | --- |
| 수용 | 바뀐 claim/L·새 fact·이유 기록, 같은 코드 사실 오류는 서버 검증/재계산 후 새 score snapshot으로 수정 |
| 일부 | 적용한 부분·적용 안 한 부분·이유를 분리 |
| 기각 | 근거 fact_id와 이유 요구. 의견과 기계 검증 위반을 구분 |
| 기계 위반 | 잘못된 fact·코드 점수 변경·L 중복·금지 상쇄는 기각할 수 없음, 제출 validator가 거절 |
| 실패/시간 초과 | 일부·전체 실패 모두 평가 미완료를 명시하고 기계 검증 통과 결과 제공. failed reviewer 명단·coverage 표시, 동의로 계산하지 않음 |
| 반복 | **평가 1라운드 + decision 수정 1회**, 수정 후 기계 검증만. 추가 평가가 필요하면 다음 요청으로 분리 |

끄는 스위치 없이 평가자 4명 모두 실행한다. MOCK_MODE에서는 같은 단계·계약을 대역으로 검증하고 예산 상한은 실제 실행과 같이 집행한다. 사용자 목표에 따라 평가자 전원 동의라도 decision의 최종 제출 단계는 수행한다. 현재는 no_comments/all_failed면 final 호출을 건너뛸 수 있으므로 바뀌는 동작이다(`backend/app/agents/orchestration/nodes/evaluation.py:70`).

## 7. 보고서 출력 계약

ReportProposal={summary_segments,candidates≤5,excluded_candidates≤5,limitations_segments,L_records}. Candidate={industry_code,reasons_segments,risks_segments,confirmation_conditions_segments,fact_ids}. 점수·배지·금지·순위·숫자 값 필드는 모델 제안에 받지 않는다. 서버가 registry·v0.8 scores로 계산해 DecisionResult에 붙인다.

| 필드 | DecisionResult 서버 출력 |
| --- | --- |
| 버전 | schema_version=2.0, rubric_version=v0.8, tool_contract_version, request_id, run_id, report_id, score_snapshot_id, evidence_snapshot_ids |
| 검토 후보 | code·name·코드 point/90 + L point/10, L 대상/선정 이유·review_state. 대상 밖 unknown=판단 미검토, 대상 안 근거 부족 unknown=판단 미확인. A/B/H·비율·coverage·배지·G |
| 근거 문장 | segments=[{type:text,text},{type:fact,fact_id,format:count/percent/rate/distance/text}]. 모델은 값 복사·산술 금지 |
| L | 새 요인·fact_id·호출 도구·자문 반영·grade/unknown. 새 근거가 없으면 등급 생성 금지 |
| 검토 상태 | 평가자 4명 상태·지적·수용/일부/기각 로그, review_completeness |
| 확인 조건 | 건축물 용도 등 미확인·자료 시점/공간 한계·partial·예산 제한 |

숫자는 서버 renderer가 fact.value·단위로 채운다. grade enum·업종 코드·고정 시간대/연령 라벨은 구조화 제어값이며 측정 숫자 복사와 구분한다. 모델 자유문장에 인용 없는 수치가 있으면 거절한다. 근거는 fact_id만 인용한다. 기존 render_cited·`{i}` 자리표시자·agent/path 인용은 삭제하고 typed fact 슬롯 renderer로 교체한다. 원문 숫자를 텍스트에 붙이는 우회도 검사한다.

최종 배열은 전체 51업종 채택 점수의 원점수 하한→coverage→코드로 재검증한다. L 검토는 상위10+추가2로 제한하고 대상 밖은 unknown·판단 미검토로 남기며 '전체 업종의 L을 검증했다'고 하지 않는다. Top 5에 보류/조건부가 있어도 추천처럼 표시하지 않는다.

## 8. schemas.py 변경안 — 팀 계약 교체

**결정:** 최종 배치는 공통 계약 schemas.py·내부 계약 app/agents/agentic/contracts.py다. PR1~PR6에는 모든 새 계약을 contracts.py에 최종 이름 그대로 두어 기존 실행을 유지한다. PR7에서 DecisionRequest·DecisionResult·Evidence·QuestionSnapshot을 schemas.py로 옮겨 기존 계약을 교체한다. V2 접미사와 구 결과·질문 reader를 만들지 않는다. schemas.py 교체안의 팀 승인은 완료됐으며 실제 파일 변경은 PR7에서 적용한다. 이번에는 문서만 수정한다.

| schemas.py 모델 | 변경안·이유 |
| --- | --- |
| AnalysisTask / AgentAnalysis | 그대로 유지. snapshot·계산 metadata는 AgentAnalysis.data 내부에만 추가 |
| DecisionRequest | request/run/site/snapshot 참조·rubric/tool version·remaining_budget. 전체 analyses/digest 입력과 모드 dispatch 제거 |
| DecisionResult 및 IndustryAssessment/DecisionContent | 코드 ○/90 + L ○/10, 점수 구간·비율·coverage·배지·검토 후보 Top 5·fact 슬롯·L 검토 상태·평가 요약. 기존 보고서 계약 교체 |
| Evidence | {fact_id} 참조로 교체. agent/path·EvidenceRef 인용 계약 제거, registry가 요청·snapshot·업종·citable 검증 |
| QuestionSnapshot | run/snapshot/score/draft refs·도구 hash·누적 예산·채택 fact 목록·질문 세션. 기존 QuestionSnapshotV2 통합 제거, 구 세션 재개 불가 |
| AnalysisMode·Specialist 관련 모델 | single_decision/multi_agent enum·전문가 브리핑/행동 전용 모델 제거. 팀 공통 소비자 함께 갱신 |
| 평가 응답의 공통 경계 | DecisionResult에 평가 상태·반영 요약만 노출. 내부 ReviewIssue/Resolution은 contracts.py에 정의 |

| app/agents/agentic/contracts.py 내부 계약 | 내용 |
| --- | --- |
| 도구 입출력·ToolReply/ToolError | 3절 입력 union·출력·권한·오류·상한 |
| Scorecard / FactView | 점수·상태·레지스트리 읽기 출력 |
| ReportProposal / LRecord | 모델 보고서 제안·새 근거 판단 기록. 서버 출력 DecisionResult와 구분 |
| ReviewIssue / Resolution | 평가 지적·수용/일부/기각과 이유 |
| AdvisorAnswer | 대안 해석·fact_ids·조건·확신도. 점수 없음 |

모델 자유문장·원문 응답은 경계에서 검증한다. 프롬프트는 도구 계약을 참조하고 DB 내부 열·함수명을 의존하지 않는다.

## 9. 프론트·API 영향 — 새 결과 계약으로 전환

GET /api/v1/analyses/{id}의 URL과 status/site/result/error envelope·폴링 seq는 재사용한다. result는 새 DecisionResult만 반환하며 구 결과 변환·버전별 adapter는 만들지 않는다. source_analyses 거대 배열을 기본 결과나 모델 입력에 재삽입하지 않는다. 숫자는 fact 슬롯 renderer로 제공하고 원문 SQL·키는 GET/이벤트에 노출하지 않는다.

**develop 리포트 화면(#38)은 새 DecisionResult에 맞춰 수정해야 한다.** PR1에서 계약을 공유하고 PR6에서 목업 GET을 제공한다. PR7 통합 전환 전에 코드/L 분리·점수 구간·배지·Top 5·L 미검토·평가 미완료·fact 슬롯 표시를 연결하고 프론트 검사를 통과한다. 화면/진행 이벤트 구현을 통합 전환 뒤로 미루지 않는다.

현재 진행은 events seq 폴링이며 SSE가 아니다(`docs/API_CONTRACT.md:210`, `:224`). mock 진행 시뮬레이션 TODO도 실제 stage 소비로 교체한다(`frontend/app/analysis-progress/page.tsx:93`, `frontend/lib/hooks/useAnalysisProgressSimulation.ts:17`).

| 단계 | stage/event·detail 계약 | 화면/전환 작업 |
| --- | --- | --- |
| 원문 수집 | 기존 분석 agent stages + raw_capture completed {source,snapshot_id,partial} | 분석 3종 상태·부분 수집 표시 |
| 계산/채점 | metrics/scorecard started·completed {rubric_version,industry_count} | 코드 채점 단계 표시 |
| 판정 도구 | decision started/completed {phase:draft/final}; decision.tool completed {tool,status} | 원문·SQL·키·fact 값은 이벤트에서 제외 |
| 자문 | advisor started/completed {status} | consult.*·briefing stages 삭제 |
| 평가 | evaluate.examiner/founder/customer/landlord_advocate started/completed {status,issues_count} | 항상 4명 상태·평가 미완료 표시 |
| 질문/종료 | questions waiting, run completed/failed/draft_available | 새 QuestionSnapshot으로 대기/재개. 유효 초안과 final 구분 |

PR1에서 API_CONTRACT의 결과·질문·stage를 갱신하고 PR6에서 런타임·GET·이벤트를 연결한다. 프론트 담당은 PR7의 전환 완료 조건에 포함해 검증한다. retry는 같은 snapshot·저장 예산을 이어받는다. DB 버전 불일치는 시작 오류와 명시적 초기화 안내로 처리한다.

## 10. 비용·시간 예산

입력 약 31만 토큰·약 80초는 **사용자가 제공한 이전 실행 측정치**다. 이번에 해당 원 실행 로그를 재측정하지 않았다. `docs/backend-design.md:158`의 80초·19호출은 부하 산술 가정이므로 독립 실측 근거로 쓰지 않는다. 아래는 설계 추정이며 실제 공급자 요금·캐시 할인·HTTP 지연을 보장하지 않는다.

| 항목 | 지금 문제 | 새 구조 추정/측정 방법 |
| --- | --- | --- |
| 초기 입력 | 자료/digest·브리핑 선행 입력 | 고정 지시문·도구 + 최소 Site·snapshot refs. 첫 scorecard/facts에서 필요한 값만 조회 |
| 정상 입력 예 | 역할별 입력 중복 | L 최대12개를 4묶음으로 검토: decision 초안7+최종2=9호출×평균7,000=63,000 + 평가자8호출×6,000=48,000 + 보조1호출×4,000=4,000 → **약115,000 입력 토큰**, 이전310,000 대비 약63% 감소 가설 |
| 출력 | 긴 전문 요약·재판단 | 위 18호출×평균800이면 약14,400 출력 토큰. 구조화 출력 상한24,000. 기존 출력 실측 없어 비용 절감률은 미확정 |
| 호출 | 요약·되묻기 | 예시18회(decision9+평가8+보조1)·최대26회. 도구 왕복이 늘면 고정 prompt와 대화가 반복돼 입력도 늘 수 있음 |
| 시간 | 이전 약80초 | decision 순차9×3~6초 + 평가 병렬2×3~6초 + 보조3~6초 + 수집30~60초 → 약66~132초 **가정**. 도구/재시도/긴 모델 지연 시 2~3분 가능, 300초 상한 |
| 캐시 | 불안정 prompt 변경 | 버전별 고정 prefix·도구 스키마·업종 enum으로 공급자 prompt cache 후보. 지원/할인·적중률은 사용량으로 확인 |
| 원자료 | 재전송/재수집 | 요청당 단일 snapshot의 SQL/사실 읽기만. 지도·규제 추가 관측은 append-only, 기초 API 재수집·부모 snapshot은 2차 |

이 예산은 10~12개 각각에 독립 모델 호출을 주는 방식이 아니라 공동 조회·최대3업종 묶음 검토를 전제로 한다. 한도 안에서 근거를 확보하지 못한 대상은 unknown·검토 제한으로 남기며 예산을 자동 확대하지 않는다.

계측은 role별 호출·input/cached_input/output·HTTP·도구 응답 크기·SQL ms·지연 p50/p95·L unknown·평가 실패·보고서 검증 실패를 저장한다. 토큰 절약이 정확도 하락을 숨기지 않게 동일 주소·같은 snapshot의 목업·고정 자료에서 검증하며 전환 전 확보한 시험 지표와 비교한다. 옛 실행 경로를 운영에 남기지 않는다. 금액 환산은 실제 model별 요금을 설정한 뒤 별도로 하며 이번 문서에서 가격을 가정하지 않는다.

## 11. 1차 구현 계획 — PR1~PR7

구현 PR은 **feat/agentic-decision**을 base로 순서대로 리뷰·병합한다. PR7 전환까지 통과한 뒤 이 브랜치를 develop에 한 번에 병합한다. 중간 기능을 develop의 모드 스위치로 노출하지 않는다. 이번 작업에서는 브랜치를 생성하거나 PR을 열지 않는다.

| PR | 범위 | 목업·고정 자료 검증 |
| --- | --- | --- |
| PR1 계약 | 승인된 교체안의 모든 새 모델을 contracts.py에 최종 이름으로 정의 + API_CONTRACT에 PR7 이후 계약 추가. schemas.py 변경·실행 연결 없음 | 새 JSON fixtures·직렬화/검증, cross-request 거절, 90/10·구간·배지·Top 5·fact 슬롯. AnalysisTask/AgentAnalysis 불변 확인 |
| PR2 원문 저장 | 요청당 snapshot 1개·raw capture·CSV file 원천·조회 뷰·계보·새 DB 스키마 | 제외 업종 원문 보존·중복/누락·append-only/cutoff·DB 실패 전파. 옛 DB 변환 코드 없음 |
| PR3 facts·코드90 | v0.8 순수 엔진·registry·scores·기준선/프로필 버전 | L unknown·C1 sqrt·n.a. 분모·90/10·G 금지·계보. 기존 8곳 시험 결과를 익명 고정 fixture로 재현 |
| PR4 읽기 도구 | score/facts/raw SQL 자동 등록·지도/규제 wrapper·지도 숨은 LLM 제거. mode=ro+authorizer+행/시간 상한 | 쓰기·DDL·PRAGMA·ATTACH·직접 table/cross-request·WITH 거절, 50행/2초·집계 uncitable. category_match/name_match/unknown·거리, 지도 모델 호출 0회·규제 출력 불변 |
| PR5 decision 루프·보조 | 고정 prompt·도구 루프·상위10+추가2 L·초안/최종·예산·새 질문 재개·ADVISOR 설정 | 범위·새 근거·중복 채점 거절·반복 금지·자문 실패에도 단독 채점·실제 모델/계열·예산 재개. 분석/digest context 삽입 없음 |
| PR6 평가자·보고서·GET | 항상 4명 read 검토·review 반영·fact renderer·final·새 GET·stage 연결 | 4명 호출·일부/전체 실패 표시·L 중복/코드 변경 거절·수용/일부/기각·숫자 슬롯·초안 상태·새 질문 대기/재개. 새 응답 계약만 제공 |
| PR7 전환 | DecisionRequest/DecisionResult/Evidence/QuestionSnapshot을 contracts.py에서 schemas.py로 옮겨 기존 것을 교체, 옛 모드·specialists·브리핑·행동 JSON·legacy 근거/renderer/reader 삭제, 환경변수·캐시·테스트 정리, DB 스키마 버전 검사·초기화 안내, .env.example·README·프론트 연결 | 구 경로/import/설정 참조 0건, 옛 DB는 명확한 오류·초기화 안내/자동변환 없음, 새 DB 시작·질문 재개·MOCK_MODE 전체 흐름. #38 화면·실제 stage 소비·프론트 검사 통과 |

운영 채점 엔진을 scripts에서 import하되 시험 CLI는 유지한다. 실제 decision 프롬프트는 도구 구현 후 로드맵5단계, 평가자 페르소나는 로드맵6단계에서 작성한다. PR7 완료 검증에는 해당 프롬프트·페르소나와 비용 상한을 적용한 단일 흐름 목업 검증이 포함된다. 통합 전환 전 저장 결과는 버리고 새 DB로 시작한다.

### 나중 작업 — 2차

| 항목 | 범위·선행 조건 |
| --- | --- |
| SQL AST·CTE | 범용 AST·승인 뷰 이름 가림 검사 후 CTE 허용 검토. 1차 authorizer를 제거하는 대체가 아님 |
| 재수집·부모 snapshot | 동일 요청 기초 자료 재수집·부모/자식 체인·채택 snapshot 선택·동일 조건 재계산 |
| 진행 화면 고도화 | 단일 모드 stage·결과 연결은 PR6/PR7 필수. 이후 상세 도구 타임라인·비용 시각화 개선 |
| 모델별 사용량 기록 보강 | PR5부터 응답 실제 모델명·계열·usage를 기록한다. 요청 모델명과 응답 전 실패한 호출의 설정 모델 기록은 후속 작업. 이전 실행은 모델명이 없어 식별할 수 없음 |

기존 경로 정리는 PR7에 포함한다. 구현 PR은 ruff·format·mypy·unittest·catalog check, 프론트 변경은 format/lint/build를 검사한다. 실제 API·유료 실행은 별도 승인 범위에서만 수행한다.

## 12. 확정 결정과 남은 질문

| 확정 결정 | 내용 |
| --- | --- |
| 초기 예산 | 전체300초·모델26/상한28·누적 입력160,000/출력24,000·도구40. 실제 테스트 후 조정 |
| 상주·직장 원천 | 현재 분기 CSV를 source_type=file로 저장하고 파일 해시·시점을 표시 |
| 평가 실패 | 일부·전체 실패 모두 평가 미완료 표시와 함께 기계 검증된 결과 제공. 동의로 간주하지 않음 |
| 보조 모델 | Sonnet5 시작·다른 계열 권장·실제 사용 모델/계열 기록. 변경은 환경변수. 자문 실패와 L 채점 분리 |
| L 검토 범위 | 코드 하한 상위10+근거 있는 추가2, 대상 밖 판단 미검토. 최종 정렬/배지는 v0.8 유지 |
| 현재 보존 | 전환 후 새 원문·도구 기록 전부 보존. 전환 전 구 DB 결과·질문 세션은 폐기 |
| 실행·근거 | 새 구조 단일 모드·평가자 항상 실행·fact_id만 인용. 지도 검색 LLM 없음 |
| 계약 분리 | schemas.py 팀 계약 교체, agentic/contracts.py 내부 계약. V2 접미사 없음 |
| 구현 통합 | feat/agentic-decision 기준 중간 PR 리뷰 → PR7 통과 → develop에 한 번 병합 |

| 남은 사용자 확인 | 필요 사항 |
| --- | --- |
| 운영 보존 기간 | 지금은 전부 보존. 운영 배포 전 원문·도구·임대인 답변 기록의 보존/삭제 정책 결정 |
| Sonnet 연결 확인 | 최근 기본 ELICE 호출은 성공했으나 ADVISOR 모델·키 미설정으로 Sonnet은 미확인. 안전한 역할 설정 후 별도 승인 범위에서 확인. 키를 채팅에 보내지 않음 |

schemas.py 공통 계약 교체안은 팀 승인 완료, 실제 교체는 PR7이며 API_CONTRACT에는 합의된 응답·질문·stage를 반영한다. 1차 SQL은 AST를 미루는 대신 CTE까지 허용하지 않는 보수적 범위이며, 확장 전 안전 검사를 추가한다.


## 13. 팀 공지 문안

### 프론트 담당

- 구조 구현 PR은 feat/agentic-decision에 모으고 PR7 완료 후 develop에 한 번에 병합합니다.
- PR1에서 새 DecisionResult/API 계약을 공유하고 PR6에서 목업 GET을 제공합니다.
- develop 리포트 화면(#38)을 코드 ○/90 + L ○/10·점수 구간·배지·Top 5·fact 슬롯에 맞춰 변경해야 합니다.
- 판단 미검토·평가 미완료·새 질문 재개와 실제 진행 stage를 연결하고, PR7 전환 전 프론트 검사를 통과합니다.
- 옛 결과/질문 DB는 초기화하며 구 응답 변환 화면은 만들지 않습니다.

### 규제 담당

- education_zone.py의 조회 코드·출력은 그대로 재사용합니다.
- bf24caf에서 decision 입력에 주입하던 규제 자료는 check_regulation 읽기 도구로 연결합니다.
- 폴리곤의 입력 좌표 포함·조회 오류 상태를 유지하고, fact_id로 근거를 등록해 판정관/평가자가 확인합니다.
- 지도·규제 조회 결과의 재해석으로 확정 규제 금지를 상쇄하지 않으며 규제 코드 변경은 이번 전환 범위에 없습니다.

## 14. 변경 이력

| 버전 | 내용 |
| --- | --- |
| v0.1 | 원문/계산 분리·fact_id·SQL·코드90/L10·도구·평가자 기본 설계 |
| v0.2 | L 상위10+추가2·자문 실패와 채점 분리·단일 snapshot·초기 예산·보조 모델 설정, 1차/2차 범위 구분 |
| v0.3 (2026-10-14) | 단일 모드·항상 평가·fact 전용 근거·구 DB 초기화 결정. 지도 LLM/캐시 제거, schemas와 내부 contracts 분리, PR7 전환·통합 브랜치·팀 공지 추가 |

PR1 배치 보완: PR1~PR6는 모든 새 계약을 contracts.py에 두고 schemas.py를 수정하지 않는다. PR7 이동 시 내부 계약 의존/import도 함께 정리하며 기존 실행 경로를 제거한다.


### PR2 원문 저장 구현 메모

- 요청당 snapshots 1개, 실행마다 run_id 분리. raw_responses/raw_rows는 append-only로 저장하고 중복 페이지·행은 duplicate_of로 표시한다.
- 서울 API는 공통 transport, 상권은 StoreClient 응답, 상주/직장 CSV는 파싱 전 저장한다. 제외 업종과 미사용 칼럼도 원문에 남긴다.
- 현재 상권 캐시는 필드가 축소돼 있으므로 from_cache 원문 재사용은 partial이다. 재수집하지 않고 한계를 기록한다. 최신 분기 탐색 1행 요청은 전체 페이지 누락 계산에서 제외한다.
- scrub 한 함수로 인증 필드·서울 URL 경로·인증 쿼리·헤더·알려진 키의 응답 반사를 제거한다. payload_hash는 정제된 저장 원문의 해시다. CSV는 파일 바이트 해시·파일명·분기를 별도 기록한다.
- 요청 범위의 scoped_reader가 raw_request_id/raw_snapshot_id를 서버에서 바인딩한다. 일반 연결은 null 범위로 뷰에 0행만 보이며, 모델 SQL 권한·authorizer는 PR4에서 연결한다.
- SQLite 저장은 to_thread로 격리하고 취소 시 진행 중 쓰기가 종료된 뒤 partial 마무리한다. RawStorageError는 API 오류나 AgentAnalysis로 숨기지 않고 failed 요청으로 전파한다. 스냅샷 마무리는 완료 상태 저장 전에 수행한다.
- 2026-10-14 승인 확인: 기본 ELICE function calling 1회는 LLM_REQUEST_ERROR·tool 인자 조각0·usage 없음. ADVISOR 모델·키 미설정으로 Sonnet 호출은 생략했다. 도구 실행·추가 재호출은 없었으며 PR5 연결 전 호환성은 미확인이다.

수집 완료 시 스냅샷을 먼저 마무리하며, 이후 decision 실패나 새 수집 없는 질문 재개가 이미 완전한 원문을 partial로 바꾸지는 않는다.


### PR3 구현·검증 메모

| 항목 | 구현 |
| --- | --- |
| 원문 캐시 | raw-v2 파일·version=2. API 페이지 envelope를 축소 없이 저장·복사하고 cache_hit/original_collected_at 기록. 옛 캐시는 읽지 않음 |
| 단일 채점 엔진 | app/agents/agentic/scoring.py가 rubric_dryrun.py의 v0.8 계산·판정을 소유. CLI는 import만 하며 민감도 시험을 유지 |
| 원문 formatter | 저장된 상권·유동·상주/직장·개폐업 행에서 기존 map_stores/build_middle_rows/_aggregate/_benchmark/_trend/resident_block/worker_block/_aggregate_rows 호출. 외부 호출 경로 없음 |
| 사실 저장 | facts와 fact_sources. f_UUID, 값·단위·기간·비교 기준·원문 행/응답 참조·계산/입력 버전. 동일 값/계보는 ID 재사용, 새 값은 새 ID. UPDATE 거절 |
| 코드 점수 | score_snapshots/scores. 항목·배점·등급·점수·상태·fact_ids와 A/B/H·coverage·배지·Top 5 저장. L unknown·unreviewed, 적용 배점에는 포함 |
| 연결 | 분석 3종 수집 후 사실·점수 저장. 기존 decision 데이터/행동 JSON은 바꾸지 않으며 PR7에서 교체 |
| 실패·부분 수집 | 저장/채점 실패는 서비스 failed로 전파. 행·페이지가 불완전한 원천의 문항은 unknown, 승인 미적용은 n.a.로 유지 |
| 규제 | 기존 출력만 복사하며 조회 코드는 유지. geometry 없는 구역은 좌표 포함 미확인으로 해당 제한 업종 G unknown. 조회 영역에 구역이 없으면 해당 없음 |
| 재현 | verify_rubric_reproduction.py는 8개 표본·기준 JSON을 읽기만 함. 408/408 항목 상태/등급/점수·배지·Top 5 일치, 합계 추천9/조건부1/보류377/비추천21 |

#### PR5 호출 방식 확정 — 앱 경로 재확인

- Luna는 앱 경로의 `max_completion_tokens`·`reasoning_effort=none`에서 function calling을 지원한다.
- HTTP 200, get_scorecard 입력 검증 통과, 스트리밍 인자 조각 28개, 입력 469·출력 41·합계 510 토큰을 확인했다.
- reasoning을 켜는 조합은 tools와 함께 400으로 거절됐다. decision·평가자는 reasoning_effort=none을 사용한다.
- PR5는 기존 Chat Completions 도구 경로를 사용한다. Responses 전환은 7단계 실테스트에서 판단 품질이 부족할 때만 검토한다.

#### PR4 구현 순서

1. SQL 격리·직접 필드 fact 등록 테스트 → 읽기 전용 SQL 실행기(승인 뷰·authorizer·50행·2초).
2. 저장된 점수/fact 읽기·actor 권한·호출 상한 테스트 → 현재 스냅샷 도구 실행기.
3. 지도 결정론·모델 생성 금지·규제 공유 테스트 → 지도 규칙과 읽기 도구, 지도/규제 뷰.
4. 기존 지도 LLM·프롬프트·캐시 설정 삭제와 호출부/테스트 갱신 → 전체 검사 후 문서/PR4 분리 커밋.


### PR5 구현 계획 (2026-10-14)

- 기존 서비스·schemas는 유지하고 새 execute_agentic_analysis / resume_agentic_analysis 서비스로 연결한다.
- 모델 응답 receipt에 실제 model·usage를 기록한다. advisor의 reasoning은 공통 Luna 설정을 상속하지 않고 역할 값이 비면 생략한다.
- 원문 기반 코드 점수 → 고정 프롬프트·점수 요약 → 읽기/자문/질문/초안 도구 루프 → 서버 L 근거 검증·재채점·숫자 렌더링 순으로 실행한다.
- L은 코드 하한 상위 열 업종과 근거 있는 추가 두 업종만 허용한다. 문항 fact·기본 점수 지표 반복은 거절한다.
- 질문 세션·대화·모델/도구 예산은 별도 실행 상태에 저장해 재개한다. 평가자는 공유 for_actor 실행기만 만들고 PR6 전에는 실행하지 않는다.
- 테스트: 도구 루프·L 거절/범위·보조 실패/상한·질문 재개·예산 종료·반복 중단·영구 저장 실패. 모두 대역으로 검증한 뒤 승인 주소 한 곳을 실제 실행한다.
- Sonnet 확인: reasoning none은 HTTP 400으로 거절. 해당 옵션만 생략한 재시도는 HTTP 200(model=claude-sonnet-5, usage=849/200)이지만 출력 상한으로 JSON 검증은 미완료. 추가 진단 호출은 하지 않는다.

#### PR5 구현 계약·검증

| 항목 | 구현 |
| --- | --- |
| 새 서비스 | execute_agentic_analysis / resume_agentic_analysis. 기존 API·그래프 연결은 유지하며 전환은 PR7 |
| 첫 입력 | 요청·좌표·스냅샷 ID, 업종별 코드 점수 요약과 L 상위 열 업종. 분석 원문·digest 미주입 |
| 모델 호출 | 기존 스트리밍 Chat Completions, tool_choice=required, parallel_tool_calls=False, decision reasoning_effort=none |
| 대화 예산 | 전체 대화는 DB 보존. 모델에는 고정 지시문·요약·최근 도구 응답·최대 64개 fact만 전달. 잘린 도구 목록은 cursor/has_more 명시 |
| L 거절 | 현재 요청의 관측·인용 가능 fact, 실제 성공 도구 기록, 새 요인만 허용. 코드 채점 근거 재사용·같은 주장/근거 집합 중복·범위 초과 거절 |
| L 등급 | 최고는 서로 다른 유리 요인 둘 이상·불리 없음. 최저는 불리 둘 이상 또는 major_constraint=true인 큰 운영 제약. 한 불리 요인은 낮음, 중립/상쇄는 중간 |
| 자문 | 최대 두 회, 선택 fact와 질문만 전달하며 도구 미제공. 실패는 advisor_unavailable로 기록하고 decision 계속. 실제 응답 model·계열·usage 저장 |
| 보조 설정 | ADVISOR_LLM_REASONING_EFFORT가 비면 해당 옵션을 생략. .env는 변경하지 않고 .env.example에 이름만 추가. JSON 형식은 유지 |
| 질문 재개 | 답변 fact·질문 answered·실행 running 상태를 같은 트랜잭션으로 저장. 모델/도구 예산과 규제·지도 캐시 복원. 대기 시간은 활성 시간에 미포함 |
| 종료 | 전체 300초·모델 26(설계 안전 상한 28 이하)·입력 160k/출력 24k·도구 40. 초안 decision 최대 여덟 회, 마지막 회는 제출만 허용. 반복/상한 시 코드 점수와 유효 초안으로 종료 |
| 결과 | 코드 90점+L 10점 재계산, fact 슬롯을 코드로 렌더링, 초안 저장. PR5는 평가 미실행을 명시하고 PR6에서 평가·최종 반영 |
| 저장 | agentic_runs / agentic_reports / advisor_consults / agentic_questions 추가. 원문·facts·scores는 기존 PR2~4 계약 재사용 |
| 독립 리뷰 | 질문 재개 캐시 유실, 요인 복제로 등급 상승, 답변 저장 실패 경계를 회귀 테스트로 고정 |

#### PR5 승인 실실행 관찰 (테헤란로 152, 2026-10-14)

| 항목 | 관찰 |
| --- | --- |
| 실행 결과 | 수집 단계에서 AGENTIC_FAILED, 약 47.34초. 유동 ok·개폐업 partial 저장, 상권 분석 결과는 미저장 |
| 모델/도구 | 모두 영 회. 따라서 입력/출력 토큰 영, 자문·L 판단·최종 Top 5 없음 |
| 원문 | 상권 응답 63개·개폐업 13개·유동 15개·상주/직장 파일 각 하나 저장. 부분 스냅샷으로 유지 |
| 추가 점검 | 저장 원문 대역으로 상권 계산·parse_data 계약 검증은 partial 결과로 통과. 최초 실패 원인은 확정하지 못함 |
| 계측 한계 | 일회성 결과 요약에서 테이블명을 잘못 사용해 최초 예외 유형 계측을 잃음. DB만 다시 읽었으며 추가 외부/유료 호출 없음 |
| 검증 | ruff check·format·mypy(153개 소스)·전체 unittest 867개·카탈로그 check 통과. 실서비스 모델 루프 연결 검증은 미완료 |

결과·원문은 ignored cache에만 보관한다. 실제 모델 루프 재검증은 별도 승인 실행으로 남기며, 이번 관찰 후 프롬프트를 조정하지 않았다.
