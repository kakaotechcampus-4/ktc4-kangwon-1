# 멀티에이전트 전환 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans 또는 superpowers:subagent-driven-development로 아래 작업을 순서대로 수행합니다. 체크박스는 검증까지 끝난 항목만 완료 처리합니다.

**Goal:** 기존 계산·근거 검증을 유지하면서 전문가 브리핑, 최대 2라운드 되묻기, 선택적 임대인 질문·재개를 추가합니다.

**Architecture:** 초기 분석은 기존 고정 그래프로 실행합니다. `multi_agent`에서만 공통 전문가 실행기를 붙이고, 감독 역할의 최종판단이 되묻기를 선택합니다. 원자료와 최종 결과 계약은 유지하며, 저장된 실행 모드·예산·자료 차수로 재개합니다.

**Tech Stack:** Python 3.12, 기존 LangGraph·Pydantic·httpx·OpenAI 호환 클라이언트·SQLite·unittest. 추가 의존성 없음.

**Spec:** [multi-agent-design.md](../../multi-agent-design.md). 이 문서는 설계의 구현 계획이며, 아래 보완 결정은 구현 전 확인 대상입니다.

**실행 결과(2026-09-29):** 작업 1~7 구현 및 대역 검증 완료. 백엔드 540개·검증 도구 31개 통과.
세부 검증·리뷰 보완·실측 전 한계는 [진행 기록](../../multi-agent-progress.md)에 정리했습니다.
P6 유료 실측·팀 승인·발표자료는 이번 완료 범위에 포함하지 않습니다.

## Global Constraints

- 기준: `feature/mvp-1.5-orchestra`, `d2c4571`. 설계의 P1~P5 구현과 P6 측정 준비가 범위입니다.
- `AnalysisTask`, `AgentAnalysis`, `DecisionResult`의 필드와 기존 API 최종 응답은 유지합니다.
- 기본값은 `ANALYSIS_MODE=single_decision`. `multi_agent`만 새 브리핑·되묻기 경로를 사용합니다.
- 판정 지시문 수정은 허용됐습니다. 이미 수정된 `decision/prompt.md`의 도구 우선·폐업률 규칙과 `decision/agent.py`의 P0 변경을 보존하고 필요한 차이만 덧붙입니다.
- 계산·공간 범위·75개 업종표를 바꾸지 않습니다. 에이전트 사이 직접 의존을 새로 만들지 않고 연결은 오케스트레이션에서 담당합니다.
- 전문가별 도구 최대 4회, 되묻기 최대 2라운드, 라운드당 최대 3명·전문가당 1질문, 임대인 최대 1회·3항목, 전체 LLM 최대 12회, 그래프 재귀 제한 32.
- 전체 실행 시간은 기존 `ANALYSIS_TIMEOUT_SECONDS` 기본 600초. 사람의 답변 대기 시간은 제외하되 실행·재개가 사용한 시간을 합산합니다.
- 외부 호출은 비동기, SQLite·파일 작업은 `asyncio.to_thread()` 사용. 취소·저장·원자료 계약 오류를 전문가 실패로 숨기지 않습니다.
- 프론트엔드·발표자료는 수정하지 않습니다. 커밋·푸시, 유료 실측은 별도 요청 전 수행하지 않습니다.
- 설계의 팀 공통 계약 PR 합의는 구현·테스트 성공과 별도입니다. 이 작업만으로 팀 승인을 받았다고 기록하지 않습니다.

## Review Focus

