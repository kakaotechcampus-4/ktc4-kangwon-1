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
schemas.py   팀 공통 계약 (여기를 바꾸면 남의 코드가 깨진다)
agent.py     한 에이전트의 흐름. 외부 호출·계산·조립을 순서대로 부른다
client.py    외부 API 호출만. 계산하지 않는다
metrics.py   순수 계산만. 네트워크·파일을 모른다
llm.py       모델 호출과 응답 파싱만
schemas.py   (에이전트 안쪽) 그 에이전트의 data 구조
```

**계산 함수는 순수하게 둡니다.** `metrics.py`가 네트워크를 모르기 때문에 시험이 빠르고 안정적입니다.

### 비동기

- 외부 호출은 전부 `async`입니다. `httpx.AsyncClient`, `AsyncOpenAI`를 씁니다.
- 대기는 `await asyncio.sleep()`입니다. `time.sleep()`은 이벤트 루프를 멈춥니다.
- 여러 요청을 동시에 보낼 때는 `asyncio.Semaphore`로 상한을 겁니다.
  공공데이터 쿼터가 하루 10,000건이고 429가 옵니다. 기본 4개(`SBIZ_MAX_CONCURRENCY`).
- 파일 캐시 읽기·쓰기는 동기로 둡니다. 로컬 디스크는 짧고, 비동기로 바꿀 값어치가 없습니다.

### 에러 처리 — 어디서 무엇을 하나

| 위치 | 정책 |
| --- | --- |
| `client.py` | 외부 실패를 `SbizApiError`로 바꿔 올린다. 재시도는 여기서 한다 |
| `agent.py` | 예외를 밖으로 내보내지 않는다. `status`와 `warnings`로 표현한다 |
| `orchestrator.py` | 한 에이전트가 죽어도 나머지를 살린다. 죽은 것은 `status="error"`로 채운다 |
| `decision/llm.py` | 모델 실패는 **대체하지 않고 올린다**. 틀린 판단보다 실패가 낫다 |
| `api/v1/routes.py` | 예외를 HTTP 상태로 바꾼다. 400은 사용자 입력, 502는 외부 실패 |

`status` 네 가지의 뜻은 이렇게 고정합니다.

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
