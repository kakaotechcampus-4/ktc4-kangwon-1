# Agentic decision 구조 설계안 v0.5 — 로컬 자료·전체 업종 L

## 숫자 식별자 검사 보완 (2026-10-15)

- `app/text.py` 한 곳에서 업종 코드 형식·`f_`와 8자리 16진수 fact 별칭·독립된 분기 코드를 제외하고 숫자를 검사한다. 업종의 카탈로그 존재 검증은 이 함수에서 하지 않는다. 측정값·비율·개수와 기존 유니코드 숫자 검사는 유지한다.
- report 세 곳·평가자·L note는 같은 함수를 계속 사용한다. 프롬프트·예산·자료 DB는 변경하지 않는다.
- 기존 평가자 오류 재제출 두 회는 **이미 처리됨**. 빈 근거의 레코드별 거절은 기존에 없으므로 보완한다. 유효 지적을 보존하고 거절 지적 ID·이유를 반환하며, 수정 제출이 완료되기 전에는 평가 완료로 기록하지 않는다.
- 게이트 통과 후 홍대 공개 API 실테스트 한 회만 실행·녹화하고 결과와 무관하게 푸시 전 점검을 다시 한다. 모든 푸시 게이트가 통과할 때만 이 브랜치를 일반 푸시한다.

작성: 2026-10-13 · 개정: 2026-10-14 · 구현 통합 브랜치: feat/agentic-decision · 상태: **로컬 읽기 도구·단일 공개 API·평가자 연결 완료, 삭제·리팩토링 후 검증 중**.
기준: [채점표 v0.8](decision-prompt-rubric.md)의 확정 규칙. 코드 90점 + decision의 L 10점, 단일 모드·fact_id·평가자 네 명은 유지한다.

사용자 결정: 상가·개폐업·유동·상주·직장은 요청 시 API 수집하지 않는다. 수동 분기 갱신으로 서울 전체 자료를 미리 적재하고, 요청은 가진 최신 활성 버전을 SQL로 읽는다. 카카오 지도(기존 주소 변환 포함)·V-World 규제만 실시간이다. RAG·벡터 검색은 사용하지 않는다.

v0.4 최초 조사는 문서만 수정했다. 이번 LD1·LD2는 사용자 승인 범위의 서울 API 확인/적재와 자료 DB 코드·테스트·.env.example을 추가한다. schemas.py·.env·규제 코드와 요청 경로는 바꾸지 않으며 LLM 호출은 없다. 다운로드 사이트는 새로 조회하지 않았다. 문서 끝의 PR2~PR5 메모는 **이전 구현·실패 기록**이며 v0.4 구현 지시가 아니다. 최초 실패 원인 추적은 종료한다.

## 1. 한 장 요약

현재 실행은 주소 → 고정 로컬 자료 버전 → facts·코드 90점 → decision 읽기 도구·L →
평가자 네 명 병렬 → 피드백 한 번 → 최종 fact 렌더링이다. 옛 브리핑·전문가·그래프는 삭제한다.
실행 모드는 하나이며 요청 DB 버전은 4다. 자료 DB는 별도이며 초기화 대상이 아니다.
운영 예산은 입력 400k·출력 60k·모델 40회·600초·호출당 출력 16k다.
L은 전체 51업종이며 submit_l 분할 제출 → 재계산 → submit_draft 순서로 분리한다.
역할별 예산·이전 홍대 실측·구현 단계는 [전체 L 구현 계획](whole-industry-l-plan.md)이 현재 기준이다.
평가자는 각 입력 40k·출력 5.5k·네 호출을 보장하며 최종 두 호출은 decision 몫에서 보존한다.
측정은 서버 인자로 켜며 API 본문에서 바꿀 수 없다. 공간 요건 CSV는 미검토 초안이며
공간 비교 fact에 초안·확신도 표시를 보존하며 미확인·해당 없음은 L 가감점 근거로 쓰지 않는다.
정리 범위·단계 검증은 [cleanup-plan](cleanup-plan.md), 프롬프트 변경 이유는
[prompt-change-notes](prompt-change-notes.md)를 기준으로 한다.

```text
[요청과 분리: 운영자 수동 분기 갱신]
파일 / 분기 API 일괄 수집 → 비활성 자료 버전 적재 → 필드·행·계산 검증
 → release의 원천 버전 목록을 한 트랜잭션으로 활성화 (실패 시 이전 release 유지)

[요청]
주소 → 기존 카카오 주소 변환 → 활성 release/원천 버전 목록 고정
 → 로컬 SQL: 반경 점포·비교 범위·상권 선택·개폐업 12분기·유동 5분기·상주/직장
 → 기존 계산·formatter·채점기 → 작은 facts/scores·snapshot 저장
 → decision: 고정 프롬프트 + 계산 조회 / 제한된 로컬 SQL / 지도 / 규제
     ↔ 필요할 때만 보조 모델 자문 / 임대인 질문
 → L 10점·초안 → 평가자 네 명 → 피드백 반영 → 코드 검증·최종 보고서
```

snapshots에는 원문을 복사하지 않고 **release_id + 사용한 자료 버전 ID 목록**과 카탈로그·프로필·baseline·계산 버전을 고정한다. 질문 재개·평가·초안 수정에도 이 목록을 사용한다. 갱신 중에도 요청은 시작한 버전을 끝까지 읽는다.

### 1.1 원천 조사 — 로컬 근거만

확인값은 2026-10-14 로컬 파일/저장 응답 기준이다. 서울시 일괄 파일 제공 여부를 모르면 없다고 단정하지 않고 API 일괄 수집을 준비한다.

| 원천 | 일괄 파일·형식·갱신 | 서울 전체 규모 | 현재 필드 호환·차이 | 근거 |
| --- | --- | --- | --- | --- |
| 소진공 상가(상권)정보 | **확인**: 202606 서울 UTF-8 CSV, 분기 스냅샷. 행 안에 분기 열은 없음 | 실파일 554,092행·301,889,640B(287.90MiB), 39열 | Store 파서의 14필드 전부 대응. 한글→API 영문 열 매핑. CSV에는 표준산업분류·층/호 등 추가 열도 있으며 적재 때 보존. reference_date/폐업 상태는 현재 사용 자료에서 확인 못 함 | `backend/scripts/build_density_baseline.py:236`, `commercial_area/client.py:189`, `docs/decision-prompt-rubric.md:413` |
| 점포·개폐업(상권) `VwsmTrdarStorQq` | **파일 제공/파일 열 미확인**. 현 코드 JSON API의 분기·상권 조회는 확인됨. CSV/Excel이 있으면 필수 열 검증 후 우선 사용 | 상권 1,650 × 서울 업종 최대 100 = 최대 165,000행/분기(상한 추정). JSON 40~80MiB/분기 추정, 기존 기본 분석은 12분기 | API 필수 14열: 분기, 상권 종류/코드/이름, 서울 업종 코드/이름, 점포·유사업종·가맹점 수, 개업/폐업 수·비율. 파일이 없으므로 완전 호환은 아직 판정 불가 | `business_lifecycle/client.py:17,130`, `config.py:21` |
| 추정유동(길단위인구-상권) `VwsmTrdarFlpopQq` | **파일 제공/파일 열 미확인**. JSON API 분기별 서울 전체 조회는 기존 코드로 확인 | 과거 기준선 1,648행/분기, 최근 영역 응답은 약 1,650. JSON/CSV 약 1~3MiB/분기 추정. D4 포함 최근 5분기 유지 | 분기·상권 코드, 총량·남/여, 시간대 6·요일 7·연령 6열이 필수. 통행량은 **분기 합계**이며 주거/직장 인원과 단위가 다름 | `floating_population/config.py:17`, `client.py:92`, `models.py:173`, `scripts/measure_flpop_baseline.py` |
| 상주 `VwsmTrdarRepopQq` | **로컬 CSV 확인**. 공식 일괄 파일 제공 여부는 미확인. 분기 라벨이 있지만 README 실증에서는 값이 여러 해 동일 | resident.csv: 2026Q2, 1,633행·137,365B. 기존 API 전체는 약 36,000행/22분기 | 현재 파서 필수 11열은 모두 있음: 분기·상권 코드/이름·총량·연령 6·가구 수. 현재 CSV는 `write_snapshot`이 남긴 **축소본**, 전체 API 열을 보존한 원문은 아님 | `floating_population/README.md:305,322`, `population.py:51`, `models.py:151`, `scripts/fetch_population_snapshot.py:1` |
| 직장 `VwsmTrdarWrcPopltnQq` | **로컬 CSV 확인**. 공식 파일 제공 미확인. 분기 라벨과 실제 값 갱신을 구분 | worker.csv: 2026Q2, 1,641행·122,307B. 기존 API 전체 약 36,000행/22분기 | 현재 파서 필수 10열 전부 있음: 분기·상권 코드/이름·총량·연령 6. 총가구 수는 없음. 역시 축소본 | 동일 README/스크립트, `models.py:151` |
| 상권 영역 SHP | **로컬 파일 확인**: shp/dbf/shx/prj/cpg. 현재 다운로드 제공 위치·갱신 주기는 미확인, 분기라고 단정하지 않음 | 1,650피처, 묶음 4,456,586B(4.25MiB); SHP 본체 약 3.47MiB | EPSG:5181, 폴리곤·대표점·RELM_AR·구/동 코드. DBF 10자 제한으로 `XCNTS_VALU`, `TRDAR_CD_N` 등 열명이 축약됨. API 중심점 응답은 폴리곤 대체물이 아님 | `business_lifecycle/config.py:19`, `area_resolver.py:139,148,335`, 실제 파일 헤더 |
| 영역 대표점/면적(보조) `TbgisTrdarRelm` | 패키지 `seoul_trade_areas.csv`에 code/name/kind/signgu/adstrd/x/y/area_m2 존재. API 서울 전체도 2페이지 확인 | CSV/SHP 약 1,650개, 기준선의 1,648개와 차이 있음 | 유동의 **기존 원 근사·면적 안분** 유지용. SHP의 중심·면적과 일치하면 같은 버전에서 제공; 불일치하면 별도 버전으로 고정하고 차이를 표시 | `commercial_area/data/seoul_trade_areas.csv:1`, `floating_population/client.py:86`, `models.py:96` |

상주·직장 갱신은 현재 `fetch_population_snapshot.py`가 두 API의 전 분기를 받아 최신 분기만 CSV로 남기는 방식이다. 새 적재기는 받은 전체 원본/열을 보존하고 필요한 분기를 로컬로 고른다. 분기 번호가 최신이라고 실제 인구 추정값이 갱신됐다고 표현하지 않는다.

**상가 CSV 호환 근거:** `backend/cache/rubric_samples/c1-evidence-report.md:17`와 `c1-density-audit.json`에서 8곳·주요 40개 밀도의 최대 배수 차이는 약 **1.014**. 전체 408조합에서 1.3배 이상/한쪽만 영인 사례는 없었다. 이는 그 파일·8곳의 증거이며 모든 분기·서울 경계까지 동일하다는 보장은 아니다. 500m 경계 점포 14개·API 기준일 null·폐업 상태 열 부재를 함께 기록한다.

### 1.2 파일 미확인 원천의 분기 일괄 수집 예산

모두 **갱신 스크립트에서만**, 요청 중 호출 영 회. HTTP 페이지당 1,000행은 기존 클라이언트 설정이다. 아래는 탐색·재시도 제외 추정이며 재시도도 일일 예산에 센다. 하루 10,000회는 사용자 지정 예산으로 비교한다. 기존 README의 10,000회는 소진공 API 설명이므로 모든 서울시 서비스의 실제 할당량을 같다고 단정하지 않는다.

