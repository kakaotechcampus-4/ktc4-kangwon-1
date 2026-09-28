# 카카오맵 선택적 조회 구현 계획

> 실행 지침: superpowers:executing-plans로 작업 순서대로 구현한다. 승인 전 제품 코드를 수정하지 않는다.

**목표:** 최종판단이 요청한 주변 업종·시설을 오케스트레이터가 조회하고, 75개 업종 매핑·근거 저장·질문 후 재개까지 연결한다.

**구조:** 기존 세 분석은 유지한다. 지도 전용 관측을 선택형 입력·출력으로 추가하고 LangGraph에서 최대 한 배치만 실행한다. 공통 LLM 클라이언트와 SQLite 저장 방식을 재사용한다.

**기술:** Python 3.12, 기존 Pydantic·httpx·LangGraph·sqlite3·unittest. 추가 의존성 없음.

**설계:** [승인한 설계](mvp19-map-design.md).

**실행 결과:** 순차 구현 완료. 백엔드 449개·검증 도구 26개 대역 테스트 통과. 실제 외부 연결은 미검증. 상세 기록은 [진행 기록](mvp19-map-progress.md) 참고.

## 공통 제약

- 현재 `feature/mvp-1.5-orchestra`에서 기존 변경을 보존한다. 브랜치 전체 병합·자동 커밋·푸시 없음.
- 원본 기준은 `daa3f14`. 지도 폴더·지도 테스트·지도 실행 예제만 가져온다.
- 세 분석 에이전트·75개 마스터·프론트·HTTP API는 수정하지 않는다.
- 지도는 주입한 실행에서만 사용한다. 최대 1배치·요청 5개·검색 표현 50자·검색당 첫 페이지 15개.
- 기존 보완 1회·질문 3개/1회 유지. 질문 답변 후에는 최종판단만 실행한다.
- 실제 API·LLM은 이번 자동 검증에서 호출하지 않는다. 키·외부 오류 원문은 로그·DB에 남기지 않는다.
- 주석·문서는 한국어. 모델 출력 구조와 마스터 포함 여부를 코드로 검증한다.

## 검토 초점

1. 두 검색에 같은 장소가 등장하거나 동일 ID의 분류가 충돌할 때 중복 집계·임의 분류를 하지 않는다. 작업 2.
2. 검색 0건과 검색 실패, 매핑 실패가 구별된다. 작업 1·2.
3. 부분 실패 자료·매핑 불명 장소를 특정 업종의 확정 근거로 인용하지 못한다. 작업 3.
4. 지도→보완과 보완→지도 모두 횟수 제한을 지키며, 질문 재개에서 재조회하지 않는다. 작업 4·5.
5. 조회 저장 후 취소·최종판단 실패에도 관측은 남고, DB 실패는 성공으로 위장되지 않는다. 작업 5.

## 작업 1. 지도 도구 도입·계약

**파일:** 원본 `backend/app/agents/map_analysis/` 7개 파일, `backend/tests/test_map_analysis.py`, `backend/examples/run_map_analysis.py`; 수정 `backend/app/schemas.py`; 신규 `backend/tests/test_map_contract.py`.

**계약:** 공통 공개 모델은 schemas.py에 정의한다.

- `MapQuery`: kind(industry/infrastructure), industry_code 또는 facility_code, query(업종만 1~50자), why_needed, expected_impact. 종류별 필드 혼합 금지.
- `MapLookupPlan`: action=map_lookup, queries(1~5개). 실제 실행 ID는 모델이 만들지 않는다.
- 시설 코드는 원본 CATEGORY_CODES의 18개 카카오 코드를 공통 Literal로 고정한다. 별칭은 모델 계약이 아닌 검색 편의 기능이다.
- `MapObservation`: request_id, observation_id, site, radius_m, queried_at(UTC), master_version, status(ok/partial/no_data/error), data, warnings.
- data는 `queries`(코드가 만든 q1~q5를 키로), `places`(장소 ID를 키로), `industries`(중분류 코드를 키로) 세 영역. JsonValue 자유 객체 대신 필드가 고정된 중첩 모델로 검증한다.
- 검색 결과: 요청 종류·대상 코드·검색 표현·실제 방식/카테고리, status, total_count(int 또는 null), place_ids, has_more(bool 또는 null), error(안전한 코드 또는 null).
- 장소: 원본 이름·카테고리·코드·거리·URL, mapping_status(mapped/ambiguous/unmapped/not_applicable), industry_code 또는 null, mapping_method·reason. 업종 집계는 mapped 장소만 포함한다.
- 업종 집계: 공통 코드·명칭·대분류, place_ids, sampled_count. 개수와 고유 ID 수가 같아야 한다.

