# 채움 — 공실에 맞는 업종을 찾아드립니다

카카오테크 캠퍼스 4기 2단계 팀 프로젝트 · 강원대 1팀

빈 상가 주소 하나를 넣으면 **그 자리에 어떤 업종이 맞는지** 근거와 함께 리포트로 돌려줍니다.
쓰는 사람은 상권 분석을 배운 적 없는 임대인입니다.

```
주소 입력 → 좌표 변환 → 분석 에이전트 3종 병렬 실행 → 중재(업종 판단) → 리포트
```

## 구조

| 폴더 | 내용 | 문서 |
| --- | --- | --- |
| `frontend/` | Next.js 16 · React 19 · Tailwind v4 | [frontend/README.md](frontend/README.md) |
| `backend/` | FastAPI · Python 3.12 · 비동기 | [backend/README.md](backend/README.md) |
| `docs/` | 팀 규칙 | 아래 표 |

| 문서 | 언제 읽나 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | **코드를 고치기 전에.** 사람과 AI 에이전트가 함께 읽는 기준 |
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | 이름·계층·에러 처리·반응형 규칙 |
| [docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md) | 브랜치·커밋·PR·리뷰 |
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | 프론트와 백엔드가 주고받는 형태 |

## 빠르게 띄우기

키가 없어도 전체 흐름이 돕니다.

```bash
# 1) 백엔드 (터미널 A)
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
MOCK_MODE=1 .venv/Scripts/python -m uvicorn app.main:app --reload

# 2) 프론트엔드 (터미널 B)
cd frontend
npm install
npm run dev
```

- 화면 <http://localhost:3000>
- API 문서 <http://127.0.0.1:8000/docs>

실제 분석을 돌리려면 `backend/.env.example`을 `backend/.env`로 복사해 키를 채웁니다.

## 만든 것 / 남은 것

| 구성 요소 | 상태 |
| --- | --- |
| 팀 공통 스키마 (`backend/app/schemas.py`) | ✅ |
| 상권·경쟁 분석 에이전트 | ✅ |
| 중재(업종 판단) 에이전트 | ✅ |
| 오케스트레이터 · `POST /api/v1/analyses` · CORS | ✅ |
| 랜딩 · 공실 입력 화면 | ✅ (백엔드 연동 전) |
| 유동인구 에이전트 | ⬜ |
| 개폐업 에이전트 | ⬜ |
| 리포트 에이전트 · 결과 화면 | ⬜ |
| 프론트 ↔ 백엔드 실제 연동 | ⬜ |

## 검사

```bash
cd backend  && .venv/Scripts/python -m ruff check . && .venv/Scripts/python -m mypy \
            && .venv/Scripts/python -m unittest discover -s tests
cd frontend && npm run format:check && npm run lint && npm run build
```

PR마다 CI(`.github/workflows/ci.yml`)가 같은 것을 돌립니다.

## 데이터 출처

```
상가(상권)정보 — 소상공인시장진흥공단 (2026), data.go.kr
가맹정보 — 공정거래위원회 (2026), data.go.kr
```

공공누리 데이터는 출처표시가 의무입니다. 리포트와 화면 하단에 넣습니다.
