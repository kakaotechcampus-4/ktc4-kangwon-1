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
