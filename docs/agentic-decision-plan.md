# Agentic decision 구조 설계안 v0.2

작성: 2026-10-13 · 개정: 2026-10-14 · 대상: perf/decision · 상태: 검토 반영·1차 구현 계약안, 코드 미적용.
기준: [채점표 v0.8](decision-prompt-rubric.md)의 **확정 규칙**. 로드맵: 51업종 완료 → 채점표 완료 → **3 구조 설계** → 4 구조 구현 → 5 decision 프롬프트 → 6 평가자 4명 → 7 실테스트·효율화.

사용자가 확정한 흐름·SQL 방식·fact_id·L 역할은 고정한다. 아래 스키마·도구 명칭과 권한은 계약 PR 합의 대상이다. 초기 예산·CSV 원천·평가 실패 제공 정책은 사용자 결정으로 확정했으며 실테스트 후 조정한다. 이번에는 승인된 Sonnet 게이트웨이 확인만 최초 1회·재시도 1회 시도했다. 그 밖의 외부 API·LLM 호출은 없다.

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
             SQLite 최종 저장 → 기존 GET/진행 이벤트 + v2 결과
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

'삭제'는 새 경로 검증 뒤 신규 실행에서 제거한다는 뜻이다. 과거 DB·GET·질문 재개 호환 코드를 동시에 지우지 않는다.

| 구분 | 현재 코드·위치 | 제안 |
| --- | --- | --- |
| 재사용 | `backend/app/agents/orchestration/graph.py:40` | LangGraph·병렬 분석·대기/재개 유지, 그래프 연결은 새 단계로 교체 |
| 교체 | `backend/app/agents/orchestration/deps.py:50`, `state.py:43` | GraphDeps에 조회/저장 포트·actor별 예산, state는 스냅샷·draft·review 참조 중심 |
| 재사용/확장 | `backend/app/execution/policy.py:38`, `backend/app/services/execution_policy.py:1`, `backend/app/llm/budget.py:16` | 기존 정책 호환 경로와 예약 호출·저장 오류 전파 유지, 도구/토큰/실제 HTTP 한도 추가 |
| 교체 | `backend/app/agents/orchestration/nodes/decision.py:33`, `decision/agent.py:113`(agents 아래) | final/ask_specialists/supplement/map_lookup/ask_user 판정 JSON을 도구 루프로 교체 |
| 삭제(신규 경로) | `backend/app/agents/decision/context.py:64`, `agent.py:508` | 전체 분석/digest·브리핑 삽입 제거. 시스템 지시문·도구 스키마는 고정 |
| 삭제/대체 | `backend/app/agents/specialists/agent.py:138`, `agent.py:185`; `orchestration/nodes/deliberation.py:43`(agents 아래) | write_brief·분야별 재분석 자문 제거, _run의 루프·주입 패턴만 검토 재사용 |
| 재사용/분리 | `backend/app/agents/map_analysis/agent.py:125`, `client.py:52`, `mapping.py:64` | 비동기 검색·캐시·거리·관측 검증 재사용. judge_matches의 숨은 LLM 호출은 기본 map_search에서 분리 |
| 교체/재사용 | `backend/app/agents/orchestration/supplement.py:39` | 일반 supplement 판정 분기 제거. 수집 실패·부분 자료·재계산 adapter는 서비스에서 재사용 |
| 교체/재사용 | `backend/app/agents/evaluators/agent.py:175`, `orchestration/nodes/evaluation.py:18`(agents 아래) | 4역할·실패 격리·병렬 실행 유지, digest 입력과 추가 행동 요청을 읽기 도구 검토로 교체 |
| 재사용/확장 | `backend/app/evidence/index.py:58`, `index.py:203`, `citations.py:36` | 업종 소유·citable·경로 검증을 사실 등록에 재사용. path 직접 인용은 legacy 전용 |
| 재사용/확장 | `backend/app/db/repository/results.py:27`, `questions.py:162`, `evaluations.py:21`, `backend/app/db/schema.sql:3` | 요청·시도·질문·결과·평가 이력 보존, 원문/facts/scores/호출 감사 테이블 추가 |
| 재사용/확장 | `backend/app/services/analysis.py:215`, `persistence.py:50`, `views.py:16`, `mocking.py:18` | 서비스 트랜잭션·재개·목업·GET 조립 유지, snapshot 포트와 v2 응답 추가 |
| 재사용/이관 | `backend/scripts/rubric_dryrun.py:72`, `:322`, `:404` | score_item·summarize를 운영 순수 채점 엔진으로 이관. CLI·민감도·표본 수집은 scripts에 유지 |
| 재사용 | `backend/app/agents/commercial_area/industries.py:23`, `metrics.py:92`; `business_lifecycle/formatter.py:163`(agents 아래) | 소분류 우선 51업종 매핑·결정론적 지표·한국어 formatter 유지 |
| 유지/PR 제안 | `backend/app/schemas.py:80`, `:94`, `:486`, `:570` | AnalysisTask/AgentAnalysis 유지, Decision 입출력은 아래 v2 안을 팀 PR에서 합의 |
| 유지/확장 | `docs/API_CONTRACT.md:224`, `:244`; `backend/app/api/v1/responses.py:29` | 폴링·seq 유지, stage와 버전별 결과 계약 추가 |

