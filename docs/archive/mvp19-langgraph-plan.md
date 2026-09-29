# MVP1.9 LangGraph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 기존 결과·저장·오류 처리를 보존하면서 오케스트레이터와 보완 루프를 LangGraph로 실행한다.

**Architecture:** `run_react()` 계약은 유지하고 내부 실행만 `graph.py`에 위임한다. 분석 병렬 실행은 기존 `run_agents()`를 재사용하고 판단·보완을 별도 노드로 연결한다. 실행 의존성은 클로저로 주입하고 요청별 데이터만 그래프 상태로 관리한다.

**Tech Stack:** Python 3.12, LangGraph StateGraph, 기존 OpenAI 호환 클라이언트·Pydantic·sqlite3·unittest.

**Spec:** [전환 설계](mvp19-langgraph-design.md)

## Global Constraints

- `feature/mvp-1.5-orchestra`에서 이어서 작업한다. 인구 통합 기준 커밋은 `7a8e514`다.
- 이번 단계에는 사용자 질문·재개, 체크포인트 DB, 새 HTTP API, 건축물·법률 연계를 넣지 않는다.
- 개폐업은 폴리곤 기준을 유지한다.
- 공통 `schemas.py`, 분석 에이전트와 최종판단 분석 로직은 변경하지 않는다.
- 오케스트레이터 모델 최대 6회, 보완 최대 1라운드, 최종판단 내부 교정 1회는 유지한다.
- 그래프 자동 재시도는 추가하지 않는다. 모델·저장 콜백을 중복 실행하지 않는다.
- 한국어 주석을 사용한다. 새 커밋과 푸시는 별도 요청 전 수행하지 않는다.
- 명령은 `conda activate chaeum` 후 실행한다. 유료 API·LLM 호출 없이 검증한다.

## Review Focus

1. 모델의 6번째 호출이 유효한 최종판단이면 성공하고, 잘못된 호출이면 추가 호출 없이 실패해야 한다. 작업 2에서 검사한다.
2. 보완 후에도 추가 보완을 요청하면 두 번째 보완 실행 없이 실패해야 한다. 작업 1·2에서 검사한다.
3. 병렬 분석 중 저장 콜백이 실패해도 이미 시작한 분석을 수집하고 최종판단을 실행하지 않아야 한다. 작업 3에서 검사한다.
4. 동시 요청이 같은 그래프 구현을 사용해도 메시지·분석·횟수가 섞이면 안 된다. 작업 3에서 검사한다.
5. 보완 실패·미채택 또는 전체 취소 시 DB 이력과 안전한 trace가 남아야 한다. 작업 3에서 검사한다.

## 작업 1. 보완 실행을 판단에서 분리

**파일:** `backend/app/agents/orchestration/supplement.py`, `backend/tests/test_supplement_loop.py`.

**인터페이스:** 기존 `validate_tools()`와 `SupplementTool` 유지. 새 `async execute_supplement(task: AnalysisTask, analyses: list[AgentAnalysis], plan: SupplementPlan, *, tools: list[SupplementTool], on_event: OnSupplement | None, operation_timeout: float) -> tuple[list[AgentAnalysis], list[str], list[SupplementEvent]]`는 갱신 자료·피드백·이벤트를 반환한다. 실행 가능 도구 목록은 기존 eligible 조건으로 판단 단계에서 필터링하고 실행 직전 재확인한다.

- [ ] 기존 테스트에 단일 보완 실행 경계 검사를 추가하고 실패를 확인한다. 성공 시 요청 대상만 갱신, 실패·미채택 시 원본 유지, 잘못된 ID 시 예외, 이벤트 순서는 requested 다음 완료 상태여야 한다.
- [ ] `decide_with_supplement()`의 작업 실행·검증·채택 부분을 위 함수로 추출한다. 기존 래퍼는 전환 중 이 함수를 호출해 회귀 테스트를 유지한다.
- [ ] 보완 실행 함수에서는 최종판단 모델을 호출하지 않는 것을 대역 호출 횟수로 확인한다.
- [ ] `cd backend; python -m unittest discover -s tests -p test_supplement_loop.py -v`와 `test_real_supplements.py`를 실행해 전부 통과시킨다.

## 작업 2. 기존 호출 계약을 유지하는 그래프 전환

**파일:** 새 `backend/app/agents/orchestration/graph.py`, 기존 `workflow.py`, `supplement.py`, `backend/pyproject.toml`, `backend/tests/test_orchestration_react.py`, 새 `backend/tests/test_orchestration_graph.py`.