1. 병렬 전문가·지도 매핑·교정·질문 재개가 호출 예산을 각각 초기화하거나 초과하지 않아야 합니다. 작업 3·6에서 검증합니다.
2. 사용자 답변을 기다리는 동안 환경변수가 바뀌어도 기존 요청의 실행 모드·자료 차수·업종표 버전은 바뀌면 안 됩니다. 작업 6에서 검증합니다.
3. 다른 업종의 숫자, 인용 불가 값, 우연히 같은 숫자는 근거가 아닙니다. 작업 2에서 소유 업종·경로·단위를 함께 검증합니다.
4. 보완·지도 조회를 여러 번 해도 이전 정상 자료와 이력이 사라지면 안 됩니다. 작업 4·6에서 검증합니다.
5. 외부 모델 실패는 대체 브리핑으로 계속할 수 있지만 저장 실패·취소는 성공으로 바뀌면 안 됩니다. 작업 3·5·6에서 검증합니다.

## 기존 설계에 필요한 보완 결정

| 항목 | 구현 기준 |
| --- | --- |
| 호출 예산 | 설계의 `3+3+6`에는 도구 선택과 교정이 빠져 있습니다. 실제 모델 요청 시도를 모두 세며, 지도 업종 매핑도 포함합니다. 멀티 모드의 SDK 내부 자동 재시도는 끄고 숨은 호출을 없앱니다. |
| 최종판단 예산 | 전문가 작업에는 마지막 판정·교정용 2회를 사용하지 못하게 합니다. 예산이 부족하면 도구를 더 제공하지 않고 현재 유효 자료로 마무리하도록 요청합니다. 유효한 최종 결과가 없으면 명시적 실패이며 결과를 만들어 성공시키지 않습니다. |
| 지시문 | 도구 우선·폐업률 표현은 유지합니다. 기존 모드의 `supplement/map_lookup`와 새 모드의 `ask_specialists`를 분리합니다. 새 모드는 답변 후에도 남은 예산 안에서 전문가에게 물을 수 있지만 임대인 재질문은 금지합니다. |
| 지도 답변 | 지도는 `AgentAnalysis`가 아닙니다. `SpecialistAnswer`에 선택형 `map_observation`을 추가하고, 지도 답변은 기존 `MapObservation.data`의 허용된 경로를 검증합니다. |
| 지도 이력 | 현재 요청당 한 행인 `map_observations`를 `(request_id, attempt)` 이력으로 확장합니다. 기존 행은 1차로 보존합니다. 최종 결과에는 최신 채택 관측 하나만 들어갑니다. |
| 지도 검색 범위 | 기존 계약의 최대 5개 조회를 유지합니다. 새 검색은 기존 조회와 합친 최대 5개 계획으로 기존 `observe()`를 실행합니다. 동일 조회는 저장 결과를 재사용합니다. 여섯 번째 조회는 거절 기록을 남깁니다. 새 집계 알고리즘은 만들지 않습니다. |
| 보완 이력 | 현재 결과 차수 2 고정을 제거합니다. 저장소가 다음 차수를 발급하고, 채택한 차수만 최종 결과·질문 스냅샷에 참조합니다. 실패한 시도는 이전 정상 결과를 대체하지 않습니다. |
| 실행 상태 | 요청에 실행 모드와 사용 예산을 저장합니다. 대기·재개·판정 재시도로 12회 예산을 초기화하지 않습니다. 이미 소진했다면 새 요청 없이 추가 유료 호출을 하지 않습니다. |
| 폐업률 요약 | 원자료의 `rate_basis`·기간·단위를 보존합니다. 설계의 ‘석 달 평균’은 최근 4개 분기의 점포 수 기준 가중 분기 비율과 구분해 표현하며 새 평균을 계산하지 않습니다. |

## 파일 구성

