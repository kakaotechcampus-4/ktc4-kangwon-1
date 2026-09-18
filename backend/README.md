# 백엔드

주소 하나를 받아 **그 자리에 맞는 업종**을 근거와 함께 돌려주는 FastAPI 서버입니다.

## 무엇으로 되어 있나

```
app/
├─ main.py            FastAPI 진입점 · CORS
├─ api/v1/routes.py   HTTP 경계. 예외를 상태 코드로 바꾼다
├─ services/analysis.py  주소 → 병렬 분석 → 최종 판단 → SQLite 저장
├─ db/                실행 상태·분석 결과 저장과 조회
├─ address.py         주소 → 좌표 (팀 공통 진입점)
├─ schemas.py         ★ 에이전트 사이 계약. 바꾸면 남의 코드가 깨진다
├─ mocks.py           키 없이 전체 흐름을 돌리는 목업
└─ agents/
   ├─ decision/          최종 업종 판단   (구현됨)
   ├─ orchestration/     세 분석 병렬 실행 (구현됨)
   ├─ floating_population/  유동인구      (구현됨)
   ├─ business_lifecycle/   개폐업        (구현됨)
   └─ commercial_area/      상권·경쟁 분석 (구현됨)
```

## 에이전트 파일 역할

- 공통: 세 분석 에이전트의 `agent.py`는 공개 `analyze`와 실행 흐름을 유지합니다. `decision/`과 `orchestration/` 구조는 바꾸지 않았습니다.
- `floating_population`: `metrics.py`는 집계·기준선·추세·반경·신뢰도 계산, `geo.py`는 좌표와 상권 겹침 판정, `llm.py`는 자료 선별과 fallback을 담당합니다.
- `business_lifecycle`: `input_builder.py`가 모델 입력을 조립하고, `preprocess.py`·`scoring.py`·`formatter.py`가 전처리·점수·출력 변환을 나눕니다. `llm.py`는 배치 호출과 결과 검증, `prompt.md`는 시스템 프롬프트입니다.
- `commercial_area`: `industries.py`가 업종 마스터를 읽고 씁니다.

## 흐름

```
POST /api/v1/analyses  { address }
        │
        └─ services.analysis.execute_analysis()
              ├─ address.resolve_site()      주소 → 좌표 (카카오 단일 주소 후보 검증)
        │
              ├─ orchestration.run_agents()  ← 여기서 세 에이전트가 동시에 돈다
        │     floating_population ┐
        │     business_lifecycle  ├─ 각자 AgentAnalysis 를 만든다
        │     commercial_area     ┘   실패해도 다른 에이전트를 멈추지 않는다
        │
              ├─ decision.analyze()          추천·비추천 업종 + 근거 검증
              └─ SQLite 저장 → DecisionResult / GET 저장 결과
```

API와 실행 예제는 `services.analysis.execute_analysis()`를 사용합니다.
ReAct가 주소를 한 번 확정하고 세 분석을 병렬 실행하며, 분석별 결과와 최종판단을 SQLite에 저장합니다.

## 왜 비동기인가

분석 한 번이 만드는 외부 요청 수입니다 (강남 기준, 실측).

| 조회 | 건수 | 페이지 |
| --- | --- | --- |
| 반경 500m | 4,922 | 5 |
| 반경 2km (LQ 기준선) | 47,096 | 48 |
| 자치구 전체 | 66,269 | 67 |

동기 클라이언트로는 이 120번이 한 줄로 줄을 섭니다. 그래서 `httpx.AsyncClient`를 쓰고,
**첫 페이지에서 전체 건수를 확인한 뒤 나머지 페이지를 동시에** 받아옵니다.
다만 공공데이터 쿼터가 하루 10,000건이고 429가 오므로 동시 요청 수를 제한합니다
(`SBIZ_MAX_CONCURRENCY`, 기본 4).

## 실행

### API 원본 응답 목업 + 실제 에이전트·LLM

```bash
python examples/run_api_mock.py
python examples/run_api_mock.py --input examples/fixtures/api_responses.json
```

