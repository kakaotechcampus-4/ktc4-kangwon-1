# MVP1.9 선택적 질문·재개 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans 또는 superpowers:subagent-driven-development로 승인된 실행 방식에 따라 진행한다. 체크박스로 진행 상태를 기록한다.

**Goal:** 임대인에게 필요한 정보만 최대 3개·1회 질문하고, 저장된 분석을 재사용해 답변 후 최종판단을 완료한다.

**Architecture:** 기존 LangGraph에 질문 종료와 판단부터 재개하는 진입을 추가한다. 질문 경계의 상태와 분석 실행 차수를 기존 SQLite에 저장한다. 네이티브 interrupt·별도 체크포인터·LangChain 모델 래퍼는 추가하지 않는다.

**Tech Stack:** Python 3.12, 기존 LangGraph·Pydantic·asyncio·sqlite3·unittest.

**Spec:** [선택적 질문·재개 설계](mvp19-questions-design.md).

**실행 결과:** 작업 1~6 구현 완료. 아래는 최초 계획이며, 실제 테스트 배치·그래프 구성 조정과 최종 검증 결과는 [진행 기록](mvp19-questions-progress.md)을 기준으로 확인한다.

## 공통 제약

- 기준: `feature/mvp-1.5-orchestra`, `b835ef9`. 시작 시 브랜치·미커밋 변경을 다시 확인한다.
- 문서·주석은 한국어. 세 분석 에이전트·HTTP API·프론트·업종 마스터는 수정하지 않는다.
- 기존 `AnalysisTask`, `AgentAnalysis`, `DecisionRequest`, `DecisionResult` 필드는 유지한다. 새 공통 계약은 팀 PR 검토 항목이다.
- 질문은 최대 3개, 한 번만. 데이터 보완은 기존 최대 1라운드. 답변 후에는 최종 결과만 허용한다.
- 답변은 항목당 최대 1,000자. 모름·건너뛰기·부분 제출을 허용한다.
- 질문 기능은 명시적으로 켜는 실행에만 적용한다. 기존 호출은 최종 결과만 반환한다.
- 외부 API·실제 LLM 없이 먼저 검증한다. 설치·커밋·푸시는 이번 계획 작성에 포함하지 않는다. 구현 때도 별도 요청 없이 커밋하지 않는다.

## 검토 초점

1. 보완 실패로 2차 분석이 저장돼도 채택된 1차 자료를 복원해야 한다. 작업 3·5에서 검사한다.
2. 대기 저장 직후 취소되거나 trace 기록이 실패해도 대기를 failed로 덮어쓰지 않는다. 작업 5·6에서 검사한다.
3. 같은 답변의 배열 순서가 달라도 중복 제출로 판단한다. 작업 3에서 검사한다.
4. 출력 교정 호출에서 질문이나 보완으로 새 루프를 시작하지 못한다. 작업 2에서 검사한다.
5. 반경 컬럼이 없던 구형 DB와 이미 자식 이력이 있는 DB 모두 마이그레이션으로 보존한다. 작업 3에서 검사한다.

## 파일 배치

| 파일 | 작업 |
| --- | --- |
| `backend/app/schemas.py` | 질문·답변·대기·저장 스냅샷 모델 추가 |
| `backend/app/agents/decision/agent.py`, `llm.py`, `prompt.md` | 질문 분기 파싱·정책·사용자 정보 전달 |
| `backend/app/agents/orchestration/graph.py`, `workflow.py` | 질문 분기·재개 진입·콜백 |
| `backend/app/db/schema.sql`, `connection.py`, `repository.py` | 질문 저장·조건부 재개·마이그레이션 |
| `backend/app/services/analysis.py` | 초기 실행·대기 저장·재개 서비스 |
| `backend/tests/test_questions.py` | 새 계약과 정규화 검증, 신규 |
| `backend/tests/test_decision_agent.py`, `test_decision_llm.py` | 질문 선택·파싱 회귀 |
| `backend/tests/test_repository.py` | DB 상태 전이·중복·마이그레이션 |
| `backend/tests/test_orchestration_graph.py`, `test_analysis_service.py` | 분기·재개·호환성 |
| `validation_tool/run.py`, `trace.py`, `test_validation_tool.py`, `README.md` | 로컬 질문·답변·재개 검증 |
| `backend/README.md` | 사용법·지원 범위 |