- [ ] 원본 파일을 정확한 경로만 apply_patch로 도입하고 원본 대역 테스트를 실행한다. `git cherry-pick`으로 별도 커밋을 만들지 않는다.
- [ ] `test_map_contract.py`에 6개 요청·51자 검색어·잘못된 업종/시설 코드·종류 혼합·실패 count=0·matched 코드 없음 거절 테스트를 작성하고 실패 확인.
- [ ] 공통 모델과 검증 구현. 같은 마스터 조회 함수를 사용한다. 지도 외부 응답 모델과 공통 전달 모델의 역할을 분리한다.
- [ ] `python -m unittest discover -s tests -p 'test_map*.py' -v` 통과 확인.

## 작업 2. 원본 장소 보존·매핑

**파일:** 지도 `agent.py`, `client.py`, `config.py`, `schemas.py`; 신규 `mapping.py`, `prompt.md`, `backend/tests/test_map_mapping.py`; `.env.example`, 필요 시 `pyproject.toml` 패키지 자료 항목.

**인터페이스:**

- 기존 `search()`와 예제는 유지한다. 실제 연결용 `async observe(task: AnalysisTask, plan: MapLookupPlan, *, settings=None, client=None, generate_mapping=None) -> MapObservation`을 추가한다.
- `mapping.py`: `async map_categories(categories: dict[str, dict[str, str]], *, generate=None, settings: LLMSettings | None=None) -> dict[str, CategoryMapping]`.
- CategoryMapping은 원본 카테고리 식별자에 대한 상태·공통 코드·이유. 모델 응답은 입력과 키가 정확히 일치해야 하며 중복·추가·누락을 거절한다.
- 기본 매핑 호출은 기존 complete_json과 `LLMSettings.from_env("MAP_MAPPING")` 사용. 단일 배치 호출이며 자율 도구 실행·반복 교정·영속 캐시는 추가하지 않는다.

- [ ] 동일 장소 중복, 검색 대상과 실제 업종 불일치, 코드 없는 분류, 상충하는 원본 분류, 매핑 모델 실패 테스트를 작성하고 실패 확인.
- [ ] 검색 결과의 장소 ID를 보존하고 중복 제거. ID가 없거나 자료가 잘못된 항목은 경고로 제외하며 정상 전체 자료인 것처럼 처리하지 않는다. 동일 ID의 상충 분류는 ambiguous 처리.
- [ ] 원본 카테고리를 한 번에 매핑. 미확정은 코드 null. 명칭은 마스터에서 채우고 실패 시 원본 자료만 보존.
- [ ] 원본 search의 요약을 관측에 재사용하되 전체 건수·표본 수를 분리. 실패는 null, 정상 0건은 0. 거리의 NaN/Infinity 등 잘못된 값은 거절하거나 누락 표시.
- [ ] settings의 동시성·표본 크기·재시도 값을 네트워크 전에 검증. 반경 상한 초과를 축소하지 않고 안전한 오류 관측으로 반환.
- [ ] 정상 0건, 일부 실패, 전부 실패, 일부 매핑 실패의 관측 상태를 테스트. 인프라만 요청하면 매핑 LLM 0회, 업종 분류가 있으면 최대 1회인지 단언.
- [ ] `test_map*.py` 통과 확인. prompt 패키지 포함과 별도 매핑 모델 환경변수 안내 확인.