현재 상주·직장은 동봉 CSV 스냅샷을 사용한다(`backend/app/agents/floating_population/population.py`). 그림의 인구 수집은 원천 adapter 경계다. 기존 CSV를 API에서 갓 받은 자료처럼 표시하지 않는다. 우선 file 원천도 같은 원문 저장 계약으로 가져오며, 실시간 API 전환은 열린 질문이다.

## 2. 데이터 저장 설계(SQLite)

기존 테이블을 지우지 않는 추가 마이그레이션이다. 1차는 요청당 원문 snapshot_id **1개**를 유지한다. run_id·분석/판단 attempt는 실행·재개 기록이며 새 원문 스냅샷을 만들지 않는다. 부모 스냅샷·기초 자료 재수집은 2차로 미룬다. 원문은 매 페이지 수집 직후 저장하고 모든 수집이 끝나야 계산하는 강제 장벽 대신, 수집 완료/부분 스냅샷을 명시한 뒤 계산한다.

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

새 analysis_mode는 기존 analysis_requests의 CHECK 허용값에 없으므로 PR2에서 보존 마이그레이션(테이블 복사·FK/행 수 검증)을 함께 한다. 기존 모드의 값을 임의로 바꾸지 않는다.

기존 analysis_requests·agent_results·decision_results·question_sessions·analysis_events는 계속 쓴다(`backend/app/db/schema.sql:3`, `:27`, `:43`, `:145`, `:163`). 사실 저장·호출 감사·최종 채택 실패는 서비스 오류로 전파한다. 진행 화면 이벤트의 저장 실패만 기존처럼 격리한다(`backend/app/services/persistence.py:36`).

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
| map_search | {industry_code:Code **또는** facility_code:KakaoEnum, radius_m:int 50~500, limit≤20}. 좌표는 현재 Site 고정 | {observation_id,places[{place_id,name,category,distance_fact_id,match_status,fact_ids}],coverage,has_more}. 동종 미확인은 명시 | common + MAP_UNAVAILABLE/MATCH_UNCERTAIN | 요청 전체 서로 다른 검색 6개·지도 HTTP 20회·각 검색 15초 | decision·평가자 |
| check_regulation | {}. 현재 좌표·저장된 구역 snapshot 사용 | {status,queried_at,contains_verified,zones,fact_ids,industry_restrictions,limitations}. 건축물대장은 현재 unavailable | common + REGULATION_UNAVAILABLE | 실제 구역 조회 요청당 1회, actor 호출 각 1회·캐시 공유 | decision·평가자 |
| ask_advisor | {question:string≤800자,fact_ids:[FactId]≤12,industry_codes?:[Code]≤3} | {consult_id,status,interpretations[{claim,fact_ids,conditions,confidence}],missing_facts,limitations}. 점수 없음 | common + ADVISOR_UNAVAILABLE | 요청당 최대 2회·각 45초·출력≤1,000토큰 | decision만 |
| ask_user | {questions:[{field:기존 QuestionField,question:string≤200자,reason:string≤200자}]≤3} | {question_session_id,status:waiting_for_input}. 답변은 재개 시 typed user facts | common + QUESTION_NOT_ALLOWED/ALREADY_ANSWERED | 요청당 1세션·질문≤3. 기존 답변 항목 재질문 금지 | decision만 |
| submit_draft | {phase:draft/final,report:ReportProposal,review_resolutions?:[ReviewResolution]}. 점수 숫자 없음 | {report_id,validation_status,rendered_preview_ref,score_snapshot_id}. final도 같은 구조화 제출 도구 | common + REPORT_INVALID/L_EVIDENCE_INVALID/REVIEW_UNRESOLVED | draft 1회·final 1회, 스키마 오류 교정 총 1회(예산에 포함) | decision만 |
| submit_review | {draft_id:ID,verdict:agree/conditional/oppose,issues:[ReviewIssue]≤4} | {review_id,status}. actor는 실행기가 고정 | common + DRAFT_MISMATCH/INVALID_REFERENCE | 평가자 각 1회·지적별 근거 fact_id≤3 | 평가자만 |