불필요한 질문 에이전트·범용 체크포인트 프레임워크·새 설정 패키지는 만들지 않는다. `validation_tool`은 현재 Git 제외 대상이므로 로컬 변경과 PR 포함 파일을 구분한다.

## 작업 1. 질문·답변 계약

**파일:** `schemas.py`, 신규 `tests/test_questions.py`.

**인터페이스:**

- `QuestionField`: floor / exclusive_area / space_condition / existing_facilities / industry_preferences.
- `LandlordQuestion`: field, text, why_needed, expected_impact. 문자열은 기존 `Text` 규칙을 사용한다.
- `QuestionPlan`: action="ask_user", questions. 1~3개·항목 중복 금지. 모델은 요청 ID를 생성하지 않는다.
- `WaitingForInput`: status="waiting_for_input", request_id, question_set_id, questions.
- `LandlordAnswer`: field, status(answered / unknown / skipped), value(문자열 또는 null). answered만 1~1,000자 값 필수, 나머지는 null.
- `AnswerSubmission`: request_id, question_set_id, answers. 0~3개·항목 중복 금지.
- `QuestionSnapshot`: version=1, task, waiting, source_attempts, supplement_done, feedback. 내부 저장용이며 LLM 출력에 포함하지 않는다. 분석 본문·함수·비밀키는 저장하지 않는다.
- `normalize_answers(waiting: WaitingForInput, submission: AnswerSubmission) -> AnswerSubmission`: 요청·묶음·항목 검증, 빠진 항목을 skipped로 채우고 항목 코드 순으로 정렬한다.

- [ ] 위 경계값을 검사하는 실패 테스트를 작성한다. 핵심 단언:

```python
self.assertEqual(len(normalized.answers), len(waiting.questions))
self.assertEqual(normalized.answers[0].status, "skipped")
# 4개 질문, 중복 항목, 1,001자 답변, 다른 묶음 ID는 ValidationError/ValueError
```

- [ ] `python -m unittest discover -s tests -p test_questions.py -v`로 새 계약 부재에 따른 실패를 확인한다.
- [ ] 모델·정규화 함수를 구현한다. 스냅샷의 task/대기 요청 ID, 세 분석 ID와 양의 정수 실행 차수를 검증한다.
- [ ] 같은 명령이 통과하고 기존 스키마 사용 테스트가 유지되는지 확인한다.

## 작업 2. 최종판단의 선택적 질문

**파일:** `decision/agent.py`, `llm.py`, `prompt.md`, 기존 최종판단 테스트 2개.

**인터페이스:**

- `evaluate()`의 기존 인자에 `question_fields: list[QuestionField] | None = None`, `user_answers: list[LandlordAnswer] | None = None`, `site: Site | None = None`을 추가한다.
- 반환은 `DecisionResult | SupplementPlan | QuestionPlan`. `GenerateDecision`, `generate_decision()`도 QuestionPlan을 파싱한다.
- `analyze()`는 계속 최종 결과만 허용한다. 질문 목록이 없거나 교정 단계이면 질문 요청을 거절한다.

- [ ] 질문 허용/비허용, 목록 밖 항목, 최종 출력 교정 중 질문 금지 테스트를 먼저 작성한다.
- [ ] `python -m unittest discover -s tests -p 'test_decision*.py' -v`로 실패를 확인한다.
- [ ] 기존 스키마 선택 로직에 ask_user를 추가하고 현재 안전한 오류 진단 방식을 유지한다.
- [ ] `evaluate()`가 구조·허용 항목을 검증하도록 한다. 필드 목록과 사용자가 제공한 답변은 별도 JSON 항목으로 전달한다. Site의 상세주소는 문맥으로 전달하되 정규식으로 층수를 임의 확정하지 않는다.
- [ ] 프롬프트에 질문의 필요성·영향, 임대인 관점, 3개/1회, 자료와 지시문 구분, 사용자 답변을 API 근거로 인용하지 않는 규칙을 추가한다.
- [ ] 기존 no_data 단축 경로를 유지한다. 분석 자료가 전혀 없고 실행 가능한 보완도 없으면 질문으로 관측 자료를 대신하지 않는다.
- [ ] 같은 테스트 명령으로 통과 확인. 핵심 단언은 `QuestionPlan` 반환, 재개 시 최종 결과 반환, 원본 `source_analyses` 불변이다.