## 작업 3. 최종판단·지도 근거

**파일:** `schemas.py`, `agents/decision/agent.py`, `llm.py`, `prompt.md`; 신규 `tests/test_map_decision.py`.

**인터페이스:**

- DecisionRequest와 DecisionResult에 `map_observation: MapObservation | None = None` 추가. 요청 ID 일치 검증.
- Evidence.agent_id는 기존 AgentId 또는 map_analysis. 실행 AgentId는 수정하지 않는다.
- `evaluate(..., allow_map_lookup: bool=False)` 반환에 MapLookupPlan 추가. GenerateDecision·generate_decision 파싱도 함께 변경.
- analyze는 계속 최종 결과만 허용한다. 관측은 코드가 최종 결과에 붙인다.

- [ ] 지도 요청 허용/비허용·출력 교정 중 지도 요청 금지·원본 관측 보존·지도 ID 불일치 테스트 RED 확인.
- [ ] 지도 관측 프롬프트 전달과 네 가지 결과 분기(final/supplement/map_lookup/ask_user) 구현. 관측이 이미 있으면 추가 조회 요청 금지.
- [ ] 근거 검증 확장: queries의 성공한 total_count(0 포함), 정상 조회 장소의 이름·거리, mapped 업종의 집계 경로를 허용한다. 실패 검색·오류 메타데이터·미확정 매핑을 업종 근거로 인용하지 못하게 한다.
- [ ] 업종 집계·매핑 코드 경로는 해당 추천 업종과 코드 일치를 검사한다. 다른 업종의 비교는 문장에 참고 맥락으로만 사용하며 직접 업종 근거로 오인하지 않게 프롬프트에 명시.
- [ ] 지도-only 추천 금지, 통계 합산 금지, 표본·원본 분류·조회 시점 한계를 prompt에 추가.
- [ ] `python -m unittest discover -s tests -p 'test*decision*.py' -v` 통과.

## 작업 4. 오케스트레이터 선택 실행

**파일:** `agents/orchestration/graph.py`, `workflow.py`, `tools.py`, `prompt.md`; 신규 `tests/test_map_graph.py`.

**인터페이스:**

- tools.py에서 `MapLookup = Callable[[AnalysisTask, MapLookupPlan], Awaitable[MapObservation]]` 공개.
- run_react/run_graph에 `map_lookup: MapLookup | None=None`, `on_map_requested: Callable[[AnalysisTask, MapLookupPlan], Awaitable[None]] | None=None`, `on_map_completed: Callable[[MapObservation], Awaitable[None]] | None=None` 추가.
- GraphState에 map_done과 map_observation. execute_map 노드: 요청 알림 → 제한시간 내 도구 → 계약·식별자·좌표·반경 검증 → 완료 알림 → 판단 복귀.

- [ ] 지도 없음, 지도→보완, 보완→지도, 두 번째 지도 요청 거절, 지도→질문 테스트를 먼저 추가.
- [ ] 좌표·반경은 task를 복사해 주입. 기존 agent_timeout을 지도 배치에도 적용. 일반 외부 실패·시간초과는 안전한 오류 관측으로 변환하되 계약·콜백 오류는 전파.
- [ ] map_done은 성공 여부와 무관하게 한 번 실행 후 True. 각 분기 뒤 남은 보완·질문 선택지만 제시. 기존 보완 후 무조건 최종이라는 코드를 이 정책에 맞춘다.
- [ ] 초기 주소·분석 선택의 6회 제한을 유지하고 전체 그래프 제한 안에서 최장 유효 경로가 종료되는지 확인.
- [ ] `python -m unittest discover -s tests -p 'test*graph*.py' -v` 및 기존 오케스트레이터 테스트 통과.

## 작업 5. DB·서비스·질문 재개

**파일:** `db/schema.sql`, `repository.py`, `services/analysis.py`; 신규 `tests/test_map_repository.py`, `tests/test_map_service.py`.

