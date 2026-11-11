# 채움 — 공실에 맞는 업종 분석

카카오테크 캠퍼스 4기 · 강원대 1팀

빈 상가 주소 하나를 받아, 그 자리에 어떤 서비스 업종이 맞는지 근거와 한계까지 담아 임대인이 읽을 수 있는 리포트로 돌려줍니다.
추천 대상은 서비스 업종 51종입니다.

- **문제:** 임대인은 빈 상가에 어떤 업종이 맞는지 판단할 자료와 기준을 모으기 어렵습니다.
- **대상:** 입점 후보를 검토하는 임대인입니다. 실제 입점 가능성·매출·수익을 보장하는 서비스는 아닙니다.
- **데모:** 주소·층 입력 → 확인 화면에서 면적·설비 확정 → 분석·필요한 질문에 답변 → 근거와 확인 조건이 있는 보고서 조회.

| 운영 | 주소 |
| --- | --- |
| 서비스 | https://chaeum-ai.kr |
| API | https://api.chaeum-ai.kr (상태 확인 https://api.chaeum-ai.kr/health) |

예시 중개사·매칭 화면, chum.ai 표기, 로그인 뒤 주소 입력, 그리고 AI 분석에서 평가자가 실패해도 계속 진행하거나 예산이 차면 코드 점수로 마무리하는 것처럼 일부러 그렇게 만든 부분은 [docs/DESIGN_INTENT.md](docs/DESIGN_INTENT.md)에 적었습니다.

![주소 하나가 리포트가 되기까지](docs/images/architecture-flow.png)

- **100점 = 코드 90점 + decision 판단 10점.** 수요 35 · 경쟁 30 · 안정성 15 · 시설 10은 코드가 계산하고, 코드가 볼 수 없는 것(주변 환경, 임대인 답변, 지표끼리의 충돌)만 decision이 10점으로 판단합니다.
- **숫자는 코드만 씁니다.** 모델은 숫자를 직접 쓰지 않고 근거(fact)를 가리키기만 하며, 문장의 숫자는 서버가 채웁니다.
- **평가자 4명이 항상 초안을 검토합니다.** 검토 의견은 decision이 한 번 반영한 뒤 서버가 최종 검증합니다.
- **자료는 분기마다 한 번 받아 둡니다.** 요청은 자료를 복사하지 않고 고정한 버전을 읽으므로, 같은 요청은 언제나 같은 자료를 근거로 삼습니다.

| 경로 | 역할 |
| --- | --- |
| [backend/](backend/README.md) | 로컬 자료 계산, decision, 평가, 저장, API |
| [frontend/](frontend/README.md) | 주소 입력과 결과 화면 |
| [docs/](docs/) | 팀 규칙, API 계약, DB 구조, 설계 기록 |

## 실행

Python 3.12 환경에서 프로젝트 루트부터 실행합니다. 환경이 없으면 `conda create -n chaeum python=3.12`로 먼저 만듭니다.

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

### 키·자료 DB 없이 확인하기

- **화면:** `frontend/.env.local`에 `NEXT_PUBLIC_MOCK_MODE=true`를 두고 `npm run dev`를 띄우면, 백엔드 없이 주소 입력부터 리포트까지 예시 자료로 돕니다.
- **API:** `?mock=true`를 붙이면 외부 호출 없이 고정 응답을 돌려줍니다. 분석 API는 메일 인증을 마친 계정의 로그인 쿠키와 허용된 출처(`Origin`)가 있어야 받으므로, 아래 순서로 호출합니다. 백엔드를 띄워 둔 채 다른 터미널(Git Bash · macOS · Linux)에서 실행합니다.

```bash
cd backend

# 1. 메일 인증까지 끝난 시험 계정을 요청 DB에 만듭니다
python scripts/create_e2e_user.py storage/chaeum.sqlite3 demo@example.com demo-pass-1234

# 2. 로그인해서 세션 쿠키를 받습니다
curl -c storage/cookies.txt -X POST http://localhost:8000/api/v1/auth/login   -H 'Origin: http://localhost:3000' -H 'Content-Type: application/json'   -d '{"email":"demo@example.com","password":"demo-pass-1234"}'

# 3. 질문을 허용한 분석을 시작합니다
curl -b storage/cookies.txt -X POST 'http://localhost:8000/api/v1/analyses?mock=true'   -H 'Origin: http://localhost:3000' -H 'Content-Type: application/json'   -d @- <<'EOF'
{"address":"서울 송파구 오금로 404","allow_questions":true}
EOF
```