| 원천 | 분기 갱신 HTTP | 최초 채우기 | 판단 |
| --- | --- | --- | --- |
| 상가 서울 CSV / SHP | 파일 사용이면 영 회 | 파일 수동 입수 | 상가 파일 대체 소진공 API 수집은 기본안에서 제외 |
| 점포·개폐업 | 서울 전체 분기 필터가 지원되면 최대 약 165회. **2026-10-14 승인 실호출로 분기 필터 확인** | 같은 조건이면 12분기 최대 약 1,980회 | 2026Q2 실응답 75,912행, 76HTTP. 다른 분기 수는 실행 시 총행 수로 산정 |
| 점포·개폐업 과거 방식(채택 안 함) | 현 코드처럼 상권별, 각 최대 100행이므로 약 1,650회/새 분기 | 12분기 약 19,800회 → 최소 이틀로 분할(재시도/다른 자료 포함 시 더 필요) | 하루 10,000 미만으로 체크포인트·예산 차단. 구/서울 집계 API로 상권 행을 대체하지 않음 |
| 유동 | 새 분기 약 2회 | 최근 5분기 약 10회 | 기존 서울 전체 분기 조회 재사용 |
| 상주·직장 | 분기 필터가 먹지 않는 기존 동작 기준 합계 약 73회(36+37) | 동일 약 73회, 받아 필요한 기간만 적재 | `fetch_population_snapshot.py:55` 동시 8·재시도 2회; 행 증가 시 `ceil(total/1000)` 재산정 |
| 대표점/면적 보조 | 약 2회, 파일/일치 SHP면 영 회 | 동일 | 공간 버전은 데이터 분기와 별도 관리 |
| S 서울 기준선(보조) `VwsmMegaStorW` | 기존 전체 2,200행·3회 | 동일 | `measure_lifecycle_baseline.py:27`의 **점포-서울시**. 상권별 `VwsmTrdarStorQq` 대체 불가 |

채택 방식은 **분기 전체 페이지**이며 상권별 수집은 사용하지 않는다. 2026Q2 개폐업은76회, 유동은약2회다. 초기12분기 호출 수는 각 분기의 총행 수로 산정한다. 상주/직장은 최초 동봉CSV라 영 회이며 전체 API 갱신 시약73회다. 아래 실제 적재 결과가 초기 추정보다 우선한다.

### 1.3 지난 91초의 구성과 페이지 크기

| 상권 조회 | 저장 응답 | page_size | 원문 저장 시각 범위 | 해석 |
| --- | --- | --- | --- | --- |
| 주소 500m | 6페이지 / 5,182점포 | 1,000 | 약 1.03초 | 모두 cache_hit=true, 새 HTTP 지연 측정값이 아님 |
| LQ 2km | 48페이지 / 47,096점포 | 1,000 | 약 25.09초 | 역시 캐시 원문 재복사 구간 |
| 강남구 전체 | 67페이지 / 66,269점포 | 1,000 | 약 62.15초 | 실제 갱신 수집·저장 구간. HTTP와 DB 시간을 따로 계측하지 않았음 |

이 범위들은 parse/대기와 다른 분석 병렬 구간을 포함하지 않아 정확한 91초 분해나 합산식은 아니다. page_size는 `commercial_area/config.py:39`, `client.py:308` 및 저장 args에서 **이미 1,000**이다. 더 크게 받을 수 있다는 근거는 없으며 이번에 확인 호출하지 않는다. 로컬 전환은 기본 반경·LQ·구 조회의 페이지 수를 요청 경로에서 없앤다.

### 현재 코드 분류

새 구조는 유일한 실행 경로다. LD6 전환 시 기존 모드·근거·저장 결과를 폐기하며 과거 결과·질문 세션을 읽는 코드는 만들지 않는다. 평가자 4명은 항상 실행한다. 개발 비용은 MOCK_MODE와 예산 상한으로 관리한다.

| 구분 | 현재 코드·위치 | 단일 모드 전환 범위 |
| --- | --- | --- |
| 재사용/교체 | `backend/app/agents/orchestration/graph.py:40` | LangGraph·주소·질문 재개 기반 유지. 분석 3종 입력 수집은 버전 고정 로컬 SQL로 교체 |
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

현재 상주·직장은 동봉 CSV를 사용한다. v0.4에서는 두 파일도 분기 자료 DB에 한 번 적재하고, 요청 시 파일을 다시 저장하지 않는다. 현재 코드 분류 표는 기존 경로의 출발점이며 원천 수집·계보 교체는 아래 v0.4 계획이 우선한다.

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

## 2. 데이터 저장 설계 — 자료 DB / 요청 DB 분리

### 2.1 자료 DB

`LOCAL_DATA_DB_PATH`(미지정: 사용자 홈/.chaeum/market_data.sqlite3) 한 개를 버전별 행으로 관리하고, 요청은 **mode=ro**로 연다. 갱신만 쓰기 권한을 갖는다. SQLite WAL로 이전 활성 자료를 읽는 동안 비활성 버전을 적재할 수 있다. 변경 중인 WAL DB에 `immutable=1`을 쓰지 않는다. 운영 배포 시 파일 위치·동시 작성자 정책은 별도 설정하며 이번에 .env를 바꾸지 않는다.

| 테이블 | 키·열 | 인덱스·규칙 |
| --- | --- | --- |
| data_versions | version_id, source, quarter(nullable), source_period, file_sha256, content_sha256, schema_version, mapping_version, loaded_at, row_count, state(staged/active/retired), archive_ref | 원천·분기·파일 해시·변환 버전 조합으로 동일 적재 판별. 다분기 파일은 분기별 자식 버전과 원본 해시를 연결. SHP에 없는 분기를 만들지 않음 |
| data_releases / release_versions | release_id, 원천 버전 목록, 활성 포인터, activated_at, validation_ref | 필요한 원천·기간이 준비된 release만 한 트랜잭션으로 활성화. 기존 release 목록은 불변 |
| stores | version_id, store_id, 원 대/중/소분류, service_industry_code(nullable), 상호·지점·주소·구/동, lat/lon, x/y, 나머지 원문 열 | PK(version_id,store_id), (version_id,구,업종), 위경도 범위 복합 인덱스로 시작. RTree는 측정 후 도입. 제외 업종 원문도 유지. `map_stores`/소분류 우선 규칙으로 **적재 시** 매핑 |
| lifecycle | version_id, quarter, trade_area_code, seoul_industry_code, 원문 14열 | PK(version_id,quarter,상권,서울코드), (상권,quarter), (quarter,서울코드). 비율 평균 금지 |
| floating | version_id, quarter, trade_area_code, 총량·남녀·시간대6·요일7·연령6·원문 추가 열 | PK(version_id,quarter,상권), (상권,quarter). 최근 5분기와 같은 상권 집합으로 YoY |
| resident / worker | version_id, quarter, trade_area_code, 현재 파서의 필수 열·원천에 있는 추가 열 | PK(version_id,quarter,상권). 상주만 가구 수. 받은 필드 전부 보존하고 필수 열 부족은 활성화 거절 |
| trade_areas | version_id, trade_area_code, 구/동·상권 종류, 대표점·면적, polygon/rings, bbox, CRS, geometry_hash | PK(version_id,상권), 상권 코드 인덱스와 저장 bbox. DBF 축약 열 어댑터. 포함 우선·300m 최근접 규칙 재사용 |
| coverage_groups | version_id, quarter, trade_area_code, 관측/명시적 빈 그룹/미확인, 원천 근거 | 전체 파일에 행이 없다는 이유만으로 해당 상권 전체를 영으로 만들지 않음 |
| district_counts(파생) | store_version_id, mapping_version, district_code, service_industry_code, count, calc_version | 구별 51업종 집계만 적재 때 생성. 원문 복사 아님. 구 전체 점포를 요청 메모리로 펼치지 않음 |

원본 CSV/SHP/API 분기 파일은 저장소 밖 자료 보관 영역에 **버전당 한 벌** 둔다. DB는 원천별 열을 정규화해 저장하며 원문 JSON과 같은 열을 중복 복제하지 않는다. 모르는 추가 열은 원천별 확장 열/메타데이터로 보존하고 모델에 허용한 열만 노출한다. file_sha256은 적재 때 검증하고, 요청마다 288MiB 파일을 재해시하지 않는다. 활성 자료는 덮어쓰지 않으며 값 수정은 새 버전이다.

공간 조회는 위경도 범위 인덱스로 후보를 좁힌 뒤 기존 `haversine_m`/폴리곤 함수로 최종 판정한다. 직사각형이나 투영 거리만으로 500m를 확정하지 않는다. 유동은 기존 중심점·면적 원 근사 방식을 유지하며 이번 변경으로 실제 폴리곤 안분으로 바꾸지 않는다. 서울 CSV는 서울 경계 밖 점포를 포함하지 않으므로, 예전 전국 반경 API와 서울 외곽 2km 비교가 달라질 수 있다. 서울 범위를 명시하고 경기 자료 필요 여부를 사용자 확인으로 남긴다.

### 2.2 요청 DB와 계보

`analysis_requests.sqlite3`에는 요청·좌표·snapshot·facts·scores·관측·도구/모델 기록·초안/최종만 둔다. 55만 점포나 12분기 개폐업 행을 복사하지 않는다. 자료 DB와 요청 DB의 FK는 파일을 넘을 수 없으므로 버전/행 존재 검증은 서버가 한다.

| 기록 | 저장 단위 | 검증 |
| --- | --- | --- |
| snapshot | release_id, 사용한 source_version_ids, 기간, catalog/profile/baseline/rubric/calc 버전, 좌표·반경·선택 상권 | 요청 시작/질문 재개/평가 전 버전 고정. 새 활성 버전으로 몰래 재개 금지 |
| 직접 셀 fact | fact_id, 값·단위, data_version_id, 자연 행 키, 원문 열, 기대 해시 | 해당 버전이 snapshot에 있고 행/열 값이 실제 존재. 예: 점포명, 한 분기 특정 서울 업종의 점포 수 |
| 집계 fact | fact_id, 값·단위, provenance_id → 버전 목록·query_id·정규화된 조건·calc_version·mapping/baseline 해시 | 허용 계산 레시피로 재현 가능. 수천 행 ID/행별 fact_sources 링크를 생성하지 않음 |
| provenance_queries | query_id, 레시피 이름, SQL/파라미터의 정규화 해시, 좌표·반경·상권·업종·기간, 버전 목록 | 같은 조건은 한 번 저장. 모델 임의 SQL 집계값은 자동으로 사실 등록하지 않음 |
| 지도·규제·답변 관측 | observation_id, 원천, 시각·상태·해시·필요 관측 필드, fact 참조 | 현재 요청만. 키·인증 URL 제거. 숫자 렌더링/규제 포함 검증 유지 |
| 감사·보고서 | 도구 결과 한 벌 + 참조, 모델/usage, 질문/답변, L·평가·반영 기록, 최종 fact 슬롯 | 대화 상태에 도구 본문/자료를 반복 복사하지 않음. 보존 한도·잘림은 명시 |

fact_id는 f_UUID·불변 규칙을 유지한다. CSV의 행 번호만 키로 쓰지 않는다. 점포는 store_id, 개폐업은 (quarter,trade_area_code,seoul_industry_code), 인구는 (quarter,trade_area_code), 영역은 trade_area_code를 쓴다. source_version_id와 함께 해석하므로 같은 자연키라도 자료 수정 시 다른 계보다.

집계의 예는 밀도·LQ·C1·S 지수·유동 시간/연령 적합 지수다. 여러 버전/기간을 섞는 계산은 참여한 버전을 모두 고정한다. 계산 버전·예상 source hash가 달라지면 인용 검증을 실패시키며 다른 활성 버전으로 대체하지 않는다. 자료 버전이 제거되면 SOURCE_UNAVAILABLE로 표시한다. 서울 개폐업 자료가 없는 여섯 업종과 표본 부족·영 분모·결측/영값 구분은 v0.8 그대로다.

