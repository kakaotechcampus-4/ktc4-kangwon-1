# 채움 — 공실에 맞는 업종 분석

카카오테크 캠퍼스 4기 · 강원대 1팀

빈 상가 주소를 받아 서비스 업종 51종의 추천 근거와 한계를 임대인이 읽을 수 있는 리포트로 제공합니다.

```text
주소 → 좌표 → 고정된 로컬 자료 버전 조회
     → 코드 채점 90점 + decision 판단 L 10점
     → 초안 → 네 평가자 병렬 검토 → decision 최종 반영·검증
     → 요청 SQLite 저장 → API 조회
```

decision은 필요한 원문·지도·규제 조회와 임대인 질문을 도구로 선택합니다.
숫자는 코드가 계산하며 모델의 근거 인용과 최종 출력은 서버가 검증합니다.

| 경로 | 역할 |
| --- | --- |
| [backend/](backend/README.md) | 로컬 자료 계산, 단일 decision, 평가, 저장과 API |
| [frontend/](frontend/README.md) | 주소 입력과 결과 화면 |
| `docs/` | 팀 규칙, API 계약과 설계 기록 |

## 실행

Python 3.12 환경에서 프로젝트 루트부터 실행합니다.

```powershell
conda activate chaeum
python -m pip install -e "./backend[dev]"
cd backend
python -m uvicorn app.main:create_app --factory --reload
```

백엔드 설정은 [backend/.env.example](backend/.env.example)을 참고합니다.
실제 분석 전에 저장소 밖 자료 DB의 완전한 활성 묶음이 필요합니다.
외부 호출 없는 API 확인은 `POST /api/v1/analyses?mock=true`로 실행합니다.
요청·질문·답변 형태는 [API 계약](docs/API_CONTRACT.md)을 따릅니다.

별도 터미널에서 프론트를 실행합니다.

```powershell
cd frontend
npm install
npm run dev
```

화면은 <http://localhost:3000>, 백엔드 문서는 <http://localhost:8000/docs>입니다.

## 협업 문서

- [작업 기준](AGENTS.md)
- [코드 컨벤션](docs/CONVENTIONS.md)
- [Git 작업 규칙](docs/GIT_WORKFLOW.md)
- [API 계약](docs/API_CONTRACT.md)
- [공통 업종·매핑](backend/app/industries/README.md)
- [이전 설계 기록](docs/archive/README.md)

실제 키·주소별 실행 기록·자료 DB·원문 CSV는 커밋하지 않습니다.
요청 DB는 스키마 3이며 기존 요청 파일의 재생성 절차는 백엔드 README를 따릅니다.
