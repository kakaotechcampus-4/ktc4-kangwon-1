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

현재 공개 API는 `services/analysis.py`에서 단일 decision 도구 루프를 실행합니다.

```
주소 → 좌표(address.py)
     → 자료 DB 버전 고정·SQL 조회(local_data) + 시설·규제 사전 조회
     → 코드 채점·fact 저장(agentic)
     → decision 도구 루프: 필요한 조회·선택적 질문·답변 재개 → 초안
     → 평가자 4명 병렬 검토 → decision이 한 번 반영
     → 서버 검증·요청 SQLite 저장 → API 조회
```

## 반드시 지킬 것

1. **공개 결과는 `backend/app/schemas.py`, 도구 입력·응답은 `backend/app/agentic/contracts.py`가 기준이다.**
   `AnalysisTask`·`AgentAnalysis`는 수집·계산 경계에도 사용합니다. HTTP 요청·응답 모델은
   `app/api/v1/`에 있습니다. 계약 변경은 호출자·화면에 영향을 주므로 PR에서 합의합니다.
   자료 DB는 수집·활성화용이며 요청 DB에는 버전 참조·근거·판단·질문 이력을 저장합니다.

2. **외부 호출은 전부 비동기다.** `httpx.AsyncClient`, `AsyncOpenAI`를 씁니다.
   `httpx.Client`, `time.sleep`을 새로 넣지 마세요 — 분석 한 번이 100회 넘는 HTTP 요청을 만들고,
   동기 호출은 FastAPI 이벤트 루프를 통째로 멈춥니다.
   파일·SQLite·SHP 읽기는 `asyncio.to_thread()`로 격리합니다. 서울 API 전송은 `app/seoul.py`에서 공유합니다.

3. **일반 분석 실패는 에이전트 결과로 수집한다.** 외부 API 실패는 `status="error"`와 `error`,
   부분 실패는 `status="partial"` + `warnings`로 표현해 다른 에이전트를 계속 실행합니다.
   단, 공통 계약 검증 오류는 잘못된 결과로 숨기지 않고 요청 경계까지 전파해 failed로 저장합니다.
   저장소 오류도 서비스 계층에서 전파하며 에이전트 오류로 바꾸지 않습니다.

4. **모델 응답을 그대로 믿지 않는다.** Pydantic으로 도구 계약을 검증하고,
   `agentic/report.py`에서 fact 소유·인용 가능 상태·업종·숫자 슬롯·코드 채점과의 정합성을 검증합니다.
   유효한 근거가 있다는 것만으로 모델 문장의 의미까지 참이라고 보장하지 않습니다.

5. **키는 코드에 넣지 않는다.** `backend/.env`만 씁니다. `.env.example`에 변수 이름만 올립니다.

6. **주석과 문서는 한국어로 쓴다.** 팀 전원이 한국어로 읽습니다.

## 작업 전에 돌리는 것

```bash
# 백엔드
conda activate chaeum
cd backend
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m unittest discover -s tests

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
