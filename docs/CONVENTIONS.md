# 코드 컨벤션

도구가 강제할 수 있는 것은 도구에 맡기고, 이 문서에는 **도구가 잡지 못하는 판단**을 적습니다.

## 도구가 강제하는 것

| 영역 | 도구 | 설정 위치 | 실행 |
| --- | --- | --- | --- |
| 파이썬 lint·import 정렬 | ruff | `backend/pyproject.toml` | `ruff check .` |
| 파이썬 포맷 (100자) | ruff format | 같은 파일 | `ruff format .` |
| 파이썬 타입 | mypy | 같은 파일 | `mypy` |
| TS/TSX lint | ESLint | `frontend/eslint.config.mjs` | `npm run lint` |
| TS/TSX 포맷 | Prettier | `frontend/.prettierrc` | `npm run format` |

PR마다 CI가 같은 명령을 돌립니다. **로컬에서 먼저 돌리고 올립니다.**

## 파이썬

### 이름

| 대상 | 규칙 | 예 |
| --- | --- | --- |
| 모듈 | 소문자 단수 명사 | `client.py`, `metrics.py` |
| 함수 | 동사로 시작 | `build_middle_rows`, `resolve_site` |
| 내부 전용 함수 | `_` 접두 | `_extract_items` |
| 상수 | 대문자 | `SBIZ_BASE_URL` |
| pydantic 모델 | 명사 단수 | `AgentAnalysis`, `RadiusSlice` |
| 불리언 | 상태를 읽히게 | `truncated`, `degraded` |

### 계층

```
domain/          순수 규칙과 공개 계약. 네트워크·DB·파일 쓰기를 모른다 (schemas·contracts·scoring·code90·분기·인구 기록·업종·기준값)
application/     요청 흐름(분석 실행·재개·인증·작업·리포트 확정). domain을 쓰고 저장은 포트로 한다
ai/              decision·자문·질문·평가자·도구 실행. application과 domain을 쓴다
infrastructure/  요청 DB·원문 보관(persistence), 시장 자료(market_data), 외부 API(clients), LLM, 설정
shared/          어디서나 쓰는 작은 도구(canonical JSON·시각·스레드 격리·마스킹·로그 정제)
api/v1/          HTTP 경계. application만 부른다
main.py          조립 지점. 설정·DB·라우터를 연결한다
```