`examples/fixtures/api_responses.json`에서 주소·가상 좌표와 API 원본 응답을 수정합니다.
유동인구·상권은 기존 HTTP 클라이언트의 응답 파싱부터 전처리·지표 계산까지 실행합니다.
오케스트레이터, 유동인구 자료 선별, 상권 요약, 최종판단 LLM은 `.env`의 엘리스 설정으로
실제 호출합니다. 실행 비용이 발생하며, 이 예제에는 `--offline` 옵션이 없습니다.

준비할 환경변수는 `ELICE_API_KEY`, `ELICE_BASE_URL`, `ELICE_MODEL`입니다.
데이터 API 키는 필요하지 않습니다. 데이터 조회 클라이언트는 `httpx.MockTransport`로
고정되며, 등록되지 않은 요청은 오류로 처리합니다. LLM 오류를 완성된 목업 결과로 대체하지
않습니다. 유동인구 선별·상권 요약의 기존 실패 처리와 최종판단의 오류 검증은 그대로 적용됩니다.

목업에는 상권영역, 두 분기 인구, 500m·2km·자치구 점포, 브랜드 원본 응답이 있습니다.
점포 응답은 페이지별로 나누어 반환하므로 페이지 수집도 실제 클라이언트가 수행합니다.
프랜차이즈 조회는 HTTP 클라이언트 주입을 지원하지 않아 브랜드 원본 목업을 기존 파서로
읽어 임시 캐시에 준비합니다. 브랜드 API의 실제 HTTP 조회는 이 예제로 검증하지 않습니다.
목업 캐시는 실행별 임시 폴더에 저장하고 종료 시 정리합니다.

이 예제에서만 개폐업을 `AGENT_NOT_CONNECTED`로 대체합니다. 실제 서버와 offline 연결 시험은
개폐업을 포함한 세 에이전트를 실행합니다. 최종 결과는 stdout의 `DecisionResult` JSON이며
`source_analyses`에서 이 예제가 직접 계산한 두 에이전트 결과를 확인할 수 있습니다.
기존 `run_orchestration.py --mock --offline`은 완성된 분석 결과를 재생하는 별도 예제입니다.

개롱역 올리브영 주소는 시나리오 이름이며 좌표·인구·점포는 실제 관측값이 아닙니다.
주소 좌표와 상권영역 EPSG:5181 좌표·점포 좌표는 일관되게 수정해야 합니다.
조회 반경은 500m·2km, 자치구는 11710, 유동인구 기준일은 JSON의 `today`로 고정됩니다.
목업 업종은 API 원본 분류이며 공통 75개 업종 매핑을 검증하는 자료가 아닙니다.

LLM도 대역으로 교체하여 외부 연결 없이 검증:

```bash
python -m unittest discover -s tests -p test_api_mock.py -v
```

### ReAct 분석 연결

`app.agents.orchestration.build_react_agents(settings)`는 유동인구·개폐업·상권의 실제
`analyze()`를 등록합니다. 등록 자체는 외부 API를 호출하지 않습니다.
서버·CLI에서 `ExecutionSettings.from_env()`를 만들고 `execute_analysis(address, settings=settings)`에
전달합니다. 분석 설정과 에이전트별 LLM 설정은 이 값에서 각 분석기로 명시적으로 전달됩니다.
`resolve`, `agents`, `generate_action`, `generate`, `db_path`를 주입하면 외부 호출 없이 시험할 수 있습니다.

실제 분석용 등록 함수는 `(0, 0)` 좌표를 외부 호출 전에 거절합니다.
다른 좌표의 정확성을 보증하는 검사는 아니므로, 검증된 위치만 사용해야 합니다.
`default_agents(commercial_settings)`도 같은 세 등록을 사용하며 기존 상권 설정 인자는 유지합니다.

개롱역 올리브영 가상 입력으로 외부 호출 없이 실행:

```bash
python examples/run_orchestration.py --mock --offline --db storage/offline.sqlite3
python -m unittest discover -s tests -p test_orchestration_connections.py -v
```