| 파일 | 책임 |
| --- | --- |
| `backend/app/schemas.py` | 브리핑·되묻기·답변·v2 스냅샷 추가 |
| `backend/app/evidence.py` (이동·확장) | 기존 근거 경로 탐색을 공용화. `decision/evidence.py`는 기존 import 호환 유지 |
| `backend/app/agents/specialists/{__init__.py,agent.py,tools.py,prompt.md}` (신규) | 네 역할이 공유하는 제한형 도구 실행·브리핑·답변. 역할별 실행기 복제 금지 |
| `backend/app/agents/decision/context.py` (신규) | 원자료에서 75개 업종 요약표·동네 정보·후보 경로 생성 |
| `backend/app/agents/decision/{agent.py,llm.py,prompt.md}` | 축약 입력과 새 행동 해석, 기존 최종 검증·교정 재사용 |
| `backend/app/agents/orchestration/{graph.py,consult.py,supplement.py}` | `consult.py` 신규, 전문가 도구 연결·병렬 응답·채택·분기 |
| `backend/app/llm/{client.py,budget.py}` | `budget.py` 신규, 요청 단위 호출 예산과 사용량 기록 |
| `backend/app/services/{settings.py,analysis.py}` | 역할별 설정, 저장 콜백, 실행·재개·판정 재시도 |
| `backend/app/db/{schema.sql,connection.py,repository.py}` | 새 이력과 기존 DB 마이그레이션 |
| `backend/app/api/v1/routes.py` | 조회 응답에 선택형 `deliberation` 추가 |
| `backend/.env.example`, `backend/pyproject.toml` | 모드·역할별 설정 안내, 전문가 프롬프트 패키지 포함 |
| 아래 작업별 테스트·문서 | 대역 검증, 실행 계약·측정 절차 기록 |

## 작업 1 — 추가형 공통 계약

**Files:** `backend/app/schemas.py`, `backend/tests/test_specialist_contract.py`(신규), `docs/API_CONTRACT.md`.

**Interfaces:** 설계 §5의 `SpecialistId`, `EvidenceRef`, `Finding`, `AgentBrief`, `SpecialistQuery`, `ConsultPlan`, `SpecialistAnswer`, `ToolCallRecord`를 추가합니다. `SpecialistAnswer.map_observation: MapObservation | None = None`과 `limitations: list[Text] = []`를 더합니다. `QuestionSnapshot` v1은 유지하고 `QuestionSnapshotV2`를 별도로 추가합니다.

- [x] 실패 테스트 작성: 알 수 없는 업종 코드, 한 라운드 같은 전문가 중복, 4명 질문, 3라운드 답변, 다른 요청의 분석·지도 삽입을 모두 거절합니다. 지도 답변의 `analysis`와 일반 분석 답변의 `map_observation`도 거절합니다.
- [x] `python -m unittest discover -s tests -p test_specialist_contract.py -v`로 기대한 계약 실패 확인.
- [x] 모델 제약 구현. 요청 ID·agent ID·도구 이력은 코드가 소유하며 모델이 바꾸지 못합니다. `QuestionSnapshotV2`는 기존 task·waiting·source_attempts에 brief 에이전트 목록·완료 consult 라운드·지도 채택 차수·소비 예산을 참조합니다.
- [x] 기존 v1 직렬화와 세 원본 계약의 JSON 스키마가 달라지지 않았음을 비교하고 테스트 통과 확인.
- [x] 계약 문서에 현재·신규 모드를 구분해 기록. 이 단계에서 서비스 기본 동작은 변경하지 않음.

## 작업 2 — 축약 입력과 전문가 근거 검증

**Files:** `backend/app/evidence.py`, `backend/app/agents/decision/evidence.py`, `backend/app/agents/decision/context.py`, `backend/app/agents/specialists/tools.py`, `backend/tests/test_specialist_context.py`(신규), 기존 `test_decision_evidence.py`.

**Interfaces:**
- `build_context(request: DecisionRequest, *, briefs: list[AgentBrief], answers: list[SpecialistAnswer]) -> dict[str, JsonValue]`: `industry_digest`, `neighborhood`, `briefs`, `answers`, `industry_evidence` 생성.
- `validate_findings(findings: list[Finding], *, agent_id: SpecialistId, data: dict[str, JsonValue]) -> tuple[list[Finding], list[str]]`: 유효 항목과 안전한 폐기 사유 반환.
- `fallback_brief(task: AnalysisTask, analysis: AgentAnalysis) -> AgentBrief`: 검증 가능한 기존 수치·경고만 사용.