- 수집 패키지(`infrastructure/market_data/*`) 안에서도 `client.py`는 외부 호출만, `metrics.py`는 순수 계산만 둡니다.
- 방향 규칙은 `tests/test_architecture.py`가 검사합니다. 예외 목록 없이 위반 0건이어야 통과합니다.
- 상대 import는 쓰지 않습니다(ruff TID252).
- `sqlite3`·`httpx`·`openai`는 infrastructure에서만 씁니다. 저장소가 중복·경합 같은 DB 사정을 처리하고 필요하면 `EmailTaken`처럼 뜻이 드러나는 오류로 바꿔 올립니다.
- domain은 `os`·`sqlite3`·`httpx`·`asyncio`·`threading` 같은 I/O 모듈을 import하지 않습니다. 코드와 함께 배포되는 기준 CSV는 `domain/resources.py`의 `read_bundled_csv`로만 읽습니다. 서울 인구 스냅숏처럼 읽을 때 원문을 기록하는 자료는 호출하는 쪽이 함수로 넘깁니다(`evaluate(..., age_baseline=)`).
- application·ai는 DB를 직접 열지 않고 `application/ports/storage.py`의 저장 창구(`open_stores(path)`, `storage().requests` 등)를 씁니다. sqlite 구현은 `infrastructure/persistence/stores.py`, 연결은 `app/bootstrap.py`가 합니다. 창구 정의는 저장소 함수 서명과 1:1이고 `tests/test_storage_port.py`가 검사합니다.
- 시장 자료(원문→계산 변환, 로컬 자료, 참고 분포 버전)는 `application/ports/market.py`의 `market()` 창구로 씁니다. 구현은 `infrastructure/market_data/service.py`입니다.
- 모델 호출은 `application/ports/llm.py`의 `llm()` 창구(`complete_json`·`complete_tools`·호출 기록·연결 세션)로 합니다. 호출 예산(`llm_budget.py`)·설정(`llm_settings.py`)·오류 형식(`LLMResponseError`·`LLMHTTPError`)도 같은 폴더에 있어 ai와 인프라가 함께 씁니다. 녹화 재생이 오류 클래스 이름으로 맞추므로 이름을 바꾸지 않습니다.
- 지도 장소 검색과 교육환경보호구역 조회는 `application/ports/places.py`의 `places()` 창구로 합니다. 구현은 `infrastructure/clients/places.py`입니다. 지도 매칭 규칙(`domain/place_matching.py`)과 다각형 판정(`domain/geo.py`)은 순수 계산이라 domain에 둡니다.
- application은 ai를 직접 import하지 않고 `application/ports/decision.py`의 `decision()` 창구(예산·판단 루프 생성/재개 검증/재개)로 부릅니다. 구현은 `ai/engine.py`입니다. 채점 전 시설·규제 조회(`application/preflight.py`, `application/map_regulation.py`)는 AI와 무관하므로 application에 두고, 채점 경로는 AI 폴더 없이 불러올 수 있어야 합니다(`tests/test_architecture.py`).
- AI의 원문 SQL 조회는 입력 검증·응답 조립만 `ai/sql_tool.py`에 두고, 읽기 전용 연결·권한 검사·임시 뷰는 `infrastructure/persistence/raw_query.py`(`storage().raw_query`)가 맡습니다. 뷰 목록과 필드 정의는 `domain/raw_views.py`입니다. 그래서 SQL 문장은 인프라 밖에 없습니다.
- 주소 확인·건축물대장 조회는 `sites()`, 카카오 로그인·메일은 `identity()`, 데모 모드 대역은 `demo()` 창구로 부릅니다(`application/ports/`). 건축물대장 응답 모델은 `domain/building.py`입니다.
- API에는 HTTP 입출력만 둡니다. 소유자 판정·답변 접수 조건·입력값 변환은 application(`requests.py`, `answers.py`)에 둡니다.
- application 모듈에는 불러오기·저장만 두고, 같은 입력이면 같은 답을 내는 규칙은 domain에 둡니다: 리포트 문장·순위·조건 제외(`domain/report.py`), 공간 대조(`domain/space_fit.py`), fact 식별값·인용 가능 판정·지표 이름(`domain/facts.py`). 질문 답 저장은 `application/answers.py`입니다.
- 창구는 처음 쓰일 때 `app.bootstrap`을 불러 연결합니다. 그래서 계층 모듈은 `app.bootstrap`·`app.main`을 import하지 않습니다(`tests/test_architecture.py`).
- 시험에서 저장소 함수를 바꿔치기할 때는 `repository/requests.py` 같은 하위 모듈을 patch합니다. 패키지 `repository`가 재수출한 이름을 patch하면 창구에는 반영되지 않습니다. 창구 구현 클래스가 클래스 속성으로 묶어 둔 함수(`stores.py`의 `initialize`·`capture`·`raw_query`, `llm/service.py`, `market_data/service.py`)는 정의한 모듈을 patch해도 반영되지 않으므로 `patch.object(llm(), "complete_json")`처럼 창구 객체를 patch합니다.

**계산 함수는 순수하게 둡니다.** `metrics.py`가 네트워크를 모르기 때문에 시험이 빠르고 안정적입니다.

**수집 패키지는 다른 수집 패키지를 import 하지 않습니다.** 다만 둘 이상이 쓰는 코드를 복사하지는
않습니다. 파일·네트워크를 모르는 순수 계산이면 `domain/`으로 올리고(`domain/geo.py`), 요청 흐름을
다루면 `application/`에 둡니다.

### 비동기

- 외부 호출은 전부 `async`입니다. `httpx.AsyncClient`, `AsyncOpenAI`를 씁니다.
- 기존 개폐업 동기 I/O 파이프라인은 `asyncio.to_thread()`로 격리해 이벤트 루프를 막지 않습니다.
- 대기는 `await asyncio.sleep()`입니다. `time.sleep()`은 이벤트 루프를 멈춥니다.
- 여러 요청을 동시에 보낼 때는 `asyncio.Semaphore`로 상한을 겁니다.
  공공데이터 쿼터가 하루 10,000건이고 429가 옵니다. 기본 4개(`SBIZ_MAX_CONCURRENCY`).