예제는 기존 분석 결과 목업을 사용합니다. 연결 테스트는 실제 세 분석 함수를
실행하되 API 클라이언트와 LLM을 대역으로 교체합니다. 키가 있어도 네트워크를 차단합니다.
`--offline`을 빼면 기존 예제는 실제 LLM을 호출합니다. 이번 검증에는 실제 API·LLM 및
카카오 주소 검색 연결 시험을 포함하지 않습니다.

Python **3.12**가 필요합니다. `pyproject.toml`이 `>=3.12,<3.13`으로 고정합니다.

```bash
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m uvicorn app.main:create_app --factory --reload
```

- API 문서: <http://127.0.0.1:8000/docs>
- 상태 확인: <http://127.0.0.1:8000/health>

### 키 없이 띄우기

```bash
MOCK_MODE=1 .venv/Scripts/python -m uvicorn app.main:create_app --factory --reload
```

또는 요청에 `?mock=true`를 붙입니다. 목업도 진짜 오케스트레이터와 중재를 지나가므로
응답 형태가 실제와 같습니다. 프론트 연동은 이걸로 먼저 시작하면 됩니다.

`create_app` 호출 시 `.env`를 먼저 읽은 뒤 CORS와 실행 설정을 만들며, DB는 서버 lifespan에서
초기화합니다. 모듈 import만으로 환경 파일·DB·외부 API에 접근하지 않습니다.
테스트는 `create_app(settings=ExecutionSettings(db_path=임시경로), load_env=False)`를 사용합니다.

### 저장 결과 조회와 실행 제한시간

`GET /api/v1/analyses/{request_id}`는 `status`(pending/running/completed/failed), 입력 주소,
객체로 파싱한 `site`, `result`, `error` 및 시각을 반환합니다. 없는 ID는 404입니다.
과거 결과의 업종명은 현재 75업종 규칙으로 다시 검증하지 않습니다.
POST 성공 본문은 기존 `DecisionResult`이며, 성공·처리된 실패 응답의 `X-Request-ID` 헤더로
저장된 요청을 조회할 수 있습니다. 이 헤더는 CORS에 노출됩니다. 저장 시작 전 실패는 행이 없을 수 있습니다.
본문 검증은 422, 주소 입력 오류는 400, 외부 서비스 실패는 502, 저장·계약 오류는 500이며
오류 응답에는 키·외부 URL·원문 예외를 싣지 않습니다.

기본 분석별 제한시간은 180초, 전체 실행은 600초입니다. 유한한 양수만 허용하며 환경변수 또는
`execute_analysis(agent_timeout=..., overall_timeout=...)`로 주입합니다. 분석별 만료는
`AGENT_TIMEOUT` 결과로 수집하고, 전체 만료는 failed 기록 후 `TimeoutError`를 재전파합니다.
취소도 failed 기록 후 `CancelledError`를 재전파합니다. 이미 최종 commit이 성공했다면
completed를 보존하고 취소만 전달합니다. INSERT·짧은 저장 작업은 결말을 확인한 뒤 정리합니다.
스레드의 동기 작업은 취소로 강제 중단할 수 없어 실제 종료가 제한시간보다 늦을 수 있습니다.
특히 개폐업의 기존 동기 파이프라인은 취소 후에도 스레드에서 끝까지 돌 수 있지만,
취소된 서비스가 그 결과로 최종 성공 저장을 계속하지는 않습니다.

두 실행 예제는 `--db`로 저장 파일을 지정할 수 있습니다. 생략 시 `SQLITE_PATH`,
그마저 없으면 `backend/storage/chaeum.sqlite3`를 사용합니다. offline도 결과를 저장합니다.
`run_api_mock.py`는 데이터 API 대역 + 실제 LLM이며 개폐업은 예제 전용 미연결 대역입니다.
`run_orchestration.py --mock --offline`은 LLM·도구 선택까지 대역이므로 키가 있어도 외부 호출이 없습니다.

## 환경변수