- [x] 실패 테스트 작성: 요약표 코드 집합이 마스터 75개와 일치하고, 실제 0·결측·인용 불가가 구분되며 원자료를 수정하지 않는지 확인.
- [x] 다른 업종 경로, `citable:false`, 부모 경로 우회, 없는 경로, 임의 숫자·퍼센트 환산을 넣은 finding은 제거되는 테스트 추가.
- [x] `python -m unittest discover -s tests -p test_specialist_context.py -v`로 실패 확인.
- [x] 기존 `index_paths()`와 업종 소유 판단을 공용 위치로 이동하고 이전 import는 얇게 유지. 지도 경로 허용 규칙도 최종판단과 전문가가 같은 검증을 사용하게 함.
- [x] 요약표는 업종별 점포 수·LQ·개폐업 지표·점수·신뢰도를 값·단위·기간·원본 경로와 묶음. 점수 없는 업종도 행은 유지. 후보 경로는 브리핑·답변 업종과 점수 상·하위 각 5개에서 선택하고, 75개 행의 핵심 경로는 항상 노출.
- [x] 숫자 검증은 인용된 스칼라 값과 표기 단위를 비교. 정수는 일치, 소수는 표기 마지막 자리의 반 단위까지 반올림 허용. 지원하지 않는 단위 변환·숫자 축약·기간 파생은 허용하지 않음. 날짜·업종 코드 자체를 지표 숫자로 비교하지 않는 테스트 포함. 문자열 전체에서 우연히 같은 숫자를 찾는 방식은 금지.
- [x] 인구는 통행량·상주·직장 인구를 별도 값으로 유지. 브리핑 `claim`과 `headline`은 인용 가능한 경로 목록에서 제외.
- [x] 위 테스트와 기존 `test_decision_evidence.py` 통과 확인.

## 작업 3 — 공통 전문가 실행기·역할별 모델·호출 예산

**Files:** `backend/app/agents/specialists/{__init__.py,agent.py,tools.py,prompt.md}`, `backend/app/llm/{client.py,budget.py}`, `backend/app/services/settings.py`, `backend/.env.example`, `backend/pyproject.toml`, `backend/tests/test_specialist_agent.py`·`test_llm_budget.py`(신규), 기존 `test_execution_settings.py`.

**Interfaces:**
- `SpecialistTool`: 도구 JSON 정의와 `execute(arguments: dict[str, JsonValue]) -> Awaitable[dict[str, JsonValue]]`를 묶음. 실행기는 등록된 도구만 호출.
- `write_brief(task: AnalysisTask, analysis: AgentAnalysis, *, generate, tools: dict[str, SpecialistTool]) -> AgentBrief`.
- `answer_query(task: AnalysisTask, query: SpecialistQuery, round_number: int, *, analysis: AgentAnalysis | None, observation: MapObservation | None, generate, tools: dict[str, SpecialistTool]) -> SpecialistAnswer`.
- `LLMBudget(limit=12, used=0)`의 `reserve(role: str, *, final: bool) -> int`: 요청 시도 번호를 원자적으로 배정. 호출 기록에 모델 역할·입출력 토큰·경과 시간·성공 여부 저장.