common 오류는 INVALID_ARGUMENT / SOURCE_UNAVAILABLE / SNAPSHOT_MISMATCH / BUDGET_EXCEEDED / TIMEOUT / DUPLICATE_CALL이다. 부분 결과는 partial·truncated·누락 필드를 표시하고, '조회 범위 내 확인한 수'만 인용한다. 계약 검증·fact 저장·호출 감사 저장 실패는 일반 error ToolReply로 숨기지 않고 실행 실패로 전파한다(AGENTS.md 3).

map_search는 기존 PlaceClient·카테고리·거리·MapObservation을 재사용한다. 검색에 별도의 지도 LLM이 자동 발생하지 않도록 기본 경로는 결정론적 일치만 쓰고 애매한 업종은 match_status=unknown이다. 기존 judge_matches 캐시를 쓸 때도 모델·버전·확신도 출처를 남긴다. 추후 LLM 분류가 필요하면 별도 명시 예산을 합의한다(`backend/app/agents/map_analysis/mapping.py:64`). 지도 조회 0건·has_more를 실제 동종 가게 없음으로 확대하지 않는다.

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

| 환경변수(이번 .env.example에는 이름만) | 비었을 때 실제 기존 fallback |
| --- | --- |
| ADVISOR_LLM_MODEL | ELICE_MODEL |
| ADVISOR_LLM_BASE_URL | ELICE_BASE_URL |
| ADVISOR_LLM_API_KEY | ELICE_API_KEY |
| ADVISOR_LLM_MAX_TOKENS | LLM_MAX_TOKENS, 없으면 기존 기본값 |
| ADVISOR_LLM_TIMEOUT_SECONDS | LLM_TIMEOUT_SECONDS, 없으면 기존 기본값 |

모델·인증·주소는 ELICE_*를, 길이·시간은 기존 LLM_*를 사용한다. 실제 .env나 운영 설정은 이번에 바꾸지 않았다. Sonnet로 시작하려면 운영자가 ADVISOR 역할 설정에 원하는 모델과 그 모델 접근 가능한 연결을 지정해야 한다. 같은 계열 fallback도 기록하며 임의로 다른 모델을 재호출하지 않는다.

### 승인된 게이트웨이 일회성 확인 (2026-10-14)