**인터페이스:** repository의 기존 db_path 규칙을 유지한다.

- `start_map_lookup(task: AnalysisTask, plan: MapLookupPlan, *, db_path=None) -> None`
- `complete_map_lookup(observation: MapObservation, *, db_path=None) -> None`
- `get_map_observation(request_id: str, *, db_path=None) -> MapObservation | None`
- map_observations: request_id PK/FK, plan_json, task_json, status(running/completed), observation_json nullable, created_at, completed_at nullable. JSON·ID·상태별 NULL 제약. 중복 실행 INSERT 거절.
- execute_analysis에 map_lookup 선택 인자 추가. start/complete 콜백은 기존 _settle·to_thread 방식으로 저장.

- [ ] 요청·관측 불일치, 중복 저장, DB 오류, 취소, 정상 완료와 partial/error 관측 저장 테스트를 먼저 작성.
- [ ] 완료 시 저장 task·plan과 관측 대상·위치·반경 대조. repository.complete_request에서 결과의 관측과 저장 관측 동등성 검증. running 관측이 있으면 최종·질문 완료 금지.
- [ ] 질문 저장 전에 지도 완료 보장. resume_analysis에서 관측을 DecisionRequest에 넣어 기존 resume_graph로 전달한다. 지도 함수는 재개에 주입하지 않는다.
- [ ] 옛 DB 초기화·지도 없는 기존 결과·기존 질문 기록을 그대로 읽는 회귀 검사. 강제 종료 running 자동 복구는 제외.
- [ ] 지도→질문→새 서비스 호출 재개에서 지도 호출 1회·기존 분석 이력 불변·최종 관측 동일을 단언. 동일 답변 중복 제출 시 추가 모델 호출 없음.
- [ ] `python -m unittest discover -s tests -p 'test_map*.py' -v` 및 기존 repository/service/question 테스트 통과.

## 작업 6. 검증 도구·문서·전체 검수

**파일:** `validation_tool/run.py`, `trace.py`, 신규 `test_map_validation.py`, README; `backend/README.md`, 지도 README·예제; 본 계획의 진행 기록.

- [ ] `--with-map`(실제 실행 선택)와 `--offline-map`(API·매핑·판단 모두 대역) 옵션 추가 테스트를 먼저 작성. 기존 옵션의 의미 유지, 상충 모드 조합 거절.
- [ ] 지도 요청·조회·매핑·완료 이벤트를 trace에 추가. API 키·사용자 답변 원문 기록 금지. 재개는 저장 모드를 따르고 실제 모델로 자동 전환하지 않음.
- [ ] 별도 프로세스에서 대역 지도→질문→답변 재개 시험. 최종 JSON·DB·trace의 관측 일치, 네트워크 호출 0회 확인.
- [ ] 지도 검색 한계와 75개 매핑이 LLM 추론임을 README에 기록. validation_tool은 Git 제외 상태라는 사실 유지.
- [ ] Python 3.12에서 아래 전체 검증. 실제 통과 수를 기록하며 이전 394개를 고정 기준으로 삼지 않는다.

```powershell
# backend
python -m unittest discover -s tests
python -m ruff check --no-cache .
python -m mypy
# 변경된 파이썬 파일만 ruff format --check로 검사
# repository root
python -m unittest discover -s validation_tool -p 'test*.py'
python -m ruff check --no-cache --config backend/pyproject.toml validation_tool
git diff --check
```

- [ ] 독립 리뷰에서 위 다섯 검토 초점과 질문 재개 회귀 확인. 실제 API·LLM 품질 검증은 미실시로 명시.
- [ ] 변경 파일과 테스트 결과를 보고. 커밋·푸시는 하지 않는다.

## 실행 방식

이전 작업과 동일하게 이 세션에서 순차 구현하고 마지막에 독립 리뷰한다. 원본 가져오기→계약→매핑→판단→그래프→저장의 의존성이 있어 병렬 구현은 사용하지 않는다. 계획 검토 후 시작한다.
