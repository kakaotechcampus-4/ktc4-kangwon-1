# AGENTS.md — 이 저장소에서 일하는 방법

사람과 AI 에이전트가 함께 읽는 문서입니다. 코드를 고치기 전에 이 문서를 먼저 읽습니다.

## 이 프로젝트가 하는 일

빈 상가 주소 하나를 받아 **그 자리에 어떤 업종이 맞는지** 근거와 함께 리포트로 돌려줍니다.
쓰는 사람은 상권 분석을 배운 적 없는 임대인입니다. 그래서 숫자만큼 **그 숫자를 풀어 쓴 문장**이 중요합니다.

## 구조

```
frontend/   Next.js 16 · React 19 · Tailwind v4
backend/    FastAPI · Python 3.12 · 비동기(asyncio)
docs/       규칙 문서 (컨벤션 · Git · API 계약)
```

데이터 흐름은 한 방향입니다.

```
주소 → 좌표(address.py)
     → 분석 에이전트 3종 병렬 실행(orchestrator.py)
          floating_population · business_lifecycle · commercial_area
     → 중재(decision) : 추천·비추천 업종과 근거
     → 리포트(report)  : 화면용 구성          ← 아직 미구현
```

## 반드시 지킬 것

1. **에이전트 사이 입출력은 `backend/app/schemas.py`가 유일한 기준이다.**
   여기 정의된 `AnalysisTask` / `AgentAnalysis` / `DecisionRequest` / `DecisionResult`를 바꾸면
   다른 사람 코드가 같이 깨집니다. 바꾸려면 PR에 먼저 올려 합의합니다.
   각 에이전트가 자유롭게 정하는 곳은 `AgentAnalysis.data` 안쪽뿐입니다.

2. **외부 호출은 전부 비동기다.** `httpx.AsyncClient`, `AsyncOpenAI`를 씁니다.
   `httpx.Client`, `time.sleep`을 새로 넣지 마세요 — 분석 한 번이 100회 넘는 HTTP 요청을 만들고,
   동기 호출은 FastAPI 이벤트 루프를 통째로 멈춥니다.

3. **에이전트는 예외를 밖으로 던지지 않는다.** 실패는 `status="error"`와 `error`로 표현합니다.
   부분 실패는 `status="partial"` + `warnings`입니다. 한 에이전트가 죽어도 나머지는 계속 돕니다.

4. **모델 응답을 그대로 믿지 않는다.** 구조는 pydantic으로 검증하고,
   근거(`evidence.path`)는 실제 입력 자료에 있는 필드인지 확인합니다(`decision/agent.py`).

5. **키는 코드에 넣지 않는다.** `backend/.env`만 씁니다. `.env.example`에 변수 이름만 올립니다.

6. **주석과 문서는 한국어로 쓴다.** 팀 전원이 한국어로 읽습니다.

## 작업 전에 돌리는 것

```bash
# 백엔드
cd backend
.venv/Scripts/python -m ruff check . && .venv/Scripts/python -m ruff format .
.venv/Scripts/python -m mypy
.venv/Scripts/python -m unittest discover -s tests

# 프론트엔드
cd frontend
npm run format:check && npm run lint && npm run build
```

CI(`.github/workflows/ci.yml`)가 PR마다 같은 것을 돌립니다.

## 손대면 안 되는 파일

`.github/workflows/assign-mentor.yml` · `notify-discord.yml` · `convention-check.yml` · `.github/CODEOWNERS`
운영진이 관리하는 리뷰 자동화입니다. 고치면 멘토 자동 지정이 멈춥니다.

## 더 읽을 것

| 문서 | 내용 |
| --- | --- |
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | 코드 스타일·이름 규칙·에러 처리 정책 |
| [docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md) | 브랜치·커밋·PR·리뷰 규칙 |
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | 프론트엔드와 백엔드가 주고받는 형태 |
| [backend/README.md](backend/README.md) | 백엔드 구조와 실행 |
| [frontend/README.md](frontend/README.md) | 화면 구조와 실행 |