기존 `app/llm/client.py:131` 경로의 stream=True·include_usage=True를 사용했다. 기본 json_object만으로 스키마 지원을 주장하지 않도록 일회성 메모리 wrapper에서 response_format=json_schema(strict=True)를 지정하고 {ok:true}를 요청했다. max_completion_tokens=200·timeout45초·SDK 자동 재시도0. 확인 코드는 저장소에 남기지 않았다.

| 확인 | 결과 |
| --- | --- |
| 모델 응답 성공 | 실패: 최초·허용 재시도 모두 LLM_REQUEST_ERROR |
| 스트리밍 | 재시도 HTTP200·text/event-stream 도착, 정상 chunk 0개. 스트리밍 추론 성공 아님 |
| usage | 반환 없음. 입력·출력 토큰/과금 미확인 |
| JSON Schema | 요청했으나 모델 접근이 거절돼 응답 지원 여부 미확인 |
| 시간 | 최초 0.859초·재시도 0.640초 |
| 서버 오류 | Model 'anthropic/claude-sonnet-5' is not allowed. Allowed: ['gpt-5.6-terra', 'openai/gpt-5.6-terra'] |

ADVISOR 역할의 별도 endpoint/key가 없어 공통 ELICE 연결로 확인했다. 이 연결의 모델 허용 목록 문제이며 Sonnet 자체의 JSON/스트리밍 비호환으로 단정하지 않는다. 별도 Sonnet용 ADVISOR_LLM_BASE_URL/API_KEY 설정 후 다음 승인된 시험에서 재확인해야 한다. 키·URL 원문은 출력·문서에 남기지 않았다. 재시도 한도를 소진했으므로 추가 호출하지 않았다.

## 6. 평가자 4명

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

사용자 목표에 따라 평가자 전원 동의라도 decision의 최종 제출 단계는 수행한다. 현재는 no_comments/all_failed면 final 호출을 건너뛸 수 있으므로 바뀌는 동작이다(`backend/app/agents/orchestration/nodes/evaluation.py:70`).

## 7. 보고서 출력 계약

ReportProposal={summary_segments,candidates≤5,excluded_candidates≤5,limitations_segments,L_records,review_resolutions}. Candidate={industry_code,reasons_segments,risks_segments,confirmation_conditions_segments,fact_ids}. 점수·배지·금지·순위·숫자 값 필드는 모델 제안에 받지 않는다. 서버가 registry·v0.8 scores로 계산해 ReportV2에 붙인다.

| 필드 | ReportV2 서버 출력 |
| --- | --- |
| 버전 | schema_version=2.0, rubric_version=v0.8, tool_contract_version, request_id, run_id, report_id, score_snapshot_id, evidence_snapshot_ids |
| 검토 후보 | code·name·코드 point/90 + L point/10, L 대상/선정 이유·review_state. 대상 밖 unknown=판단 미검토, 대상 안 근거 부족 unknown=판단 미확인. A/B/H·비율·coverage·배지·G |
| 근거 문장 | segments=[{type:text,text},{type:fact,fact_id,format:count/percent/rate/distance/text}]. 모델은 값 복사·산술 금지 |
| L | 새 요인·fact_id·호출 도구·자문 반영·grade/unknown. 새 근거가 없으면 등급 생성 금지 |
| 검토 상태 | 평가자 4명 상태·지적·수용/일부/기각 로그, review_completeness |
| 확인 조건 | 건축물 용도 등 미확인·자료 시점/공간 한계·partial·예산 제한 |

숫자는 서버 renderer가 fact.value·단위로 채운다. grade enum·업종 코드·고정 시간대/연령 라벨은 구조화 제어값이며 측정 숫자 복사와 구분한다. 모델 자유문장에 인용 없는 수치가 있으면 거절한다. 기존 render_cited의 검증 철학은 재사용하되 `{i}`·path 문자열이 아닌 typed fact 슬롯이 새 계약이다. 원문 숫자를 텍스트에 붙이는 우회도 검사한다.