질문의 유용성은 LLM 정책이다. 코드가 why_needed 문자열의 존재를 검사하는 것을 의미 타당성 검증으로 설명하지 않는다.

## 작업 3. 영속 대기·답변의 원자적 수락

**파일:** `db/schema.sql`, `connection.py`, `repository.py`, `tests/test_repository.py`.

**인터페이스:** 기존 `db_path` 키워드 규칙을 유지한다.

- `save_question_snapshot(snapshot: QuestionSnapshot, *, db_path=None) -> None`
- `get_question_snapshot(request_id: str, *, db_path=None) -> QuestionSnapshot | None`
- `claim_question_resume(submission: AnswerSubmission, *, db_path=None) -> bool`: 정규화 답변을 저장하고 대기→실행 선점 성공 시 True. 동일 답변의 이미 수락된 제출은 False. 다른 답변·잘못된 상태는 ValueError.
- `get_question_answers(request_id: str, *, db_path=None) -> AnswerSubmission | None`
- `load_question_analyses(snapshot: QuestionSnapshot, *, db_path=None) -> list[AgentAnalysis]`: 지정된 실행 차수만 복원·검증한다.

새 `question_sessions` 테이블: request_id PK/FK, question_set_id UNIQUE, snapshot_json, answers_json(nullable), created_at, answered_at(nullable). JSON 유효성·식별자·답변/시각 null 일치 제약을 둔다. 요청 상태는 analysis_requests가 단일 기준이며 이 테이블에 별도 상태를 복제하지 않는다.

- [ ] 임시 DB에서 대기 원자성, 중복 제출, 채택 차수 복원, 마이그레이션 실패 시 롤백 테스트를 작성한다.
- [ ] `python -m unittest discover -s tests -p test_repository.py -v`로 실패를 확인한다.
- [ ] `waiting_for_input`은 pending/running처럼 결과·오류·완료시각이 없는 상태로 추가한다.
- [ ] 연결 초기화에 전용 마이그레이션 함수를 추가한다. 기존 반경 추가를 먼저 처리하고, 별도 연결에서 외래키 검사를 트랜잭션 전에 잠시 해제한 뒤 BEGIN IMMEDIATE로 부모 테이블을 재구성한다. 기존 컬럼을 명시해 복사하고 자식 테이블·인덱스·트리거를 보존한다. foreign_key_check 통과 후 커밋하고 외래키를 다시 활성화한다. 사용자 DB를 삭제해 초기화하지 않는다.
- [ ] save는 snapshot 참조와 실제 저장된 Site·반경·차수·채택 이벤트를 검증하고 질문 INSERT와 상태 UPDATE를 같은 트랜잭션으로 처리한다.
- [ ] claim은 BEGIN IMMEDIATE 안에서 현재 상태·답변을 확인하고 정규화된 답변과 조건부 UPDATE를 원자적으로 저장한다. 실행 중/완료/실패한 동일 제출에는 False를 반환하고 서비스가 상태를 해석한다.
- [ ] 두 연결의 동시 claim에서 True가 한 번만 나오는지, 답변 순서 변경이 동일 제출로 처리되는지 확인한다.

```python
self.assertEqual(sum(claim_results), 1)
self.assertEqual(restored[0], adopted_first_attempt)
self.assertEqual(request["status"], "waiting_for_input")
self.assertIsNone(request["result_json"])
```

- [ ] 기존 DB·반경 없는 DB·신규 DB의 반복 initialize가 모두 통과하고, 이력 수와 내용이 유지되는지 확인한다.

## 작업 4. 그래프 질문 분기·판단 재진입

**파일:** `orchestration/graph.py`, `workflow.py`, `tests/test_orchestration_graph.py`.

**인터페이스:**