- [x] 실패 테스트: 4번째 도구 이후 추가 실행 금지, 미등록 도구·잘못된 인자 거절, 모델 실패·잘못된 finding은 fallback, 취소는 전파. 대역 함수를 넣으면 환경변수 키 유무와 무관하게 네트워크 0회.
- [x] 예산 테스트: 병렬 예약도 전체 12회 이하, 전문가가 최종용 2회를 소비하지 못함, 교정·지도 분류·실패한 HTTP도 소비, 다른 요청의 예산과 섞이지 않음.
- [x] `python -m unittest discover -s tests -p test_specialist_agent.py -v`와 `test_llm_budget.py` 실패 확인.
- [x] 기존 `complete_tools()`·`complete_json()` 전송을 재사용해 한 개 실행기 구현. `finish` 도구로 검증할 브리핑/답변을 제출하고 중간 도구 출력은 비신뢰 데이터로 전달. 도구 한도에 도달하면 추가 도구를 제거하며 예산이 없으면 코드 요약으로 끝냄.
- [x] 요청 단위 예산 문맥을 공통 전송에서 소비. 멀티 모드만 SDK 자동 재시도 0으로 설정. 모델이 반환하지 않은 usage는 0으로 꾸미지 않고 미확인으로 남김.
- [x] `SPECIALIST_FLOATING_POPULATION`, `SPECIALIST_BUSINESS_LIFECYCLE`, `SPECIALIST_COMMERCIAL_AREA`, `SPECIALIST_MAP_ANALYSIS` 접두어를 기존 `LLMSettings.from_env()`에 전달. 공통 ELICE 설정 fallback은 유지하고 모델 이름을 임의 지정하지 않음.
- [x] 실패 관찰은 경고·limitations에, 의도된 데이터 축약은 메타데이터에 기록. 프롬프트 패키지 포함과 설정 테스트 통과 확인.

## 작업 4 — 기존 계산·보완·지도 도구 연결

**Files:** `backend/app/agents/orchestration/consult.py`(신규), `backend/app/agents/orchestration/supplement.py`, `backend/app/agents/specialists/tools.py`, `backend/tests/test_specialist_tools.py`(신규), 기존 `test_real_supplements.py`·`test_map_analysis.py`.

**Interfaces:** `build_specialist_tools(task, agent_id, *, analyses, supplements, map_lookup, hooks) -> dict[str, SpecialistTool]`. 도구 래퍼는 코드가 가진 요청·사이트·반경만 사용합니다. 모델에는 주소·요청 ID를 바꾸는 인자를 주지 않습니다.

- [x] 설계 §6 도구 전체에 대해 읽기 전용 함수가 외부 API를 부르지 않고 해당 전문가 자료만 반환하는 실패 테스트 작성.
- [x] `fetch_quarter_details(codes)`는 기존 보완 전체 계산을 재사용하되 반환 상세만 요청 코드로 제한. `retry_lq_baseline()`도 기존 `eligible/accept`를 통과해야 채택. 이전 정상 값 변조 시 거절 테스트 추가.
- [x] 지도 미등록 시 도구 미제공, 지원 시설 코드 외 거절, 공통 업종 75개 외 거절, 같은 검색 재사용, 누적 6개 조회 거절, 지도 실패 후 이전 정상 관측 유지 테스트 추가.
- [x] `python -m unittest discover -s tests -p test_specialist_tools.py -v`로 실패 확인 후 래퍼 구현.
- [x] 도구가 채택한 자료는 오케스트레이터에 반환하고 저장 성공 이후 판정 입력에 반영. 지도 누적 계획은 기존 `observe()`로 재조회하며 별도 수치 병합은 만들지 않음.
- [x] 기존 보완·지도 회귀 테스트 통과 확인. 분석 계산 본체의 diff가 없는지 확인.

## 작업 5 — 감독 판정·되묻기 그래프

**Files:** `backend/app/agents/orchestration/{graph.py,consult.py}`, `backend/app/agents/decision/{agent.py,llm.py,prompt.md}`, `backend/tests/test_multi_agent_graph.py`(신규), 기존 `test_orchestration_graph.py`·`test_question_graph.py`·`test_decision_integrity.py`.

**Interfaces:**
- `run_graph()`에 기본 `mode="single_decision"`과 전문가 생성 함수 주입을 추가. 반환은 계속 `DecisionResult | WaitingForInput`.
- `decision.evaluate()`에 선택형 `deliberation` 입력을 추가하고 `ConsultPlan` 반환 지원. 미지정이면 기존 입력·분기 유지.
- `RunHooks`에 `on_brief(AgentBrief)`·`on_consult(SpecialistAnswer)` 저장 알림 추가. 기존 콜백 생략 호출 유지.