최종 배열은 전체 51업종 채택 점수의 원점수 하한→coverage→코드로 재검증한다. L 검토는 상위10+추가2로 제한하고 대상 밖은 unknown·판단 미검토로 남기며 '전체 업종의 L을 검증했다'고 하지 않는다. Top 5에 보류/조건부가 있어도 추천처럼 표시하지 않는다.

## 8. schemas.py 변경안 — 팀 PR 합의 대상

이번에는 파일을 수정하지 않았다. AGENTS.md 1에 따라 아래는 구현 전 팀 계약 PR에서 먼저 합의한다. v1 저장 결과를 v2 모델로 재검증해 과거 데이터를 깨뜨리지 않는다.

| 모델 | 제안 변경·이유 | 호환 |
| --- | --- | --- |
| AnalysisTask / AgentAnalysis | 기존 공통 필드 유지. raw_snapshot_id·calc_version·code_score_snapshot_id는 우선 data 내부 metadata로 추가 | 기존 3종 agent·서비스 유지 |
| DecisionRequest | 별도 AgenticDecisionRequestV2: request/run/site/snapshot refs·rubric/tool version·capabilities·remaining_budget. analyses 전체 필수 전달 제거 | 기존 DecisionRequest(:486) 유지, 모드별 dispatch |
| AnalysisMode | agentic_decision 신규 값, DB analysis_requests CHECK·mode별 GraphDeps/재개 검증도 같이 변경 | single_decision/multi_agent 저장 이력 reader 유지 |
| Evidence | FactReferenceV2={fact_id}; scope·source는 registry 권한으로 검증 | 기존 Evidence agent/path(:504)는 legacy renderer 전용 |
| IndustryAssessment / DecisionContent / DecisionResult | ReportProposalV2·ReportV2·ScoreSummary·LRecord·FactSegment. 단일 score 대신 코드/L·구간·coverage·badge | 기존 score/recommendations만으로 v2 의미를 억지 변환하지 않음. 새 schema_version 2.0 |
| Evaluation / EvaluationLogEntry | FactReference 기반 ReviewIssue·ReviewResolution, draft/revision IDs·failed 상태 | 기존 평가 이력 그대로 조회 |
| QuestionSnapshot | QuestionSnapshotV3: run/snapshot/score/draft refs·도구 hash·예산·채택 fact 목록·질문 세션 | 기존 :257/:680 reader 유지. 검증된 명시 마이그레이션만 |
| Tool·advisor | ToolReply/Error·도구 입력 union·AdvisorAnswer 신규. 모델 원문은 검증 후 저장 | 런타임 schema 버전 고정 |

프롬프트는 이 계약의 명칭·입출력·권한만 참조한다. 내부 DB 열이나 Python 함수명이 바뀌어도 tool_contract_version=1 계약이 같으면 프롬프트를 바꾸지 않는다.

## 9. 프론트·API 영향 — GET v2는 1차, 진행 화면·이벤트 v2는 2차

현재는 폴링 events seq·GET 상세를 쓰며 SSE가 아니다(`docs/API_CONTRACT.md:210`, `:224`). 현재 진행 화면에는 mock 시뮬레이션 연결 TODO가 남아 있어 백엔드 stage만 추가해 실제 화면이 연결됐다고 주장하지 않는다(`frontend/app/analysis-progress/page.tsx:93`, `frontend/lib/hooks/useAnalysisProgressSimulation.ts:17`).

