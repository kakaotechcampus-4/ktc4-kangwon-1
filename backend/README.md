# 백엔드

주소 하나를 받아 **그 자리에 맞는 업종**을 근거와 함께 돌려주는 FastAPI 서버입니다.

## 무엇으로 되어 있나

```
app/
├─ main.py            FastAPI 진입점 · CORS
├─ api/v1/routes.py   HTTP 경계. 예외를 상태 코드로 바꾼다
├─ orchestrator.py    주소 → 에이전트 병렬 실행 → 중재까지의 흐름
├─ address.py         주소 → 좌표 (팀 공통 진입점)
├─ schemas.py         ★ 에이전트 사이 계약. 바꾸면 남의 코드가 깨진다
├─ mocks.py           키 없이 전체 흐름을 돌리는 목업
└─ agents/
   ├─ commercial_area/   상권·경쟁 분석   (구현됨)
   ├─ decision/          중재·업종 판단   (구현됨)
   ├─ floating_population/  유동인구      (미구현)
   ├─ business_lifecycle/   개폐업        (미구현)
   └─ report/               리포트 구성   (미구현)
```

## 흐름

```
POST /api/v1/analyses  { address }
        │
        ├─ address.resolve_site()      주소 → 좌표 (카카오 또는 OSM)
        │
        ├─ orchestrator.run_agents()   ← 여기서 세 에이전트가 동시에 돈다
        │     floating_population ┐
        │     business_lifecycle  ├─ 각자 AgentAnalysis 를 만든다
        │     commercial_area     ┘   실패해도 다른 에이전트를 멈추지 않는다
        │
        └─ decision.analyze()          추천·비추천 업종 + 근거 검증
                 ↓
           DecisionResult
```

**등록되지 않은 에이전트는 중재 단계에서 "분석 누락"으로 기록됩니다.**
유동인구·개폐업이 완성되면 `orchestrator.default_agents()`에 한 줄씩 추가하면 됩니다.

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

개폐업은 `AGENT_NOT_CONNECTED` 응답을 유지합니다. 최종 결과는 stdout의 `DecisionResult`
JSON이며 `source_analyses`에서 두 에이전트가 직접 계산한 결과를 확인할 수 있습니다.
기존 `run_orchestration.py --mock --offline`은 완성된 분석 결과를 재생하는 별도 예제입니다.

개롱역 올리브영 주소는 시나리오 이름이며 좌표·인구·점포는 실제 관측값이 아닙니다.
주소 좌표와 상권영역 EPSG:5181 좌표·점포 좌표는 일관되게 수정해야 합니다.
조회 반경은 500m·2km, 자치구는 11710, 유동인구 기준일은 JSON의 `today`로 고정됩니다.
목업 업종은 API 원본 분류이며 공통 70개 업종 매핑을 구현한 데이터가 아닙니다.

LLM도 대역으로 교체하여 외부 연결 없이 검증:

```bash
python -m unittest discover -s tests -p test_api_mock.py -v
```

### ReAct 분석 연결

`app.agents.orchestration.build_react_agents()`는 유동인구·상권의 실제
`analyze()`와 개폐업 미연결 응답을 등록합니다. 등록 자체는 외부 API를 호출하지 않습니다.
`run_react(address, resolve=resolve, agents=build_react_agents())`로 명시적으로 연결합니다.
`resolve`는 주소 문자열을 받아 검증된 `Site`를 반환하는 비동기 함수입니다.

개폐업은 `status="error"`, `error.code="AGENT_NOT_CONNECTED"`를 반환합니다.
최종판단은 이 사유를 `limitations`에 기록하고 세 원본 응답을 `source_analyses`에 보존합니다.
판단 가능한 자료가 있으면 `partial`, 판단을 보류하면 `no_data`입니다.
개폐업 담당자가 공통 비동기 진입점을 제공하면 등록 함수의 해당 항목을 교체합니다.

실제 분석용 등록 함수는 `(0, 0)` 좌표를 외부 호출 전에 거절합니다.
다른 좌표의 정확성을 보증하는 검사는 아니므로, 검증된 위치만 사용해야 합니다.
기존 HTTP API와 `default_agents()`는 상권만 등록하는 고정 흐름을 유지합니다.

개롱역 올리브영 가상 입력으로 외부 호출 없이 실행:

```bash
python examples/run_orchestration.py --mock --offline
python -m unittest discover -s tests -p test_orchestration_connections.py -v
```

예제는 기존 분석 결과 목업을 사용합니다. 연결 테스트는 실제 두 분석 함수의 계산을
실행하되 API 클라이언트와 LLM을 대역으로 교체합니다. 키가 있어도 네트워크를 차단합니다.
`--offline`을 빼면 기존 예제는 실제 LLM을 호출합니다. 이번 검증에는 실제 API·LLM 및
카카오 주소 검색 연결 시험을 포함하지 않습니다.

Python **3.12**가 필요합니다. `pyproject.toml`이 `>=3.12,<3.13`으로 고정합니다.

```bash
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m uvicorn app.main:app --reload
```

- API 문서: <http://127.0.0.1:8000/docs>
- 상태 확인: <http://127.0.0.1:8000/health>

### 키 없이 띄우기

```bash
MOCK_MODE=1 .venv/Scripts/python -m uvicorn app.main:app --reload
```

또는 요청에 `?mock=true`를 붙입니다. 목업도 진짜 오케스트레이터와 중재를 지나가므로
응답 형태가 실제와 같습니다. 프론트 연동은 이걸로 먼저 시작하면 됩니다.

## 환경변수

`.env.example`을 `.env`로 복사해 채웁니다. **실제 키는 커밋하지 않습니다.**

| 변수 | 용도 | 없으면 |
| --- | --- | --- |
| `COMMERCIAL_AREA_API_KEY` | 소상공인 상가정보 | 상권 분석 `status: error` |
| `FRANCHISE_API_KEY` | 공정위 브랜드 목록 | 프랜차이즈 지표 생략 + `partial` |
| `GEOCODING_API_KEY` | 카카오 REST 키 (주소→좌표) | 정확도 낮은 OSM 사용 |
| `ELICE_API_KEY` / `ELICE_BASE_URL` / `ELICE_MODEL` | 모델 호출 | 요약·중재 실패 |
| `ANALYSIS_RADIUS_M` | 분석 반경 | 500 |
| `SBIZ_MAX_CONCURRENCY` | 동시 요청 수 | 4 |
| `CORS_ALLOW_ORIGINS` | 허용할 프론트 주소 (쉼표 구분) | `http://localhost:3000` |
| `MOCK_MODE` | `1`이면 항상 목업 응답 | 꺼짐 |

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
.venv/Scripts/python examples/run_decision.py --mock
.venv/Scripts/python examples/probe_radius.py           # API가 받는 반경 상한 실측
.venv/Scripts/python examples/build_upjong_master.py --official-csv <파일>
```

## 더 읽을 것

- 에이전트별 상세: [app/agents/commercial_area/README.md](app/agents/commercial_area/README.md)
- 코드 규칙: [../docs/CONVENTIONS.md](../docs/CONVENTIONS.md)
- 프론트와의 계약: [../docs/API_CONTRACT.md](../docs/API_CONTRACT.md)