### 2.3 query_raw 로컬 뷰·서버 바인딩

| 승인 뷰 | 보이는 자료 | 서버가 고정하는 범위 |
| --- | --- | --- |
| v_raw_stores | 로컬 stores의 원문 대응 열·버전·자연 행 키 | snapshot의 점포 버전 + 주소 반경. SQL로 반경을 늘릴 수 없음 |
| v_raw_lifecycle | 점포/개폐업 행 | 고정된 포함/300m 최근접 상권 + 선택 12분기 |
| v_raw_floating | 유동 원문 행 | 고정된 선택 상권 집합 + 5분기 |
| v_raw_resident / v_raw_worker | 상주/직장 원문 행 | 선택 상권 집합 + 실제 보유 원천 분기 |
| v_raw_trade_areas | 상권 이름·대표점·면적·범위 정보 | 해당 공간 버전과 선택/주변 후보 상권. 서울 전체 폴리곤 덤프 금지 |
| v_ref_district_counts | 구·서비스 업종별 사전 집계 51행 | 현재 snapshot의 점포/매핑 버전 + 주소의 구 |
| v_raw_map / v_raw_regulation | 실시간 관측 | 현재 request/snapshot만 |

자료 DB readonly 연결과 요청 관측 DB 연결은 서버가 구성한다. DB 연결/경로·version_id·좌표·범위를 모델 입력으로 고를 수 없다. SQL은 현재처럼 읽기 전용·authorizer·단일 SELECT·50행·2초 상한을 유지한다. 쓰기/DDL/PRAGMA/ATTACH/기반 테이블/다른 버전·요청/CTE는 거절한다. 소스 DB 별칭/임시 뷰의 authorizer 규칙은 새 테스트가 필요하다.

직접 원천 셀은 (버전,행 키,열)을 다시 대조해 fact로 등록한다. SUM/AVG/COUNT 같은 모델 SQL 결과는 uncitable로 둔다. v_ref_district_counts처럼 적재 시 만든 집계는 **승인 레시피의 집계 계보**로 등록하며 원문 셀로 가장하지 않는다. 원천별 원문 필드 호환은 1절의 적재 검증을 통과해야 한다. L의 새 근거/코드 중복 채점 금지는 바뀌지 않는다.

### 2.4 수동 분기 갱신

제안 스크립트 이름은 `scripts/update_local_market_data.py`이며 **아직 만들지 않았다**.

1. 운영자가 분기·파일 경로를 지정한다. 파일명/제공 메타데이터와 기존 버전을 비교해 새 분기·수정판 여부를 확인한다. 파일 없는 원천만 별도 수집 모드로 일괄 조회한다. 요청이 갱신을 시작하지 않는다.
2. 파일/API 본문 해시·인코딩·필드 목록을 기록하고 비활성 버전에 스트리밍 적재한다. 동일 원천·분기·해시·변환 버전이면 건너뛴다. API 갱신은 페이지/상권 체크포인트·일일 HTTP 상한을 둔다.
3. 필수 열/자연키·숫자·좌표·CRS·분기·상권 코드·전체 수집량·누락/중복을 검증한다. 중복 자연키의 값 충돌은 오류다. 예상한 카탈로그 제외는 보존하고, 새 분할 코드 미확인은 활성화하지 않는다.
4. 51업종 매핑·구 집계·공간 인덱스와 기간별 coverage를 준비한다. 기존 계산·408건 회귀와 8곳 조회 시간 목표·요청 증가량 실측을 확인한다. 단순 총행 수 감소만으로 실패시키거나 자동으로 영을 보충하지 않고 원천 수정 근거를 요구한다.
5. 필요한 원천을 모두 검증한 release를 한 트랜잭션으로 활성화한다. 실패·중단·쿼터 초과는 이전 활성 release 유지, staging만 정리/재개 가능하다. 최초 적재 실패 시 서비스는 DATA_NOT_READY이고 요청 시 API 대체를 하지 않는다.

파일별 최신 분기가 달라도 원천별 실제 기간을 보고서에 표시한다. 기본 보유 창은 개폐업 12분기·유동 5분기·점포 최신 스냅샷·상주/직장 실제 최신 자료다. v0.8 baseline은 우선 그대로 버전 고정하며 새 원천 분기와 기준선 시점 차이를 표시한다. S 기준값/분위수의 분기 갱신은 별도 검증·승인으로 진행하고 요청마다 재측정하지 않는다.

## 3. 도구 계약

현재 역할 권한·예산은 4·6절과 전체 L 구현 계획이 우선한다. 평가자는
get_scorecard·get_facts·query_raw 합계 세 번과 submit_review 한 번만 쓴다.
지도·규제는 decision만 조회하고 보조 모델에는 도구를 주지 않는다.
get_facts의 공간 비교 묶음만 source=industry_profile·metrics=[space_fit]·limit≤51을 허용한다.

v0.4에서도 도구 아홉 개의 이름·한도와 ToolReply 계약은 유지한다. 원문 조회/등록의 저장 대상과 계보는 2절의 로컬 자료 버전·행 키/집계 레시피가 우선한다. raw_row_refs 문자열은 새 버전/자연키 참조로 내보내며 내부 contracts 변경은 새 PR에서 한다.


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
| submit_l | {L_records≤17,finish?:bool}. 전체51업종·한 업종 한 번 | 제출/미제출 수·closed, 종료 시 새 점수 요약·Top5 | common + L_EVIDENCE_INVALID | 여러 묶음, 같은 업종 중복 금지 | decision만 |
| submit_draft | {phase:draft/final,report:ReportProposal,review_resolutions?:[Resolution]}. L 입력 없음·후보/제외 각각≤5 | {report_id,validation_status,rendered_preview_ref,score_snapshot_id} | common + REPORT_INVALID/REVIEW_UNRESOLVED | L 종료 뒤 초안·최종, 거절도 예산에 포함 | decision만 |
| submit_review | {draft_id:ID,verdict:agree/conditional/oppose,issues:[ReviewIssue]≤4} | {review_id,status}. actor는 실행기가 고정 | common + DRAFT_MISMATCH/INVALID_REFERENCE | 평가자 각 1회·지적별 근거 fact_id≤3 | 평가자만 |

common 오류는 INVALID_ARGUMENT / SOURCE_UNAVAILABLE / SNAPSHOT_MISMATCH / BUDGET_EXCEEDED / TIMEOUT이다. 동일 도구·정규화 인자는 재실행하지 않고 이전 응답에 duplicate=true·이미 조회한 결과 표시를 붙인다. 부분 결과는 partial·truncated·누락 필드를 표시하고, '조회 범위 내 확인한 수'만 인용한다. 계약 검증·fact 저장·호출 감사 저장 실패는 일반 error ToolReply로 숨기지 않고 실행 실패로 전파한다(AGENTS.md 3).

map_search는 PlaceClient·카카오 카테고리·거리 계산을 재사용하며 LLM 호출은 0회다. 코드 규칙의 category_match를 우선 적용하고, 명시적인 업종 검색어 규칙이 맞으면 name_match, 그 밖에는 unknown을 반환한다. 일치 상태는 검색 규칙의 결과이며 실제 경쟁점 여부의 확정 판정이 아니다. 애매한 장소의 해석은 decision이 새 fact_id를 근거로 L에서 판단한다. judge_matches·GenerateMapping·모델 프롬프트·모델별 mappings 캐시 및 설정을 제거한다(`backend/app/agents/map_analysis/mapping.py:64`, `agent.py:254`). 검색 응답 캐시를 유지할 때는 좌표·반경·검색어·규칙 버전·조회 시점을 키/출처로 남긴다. 0건·has_more를 실제 동종 가게 없음으로 확대하지 않는다. 모델 클라이언트 생성 시 실패하는 대역으로 지도 LLM 0회를 검증한다.

### query_raw와 자동 사실 등록의 경계

**register_fact는 모델 도구로 만들지 않는다.** query_raw가 자료 버전·자연 행 키·허용 필드·metric 대응·단위·기간·업종·scope를 코드로 검증해 단순 원문 셀을 자동 등록한다. 모델이 값·수식을 제출해 사실로 승인받는 경로는 없다. 평가자의 조회도 서버가 기계적으로 등록하며, 모델은 raw·계산·점수에 쓰기 권한이 없다. submit_review는 자신의 검토 출력 저장만 허용하는 예외다.

| SQL 조건 | 실행·인용 규칙 |
| --- | --- |
| 연결 | mode=ro 별도 연결. query_only는 실행기가 설정. 현재 snapshot의 자료 버전·서버 고정 공간/기간 범위 및 해당 요청의 observation cutoff에 한정된 승인 뷰만 노출 |
| 격리 | 뷰 WHERE 조건은 실행기가 바인딩한 snapshot의 version_id·반경/상권/기간과 관측의 current_request_id 범위로 고정. 모델 조건을 빼도 다른 요청은 안 보임. 연결은 actor별 독립 |
| 허용 | 단일 SELECT, 승인 뷰·안전 함수 목록, 파라미터 바인딩. SQLite authorizer로 기반 테이블 직접 읽기·sqlite_master·미승인 함수 차단. 뷰를 통한 허용 기반 접근만 승인. 범용 SQL AST 검사는 2차 |
| 금지 | INSERT/UPDATE/DELETE, DDL, PRAGMA, ATTACH/DETACH, 다중 문장, load_extension·외부 파일 함수. 방어의 중심은 읽기 전용 연결·SQLite authorizer·행/시간 상한이다. AST 없는 1차에서는 WITH/CTE를 보수적으로 거절해 승인 뷰 이름 가림을 차단한다. 범용 CTE 허용·AST는 2차 |
| 중단 | LIMIT은 최종 51행 검사로 초과 탐지. progress_handler·monotonic deadline·cancel 시 connection.interrupt로 실제 쿼리 중단. to_thread await만 취소하고 백그라운드 SQL을 방치하지 않음 |
| 원문 셀 | (data_version_id, 자연 행 키, 허용 원 필드)를 자료 DB에서 다시 읽어 값·단위·metric을 대조한 경우만 fact_id 생성. 등록 값은 SQL 수식 결과가 아니라 그 원문 셀이다. 불일치·계보 불명은 citable=false. alias로 의미·단위를 바꾸지 못함 |
| SQL 집계·임의 식·계보 불명 | 결과는 탐색용 citable=false, fact_id 미부여. 숫자를 보고서에 복사 금지. 집계는 get_facts/get_scorecard의 승인 계산 지표를 쓰고, 필요한 새 metric은 코드 PR로 추가 |

운영 쓰기 연결은 서비스 전용이며 모델 SQL 연결과 분리한다. 자동 fact 등록은 읽기 연결 밖의 서버 검증/트랜잭션으로 한다. 이를 원자료 쓰기 권한으로 해석하지 않는다.

## 4. decision 루프 — 전체 51업종 L

코드 순위로 L 대상 업종을 제외하지 않는다. 모든 51업종에 같은 등급 기준을 적용한다.
구현 순서·테스트·이전 실측·역할 예산의 상세 기준은 [전체 L 구현 계획](whole-industry-l-plan.md)이다.