| 단계 | stage/event·detail 제안 | 기존 호환 |
| --- | --- | --- |
| 원문 수집 | 기존 agent stages + raw_capture completed {source,snapshot_id,partial} | 기존 agent completed 유지 |
| 계산/채점 | metrics/scorecard started·completed {rubric_version,industry_count} | unknown stage는 일반 '분석 중'으로 표시 |
| 판정 도구 | decision started/completed {phase:draft/final}; decision.tool completed {tool,status} | actor 원문·SQL·키·fact 값은 진행 이벤트에 안 넣음 |
| 자문 | advisor started/completed {status} | consult.*는 legacy 실행에만 유지 |
| 평가 | evaluate.examiner/founder/customer/landlord_advocate started/completed {status,issues_count} | 기존 ID 표시 유지 |
| 질문/종료 | questions waiting, run completed/failed/draft_available | pending/running/waiting_for_input 의미 유지, draft_available은 계약 PR에서 추가 |

GET /api/v1/analyses/{id}는 기존 envelope(status/site/result/error 등)를 유지한다. 새 실행은 analysis_mode=agentic_decision, result.schema_version=2.0와 scorecard_summary·review·advisor 요약·확인 조건을 추가한다. 기존 source_analyses 거대 배열은 v2 모델 입력/기본 결과에 재삽입하지 않는다. 과거 v1 결과는 저장 당시 그대로 반환한다(`backend/app/services/views.py:16`, `:58`; `backend/app/api/v1/responses.py:29`).

1차 PR6은 opt-in agentic 모드와 GET v2까지만 준비하며 기존 프론트의 일반 경로는 유지한다. 신규 화면·버전별 프론트 adapter·실제 진행 폴링/이벤트 v2는 2차 PR7에서 연결한다. 위 stage 표는 2차 계약 목표다. 기존 recommendations/not_recommended 필드에 보류를 추천처럼 포장하는 fallback은 없다. 호출 원문·원자료는 내부 DB에만 두며 GET에는 필요한 설명·인용 facts만 권한 확인 후 노출한다. 이벤트 순번·폴링·질문 answers·retry URL은 유지하고, 재시도는 저장 자료·예산을 재사용한다.

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

계측은 role별 호출·input/cached_input/output·HTTP·도구 응답 크기·SQL ms·지연 p50/p95·L unknown·평가 실패·보고서 검증 실패를 저장한다. 토큰 절약이 정확도 하락을 숨기지 않게 동일 주소·같은 snapshot으로 기존/신규를 비교한다. 금액 환산은 실제 model별 요금을 설정한 뒤 별도로 하며 이번 문서에서 가격을 가정하지 않는다.

## 11. 1차 구현 계획 — 4단계용 PR1~PR6

| PR | 1차 범위 | 목업·고정 자료 검증 |
| --- | --- | --- |
| PR1 계약 | schemas v2·도구 contract v1·권한·결과·질문 재개·L 대상 상위10+추가2 | 추가 필드·cross-request 거절, 코드 순위 선정·추가 사유·대상 밖 판단 미검토, v1 golden GET |
| PR2 원문 저장 | 요청당 snapshot 1개·raw capture·CSV file 원천·조회 뷰·계보·보존 마이그레이션. 기초 재수집·부모 체인 없음 | 제외 업종 원문 보존, 중복/누락, 같은 snapshot 추가 관측 append-only·cutoff, DB 실패 전파·기존 DB 유지 |
| PR3 facts·코드90 | v0.8 순수 엔진·registry·scores·기준선/프로필 버전 | L unknown·C1 sqrt·n.a. 분모·90/10·G 금지·계보. 현재8곳9/1/377/21을 대표 fixture로 재현 |
| PR4 읽기 도구 | score/facts/raw SQL·자동 등록·지도/규제 wrapper. **mode=ro + SQLite authorizer + 행/시간 상한**, 1차 단일 SELECT | 쓰기·DDL·PRAGMA·ATTACH·직접 table/cross-request·WITH/CTE 거절, 50행/2초, 집계 citable=false, 지도/규제 unknown |
| PR5 decision·보조 | LangGraph 도구 루프·상위10+추가2의 L·초안/최종·예산·질문 재개·ADVISOR 역할 설정 | 묶음 L·대상 범위 초과/추가 근거 누락 거절·반복 금지·자문 실패에도 단독 채점·실제 모델/계열 기록·예산 재개 |
| PR6 평가·보고서·GET v2 | 4명 read 권한·review·반영·fact renderer·final·opt-in GET v2 | 일부/전체 평가 실패는 평가 미완료 표시, L 중복/코드점수 변경 거절, 수용/일부/기각, 숫자 슬롯, v1 GET 유지 |