**인터페이스:** 공개 `run_react()`의 현재 전체 인자·반환형 `DecisionResult`는 유지한다. 그래프 내부 `async run_graph()`는 동일 실행 인자를 받는다. `workflow.run_react()`에서 지연 import해 기존 workflow 유틸리티와 순환 import를 피한다. 다른 호출자는 수정하지 않는다.

- [ ] 정상 종료와 보완 경로의 실제 노드 실행 순서를 검증하는 테스트를 먼저 추가한다. 그래프가 없어서 실패하는 것을 확인한다.
- [ ] Python 3.12에서 사용할 LangGraph 릴리스와 의존성을 확인해 프로젝트에 버전 범위를 명시하고 설치한다. `python -m pip check`를 실행한다. LangChain 모델 래퍼는 추가하지 않는다.
- [ ] `GraphState`에 messages, action_calls, task, analyses, outcome, supplement_done, feedback, supplement_context를 정의한다. 상태 목록은 노드에서 복사 후 반환하고 전역으로 공유하지 않는다.
- [ ] 노드 `choose_action`, `prepare_address`, `run_analyses`, `evaluate_decision`, `execute_supplement`와 조건 분기를 구성한다. 잘못된 도구 인자는 관찰 메시지와 함께 choose_action으로 돌아간다. 정상 주소·분석 실행 후에도 기존처럼 모델 선택으로 돌아간다.
- [ ] 판단은 최종 결과면 END, 보완 계획이면 보완 노드로 이동한다. 보완 후에는 모델 도구 선택 없이 판단 노드로 돌아간다. 두 번째 판단에는 operations를 주지 않고 feedback·context를 전달한다.
- [ ] 기존 최종판단 함수를 그대로 호출하고, 보완 없는 경우의 `decision.analyze()` 경로도 보존한다. 중복된 기존 `decide_with_supplement()` 루프는 모든 호출을 확인한 뒤 제거한다.
- [ ] 모델 호출 카운터 6회를 유지한다. 그래프 안전 제한은 `recursion_limit=32`로 별도 설정한다. 정상 최대 경로가 이 제한 안에서 끝나는지 검증한다.
- [ ] `python -m unittest discover -s tests -p test_orchestration*.py -v` 및 보완 테스트를 통과시킨다. 거절·복수 도구·잘못된 순서·6번째 정상 호출·6회 실패·두 번째 보완 요청을 포함한다.

## 작업 3. 저장·취소·trace 회귀 및 실행 안내

**파일:** `backend/tests/test_analysis_service.py`, `backend/tests/test_orchestration_graph.py`, `validation_tool/test_validation_tool.py`, `backend/README.md`, `validation_tool/README.md`, 진행 기록.

**인터페이스:** 기존 `execute_analysis()`와 `on_task_prepared`, `on_analysis_completed`, `on_supplement` 계약을 유지한다. trace의 모델·분석·보완 단계명과 attempt 의미는 변경하지 않는다.

- [ ] 저장 콜백 실패 시 시작된 다른 분석이 완료되고 최종판단 미호출인지 검사한다. 취소·타임아웃 후 DB가 성공으로 기록되지 않는 기존 테스트를 유지한다.
- [ ] 서로 다른 요청 ID로 동시에 실행해 반환값과 DB 분석 이력이 섞이지 않는지 검사한다.
- [ ] 보완 성공·실패·거절·불필요 시나리오에서 기존 validation 대역을 실행한다. 전체 분석 재실행 없음, 최종판단 횟수와 저장 이력을 비교한다.
- [ ] `cd backend; python -m unittest discover -s tests -q`, `python -m ruff check .`, 변경 파일의 `ruff format --check`, `python -m mypy`를 통과시킨다.
- [ ] 루트에서 `python -m unittest validation_tool.test_validation_tool -q`를 통과시킨다. 테스트 수는 실제 결과로 기록한다.
- [ ] 설치·실행 안내에 LangGraph 전환과 질문·영속 재개 미지원 범위를 적는다. 구현 변경만 검토해 FE·DB 스키마·분석 로직이 변경되지 않았는지 확인한다.

## 실행 방식

변경 경계가 서로 밀접하므로 이 세션에서 순차적으로 직접 구현하는 방식을 권장한다. 계획 검토 후 진행하며, 구현 중 발견한 요구사항 밖 변경은 별도로 설명한다.