| 단계 | 행동·종료 | 기록 |
| --- | --- | --- |
| 코드 | 초기 점수표 한 번 확인 | 코드 점수 스냅샷·원래 순위(추적용) |
| 질문 | 층·전용면적·공간 상태를 처음 한 번 묶음 질문 | 답변·fact·예산·이전 대화 |
| 공통 근거 | 51업종 공간 비교를 코드로 생성, source+metrics로 묶음 조회 | 프로필/답변 부모 fact ID·초안 표시 |
| 추가 조사 | 기존 근거와 코드가 충돌하는 업종만 지도·SQL·자문 | 실제 성공한 도구·새 근거 |
| L 제출 | submit_l 최대17개씩 세 묶음. 한 업종 한 번. 전부 제출 또는 finish=true로 닫기 | 미제출은 unknown·판단 미제출, 개별 이유와 총개수 |
| 재계산 | 종료 시 서버가 코드90+L10·배지·Top5 계산 | 새 채점 스냅샷·요약 응답 |
| 보고서 | L 종료 뒤 submit_draft. 후보/제외 후보 각각 최대5, L 입력 없음 | fact 슬롯 초안 |
| 평가·최종 | 네 역할 병렬, 지적 한 번 반영, 코드 최종 검증 | 수용/일부/기각·이유·실패 슬롯 |

LSelection.basis는 all_industries만 둔다. 코드 점수 스냅샷·원래 순위는 기록이며 범위 제한이 아니다.
LRecord는 industry_code·selection·review_state·status·grade·new_factors·checked_questions·
tool_call_ids·advisor_consult_ids·limitations를 보존한다. unknown에는 이유가 필수다.
새 fact·업종 일치·D/C/S 중복 금지·요인별 근거 겹침 금지·숫자 슬롯·등급별 요인 수 검증은 유지한다.
프로필에 요건이 없다는 사실을 불리 요인으로 쓰지 못한다. 규제 금지는 L로 상쇄하지 못한다.

| 자원 | 안전선·격리 |
| --- | --- |
| 전체 | 입력400k·출력60k·40회·600초·호출당 출력16k |
| decision | 입력230k·출력36k·22회. 그중 최종 입력50k·출력6k·2회 예약 |
| advisor | 입력10k·출력2k·2회 |
| 평가자 | 각 입력40k·출력5.5k·4회, 읽기3+제출1 |
| 측정 | 녹화·바깥 안전선 유지. 네 평가자의 보장 자원을 침범하는 예산 대여는 허용하지 않음 |
| 반복·오류 | 중복은 재실행하지 않으며 거절도 예산에 포함. 오류 경로·유형을 비밀 없이 짧게 반환 |
| 재개 | 동일 버전·이전 messages·답변 도구 응답·사용량 누적을 유지 |

역할 시간은 병렬 실행이므로 합산 분배하지 않고 같은 600초 마감 안에서 집행한다.
실제 사용량과 진행 중 예약값을 잠금 안에서 검사한다. 미완료 L·평가·반영은 한계로 명시한다.

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

## 6. 평가자 네 명

| 역할 | 중점 | 도구 |
| --- | --- | --- |
| examiner | 사실·기간·범위·L 중복·계보 | get_scorecard / get_facts / query_raw / submit_review |
| founder | 공간·설비·운영 제약, 초안 요건의 과신 | 동일 |
| customer | 손님·동선·수요·확인 조건 | 동일 |
| landlord_advocate | 임대 지속성·답변 조건·불확실성 | 동일 |

각 역할은 읽기 최대 세 번과 제출 한 번이며 지도·규제·자문·질문 도구는 받지 않는다.
필요한 지도·규제의 기존 fact를 읽고 재조회가 필요하면 suggested_check로 남긴다.
초안·전체 L의 요인/근거·확인 조건을 짧게 전달하고 반복 스냅샷 메타데이터는 뺀다.
역할별 입력40k·출력5.5k·4호출을 다른 역할이 쓰지 못한다. 실패해도 정확히 네 슬롯을 유지한다.

ReviewIssue는 issue_id·industry_code·target·kind·comment·fact_ids≤3·suggested_check이다.
decision은 지적마다 accepted/partial/rejected와 이유·근거를 한 번 제출한다.
고정된 코드 점수를 모델이 고치지 못하며 L의 최초 채택 기록도 중복 제출로 덮지 않는다.
최종 report validator가 인용·규제·배지·순위를 다시 검사한다. 평가 실패를 동의로 간주하지 않는다.

## 7. 보고서 출력 계약

ReportProposal={summary_segments,candidates≤5,excluded_candidates≤5,limitations_segments}. L_records는 별도 submit_l로만 받는다. Candidate={industry_code,reasons_segments,risks_segments,confirmation_conditions_segments,fact_ids}. 점수·배지·금지·순위·숫자 값 필드는 모델 제안에 받지 않는다. 서버가 facts·v0.8 scores로 계산해 DecisionResult에 붙인다.

| 필드 | DecisionResult 서버 출력 |
| --- | --- |
| 버전 | schema_version=2.0, rubric_version=v0.8, tool_contract_version, request_id, run_id, report_id, score_snapshot_id, evidence_snapshot_ids |
| 검토 후보 | code·name·코드 point/90 + L point/10, 전체 업종의 검토 상태·unknown 이유. A/B/H·비율·coverage·배지·G |
| 근거 문장 | segments=[{type:text,text},{type:fact,fact_id,format:count/percent/rate/distance/text}]. 모델은 값 복사·산술 금지 |
| L | 새 요인·fact_id·호출 도구·자문 반영·grade/unknown. 새 근거가 없으면 등급 생성 금지 |
| 검토 상태 | 평가자 4명 상태·지적·수용/일부/기각 로그, review_completeness |
| 확인 조건 | 건축물 용도 등 미확인·자료 시점/공간 한계·partial·예산 제한 |

숫자는 서버 renderer가 fact.value·단위로 채운다. grade enum·업종 코드·고정 시간대/연령 라벨은 구조화 제어값이며 측정 숫자 복사와 구분한다. 모델 자유문장에 인용 없는 수치가 있으면 거절한다. 근거는 fact_id만 인용한다. 기존 render_cited·`{i}` 자리표시자·agent/path 인용은 삭제하고 typed fact 슬롯 renderer로 교체한다. 원문 숫자를 텍스트에 붙이는 우회도 검사한다.

최종 배열은 전체 51업종 채택 점수의 원점수 하한→coverage→코드로 재검증한다. L 범위는 전체51개이며 미제출·근거 부족은 개별 이유와 함께 unknown으로 남긴다. Top5의 보류/조건부를 추천처럼 표시하지 않는다.

## 8. schemas.py 변경안 — 팀 계약 교체

**결정:** 최종 배치는 공통 계약 schemas.py·내부 계약 app/agentic/contracts.py다. 전환 전에는 모든 새 계약을 contracts.py에 최종 이름 그대로 두어 기존 실행을 유지한다. LD6(기존 PR7 전환 범위)에서 DecisionRequest·DecisionResult·Evidence·QuestionSnapshot을 schemas.py로 옮겨 기존 계약을 교체한다. V2 접미사와 구 결과·질문 reader를 만들지 않는다. schemas.py 교체안의 팀 승인은 완료됐으며 실제 파일 변경은 LD6에서 적용한다. 이번에는 문서만 수정한다.

| schemas.py 모델 | 변경안·이유 |
| --- | --- |
| AnalysisTask / AgentAnalysis | 그대로 유지. snapshot·계산 metadata는 AgentAnalysis.data 내부에만 추가 |
| DecisionRequest | request/run/site/snapshot 참조·rubric/tool version. 예산은 런타임 상태에서 관리하고 전체 analyses/digest 입력과 모드 dispatch 제거 |
| DecisionResult 및 IndustryAssessment/DecisionContent | 코드 ○/90 + L ○/10, 점수 구간·비율·coverage·배지·검토 후보 Top 5·fact 슬롯·L 검토 상태·평가 요약. 기존 보고서 계약 교체 |
| Evidence | {fact_id} 참조로 교체. agent/path·EvidenceRef 인용 계약 제거, registry가 요청·snapshot·업종·citable 검증 |
| QuestionSnapshot | run/snapshot/score/draft refs·도구 hash·누적 예산·채택 fact 목록·질문 세션. 기존 QuestionSnapshotV2 통합 제거, 구 세션 재개 불가 |
| AnalysisMode·Specialist 관련 모델 | single_decision/multi_agent enum·전문가 브리핑/행동 전용 모델 제거. 팀 공통 소비자 함께 갱신 |
| 평가 응답의 공통 경계 | DecisionResult에 평가 상태·반영 요약만 노출. 내부 ReviewIssue/Resolution은 contracts.py에 정의 |

| app/agentic/contracts.py 내부 계약 | 내용 |
| --- | --- |
| 도구 입출력·ToolReply/ToolError | 3절 입력 union·출력·권한·오류·상한 |
| Scorecard / FactView | 점수·상태·레지스트리 읽기 출력 |
| ReportProposal / LRecord | 모델 보고서 제안·새 근거 판단 기록. 서버 출력 DecisionResult와 구분 |
| ReviewIssue / Resolution | 평가 지적·수용/일부/기각과 이유 |
| AdvisorAnswer | 대안 해석·fact_ids·조건·확신도. 점수 없음 |

모델 자유문장·원문 응답은 경계에서 검증한다. 프롬프트는 도구 계약을 참조하고 DB 내부 열·함수명을 의존하지 않는다.

## 9. 프론트·API 영향 — 새 결과 계약으로 전환

v0.4에서는 화면에 원천별 자료 분기/기준선 시점과 release 참조를 표시한다. 자료조회/채점 stage를 사용하고 요청별 수집 진행률은 삭제한다. 수동 갱신 진행은 운영자 경로로 분리한다. 공통 응답 필드의 최종 배치는 팀 계약 PR에서 합의하며 이번에 schemas.py/API_CONTRACT 코드를 수정하지 않는다.


GET /api/v1/analyses/{id}의 URL과 status/site/result/error envelope·폴링 seq는 재사용한다. result는 새 DecisionResult만 반환하며 구 결과 변환·버전별 adapter는 만들지 않는다. source_analyses 거대 배열을 기본 결과나 모델 입력에 재삽입하지 않는다. 숫자는 fact 슬롯 renderer로 제공하고 원문 SQL·키는 GET/이벤트에 노출하지 않는다.