- 파일 캐시 읽기·쓰기는 동기로 둡니다. 로컬 디스크는 짧고, 비동기로 바꿀 값어치가 없습니다.

### 에러 처리 — 어디서 무엇을 하나

| 위치 | 정책 |
| --- | --- |
| `client.py` | 외부 실패를 `SbizApiError`로 바꿔 올린다. 재시도는 여기서 한다 |
| `infrastructure/market_data/local/` | 자료 불완전·버전 없음은 `DataValidationError`. 검증 실패 시 활성 자료를 바꾸지 않는다 |
| `ai/` · `application/` | 도구 오류는 구조화된 결과, 계약·저장 오류는 요청 경계로 전파한다. 병렬 평가 실패를 수집한다 |
| `infrastructure/llm/` | 모델 실패를 임의의 판단으로 대체하지 않고 올린다 |
| `application/analysis.py` | 저장 오류를 에이전트 실패로 숨기지 않고 전파한다 |
| `api/v1/analyses.py` | 입력·외부 실패·계약·저장 실패를 API 계약의 HTTP 오류로 변환한다 |

수집·계산 자료의 `AgentAnalysis.status` 네 가지 뜻은 다음과 같습니다.
공개 요청·질문·최종 보고서의 상태는 [API 계약](API_CONTRACT.md)을 따릅니다.

| status | 뜻 | `data` |
| --- | --- | --- |
| `ok` | 전부 계산됨 | 있음 |
| `partial` | 일부 지표가 빠졌지만 쓸 수 있음 | 있음 |
| `no_data` | 조회는 됐는데 대상이 없음 | 비어 있음 |
| `error` | 조회 자체가 실패 | 비어 있음 |

### 주석

- **무엇을 하는지가 아니라 왜 그렇게 했는지**를 씁니다. 코드가 말하는 것을 반복하지 않습니다.
- 판단이 들어간 곳(기준선을 둘로 나눈 이유, 동시 요청 상한을 4로 둔 이유)에는 한 줄이라도 남깁니다.
- 한국어로 씁니다.

## TypeScript · React

### 이름

| 대상 | 규칙 | 예 |
| --- | --- | --- |
| 컴포넌트 파일 | PascalCase | `AddressInput.tsx` |
| 컴포넌트 | 파일명과 같게 | `export default function AddressInput()` |
| 훅 | `use` 접두 | `useAnalysis` |
| 타입 | PascalCase, `type` 우선 | `type InfoCard = {...}` |

### 폴더

```
app/          라우트 (page.tsx / layout.tsx)
components/
  ui/         재사용 기본 요소 (Button, Card, Input …)
  layout/     Header 등 공통 골격
  landing/    랜딩 전용
  form/       입력 화면 전용
lib/          API 호출·유틸
types/        백엔드 계약을 옮긴 타입
styles/       디자인 토큰
```

화면 전용 컴포넌트를 `ui/`에 넣지 않습니다. `ui/`는 어디서든 쓸 수 있는 것만 둡니다.

### 반응형 — 고정 px를 쓰지 않는다

- 컨테이너 폭은 `w-[1440px]`이 아니라 `w-full max-w-[1440px]`입니다.
  고정폭을 쓰면 그보다 좁은 화면에서 **가로 스크롤이 생깁니다.**
- 여러 장을 나열할 때는 `flex` + 고정폭이 아니라 `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3`입니다.
- 브레이크포인트는 Tailwind 기본값을 씁니다: `sm 640` · `md 768` · `lg 1024` · `xl 1280`.
- 디자인이 절대좌표로 잡혀 있으면(예: Hero의 떠 있는 카드) **비율(%)과 컨테이너 단위(cqw)** 로 옮깁니다.
  `Hero.tsx`의 `pctX` / `fs` 헬퍼가 그 예입니다.
- 색은 `styles/tokens.ts`에서 가져옵니다. 헥사값을 컴포넌트에 직접 쓰지 않습니다.

## 커밋 전 점검

```bash
cd backend  && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format --check . \
            && .venv/Scripts/python -m mypy && .venv/Scripts/python -m unittest discover -s tests
cd frontend && npm run format:check && npm run lint && npm run build
```