- [x] 실패 테스트: 세 분석 뒤 브리핑 병렬 실행 → 판정 → 전문가 최대 3명 병렬 → 재판정. 지도는 요청 전 미실행, 인구도 되묻기 대상, 3라운드는 거절.
- [x] 한 전문가 실패에도 나머지 정상 브리핑·원자료 유지, 브리핑 경로 최종 인용 거절, 최종 업종·근거 교정이 기존처럼 수행되는 테스트 추가.
- [x] `python -m unittest discover -s tests -p test_multi_agent_graph.py -v`로 실패 확인.
- [x] 새 모드만 `write_briefs`·`consult` 노드를 연결. 기존 모드의 보완·지도 분기는 유지. 새 모드에서 직접 `supplement/map_lookup` 출력은 실행하지 않음.
- [x] P0 지시문 변경 위에 모드별 행동 목록을 반영. 임대인 질문은 중요하고 답할 수 있는 정보에 한정하며 필수 단계로 만들지 않음. ‘답변 후 도구 금지’는 기존 모드에만 적용.
- [x] 보완·지도 갱신 후 오래된 finding을 새 원자료로 재검증. 판정 입력은 축약하지만 최종 검증과 `source_analyses`는 채택 원자료 사용.
- [x] 한도 도달 시 도구 미제공·명시적 관찰을 전달하고 최종판단·교정 예산 내 종료. 기존·신규 그래프 테스트 통과 확인.

## 작업 6 — 저장·v2 재개·조회 계약

**Files:** `backend/app/db/{schema.sql,connection.py,repository.py}`, `backend/app/services/analysis.py`, `backend/app/api/v1/routes.py`, `backend/tests/test_deliberation_repository.py`·`test_multi_agent_service.py`(신규), 기존 `test_question_repository.py`·`test_question_service.py`·`test_decision_retry.py`·`test_api_interactive.py`.

**Interfaces:**
- `save_agent_brief(brief, *, db_path=None) -> None`, `list_agent_briefs(request_id, *, db_path=None) -> list[AgentBrief]`.
- `save_specialist_answer(answer, *, db_path=None) -> None`, `list_specialist_answers(request_id, *, db_path=None) -> list[SpecialistAnswer]`.
- `save_supplement_event()`는 저장된 분석 차수를 반환. 호출자가 무시하던 기존 방식은 유지.
- `load_resume_context()`는 저장 모드와 v1/v2를 판별해 자료·브리핑·답변·예산을 함께 반환. v1은 기존 경로로 처리.

- [x] 실패 테스트: 새 DB·현재 DB·v1 대기 DB의 반복 마이그레이션에서 행·외래키·이력 보존, 새 연결에서도 동일 결과 조회, 중복 브리핑·답변 거절.
- [x] `agent_briefs` PK `(request_id, agent_id)`, `specialist_consults` PK `(request_id, round, agent_id)`와 JSON·상태·라운드 제약 추가. 최초 브리핑은 보존하고 지도 브리핑은 최신 지도 답변에서 파생.
- [x] `analysis_requests`에 실행 모드·예산 기록 추가. `map_observations` 차수 이력 마이그레이션, `supplement_events`에 분석 차수 참조 추가. 기존 행은 기존 의미로 복원하며 NULL에서 자료를 추정하지 않음.
- [x] `python -m unittest discover -s tests -p test_deliberation_repository.py -v`와 `test_multi_agent_service.py`로 실패 확인 후 저장 구현.
- [x] 호출 예약을 외부 전송 전에 저장하고 사용량을 종료 후 반영. 저장 실패 시 호출·성공 반환 금지. 사람 대기 전 남은 실행 시간·예산을 확정하고 재개 시 이어 씀.
- [x] v2 스냅샷 참조를 저장 자료와 대조. 같은 답변의 중복 제출은 기존 멱등 처리 유지, 다른 답변·다른 요청·업종표 버전 불일치는 거절.
- [x] 질문 답변 후 기존 분석·브리핑은 재실행하지 않음. 남은 전문가 라운드는 가능하지만 질문 재발행 금지. 판정 재시도는 저장된 자료로 최종 출력만 교정하며 새 외부 분석 금지.
- [x] GET 응답에서 멀티 모드만 `deliberation` 제공: 브리핑·라운드별 질문/답변·도구 실행 상태·소비 예산. 비밀키·원문 프롬프트·원문 예외 노출 금지. POST 최종 결과 형태는 유지.
- [x] 모드 환경변수 변경 후 재개, 답변 후 예산 초과 방지, 중도 저장 실패·취소, 두 요청 병렬 실행 테스트와 기존 서비스/API 테스트 통과 확인.