**develop 리포트 화면(#38)은 새 DecisionResult에 맞춰 수정해야 한다.** 기존 PR1 계약을 공유하고 LD5에서 목업 GET을 제공한다. LD6 통합 전환 전에 코드/L 분리·점수 구간·배지·Top 5·L 미검토·평가 미완료·fact 슬롯 표시를 연결하고 프론트 검사를 통과한다. 화면/진행 이벤트 구현을 통합 전환 뒤로 미루지 않는다.

현재 진행은 events seq 폴링이며 SSE가 아니다(`docs/API_CONTRACT.md:210`, `:224`). mock 진행 시뮬레이션 TODO도 실제 stage 소비로 교체한다(`frontend/app/analysis-progress/page.tsx:93`, `frontend/lib/hooks/useAnalysisProgressSimulation.ts:17`).

| 단계 | stage/event·detail 계약 | 화면/전환 작업 |
| --- | --- | --- |
| 로컬 자료 조회 | data_lookup started/completed {release_id,source_periods,coverage} | 수집 진행률 대신 자료 버전·조회/결측 상태 표시 |
| 계산/채점 | metrics/scorecard started·completed {rubric_version,industry_count} | 코드 채점 단계 표시 |
| 판정 도구 | decision started/completed {phase:draft/final}; decision.tool completed {tool,status} | 원문·SQL·키·fact 값은 이벤트에서 제외 |
| 자문 | advisor started/completed {status} | consult.*·briefing stages 삭제 |
| 평가 | evaluate.examiner/founder/customer/landlord_advocate started/completed {status,issues_count} | 항상 4명 상태·평가 미완료 표시 |
| 질문/종료 | questions waiting, run completed/failed/draft_available | 새 QuestionSnapshot으로 대기/재개. 유효 초안과 final 구분 |

기존 PR1 결과·질문 계약을 재사용하고 LD5에서 API_CONTRACT의 자료 기간·stage와 런타임·GET·이벤트를 연결한다. 프론트 담당은 LD6의 전환 완료 조건에 포함해 검증한다. retry는 같은 snapshot·저장 예산을 이어받는다. DB 버전 불일치는 시작 오류와 명시적 초기화 안내로 처리한다.

## 10. 용량·시간·모델 예산

아래는 **설계 목표/초기 추정**이다. LD1·LD2 전체 DB 실측은 구현 결과 절에 기록하며 LD3·LD4에서 요청10초 목표와 요청 저장 증가량을 측정한다. 요청 DB 용량 목표는 해제했으며 약1.2MB 증가를 수용한다.

| 항목 | 계획 수치 | 산정/검증 |
| --- | --- | --- |
| 서울 점포 최신 1개 버전 | 554,092행, SQL·공간/업종 인덱스 약 250~600MiB 추정 | 288MiB 원본 CSV와 39열 기준. 동일 원문 JSON 복사 없음 |
| 개폐업 12분기 | 최대 약 198만 행, SQL·인덱스 약 300~900MiB 추정 | 1,650×100×12 상한, 실제 희소행 수로 재산정 |
| 유동 5분기·상주/직장·공간 | 수만 행/약 10~50MiB 추정 | 인구 두 CSV 260kB, SHP 묶음 4.25MiB. 대표점과 폴리곤 포함 |
| 활성 자료 DB | **약 0.6~1.6GiB 추정** | 열 보존·인덱스 수에 따라 달라짐. staging/원본 보관·이전 점포 버전은 별도이며 누적 보존은 증가 |
| 요청 기본자료 조회+계산+저장 | **좌표 확정 후 10초 이하** | SQL ≤3초, 기존 계산/채점 ≤5초, 작은 사실 저장 ≤2초 목표. 8곳 cold/warm별 개별 시간 실측. 주소·지도·규제·LLM 지연은 별도 |
| 요청당 저장 증가 | **용량 목표 없음** | 약1.2MB 증가를 수용한다. WAL 체크포인트 후 두 번째 요청 증가도 실측하며 자료 공간과 요청 공간을 분리해 기록 |
| 요청 자료 API | **영 회** | 자료 provider를 호출하면 실패하는 대역으로 확인. 주소·카카오 장소·V-World만 실시간 허용 |

큰 지도/규제 응답과 반복 도구 본문도 저장량에 포함한다. 파일로 빼거나 자료 DB로 옮긴 용량도 실제 저장량에 포함한다. 감사 결과는 한 번 저장하고 대화에는 참조만 둔다. 자료 공간과 요청 공간 증가를 분리해 보고하며, 최초 자료 적재 증가를 요청당 증가와 섞지 않는다. 요청 DB 용량은 실측으로 기록하고 목표 초과로 보고하지 않으며, 필요한 근거를 삭제하지 않는다.

모델 예산은 전체600초·40회·입력400k/출력60k·호출당출력16k이며 역할 몫은 4절을 따른다. L전체51개·선택적자문2회·평가자4명이다. 요청 앞단10초는 보고서 전체 시간 약속이 아니다. 실제 model·usage·단계 시간을 기록한다. DB/SQL은 to_thread와 협력적 취소로 종료한다.

### LD1·LD2 구현 결정 (2026-10-14)

- 분기 전체 조회 확인: `VwsmTrdarStorQq/1/1000/20262`는 INFO-000, 총75,912행·반환1,000행·분기 혼합 없음·14열. 승인2회 중1회 사용. 상권별 수집은 하지 않는다.
- 수동 진입점: `backend/scripts/refresh_local_data.py`. `--source` 반복 선택, `--quarter YYYYQ`, `--quarters N`, `--seoul-csv`, `--shp`, `--api`, `--dry-run`을 사용한다. 상가 CSV는 저장소 밖, 기본 DB도 저장소 밖이다.
- 기본 묶음: 상가 최신CSV·개폐업12분기·유동5분기·동봉 상주/직장CSV·현재SHP. 인구 갱신에만 `--api`로 전분기 API를 받고 요청 분기를 선택한다. 기본자료의 실제 요청 경로는 LD3 전까지 변경하지 않는다.
- 기존 `to_store`/`map_stores`, `normalize_row`, `FlpopRecord`/`PopulationRecord`, `load_shape_features`를 재사용한다. 한글CSV 열 매핑은 기존 밀도 스크립트 상수를 재사용한다.
- 원천별 테이블은 자연키+version_id, 검색용 열(좌표·상권·업종·구), 전체 원필드 값을 payload 배열로 보존한다. 반복되는 열 이름은 source_fields에 버전당 한 번만 저장하고 raw_row()로 원래 객체를 복원한다. 전체 응답 envelope/행을 다시 복제하지 않는다. 매핑 제외 점포도 보존하며 구별51업종 점포 수(영값 포함)를 적재 때 만든다.
- 검증: 자연키 중복·필수 필드 결측·비정상 수치·분기 혼합/연속성·페이지 행 수 누락. 행 수 급변은 **직전 활성 자료 대비 ±50% 초과면 거절**한다. 초기에는 이전 활성 자료가 없으므로 변동률 검사는 적용할 수 없다.
- 활성화: 서울 상가25개 구 코드와 선택 원천 전체를 검증한 뒤 release를 한 트랜잭션으로 변경한다. `--source` 부분 갱신은 나머지 활성 원천을 그대로 포함한다. 실패 시 이전 release 유지. 동일 파일/매핑 해시는 재적재하지 않는다.
- 보존: 활성 release+직전1개. 두 묶음에서 참조하지 않는 retired 버전/원천 행은 제거한다. 실패한 staged 자료와 페이지 체크포인트는 재개용으로 남기며 운영자의 실패 작업 정리는 별도 명시 절차가 필요하다. 원본 서울CSV는 스크립트가 삭제하지 않는다.
- API 체크포인트는 원천·분기·페이지별 DB에 보존, 완료 활성화 후 삭제한다. 이어 받는 중 총행 수 변경은 거절한다. 동시4페이지·일일9,500HTTP에서 중단(10,000 예산 여유500), 재시도 자동 호출 없음. 이 카운터는 **이 DB로 실행한 수집만** 세므로 다른 앱/키 사용량은 운영자가 포함해야 한다.
- `--dry-run`: 임시 DB에서 로컬 파일 검증·적재만 하고 운영 DB/서울 API는 변경/호출하지 않는다. API 원천은 미실행으로 보고한다. 서울 밖 점포는 제외하고 LD3에서 경계 limitation을 출력한다.

### LD1·LD2 실제 적재 결과 (2026-10-14)

자료 DB: 사용자 홈 `.chaeum/market_data.sqlite3` (저장소 밖). 초기 활성 release1개·자료 버전21개·staged0개·남은 API 체크포인트0개·구별 집계1,275행(25구×51업종).

| 원천 | 기간 | 행 수 | 적재 HTTP | 시간 | 원문값 payload 크기(인덱스 제외) |
| --- | --- | ---: | ---: | ---: | ---: |
| 상가 | 2026Q2 | 554,092 | 0 | 97.78초 | 294.24MiB |
| 개폐업 | 2023Q3~2026Q2,12분기 | 917,592 | 923 | 106.01초 | 102.04MiB |
| 유동 | 2025Q2~2026Q2,5분기 | 8,242 | 10 | 2.00초 | 1.94MiB |
| 상주 | 2026Q2 CSV | 1,633 | 0 | 0.06초 | 0.17MiB |
| 직장 | 2026Q2 CSV | 1,641 | 0 | 0.08초 | 0.15MiB |
| 영역 SHP | 파일 해시/CRS,분기 미지정 | 1,650 | 0 | 0.56초 | 6.35MiB |

- 전체207.02초·자료 수집933HTTP + 사전 확인1HTTP = **934HTTP**, LLM0회. 재시도 없이 초기 수집 완료.
- DB 파일1,202,241,536B(약1.12GiB), 이 중 체크포인트 삭제 후 재사용 가능한 빈 페이지333,987,840B(약318.5MiB). 위 원천별 크기는 payload 바이트 합이며 파일 전체/인덱스 크기로 가장하지 않는다. 다음 적재에 빈 페이지를 재사용하며 이번에 VACUUM은 하지 않았다.
- 상가 최초 dry-run은 열 이름을 행마다 JSON으로 저장해 파일만1,259,483,136B였다. 버전당 열 이름1벌 + 값 배열로 바꿔 전체6원천 적재 파일이 그보다 작아졌다. 원필드는 raw_row()로 복원하며 의도한 제외 소분류 G21303의131점포도 보존했다. 미확인 분할 코드는 거절한다.
- 적재 파일은 기존 Downloads 서울202606 CSV를 사용. 자료 DB/원본/시험 로그는 커밋하지 않는다. 기존 테스트882개와408건 재현을 유지한다. **당시 로컬 DB를 조회하는 요청 경로와 요청10초/1MiB 실측을 LD3·LD4 작업으로 남겼다.**

### LD3 로컬 분석 어댑터 구현·검증 (2026-10-14)

- 적용 경로: `execute_agentic_analysis`의 기본 분석은 LocalAdapter, `resume_agentic_analysis`는 저장한 DB 경로/버전 목록을 재사용한다. 요청 시작(주소 변환 전)에 버전 묶음을 고정한다. 기존 주입형 테스트/옛 모드 경로와 공개 API의 최종 전환·삭제는 LD6다.
- 기본자료는 readonly SQL로 반경 점포·2km 비교·구 사전 집계·개폐업·유동·상주/직장·영역을 조회한다. Store/인구 파서, 기존 포함/최근접 판정, 기존 formatter 계산과 채점기를 호출한다. 원문 hook/캐시 복사/상주·직장 CSV 재읽기를 새 기본 경로에서 호출하지 않는다. 브랜드는 사전 캐시만 읽고 없으면 unknown.
- 요청 DB에는 local_snapshots(자료 DB 경로·버전 목록·설정 해시·공간조건), local_provenance(원천별 공유 조회 레시피/계산 버전), local_fact_lineage(셀 또는 집계 참조)를 추가한다. 집계의 지표·업종 조건은 facts.metric/industry_code와 결합한다. 근처형 C1만 점포와 유동 버전을 함께 참조하고, 모임형 C1은 점포 버전만, 무관 C1은 업종 프로필(설정 해시)을 근거로 한다. 행 UUID/수천 행 링크는 생성하지 않는다.
- 직접 셀은 버전·자연키·열을 원자료에서 읽어 값 검증 후 등록한다. 공간조건은 저장 때 공유하고 도구/자문/보고서 읽기 경계에서 펼친다. 정상 초안에도 로컬 limitation이 유지된다. 결측/n.a. 문항의 상태·이유는 scores/summary에 그대로 남기며 인용할 숫자 fact를 중복 생성하지 않는다.
- LD4의 query_raw는 고정 버전·반경/상권/구 범위의 로컬 뷰를 읽는다. 기본자료의 요청 DB 원문 뷰로 우회할 수 없다. get_facts/get_scorecard는 저장된 로컬 계산을 읽는다.
- 서울 경계는 선택 원천 `seoul_boundary`로 버전·해시를 기록한다. 반경 원이 경계를 넘을 때만 **서울 밖 점포 미반영**을 표시한다. 도형이 없으면 기존 두 한계 문구를 유지한다. LD4 최초 조회는 INCORRECT_KEY였으며 PR5 마무리에서 규제와 인증 방식을 통일한 뒤 성공·활성화했다.
- 갱신 뒤 기본 VACUUM, `--no-vacuum`으로 생략 가능. 이번 DB 1회 압축: 1,202,241,536B → 835,825,664B (약1.12GiB →797.11MiB). API/LLM 호출 없음.
- 동일 준비 입력을 새 전달/저장/채점 경로에 통과시켜 **408/408 일치**. 별도로 실제 로컬 SQL 자료로 8곳을 채점한 결과도 모든 등급·점수·배지가 같다. 배지9/1/377/21 유지. C1 원값22조합만 상가 CSV/API 점포 수 차이로 달라졌으며 등급 경계를 넘지 않았다. 값을 맞추기 위한 보정은 하지 않았다.
- 차이 관찰은 지도/규제에 기존 저장 관측 대역을 동일하게 넣어 기본자료 차이만 비교했다. 새 조회나 모델 호출은 영 회다. 동일 입력408 검증은 계산자료 전달/저장/채점 계약 검증이며, 미보유된 8곳 API 원문 전체를 새 SQL로 재구성했다고 주장하지 않는다.

| 주소 | 좌표 확정 후 조회·계산·저장 | 요청 DB 증가 | C1 원값 차이 코드(점수/배지 변화 없음) |
| --- | ---: | ---: | --- |
| 서울특별시 강남구 테헤란로 152 | 2.000초 | 0.949MiB | G215B,I201 |
| 서울특별시 중구 세종대로 110 | 2.609초 | 0.926MiB | 없음 |
| 서울특별시 마포구 와우산로 94 | 2.422초 | 0.914MiB | G204,G209,G215B,I210,P105,S207 |
| 서울특별시 강북구 도봉로89길 13 | 1.578초 | 0.840MiB | G215,G216,I204,I210,P105,Q102 |
| 서울특별시 노원구 동일로186길 3-24 | 1.265초 | 0.906MiB | G205,S207 |
| 서울특별시 용산구 이태원로 지하 177 | 1.422초 | 0.844MiB | I101,I204,I212 |
| 서울특별시 강남구 선릉로64길 33 | 2.703초 | 0.879MiB | I201,P105,M107 |
| 서울특별시 은평구 진관2로 15-46 | 0.968초 | 0.891MiB | 없음 |

당시 모두10초/1MiB 이내. SQL+계산+facts/scores/snapshot 저장을 측정했고 DB 기본 스키마 생성·주소변환·지도/규제 실조회·LLM 루프/최종 감사 로그는 제외했다. 요청별 원문 행/fact_sources 링크는0. 원천별 공간·기간을 보존하는 공유 계보로 첫 시험1.8MiB를 최종0.84~0.95MiB 수준으로 줄였다. 결과/요청 시험 DB는 cache에만 보관한다.

## 11. 새 PR 순서 — 로컬 자료 경로부터 전환

기존 PR1 계약·PR3 채점기·PR4 읽기 도구·PR5 루프는 재사용한다. 기존 PR 번호의 요청별 원문 저장 확대는 중단한다. 아래 LD 번호는 이번 전환 PR 순서이며 기존 PR 이력을 다시 쓰지 않는다.

| PR | 범위 | 완료 기준 |
| --- | --- | --- |
| LD1 자료 버전·적재 계약 | 원천 필드 어댑터, data_versions/release·자연키·기간·coverage, 요청 snapshot 내부 계약, 작은 가짜 CSV/SHP | 필수 열·불일치·동일 해시 재적재 차단, 수정판 새 ID, 일부 적재/실패 시 기존 release 유지. 공통 schemas 변경안은 팀 리뷰 |
| LD2 전체 자료 DB·수동 갱신 | CSV/API 배치 입고, 공간/업종/기간 인덱스, 51 매핑·구 사전 집계, 12/5분기 보유·활성화 | 실제 보유 파일 적재·행 수/코드/단위 검증, 원천별 크기/시간/HTTP 보고. 네트워크 수집은 별도 승인. 반경 경계/SHP CRS 보존 |
| LD3 로컬 분석 어댑터 | API/CSV 재수집 없이 주소 좌표로 점포·개폐업·인구 조회, 기존 계산/formatter/evaluate 호출 | 자료 API 호출 금지 대역, 포함/최근접300m·YoY 동일 집합·누락/영 규칙. **동일 자료에서 408/408·배지9/1/377/21**, 다르면 차이 표 |
| LD4 버전 계보·읽기 도구 | 직접 셀/집계 레시피 계보, readonly 뷰·범위 바인딩, facts/scores와 도구 기록 단순화 | 다른 버전/범위/요청 SQL 거절·50행2초, 해시 불일치 인용 실패, 집계에 행 링크 없음. 8곳 기본 단계≤10초·요청 증가량 실측(용량 목표 없음) |
| LD5 decision·평가·GET 연결 | 기존 PR5 루프/보조·질문 재개를 고정 release에 연결, 기존 PR6 평가4명·fact 렌더링/GET 구현 | 재개/평가에 동일 버전, L/코드 중복 거절·예산·실패 표시, 원천별 기간 출력. 목업 우선, 유료 테스트는 따로 승인 |
| LD6 단일 경로·팀 전환 | 구 원문 hooks/캐시/원문 테이블·옛 모드/전문가/legacy 근거 삭제, 기존 PR7 schemas 이관·DB 초기화 안내·프론트 | 삭제 대상 참조 영 건, 기존 DB 자동이전 없음, MOCK_MODE 새 전체 흐름·팀 계약/화면 검사. feat/agentic-decision 기준 리뷰 후 develop 병합 |

### LD6 추가 정리 목록

| 대상 | 정리 |
| --- | --- |
| local_data/adapter.py 기존 145·178·232행, registry.py 151행, persistence.py 33행 | 함수 내부 import를 모듈 상단으로 이동하고 순환 의존 확인 |
| 다른 모듈의 `_write`, `_overlapping_areas`, `_nearest_district` 사용 | 공개 함수로 바꾸고 모든 호출부·테스트 갱신 |

LD4는 새 함수 내부 import와 다른 모듈의 비공개 함수 사용을 추가하지 않는다. SQL은 서버가 읽기 전용 자료 DB를 연결한 후 TEMP 뷰로 버전·공간을 바인딩한다. 점포는 정확한 반경, 개폐업은 선택 상권, 인구는 선택 상권 집합, 구 집계는 선택 구만 보인다. 직접 셀은 버전·자연 키·열을 재조회해 fact로 등록하며 집계·표현식은 uncitable이다. 지도·규제는 요청 DB 범위를 유지한다.

### LD4 검사·실행 관찰 (2026-10-14)

| 항목 | 결과 |
| --- | --- |
| 로컬 SQL | 5개 기본자료 뷰 + v_ref_district_counts, 요청 DB의 지도·규제 뷰. readonly ATTACH는 서버만 수행, 모델 ATTACH/기반 테이블/main 기본자료 우회 거절, 50행·2초 |
| 직접 셀 | 고정 버전·자연 키·열과 반환값을 원자료에 대조. UNION/조인/다중 SELECT는 자동 등록하지 않음. 집계는 uncitable |
| 서울 경계 | 승인 1회 조회에서 INCORRECT_KEY. 활성 자료는 변경하지 않음. 진관2로 15-46·도봉로89길 13 모두 교차 미확인, 기존 한계 문구 유지. 경계 안/교차/자료 없음 대역 검사 통과 |
| 검사 | ruff check/format, mypy 160모듈, unittest 886개, 카탈로그 일치. 기존 채점 408/408 및 배지 9/1/377/21 재현 |
| 실제 실행 | 테헤란로 152 새 서비스 1회: waiting_for_input. 총 8.547초, 주소 0.188초, 로컬 조회·채점 1.921초, 루프 6.407초. 요청 DB +978,944 bytes(0.934MiB) |
| 모델 | gpt-6-luna 3회, 입력 22,018 / 출력 238토큰. Sonnet 호출 없음 |
| 도구 | get_scorecard(ok) → get_facts(INVALID_ARGUMENT) → ask_user(ok). get_facts는 source=baseline·업종 조건 없음으로 계약 검증에서 거절됨 |
| 보고서 | 층·전용면적·공간 상태 답변 대기. 지도/규제/자문/초안 제출/L 채점은 미실행. 현재 코드 상위 5는 G204 조건부, P105/R102/G213/S207 보류이며 최종 추천 아님 |

실제 실행의 프롬프트는 변경하지 않았고 재시도하지 않았다. 질문 답변 후 예산을 이어서 재개해야 초안과 L 반영 결과를 확인할 수 있다. 서울 경계는 V-World 키/허용 도메인 확인 후 별도 승인 실행으로 적재한다.

### PR5 마무리: 경계 인증 수정·시험 답변 재개 (2026-10-14)

| 항목 | 결과 |
| --- | --- |
| 경계 인증 비교 | 규제와 같은 EducationZoneSettings·VWORLD_DATA_URL 재사용, Referer 헤더·key 공백 제거, 경계에만 있던 domain 파라미터 삭제. education_zone.py는 변경 없음 |
| 경계 수집 | 승인 1회 HTTP로 서울 시도 폴리곤 1개 성공. 버전·해시 기록 후 활성화, 규제 진단용 추가 호출 불필요. 동일 키로 성공하여 키·레이어 권한 자체 문제는 아님 |
| 두 주소 500m 반경 | 진관2로 15-46은 최근접 경계 744.5m, 도봉로89길 13은 3,472.8m. 모두 경계 안, 새 요청은 서울 밖 점포 미반영 문구 없음 |
| 재개 입력 | 1층 / 약 40㎡(12평) / 이전 업종 일반 소매·주방·배기 설비 없음. 각 답변 fact 생성, 기존 스냅샷과 예산 유지 |
| 재개 결과 | 5.078초, draft_available. 동일 get_scorecard 재호출 → DUPLICATE_CALL → 코드 점수 기반 fallback 초안. 모델의 submit_draft 제출·L 판단은 없었고 설명·근거 슬롯도 비어 있음 |
| 모델별 사용량 | 재개 gpt-6-luna 1회, 입력6,881/출력56. 누적4회, 입력28,899/출력294. Sonnet 0회 |
| 누적 예산 | 모델4/26(15.4%, 절대상한28), 입력18.1%, 출력1.23%, 활성시간13.563/300초(4.52%), 도구4/40(10%) |
| 미실행 | 지도·규제·ask_advisor·L 검토. 51개 L 전부 unknown, 새 L 근거0, 거절된 L/초안 제출0. 답변은 저장됐으나 L/limitation에 쓰이지 않음 |
| 상위5 | G204 54.375 조건부, P105 49.375 보류, R102 48.75 보류, G213 48.125 보류, S207 46.875 보류. L 반영 전후 변화 없음 |
| 요청 DB | 재개+262,144bytes(0.250MiB), 최초부터 누적+1,241,088bytes(1.184MiB). 조회·채점 부분은0.934MiB였지만 보고서/답변 저장 후 당시 전체1MiB 목표 초과. 현행 용량 목표는 해제됨 |
| 검사 | ruff check/format, mypy160모듈, unittest887개, 카탈로그 일치. 인증 방식 차이 회귀 테스트 추가 |

이 재개 요청은 경계 적재 전 21개 버전을 고정했으므로 기존 경계 미확인 limitation을 유지한다. 새 활성 경계로 진행 중 스냅샷을 바꾸지 않는다. 프롬프트 수정·재실행은 하지 않았다. 구조화 fallback 생성은 확인했지만 실제 L·자문·근거 문장 작성은 검증되지 않았으며, 중복 조회 후 즉시 종료하는 현재 동작을 다음 프롬프트/루프 검토 대상으로 남긴다.

### PR5 대화 복원·반복 응답 수정과 새 요청 1회 (2026-10-14)

기존 첫 재개 입력은 저장된 메시지와 당시 model_messages 함수로 오프라인 재구성했다. 표의 길이는 값 원문을 제외한 메시지 JSON의 문자 수이며 provider 토큰 수가 아니다. 실제 첫 재개 패킷을 새로 호출해 확인하지 않았다.

| 메시지 | 저장 상태 | 기존 재개 전송 | 수정 후 재구성 |
| --- | ---: | ---: | ---: |
| system | 798 | 798 | 798 |
| user(요청) | 2,486 | 2,486 | 2,486 |
| assistant(get_scorecard) / tool | 299 / 3,948 | 빠짐 | 모두 유지 |
| assistant(get_facts) / tool | 299 / 369 | 빠짐 | 모두 유지 |
| assistant(ask_user) / tool | 519 / 362 | 519 / 362 | 519 / 788(답변·fact_id 포함) |
| 추가 user(답변) | 답변 저장 시 1개 추가 | 355·369로 두 번 전달 | 추가하지 않음 |
| 메시지 수 | 답변 전8·답변 저장 후9 | 6 | 8 |

- 새 도구 중복은 동일 actor·요청·snapshot·정규화 입력의 감사 응답을 재사용한다. 모델/외부 도구를 다시 실행하지 않고 duplicate=true·이미 조회한 결과 표시를 붙이며 시도 횟수는 소비한다. 재개는 요청 DB에서 이전 응답을 복원한다.
- 반복/오류 연속3회 종료, 정상/부분 응답 성공 시 연속 횟수 초기화. fallback에는 코드 요약 한 문장과 **decision 판단(L)을 끝내지 못해 코드 점수만으로 정렬했습니다**를 넣는다. 문맥 압축용 중복 working_facts 생성은 제거했다.
- 대역은 재개 첫 모델 입력의 전체 도구 응답·답변 fact_id·예산 연속, 응답 재사용 후 계속 실행, 연속3회/성공 후 초기화, fallback 설명을 검증한다. ruff check/format·mypy160모듈·unittest890개·카탈로그 일치. 독립 리뷰에서 중대한 결함 없음.

| 새 테헤란로152 실제 요청 | 관찰 |
| --- | --- |
| 결과·시간 | draft_available(code fallback), 8.750초. 주소/버전 준비0.140초, 로컬 조회·채점2.297초, 루프6.266초 |
| 도구 | get_scorecard(ok) → get_facts(ok) → get_scorecard(ok, 다른 인자). 반복0회 |
| 모델 | gpt-6-luna 3회, 입력22,194/출력120. Sonnet0회. 모델3/26(11.5%), 입력13.9%, 출력0.5%, 도구3/40(7.5%), 활성시간8.703/300초(2.90%) |
| 종료 원인 | 다음 호출의 대화11,996자+도구 정의15,136자로 추정13,566토큰 > 기존 호출당12,000. provider 호출 전에 예산 차단. 실제 다음 입력 토큰 수는 측정되지 않음 |
| L·자문·질문 | L observed0, 51개 unknown, 새 L 근거0, 제출/거절0, 자문/지도/규제/ask_user 미호출. 질문이 없어 시험 답변 자동 재개 경로는 실제로 진입하지 않았으며 대역에서 검증 |
| 초안 | 요약과 L 미완료 limitation 존재. 상위5 G20454.375조건부, P10549.375보류, R10248.75보류, G21348.125보류, S20746.875보류. L 반영 전후 변화 없음 |
| DB | 초기화 후 증가1,253,376bytes(1.195MiB), 파일 전체1,576,960bytes(1.504MiB). 기본자료 원문 복사0. 당시 전체1MiB 목표 초과. 현행 용량 목표는 해제됨 |

항목별 용량은 이 Python SQLite에 dbstat가 없어 **인덱스·페이지 헤더를 제외한 저장 열 값의 UTF-8 바이트 합**이다. 파일 증가 실측과 같은 단위의 물리 페이지 분해로 해석하지 않는다. dbstat 계측의 준비 단계 실패는 외부/LLM 호출 전이었으며 승인된 실제 요청은 위1건뿐이다.

| 항목 | 논리 용량(bytes) |
| --- | ---: |
| 사실·계보 | 517,202 |
| 채점(초기·fallback) | 287,089 |
| 대화·질문 | 39,799 |
| 요청·기타 | 33,841 |
| 보고서 | 25,741 |
| 도구·자문 | 13,830 |
| 원문·참조 복사 | 0 |

당시 사용자 지시대로 프롬프트·예산 수치를 수정하지 않고 추가 실행을 멈췄으며, 전체 대화 복원과 호출당12k 사전 추정 상한의 충돌(특히 도구 정의의 토큰 추정)을 다음 검토 대상으로 남겼다. 이후 현행 결정에서 호출당 입력12k 상한과 요청 DB 용량 목표를 해제했다. 위 실행 결과는 변경 전 기록이며 현행 정책의 용량 목표 초과로 보고하지 않는다. 이번 실행으로 L/자문 품질이 나쁘다고 판정할 수는 없다. 요청 용량은 대화보다 사실·계보와 중복 저장되는 채점 자료 비중이 크며, 필요한 근거는 삭제하지 않는다.

408건 기준은 `scripts/verify_rubric_reproduction.py`를 유지한다. 엔진 단독 검증뿐 아니라 **저장된 동일 원천 fixture → 로컬 SQL → 계산 입력 → 점수** 비교를 추가해야 한다. API와 새 분기 CSV의 원래 값 차이를 숨겨 등급을 맞추지 않는다. CSV의 1.014배 유사성은 408건 완전 일치 검증을 대체하지 않는다.

2026-10-19 C1 업종별 방향 변경(모임형·근처형·무관)은 C1 등급을 의도적으로 바꾸므로 `dryrun-results.json`의 "408/408 일치, 배지 9/1/377/21" 기준도 달라진다. 이 PC에는 `backend/cache/rubric_samples`가 없어 재생성하지 못했다. 표본을 가진 사람이 `dryrun-results.json`과 배지 합계를 다시 만들어야 하며, 그 전에는 `verify_rubric_reproduction.py`가 실패하는 것이 정상이다.

### 명시적 측정 모드와 녹화·재생 (2026-10-14)

| 설정 | 운영 기본 | measurement=True 실행 |
| --- | --- | --- |
| 호출당 입력 | 직전 사용자 결정대로 상한 없음 | 상한 없음 |
| 출력 | decision 3,000, 기존 advisor 설정 유지 | max_completion_tokens 최대16,000(남은 누적 출력으로 제한) |
| 전체 안전선 | 입력160k·출력24k·모델26회·300초 | 입력400k·출력60k·모델40회·600초 |
| 역할/도구 횟수 | 기존 역할별 몫 유지 | 역할/도구별 몫·강제 마지막 제출·반복3회 종료를 해제 |
| 조회 안전 | 읽기 전용 SQL·authorizer·행/시간·공간 제한 | 동일하게 유지 |
| 활성화 | 기본값False, 환경변수 추가 없음 | 서비스 함수의 명시 인자. 재개에도 같은 인자, 저장 사용량 계승 |

`recording_path` 또는 측정 실행일 때만 client가 스트리밍 조립 원문 ChatCompletion과 실제 messages를 receipt로 제공한다. `CallRecording`은 모델 응답 원문·tool_calls·usage·시간·오류를 cache JSON에 기록하고 환경 인증값을 제거한다. 녹화 저장 오류는 숨기지 않는다. ReplayGenerate는 응답을 순서대로 공급하고 실제 fact/도구 조회를 실행한다. 동적 UUID 대응·순서가 바뀐 동일 fact집합·timeout 취소를 처리하며 녹화된 모델 시간도 재생 예산에 반영한다.

`scripts/replay_agentic.py --request-db <녹화 요청 DB> --recording <모델 JSON>`은 새 DB 복사본만 수정한다. 원문/facts/초기 점수와 관측 캐시를 재사용하고 HTTP 클라이언트를 금지한다. 모델 호출·도구 순서·초안 제출 객체가 같아야 성공한다. 이 재생은 같은 고정 자료·관측에서의 코드 회귀 검증이며 새로운 데이터 분기 품질 검증을 대신하지 않는다.

| 측정 호출 | 도구 | 입력 | 출력 | 초 | 도구 결과 |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | get_scorecard | 6,506 | 41 | 2.250 | ok |
| 2 | get_scorecard | 7,914 | 35 | 1.719 | ok |
| 3 | get_scorecard | 9,238 | 26 | 1.483 | ok |
| 4 | get_facts | 10,559 | 46 | 1.875 | ok |
| 5 | get_facts | 10,396 | 46 | 2.046 | ok |
| 6 | ask_user | 10,526 | 135 | 2.436 | ok·시험답변 자동 재개 |
| 7 | get_facts | 11,061 | 101 | 2.467 | ok |
| 8 | submit_draft | 11,895 | 1,410 | 39.313 | L_EVIDENCE_INVALID: 문장 숫자는 fact 슬롯이어야 함 |
| 9 | submit_draft | 13,612 | 1,299 | 10.500 | ok·유효 초안 저장 |

- 합계모델9회(gpt-6-luna), 입력91,707·출력3,139, 전체66.641초. 모델시간합계64.089초, 최초14.110초/답변 재개52.531초. 안전선 차단 없음, 정상 submit_draft로 종료. 자문·지도·규제 미호출.
- G204 종합소매만 L observed, 2등급/5점. 1층 유리+주방·배기 없음 불리의 두 새 fact를 인용. 하한54.375→59.375, 배지조건부 유지. 나머지50업종 L unknown, 초기 상위10중1개만 검토. 이 해석의 업종 관련성(종합소매에 주방 없음이 불리한가)은 다음 프롬프트·평가 단계에서 검토해야 한다.
- 수락 초안 proposal_json은 UTF-8 4,030bytes, 마지막 호출출력1,299토큰/10.500초. 요청 DB 증가1,318,912bytes(1.258MiB)는 실측만 기록한다. 용량 목표 없음.
- 녹화: `cache/measurement-e2cdb78ecfa0414ca6514da06e6d6f72-model-calls.json`(192,436bytes/9호출), 요청 DB도 같은prefix. 환경 비밀값 포함 없음 확인. 대역 녹화/재생과 실제 녹화9개 재생 모두 도구 순서·초안 일치, 추가 외부/LLM 호출 없음.

상한은 실측×1.5를 올림한 **미적용 제안**이다. 이번 표본은 주소1개·L1업종·자문0회·평가0회이므로 전체 평가 경로의 한도로 적용하기 전에 추가 범위를 검증해야 한다. 출력16k는 측정용일 뿐 운영 설정을 바꾸지 않았다.

| 상한 제안 | 실측 기준 | ×1.5 올림 |
| --- | ---: | ---: |
| 호출당 출력 | 최대1,410 | 2,115토큰 |
| 누적 입력 | 91,707 | 137,561토큰 |
| 누적 출력 | 3,139 | 4,709토큰 |
| 모델 호출 | 9 | 14회 |
| 전체 시간 | 66.641초 | 100초 |

운영 초안 몫8회/강제 제출은 아직 유지한다. 측정 완료에9회가 필요했으므로 역할별 몫을 포함한 적용은 사용자 확인 이후 별도 변경한다. 측정 자체는1회만 실행했고 프롬프트·schemas.py·.env·education_zone.py는 변경하지 않았다.

### 삭제 / 유지

| 대상 | 처리·이유 |
| --- | --- |
| 기본 5원천의 PR2 transport 수집 hooks·요청별 page 원문 저장 | 삭제. 외부 client는 갱신 스크립트 전용으로 제한 |
| raw_payloads/raw_responses/raw_rows/raw_response_rows의 기본자료 경로 | 삭제. 자료 DB의 자연키·버전이 원문을 한 번 보존하므로 요청별 해시/행 연결 구조 불필요 |
| 기본 집계의 행별 fact_sources·행 UUID/응답 ID 목록 | 버전+쿼리 조건+계산 버전으로 교체. 직접 셀만 버전/행 키/열 계보 |
| 상가 radius/district raw-v2 캐시와 원문 재복사 | 런타임 삭제. 자료 버전·인덱스가 대체. 과거 캐시는 fixture 검증 후 운영 경로에서 읽지 않음 |
| resident.csv/worker.csv 요청 읽기·재저장 | 자료 DB 조회로 교체. 기존 파일·파서는 초기 적재/회귀용 유지 |
| SHP 요청별 읽기/범위 판정 | 적재·공간 조회로 이관. 기존 parser/CRS·polygon/최근접 계산은 재사용 |
| 지도·규제·임대인 관측 | 유지하되 작은 요청 관측과 fact 계보로 단순화. education_zone.py 수정 없이 출력 읽기 |
| `_write`, scrub, 협력적 취소·실패 진단/사용량 | 공통 유틸로 유지. 저장 모델이 바뀌어도 스레드 격리·키 제거·오류 전파는 필요 |
| 51업종 CSV/catalog·map_stores·profiles | 유지. 적재 시 매핑과 버전 검증. 소분류 분할·합병·제외 규칙 동일 |
| density/population/lifecycle baseline·scoring.py | 유지. 버전 고정·기간 한계 표시. 갱신은 배치 검증으로 분리 |
| 공정위 `load_brands()`의 숨은 실시간 호출 | 요청에서 삭제. 필요 시 운영자가 갱신한 별도 브랜드 자료/캐시만 읽고 없으면 unknown·한계 표시 (`commercial_area/franchise.py:100`) |
| 기존 브리핑·전문가·모드·legacy 근거 | 기존 단일 모드 전환 결정대로 삭제. 자료 DB 전환 때문에 되살리지 않음 |

행 단위 payload_hash 공유는 기본자료에 **유지하지 않는 쪽을 권고**한다. typed 자료 테이블/자연키가 중복 적재를 막고 snapshot은 ID만 저장하므로 raw 전개·관측 링크·중복 검사 코드를 없앨 수 있다. 최종 코드 줄 수/자료 크기/요청 증가량은 LD4에서 비교하며 현재 문서만으로 절감 측정치를 주장하지 않는다.

## 12. 결정·사용자 확인

확정: 분기 로컬 DB·수동 갱신·최신 보유 버전 사용·원천별 기간 표시·RAG 없음·지도/규제만 실시간·기존 51업종/채점표/decision/평가 계약 유지. 최초 실패 추적은 종료하고 이후 오류는 기록된 진단으로 다룬다.

| 사용자 확인 | 권고·필요 자료 |
| --- | --- |
| 직접 내려받는 상가 파일 | 이미 받은 `소상공인시장진흥공단_상가(상권)정보_서울_202606.csv` 재사용 가능. 이후 [공공데이터포털 상가정보 파일](https://www.data.go.kr/data/15083033/fileData.do)의 분기 ZIP 중 서울 파일. 저장소 밖 보관 |
| 점포·개폐업 파일 | [서울 열린데이터광장](https://data.seoul.go.kr/)에서 **상권분석서비스(점포-상권)** / `VwsmTrdarStorQq`를 찾고 파일 탭에 CSV/Excel이 있으면 **상권별 최근12분기·원필드 포함본** 전달. 이번에는 제공 여부 미확인. 없으면 분기 전체 1,000행 페이지 배치 사용 |
| 유동 파일 | [길단위인구-상권 OA-15568](https://data.seoul.go.kr/dataList/OA-15568/S/1/datasetView.do). 파일이 있으면 최근5분기, 없으면 기존 API 분기 전체 약10회 초기 수집 권고 |
| 상주·직장 | 현재 두 CSV로 초기 시작 가능. [상주 OA-15584](https://data.seoul.go.kr/dataList/OA-15584/S/1/datasetView.do), [직장 OA-15569](https://data.seoul.go.kr/dataList/OA-15569/S/1/datasetView.do)의 파일 제공은 미확인. 전체 원필드가 필요하면 기존 스크립트 배치를 갱신 단계로 이관 |
| SHP/대표점·면적 | 현재 TbgisTrdarRelm 5종 파일 묶음과 패키지 seoul_trade_areas.csv 사용 가능. 이후 [영역-상권 OA-15560](https://data.seoul.go.kr/dataList/OA-15560/S/1/datasetView.do)에서 영역 자료를 찾되 API 중심점 JSON을 SHP로 대체하지 않음. SHP 실제 갱신 출처/시점은 받은 묶음의 제공 메타데이터 필요 |
| 서울 경계 | 서울 CSV만 쓰는 첫 버전은 서울 범위를 표시. 서울 외곽 500m/2km에 포함되는 경기 점포까지 분석하려면 해당 지역 CSV 추가 필요 |
| 최신 자료와 기준선 | 우선 기존 v0.8 기준선 고정·시점 차이 표시 권고. 자동 갱신하지 않고 동기간 기준선 업데이트는 별도 검증 |
| 보존 | 활성 release + 직전 release 1개만 보존. 분기 창(개폐업12·유동5)은 각각 release 안에 포함. LD3 질문 세션 연결 전 오래된 버전 제거 시 처리 검증 |
| 구현 승인 | LD1·LD2는 승인된 구현/적재를 진행. 요청 경로 교체는 후속 LD3이며 유료 실행/LLM 호출은 하지 않음 |

상가 외 서울시 파일의 실제 헤더가 오면 API 필드와 일대일 비교하고 누락 여부를 확정한다. 위 링크는 저장소의 기존 서비스/주소 근거를 재사용한 것으로 이번에 사이트를 열어 최신 파일 제공을 확인한 것이 아니다.

## 13. 팀 공지 문안

### 프론트 담당

- 구조 구현 PR은 feat/agentic-decision에 모으고 LD6 전환 완료 후 develop에 한 번에 병합합니다.
- 기존 PR1 계약을 재사용하고 LD5에서 목업 GET·원천별 자료 분기·자료조회/채점 stage를 제공합니다.
- develop 리포트 화면(#38)을 코드 ○/90 + L ○/10·점수 구간·배지·Top 5·fact 슬롯에 맞춰 변경해야 합니다.
- 판단 미검토·평가 미완료·새 질문 재개와 실제 진행 stage를 연결하고, LD6 전환 전 프론트 검사를 통과합니다.
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
| v0.4 (2026-10-14) | 분기별 서울 로컬 자료 DB·버전 고정 snapshot·셀/집계 계보·수동 갱신·뷰 범위·LD1~LD6 전환. 요청 API/원문 복사 제거, 목표10초/1MiB. 코드 미적용 |
| v0.3 (2026-10-14) | 단일 모드·항상 평가·fact 전용 근거·구 DB 초기화 결정. 지도 LLM/캐시 제거, schemas와 내부 contracts 분리, PR7 전환·통합 브랜치·팀 공지 추가 |

PR1 배치 보완: PR1~PR6는 모든 새 계약을 contracts.py에 두고 schemas.py를 수정하지 않는다. PR7 이동 시 내부 계약 의존/import도 함께 정리하며 기존 실행 경로를 제거한다.


## 부록 — v0.3 및 PR2~PR5 구현·실행 기록 (현재 구현 이력)

이하 원문 hook·해시 공유·계보 최적화·실실행 기록은 비교 근거다. v0.4 요청/갱신 구조에서 계속 확장하지 않는다. 미착수한 구 단일-구 공유 참조 구현도 분기 로컬 DB로 대체하며 이번에 코드는 바꾸지 않았다.

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
| 단일 채점 엔진 | app/agentic/scoring.py가 rubric_dryrun.py의 v0.8 계산·판정을 소유. CLI는 import만 하며 민감도 시험을 유지 |
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

#### PR5 실패 기록·원문 저장 보완

- decision_failures 진단과 logger에 예외 클래스·오류 코드·안전한 메시지·원인 예외·수집/채점/루프 단계·시간을 남긴다. 키와 URL은 제거하며 사용자 오류 문구는 유지한다.
- 본문과 행은 payload_hash별 INSERT OR IGNORE로 공유한다. 요청별 관측 연결은 따로 저장하고 모든 뷰·fact 검증은 현재 요청·스냅샷의 연결을 확인한다.
- 요청 안 원문 작성자는 스레드 잠금으로 직렬화한다. 한 페이지는 한 트랜잭션이며 SQLite busy_timeout은 30초다. 서버 여러 대의 작성자 조정은 후속 검토 대상이다.
- 원문 행 중복 조회는 row_hash 인덱스부터 탐색한다. 요청의 모든 원문 행을 반복 훑는 실행 계획을 피한다.
- 이전 DB 이전은 하지 않는다. 비교용 구 DB는 읽기만 했고 새 실행은 새 SQLite 파일을 쓴다. 운영 DB 초기화는 PR7 범위다.

| 63페이지 오프라인 비교 | 수정 전 | 수정 후 |
| --- | --- | --- |
| 동시성·네트워크 | 작성 요청 네 개, 외부 호출 없음 | 작성 요청 네 개, 요청 안 직렬화, 외부 호출 없음 |
| 첫 요청 시간·용량 | 15.53초 / 144.01MiB | 21.97초 / 164.99MiB |
| 두 번째 요청 시간·증가량 | 23.70초 / 144.00MiB | 13.81초 / 14.35MiB |
| 두 요청 누적 | 288.01MiB | 179.34MiB |
| 공유 본문·행 | 요청마다 복사 | 본문 63벌·행 61,278개 유지, 관측 연결만 증가 |
| 잠금 오류 | 두 요청 모두 재현 안 됨 | 두 요청 모두 없음 |

최초 실패 원인은 미확정이다. 기존 상권 응답 63개는 반경 54개·강남구 9개다. 동시 상주/직장 파일·다른 분석 쓰기가 섞인 잠금 경합, 실제 API 오류/취소, 수집 후 계약 검증·저장 경계가 남은 후보다. 새 진단으로 승인 재실행 결과를 확인하며 이를 추정으로 덮지 않는다.

##### 승인 재실행 결과와 오프라인 보완

| 항목 | 결과 |
| --- | --- |
| 실실행 | 새 DB에서 한 번만 재시도. 유동 ok·상권/개폐업 partial 저장, 상권 원문 121개 응답 완료 |
| 실패 | 채점 단계가 300초 상한을 넘긴 뒤에도 스레드 종료를 기다려 끝나지 않음. 약 646.98초에 외부 종료 |
| 기록 | decision_failures에 TimeoutError·채점·외부 종료 사실(external_termination=true) 기록. 자연 발생 SQLite 잠금 오류로 기록하지 않음 |
| 시간 정확도 | 수집은 마지막 원문 시각 기준 91.34초 이상, 채점·정리 시간은 나머지 555.64초 이하 추정. phase_times_estimated=true이며 루프는 미실행 |
| DB 증가량 | 새 전체 수집 DB 344.51MiB. 63페이지 부분 수집 DB와 직접 비교하지 않음 |
| 모델 결과 | 모델·도구·자문 호출 영 회, 입력/출력 토큰 영. L 기록·최종 Top 5 없음 |
| 이번 원인 | 중간 연결 테이블을 통한 계보 검증이 행마다 스냅샷 응답 목록을 반복 탐색. _write의 취소 대기가 장시간 작업을 계속 기다림 |
| 오프라인 수정 | 계보를 400행 단위·원문 행 인덱스부터 검증. 취소 신호를 스레드에 전달하며 배치 경계에서 현재 fact 트랜잭션 롤백 후 종료 |
| 저장 자료 검증 | 실실행 DB 복사본으로 채점만 다시 수행: 20.92초, facts 1,006개·scores 561개. API·LLM 호출 없음 |

실실행은 추가로 돌리지 않았고 프롬프트는 고치지 않았다. 마지막 계보·취소 보완 이후 실제 모델 루프 연결은 미검증이다.