1차에서는 기존 DB reader·기존 신규 실행 경로·프론트를 삭제하지 않는다. 운영으로 이관한 채점은 scripts가 같은 엔진을 import하되 시험 CLI는 유지한다. decision의 실제 프롬프트는 구조 구현 계약/도구 뒤 로드맵5단계, 실제 평가자 페르소나는 로드맵6단계에서 작성한다. PR6은 런타임·주입 목업·GET 계약 범위다.

### 나중 작업 — 2차

| 항목 | 범위·선행 조건 |
| --- | --- |
| SQL AST·CTE | 범용 AST·승인 뷰 이름 가림 검사 후 CTE 허용 검토. 1차 authorizer를 제거하는 대체가 아님 |
| 재수집·부모 snapshot | 동일 요청의 기초 자료 재수집·부모/자식 체인·채택 snapshot 선택·동일 조건 재계산 |
| PR7 진행 이벤트 v2·프론트 | 9절 stage·실제 폴링·질문/재개·배지/구간/L 미검토 UI·v1/v2 adapter |
| PR8 기존 경로 정리 | 신규 경로 실테스트 후 브리핑·전문가 되묻기·거대 context 신규 실행 제거. 과거 이력 reader 보존 |
| 모델별 사용량 기록 | `app/llm/budget.py` 사용량 기록에 요청 모델명·응답 실제 모델명을 추가한다. 현재 모델명이 저장되지 않아 과거 실행의 사용 모델을 식별할 수 없음 |

구현 PR은 ruff·format·mypy·unittest·catalog check, 프론트 PR은 format/lint/build를 검사한다. 실 API·유료 실행은 별도 승인 범위에서만 진행한다.

## 12. 확정 결정과 남은 질문

| 확정 결정 | 내용 |
| --- | --- |
| 초기 예산 | 전체300초·모델26/상한28·누적 입력160,000/출력24,000·도구40. 실제 테스트 후 조정 |
| 상주·직장 원천 | 현재 분기 CSV를 source_type=file로 저장하고 파일 해시·시점을 표시 |
| 평가 실패 | 일부·전체 실패 모두 평가 미완료 표시와 함께 기계 검증된 결과 제공. 동의로 간주하지 않음 |
| 보조 모델 | Sonnet5 시작·다른 계열 권장·실제 사용 모델/계열 기록. 변경은 환경변수. 자문 실패와 L 채점 분리 |
| L 검토 범위 | 코드 하한 상위10+근거 있는 추가2, 대상 밖 판단 미검토. 최종 정렬/배지는 v0.8 유지 |
| 현재 보존 | 원문·도구 기록 전부 보존, 임의 삭제 안 함 |

| 남은 사용자 확인 | 필요 사항 |
| --- | --- |
| 운영 보존 기간 | 지금은 전부 보존. 운영 배포 전 원문·도구·임대인 답변 기록의 보존/삭제 정책 결정 |
| Sonnet 연결 접근권한 | 현재 공통 ELICE 연결은 terra 모델만 허용. Sonnet용 ADVISOR_LLM_BASE_URL/API_KEY를 안전하게 설정한 뒤 별도 승인된 호환 확인 필요. 채팅에 키를 보내지 않음 |

schemas/API 계약은 위 제품 결정과 별도로 팀 PR 합의 대상이다. 1차 SQL은 AST를 미루는 대신 CTE까지 허용하지 않는 보수적 범위이며, 확장 전 안전 검사를 추가한다.
