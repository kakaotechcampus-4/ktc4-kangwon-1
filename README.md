# ktc4-team-01
카카오테크 캠퍼스 4기 2단계 팀 프로젝트 — 강원대 1팀

## 프로젝트 구조

주소를 입력받아 유동인구·개폐업·상권 분석을 병렬 실행하고 중재 결과를 리포트로 제공합니다.
현재는 기본 폴더와 FastAPI 진입점만 준비했으며, 분석 API와 에이전트는 아직 구현되지 않았습니다.

```text
ktc4-kangwon-1/
├─ frontend/
│  └─ src/                         # 화면·백엔드 API 연동
└─ backend/
   ├─ pyproject.toml               # 파이썬 의존성·패키지 설정
   ├─ .env.example                 # API 키·모델 설정 예시
   ├─ app/
   │  ├─ __init__.py               # 백엔드 패키지
   │  ├─ main.py                   # FastAPI 진입점
   │  ├─ schemas.py                # 에이전트 간 공통 입출력
   │  ├─ orchestrator.py           # 병렬 실행·중재·리포트 연결
   │  ├─ address.py                # 주소 정규화·좌표 변환
   │  ├─ api/v1/                  # 사용자 요청 API
   │  └─ agents/
   │     ├─ floating_population/   # 유동인구 분석
   │     ├─ business_lifecycle/    # 개폐업 분석
   │     ├─ commercial_area/       # 상권·경쟁 분석
   │     ├─ decision/              # 추천·비추천 업종 판단
   │     └─ report/                # 시각화용 결과 구성
   ├─ examples/                   # 목업 자료·단독 실행 예시
   └─ tests/                      # 자동 테스트
```

공통 입출력은 `backend/app/schemas.py`에 정의했습니다. 전체 실행 흐름은 `backend/app/orchestrator.py`, 주소 변환은 `backend/app/address.py`에 구현합니다.
에이전트 내부 파일은 담당자가 작성합니다. LangChain·LangGraph는 도입이 확정되면 추가합니다.

## 백엔드 실행

Python 3.12를 사용합니다. 저장소 루트에서 실행합니다.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

API 문서는 `http://127.0.0.1:8000/docs`에서 확인합니다. 현재 등록된 분석 경로는 없습니다.
프론트엔드는 프레임워크 결정 후 초기화합니다. 실제 API 키는 커밋하지 않고 환경 변수로 관리합니다.

API 연결을 시작할 때 `backend/.env.example`을 `backend/.env`로 복사해 키와 모델 정보를 채웁니다.

## 빈 폴더 안내

에이전트 폴더에는 자리 표시용 파일도 넣지 않았습니다. Git은 빈 폴더를 추적하지 않으므로 복제 시 빈 폴더는 나타나지 않습니다.
다음 명령으로 저장소 루트에서 동일한 폴더를 만들 수 있습니다.

```powershell
New-Item -ItemType Directory -Force -Path frontend/src, backend/app/api/v1, backend/app/agents/floating_population, backend/app/agents/business_lifecycle, backend/app/agents/commercial_area, backend/app/agents/decision, backend/app/agents/report, backend/examples, backend/tests
```