`.env.example`을 `.env`로 복사해 채웁니다. **실제 키는 커밋하지 않습니다.**
서버 factory와 CLI가 시작할 때 `.env`를 한 번 읽고, 이미 프로세스에 있는 환경변수를 덮어쓰지 않습니다.
코드에 직접 주입한 설정이 가장 우선이며, LLM은 `에이전트별 *_LLM_*` → 공통 `ELICE_*`·`LLM_*`
→ 코드 기본값 순서입니다. 이전 개폐업 전용 `ELICE_MLAPI_*`는 더 이상 읽지 않으므로
`BUSINESS_LIFECYCLE_LLM_*` 또는 공통 변수로 옮깁니다.

| 변수 | 용도 | 없으면 |
| --- | --- | --- |
| `COMMERCIAL_AREA_API_KEY` | 소상공인 상가정보 | 상권 분석 `status: error` |
| `FLOATING_POPULATION_API_KEY` | 서울시 유동인구 | 유동인구 분석 `status: error` |
| `BUSINESS_LIFECYCLE_API_KEY` | 서울시 개폐업 | 개폐업 분석 `status: error` |
| `BUSINESS_LIFECYCLE_AREA_SHP_PATH` | 기본 포함 자료 대신 사용할 서울시 상권영역 SHP 경로 | 패키지에 포함된 기본 자료 사용 |
| `FRANCHISE_API_KEY` | 공정위 브랜드 목록 | 프랜차이즈 지표 생략 + `partial` |
| `GEOCODING_API_KEY` | 카카오 REST 키 (주소→좌표) | 주소 설정 오류 |
| `ELICE_API_KEY` / `ELICE_BASE_URL` / `ELICE_MODEL` | 모델 호출 | 요약·중재 실패 |
| `ANALYSIS_RADIUS_M` | 분석 반경 | 500 |
| `SBIZ_MAX_CONCURRENCY` | 동시 요청 수 | 4 |
| `CORS_ALLOW_ORIGINS` | 허용할 프론트 주소 (쉼표 구분) | `http://localhost:3000` |
| `MOCK_MODE` | `1`이면 항상 목업 응답 | 꺼짐 |

## 알려진 한계

- 서울시 업종 연결 99건 중 53건은 모델 판정이며 아직 사람 검수가 끝나지 않았습니다.
- 개폐업 상권영역 SHP 구성 파일은 패키지에 포함됩니다. 다른 자료를 쓸 때만 `BUSINESS_LIFECYCLE_AREA_SHP_PATH`로 경로를 재정의합니다.
- 카카오 주소 검색은 명확한 단일 후보만 사용합니다. 후보가 없거나 여러 주소로 해석되면 자동 우회하지 않고 400으로 거절합니다.
- asyncio 취소는 이미 실행 중인 동기 스레드를 강제 종료하지 못합니다. 취소된 결과는 성공 저장하지 않지만 개폐업 작업 스레드는 끝까지 돌 수 있습니다.

## 검사

```bash
.venv/Scripts/python -m ruff check .          # lint
.venv/Scripts/python -m ruff format --check . # 포맷
.venv/Scripts/python -m mypy                  # 타입
.venv/Scripts/python -m unittest discover -s tests
```

테스트는 **네트워크 없이** 돕니다. 외부 API는 `httpx.MockTransport`와 대역 클라이언트로 바꿉니다.
`tests/test_orchestrator_e2e.py`가 주소부터 중재까지 전체를 한 번에 지나갑니다.

CI(`.github/workflows/ci.yml`)가 PR마다 같은 네 가지를 돌립니다.

## 단독 실행 스크립트

```bash
.venv/Scripts/python examples/run_commercial_area.py --address "서울특별시 송파구 위례광장로 120"
.venv/Scripts/python examples/run_business_lifecycle.py --area-code 3120240 --base-quarter 20252
.venv/Scripts/python examples/run_decision.py --mock
.venv/Scripts/python examples/probe_radius.py           # API가 받는 반경 상한 실측
.venv/Scripts/python examples/build_upjong_master.py --official-csv <파일>
```

## 더 읽을 것

- 에이전트별 상세: [app/agents/commercial_area/README.md](app/agents/commercial_area/README.md)
- 코드 규칙: [../docs/CONVENTIONS.md](../docs/CONVENTIONS.md)
- 프론트와의 계약: [../docs/API_CONTRACT.md](../docs/API_CONTRACT.md)