3번의 HTTP 200 응답 예입니다. ID는 실행마다 달라집니다. 질문이 없는 요청은 최종 DecisionResult를 바로 반환합니다.

```json
{
  "request_id": "bc458f348ab04f54a9159f2a3ffd346b",
  "status": "waiting_for_input",
  "question_session_id": "question_dcb9106c-eb14-4d18-9e62-00131dae7d0b",
  "questions": [
    {"field":"floor","question":"몇 층인가요?","reason":"층에 따라 들어올 수 있는 업종과 손님 동선이 달라져요."}
  ]
}
```

받은 ID로 답을 보내면 같은 요청이 재개되어 최종 결과가 돌아옵니다.

```bash
curl -b storage/cookies.txt -X POST 'http://localhost:8000/api/v1/analyses/<request_id>/answers?mock=true'   -H 'Origin: http://localhost:3000' -H 'Content-Type: application/json'   -d @- <<'EOF'
{"question_session_id":"<받은 세션 ID>","answers":{"floor":"1층"}}
EOF
```

최종 결과는 `curl -b storage/cookies.txt http://localhost:8000/api/v1/analyses/<request_id>`로도 조회합니다. 쿠키나 `Origin`이 없으면 401·403으로 거절됩니다. 목업은 계약·화면 연결 시험이며 추천 품질의 근거가 아닙니다.

## 시험과 CI/CD

| 대상 | 실행 | 2026-11-11 CI 결과 |
| --- | --- | --- |
| 백엔드 | `backend/`에서 `python -m unittest discover -s tests` | 1,189개 통과, 구문 커버리지 91.75% |
| 화면 | `frontend/`에서 `npm test` | 431개 통과 |
| 브라우저 E2E | `frontend/`에서 `npm run e2e` | 4개 통과(로그인부터 리포트까지, 질문 답변 뒤 재개, 폰 화면, 탈퇴) |
| 배포 스크립트 | `bash deploy/tests/test_deploy.sh` | 배포 실패·되돌리기 상황 11개 통과 |

자동 시험은 임시 DB와 대역 모델만 쓰고 외부 API·실제 모델을 부르지 않습니다. 실제 모델로 돌린 결과는 [docs/quality-summary.md](docs/quality-summary.md)에 따로 기록합니다.

- **CI:** [ci.yml](.github/workflows/ci.yml)이 모든 PR과 develop·main push에서 위 네 가지와 형식·린트·타입 검사·빌드를 돌립니다.
- **배포:** develop에 합쳐지면 백엔드는 [deploy.yml](.github/workflows/deploy.yml)이 AWS EC2에 무중단으로 배포하고, 화면은 Vercel이 배포합니다. 새 버전이 상태 확인을 통과하지 못하면 전환하지 않고 이전 버전이 계속 서비스합니다. 절차와 되돌리기는 [docs/DEPLOY.md](docs/DEPLOY.md)에 있습니다.

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
| [백엔드 실행 분기표](backend/README.md#분기예외재개-코드-찾기) | 도구 루프·실패·평가·재개 위치 |
| [docs/quality-summary.md](docs/quality-summary.md) | 실제 실행의 실패·개선 기록과 한계 |
| [docs/TESTING.md](docs/TESTING.md) | 테스트 분류·커버리지·기술 부채 |
| [docs/DEPLOY.md](docs/DEPLOY.md) | 운영 주소·환경·배포 절차·되돌리기 |
| [docs/DESIGN_INTENT.md](docs/DESIGN_INTENT.md) | 일부러 그렇게 만든 화면·표기·AI 분석 동작과 이유 |
| [docs/consistency-live-report.md](docs/consistency-live-report.md) | 같은 주소를 실제 모델로 반복 분석한 결과, 찾은 문제와 고친 것 |
| [docs/archive/](docs/archive/README.md) | 이전 설계 기록 |

실제 키, 주소별 실행 기록, 자료 DB, 원문 CSV는 커밋하지 않습니다.
