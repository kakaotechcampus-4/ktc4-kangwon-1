# 채움 — 공실에 맞는 업종 분석

카카오테크 캠퍼스 4기 · 강원대 1팀

빈 상가 주소 하나를 받아, 그 자리에 어떤 서비스 업종이 맞는지 근거와 한계까지 담아 임대인이 읽을 수 있는 리포트로 돌려줍니다.
추천 대상은 서비스 업종 51종입니다.

![주소 하나가 리포트가 되기까지](docs/images/architecture-flow.png)

- **100점 = 코드 90점 + decision 판단 10점.** 수요 35 · 경쟁 25 · 안정성 30은 코드가 계산하고, 코드가 볼 수 없는 것(주변 환경, 임대인 답변, 지표끼리의 충돌)만 decision이 10점으로 판단합니다.
- **숫자는 코드만 씁니다.** 모델은 숫자를 직접 쓰지 않고 근거(fact)를 가리키기만 하며, 문장의 숫자는 서버가 채웁니다.
- **평가자 4명이 항상 초안을 검토합니다.** 검토 의견은 decision이 한 번 반영한 뒤 서버가 최종 검증합니다.
- **자료는 분기마다 한 번 받아 둡니다.** 요청은 자료를 복사하지 않고 고정한 버전을 읽으므로, 같은 요청은 언제나 같은 자료를 근거로 삼습니다.

| 경로 | 역할 |
| --- | --- |
| [backend/](backend/README.md) | 로컬 자료 계산, decision, 평가, 저장, API |
| [frontend/](frontend/README.md) | 주소 입력과 결과 화면 |
| [docs/](docs/DATABASE.md) | 팀 규칙, API 계약, DB 구조, 설계 기록 |

## 실행

Python 3.12 환경에서 프로젝트 루트부터 실행합니다.

```powershell
conda activate chaeum
python -m pip install -e "./backend[dev]"
cd backend
python -m uvicorn app.main:create_app --factory --reload
```

별도 터미널에서 프론트를 실행합니다.

```powershell
cd frontend
npm install
npm run dev
```

화면은 <http://localhost:3000>, 백엔드 문서는 <http://localhost:8000/docs>입니다.

실제 분석에는 키 설정(`backend/.env`)과 저장소 밖 **자료 DB**가 필요합니다. 설정과 준비 방법은 [백엔드 README](backend/README.md)를 보세요.
외부 호출 없이 응답 형태만 확인하려면 `POST /api/v1/analyses?mock=true`를 호출합니다.

## 문서

| 문서 | 내용 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 이 저장소에서 일하는 방법 |
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | 코드 스타일·이름·에러 처리 |
| [docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md) | 브랜치·커밋·PR·리뷰 |
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | 프론트엔드와 백엔드가 주고받는 형태 |
| [docs/DATABASE.md](docs/DATABASE.md) | 두 DB의 구조와 ERD, 갱신·백업 |
| [docs/decision-prompt-rubric.md](docs/decision-prompt-rubric.md) | 채점표와 L 판단 기준 |
| [docs/agentic-decision-plan.md](docs/agentic-decision-plan.md) | 구조 설계와 실측 기록 |
| [docs/archive/](docs/archive/README.md) | 이전 설계 기록 |

실제 키, 주소별 실행 기록, 자료 DB, 원문 CSV는 커밋하지 않습니다.