- `run_react()`와 `run_graph()`에 `allow_questions: bool = False`, `on_questions: Callable[[AnalysisTask, WaitingForInput, bool, list[str]], Awaitable[None]] | None = None` 추가. 반환은 DecisionResult 또는 WaitingForInput. bool 인자는 supplement_done이다.
- 새 `resume_graph(request: DecisionRequest, *, site: Site, answers: list[LandlordAnswer], feedback: list[str], supplement_context: list[SupplementEvent], generate: GenerateDecision | None = None) -> DecisionResult`.
- 그래프 작성 부분을 같은 파일의 `_build_graph(...)`로 추출해 초기/재개가 같은 evaluate_decision 노드를 사용한다. 새 별도 루프는 만들지 않는다.

- [ ] 질문 없는 실행·질문 종료·보완 후 질문·재개 최종판단 테스트를 작성한다. 분석·주소·보완 함수 호출을 기록한다.
- [ ] `python -m unittest discover -s tests -p test_orchestration_graph.py -v`로 실패를 확인한다.
- [ ] 초기 상태에 질문 허용 여부와 사용자 답변을 추가한다. evaluate_decision에서 질문 후보를 제공하고, QuestionPlan이면 코드로 묶음 ID를 생성해 질문 노드로 보낸다.
- [ ] 질문 노드는 콜백 성공 후 WaitingForInput으로 종료한다. 질문 허용 실행은 저장 콜백을 필수로 검증해 저장 없는 대기를 방지한다.
- [ ] 재개 상태는 evaluate_decision부터 진입한다. 질문 후보·보완 작업을 제공하지 않고 그럼에도 모델이 재요청하면 계약 오류로 처리한다. 기존 모델 교정 1회는 유지한다.
- [ ] 위 테스트 및 `test_orchestration*.py` 회귀 통과를 확인한다.

```python
self.assertIsInstance(waiting, WaitingForInput)
self.assertIsInstance(final, DecisionResult)
self.assertEqual(calls_after_resume["address"], calls_before_resume["address"])
self.assertEqual(calls_after_resume["analyses"], calls_before_resume["analyses"])
```

## 작업 5. 서비스 초기 실행·재개 연결

**파일:** `services/analysis.py`, `tests/test_analysis_service.py`.

**인터페이스:**

- `execute_analysis()`에 `allow_questions: bool = False` 추가. False 호출의 반환 타입은 기존대로 유지하도록 overload를 제공한다. True는 `DecisionResult | WaitingForInput`이다.
- `async resume_analysis(submission: AnswerSubmission, *, db_path=None, generate: GenerateDecision | None = None, settings: ExecutionSettings | None = None, overall_timeout: float | None = None) -> DecisionResult`.
- `AnalysisAlreadyRunningError`, `AnalysisAlreadyFailedError`를 같은 파일에 둔다. 중복 호출은 모델을 실행하지 않고 상태를 명확히 전달한다.

- [ ] 초기 대기 저장·새 서비스 호출 재개·보완 후 복원·중복 제출·취소·DB 오류 테스트를 먼저 작성한다.
- [ ] `python -m unittest discover -s tests -p test_analysis_service.py -v`로 실패를 확인한다.
- [ ] 기존 source_attempts와 준비된 task, 보완 여부·feedback으로 QuestionSnapshot을 만들고 `_settle(asyncio.to_thread(...))`로 저장한다. WaitingForInput이면 complete_request 없이 반환한다.
- [ ] resume은 DB·모델 설정·시간 제한·입력을 검증한 후 claim한다. 선점 실패 시 완료 결과 재반환, 실행 중/실패 예외를 구분한다. 다른 실행의 상태를 failed로 바꾸지 않는다.
- [ ] 선점 성공 실행만 snapshot·분석 차수·저장된 보완 이벤트·정규화 답변을 복원해 resume_graph를 호출한다. 새 요청·분석 이력은 생성하지 않는다.
- [ ] 기존 complete_request로 source_attempts를 유지한 최종 저장을 수행한다. 실패 기록은 자신이 선점한 running에만 적용한다. 대기 저장 완료 후 취소는 waiting을 보존한다.
- [ ] 서비스 테스트와 API 회귀를 실행한다. 서비스 시나리오 단언:

```python
self.assertEqual(len(agent_rows_after), len(agent_rows_before))
self.assertEqual(len(decision_rows_after), 1)
self.assertEqual(request_after["status"], "completed")
# 같은 제출을 다시 호출해도 generate 호출 횟수와 decision_rows 수는 그대로
```

답변 대기에는 실행 중 타이머를 유지하지 않는다. 재개 시 새 제한시간을 적용하며 자동 재시도·강제 종료 running 복구는 구현하지 않는다.

## 작업 6. 검증 도구·전체 회귀

**파일:** `validation_tool/run.py`, `trace.py`, `test_validation_tool.py`, `README.md`, `backend/README.md`.

**인터페이스:** 기존 CLI 인자 유지. `--allow-questions`, `--resume 실행폴더`, `--answers 답변.json`, `--skip-questions`, `--offline-questions` 추가.

- [ ] 질문 종료 후 다른 프로세스로 답변/건너뛰기 재개, 기존 trace 보존, API 미호출 테스트를 작성한다.
- [ ] 루트에서 `python -m unittest discover -s validation_tool -p test_validation_tool.py -v`로 실패를 확인한다.
- [ ] 최초 대기에서는 questions.json과 작성용 answers.example.json을 출력한다. 최종 result.json은 아직 생성하지 않는다. 사용자 입력을 기다리며 프로세스를 붙잡지 않는다.
- [ ] resume은 기존 폴더의 DB·질문 ID를 확인한다. 주소·반경·새 분석 옵션과 동시 사용은 거절한다. answers 또는 skip 중 하나만 허용한다. 기록된 대역 실행은 재개도 대역으로 실행해 실제 LLM으로 자동 전환하지 않는다.
- [ ] trace는 재개 시 append하고 실행 구간 ID를 추가한다. questions/waiting, answers/accepted, decision/resumed, run/completed를 구분한다. 답변 원문은 trace에 복제하지 않는다.
- [ ] 전체 대역 시나리오: 질문 없음 / 질문→답변 / 부분 답변 / 모두 건너뛰기 / 보완→질문 / 중복 제출 / 잘못된 묶음 / 재개 실패. DB 재조회와 호출 횟수로 확인한다.
- [ ] 아래 회귀 명령을 `conda activate chaeum` 후 실행한다. 모두 종료 코드 0이어야 한다. 실제 통과 수만 기록한다.

```powershell
# backend에서
python --version
python -m unittest discover -s tests -v
python -m ruff check .
python -m mypy
# 변경한 파이썬 파일만 나열해 포맷 검사
python -m ruff format --check app/schemas.py app/agents/decision/agent.py app/agents/decision/llm.py app/agents/orchestration/graph.py app/agents/orchestration/workflow.py app/db/connection.py app/db/repository.py app/services/analysis.py tests/test_questions.py tests/test_decision_agent.py tests/test_decision_llm.py tests/test_repository.py tests/test_orchestration_graph.py tests/test_analysis_service.py
# 루트에서
python -m unittest discover -s validation_tool -p test_validation_tool.py -v
python -m ruff check validation_tool
python -m ruff format --check validation_tool
```

- [ ] 문서에 질문 기능이 기본 비활성임과 사용 명령, 사용자 답변의 해석 한계, HTTP 미연결, 실행 중 장애의 자동 복구 미지원 사항을 기록한다.
- [ ] 변경 파일·검증 결과를 검토받는다. 커밋·푸시는 별도 요청 후 수행한다.

## 실행 방식 제안

계약·저장·그래프가 순서대로 연결되므로 한 세션에서 작업 1~6을 순차 구현하는 방식을 권장한다. 각 작업의 실패 테스트→최소 구현→통과 확인을 마친 뒤 다음 작업으로 넘어간다. 구현 완료 후 별도 리뷰를 받는다.

대안은 작업별 구현 담당과 리뷰 담당을 분리하는 방식이다. 검토는 더 촘촘하지만 작업 간 계약을 전달하는 비용이 늘어난다. 이 문서 승인과 실행 방식 선택 후 구현을 시작한다.