## 작업 7 — 전체 대역 검증·측정 준비·문서

**Files:** `backend/tests/test_multi_agent_flow.py`(신규), `backend/README.md`, `docs/API_CONTRACT.md`, `docs/TECH_DECISIONS.md`, `docs/multi-agent-progress.md`(신규). 로컬 검증 도구는 `validation_tool/run.py`, `validation_tool/test_validation_tool.py`, `validation_tool/README.md`만 필요한 범위에서 수정하고 Git 제외 상태를 유지합니다.

- [x] 대역 시나리오: 즉시 최종 / 전문가 2라운드 / 지도 보완 / 질문 대기·재개 / 전문가 전부 실패·요약표 사용 / 호출 한도 / 최종 교정 실패 / 저장 실패. 실제 계산·그래프·검증·SQLite 경로를 지나도록 작성.
- [x] `python -m unittest discover -s tests -p test_multi_agent_flow.py -v`로 실패 확인 후 빠진 연결 보완.
- [x] CLI trace에 역할·라운드·도구·채택·fallback·호출 누계·입출력 토큰·판정 입력 크기 표시. 실제 키가 있어도 대역 시나리오는 네트워크 차단 검증.
- [x] 코드 변경 전후 검사 명령과 결과·소요 시간을 진행 문서에 기록. 이전 테스트 수를 새 성공 결과로 재사용하지 않음.

```powershell
conda activate chaeum
cd backend
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m mypy
cd ..
python -m unittest discover -s validation_tool -p "test_*.py" -v
git diff --check
```

- [x] P6 실측 절차 문서화: 같은 5주소·500m, 두 모드, 시간·호출·토큰·입력 크기·근거 실패·도구 사용·추천 변화 비교. 비용 단가를 모르면 비용은 미확인으로 남김.
- [x] 유료 실측은 승인 전 미실행. 품질 우세·1.5배 시간 조건·팀 블라인드 평가는 실제 결과 없이 완료 처리하지 않음. 기본 모드는 자동 전환하지 않음.
- [x] 최종 diff에서 P0 변경 보존, 발표자료·프론트 미수정, `.env`·DB·runs 미추가 확인. PR 공통 계약 변경 목록과 남은 실측을 명시.

## 검토·실행 인계

- 구현 순서: 계약 → 축약·검증 → 전문가 실행기·예산 → 도구 → 그래프 → 저장·재개 → 전체 검증.
- 설계 P0은 현재 수정분을 출발점으로 사용합니다. P1~P5는 위 작업에 대응하며, P6는 측정 준비까지만 이번 범위입니다.
- 권장 방식: 이 세션에서 순차 구현. 계약·그래프·저장 변경이 맞물려 같은 파일을 여러 작업자가 동시에 수정하지 않습니다.
- 계획 검토 후 구현을 시작합니다. 이 문서 작성 시점에는 제품 코드 수정·신규 테스트 실행·커밋을 하지 않았습니다.
