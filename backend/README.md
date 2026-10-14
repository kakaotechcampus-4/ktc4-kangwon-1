# 채움 백엔드

Python 3.12 · FastAPI · Pydantic · sqlite3 · httpx/AsyncOpenAI

주소 하나에서 고정된 자료 버전을 읽고 업종 51종을 코드로 채점합니다.
단일 decision이 추가 근거와 임대인 답변을 확인해 설명과 L 판단을 만들고,
네 평가자가 초안을 병렬 검토한 뒤 decision이 최종 반영합니다.

```text
주소·좌표 → 로컬 자료 버전 고정 → 코드 D35/C25/S30
         → decision L10·근거 조회·질문 → 초안
         → 네 평가자 → 최종 검증·렌더링 → 요청 DB·API
```

근거는 fact ID와 원문 셀·계산 계보로 검증합니다. 모델이 쓴 숫자를 자유 문장으로 채택하지 않습니다.
`unknown`, 실제 영, 미적용, 자료 오류를 구분합니다.

## 구조

```text
app/
  schemas.py · address.py · geo.py · config.py · seoul.py
  api/v1/       분석·질문·답변·이벤트 HTTP 경계
  services/     실행·재개·작업 슬롯과 실패 저장
  agentic/      decision, 자문, 질문, 네 평가자, 채점·fact·SQL·보고서
  local_data/   자료 적재·활성화·버전 고정·계산 어댑터·계보
  agents/       인구·개폐업·상권 계산과 수집 클라이언트·지도 일치 규칙
  industries/   공통 51업종·프로필·매핑·밀도 기준선 CSV
  db/ · storage/ 요청 DB와 원문·출처 저장
  education_zone.py
scripts/        자료 갱신·기준선 생성·재현 검증
tests/          임시 DB·API/모델 대역 회귀
```

최종 판단 코드는 `app/agentic/`에 모읍니다.
수집 클라이언트는 자료 갱신·연구용으로 유지하며 일반 분석 요청에서 기본 자료 API를 다시 호출하지 않습니다.
API 입력과 결과는 [API 계약](../docs/API_CONTRACT.md)을 따릅니다.

## 설치·실행

프로젝트 루트에서 실행합니다.

```powershell
conda activate chaeum
python -m pip install -e "./backend[dev]"
cd backend
python -m uvicorn app.main:create_app --factory --reload
```

실제 키는 `backend/.env`에만 둡니다. 변수 이름은 [.env.example](.env.example), 기본값은 각 설정 모듈을 확인합니다.
예시 파일에는 변수 이름만 둡니다. 기본값을 덮어쓸 선택 변수는 값을 채우고 주석을 풀어 사용하세요.
사용하지 않는 과거 실행 모드·에이전트별 모델·분석 타임아웃 환경변수는 예시 설정에서 제거합니다.
현재 모델 역할은 공통 `ELICE_*`와 선택적 `DECISION_LLM_*`, `EVALUATOR_LLM_*`, `ADVISOR_LLM_*`입니다.
주소·지도는 `GEOCODING_API_KEY`, 규제 조회는 `VWORLD_API_KEY`와 `VWORLD_REFERER`를 사용합니다.
`ANALYSIS_MAX_CONCURRENCY`는 백그라운드 동시 분석 수, `CORS_ALLOW_ORIGINS`는 프론트 주소입니다.
주소는 공백을 정리한 뒤 200자 이내만 허용하며 제한을 넘으면 외부 조회 전에 거절합니다.

`POST /api/v1/analyses?mock=true` 또는 `MOCK_MODE=true`로 외부 호출 없이 동일한 평가·보고서 계약을 확인합니다.
상태는 `GET /api/v1/analyses/{request_id}`, 진행은 `/events`, 답변은 `/answers`에서 다룹니다.
녹화는 `create_app(recording_dir=...)` 서버 설정으로만 켭니다.

## 서로 다른 두 DB

| 설정 | 역할 | 기본 경로 |
| --- | --- | --- |
| `SQLITE_PATH` | 요청·fact·채점·질문·최종 결과 | `backend/storage/chaeum.sqlite3` |
| `LOCAL_DATA_DB_PATH` | 서울 전체 자료와 분기별 활성 release | 사용자 홈의 `.chaeum/market_data.sqlite3` |

실제 분석에는 자료 DB가 반드시 필요합니다. 환경변수를 생략할 수는 있지만 기본 경로에 완전한 활성 자료가 있어야 합니다.
자료 DB와 원문 CSV는 저장소 밖에 두세요. 요청 실행은 자료 버전을 고정하므로 활성 release가 바뀌어도 같은 버전을 읽습니다.
삭제된 옛 버전을 고정한 대기 요청은 재개 시 실패로 저장됩니다.

요청 DB는 **스키마 버전 5**입니다. 이전 버전은 자동 이전하지 않고 시작 시 거절합니다.
서버를 중지하고 기존 요청 DB와 해당 `-wal`·`-shm` 파일을 저장소 밖에 백업·이동한 뒤 다시 시작하세요.
새 요청 DB가 생성됩니다. **자료 DB(`LOCAL_DATA_DB_PATH`)는 그대로 보존하며 이 절차로 삭제하지 않습니다.**

## 자료 갱신

`scripts/refresh_local_data.py`는 적재 후 한 트랜잭션으로 새 release를 활성화합니다.
필수 원천은 stores·lifecycle·floating·resident·worker·areas이며 서울 경계는 별도로 추가할 수 있습니다.
개폐업 12분기, 유동 5분기는 연속이어야 하고 점포·개폐업·유동·상주·직장의 최신 분기가 일치해야 합니다.
잘못된 묶음은 활성 자료를 바꾸지 않으며 실패한 staged 적재를 정리합니다. 활성·직전 release를 보존합니다.

```powershell
python scripts/refresh_local_data.py --quarter 20262 --seoul-csv D:/data/seoul.csv --shp D:/data/area.shp
python scripts/refresh_local_data.py --source floating --quarter 20262 --reset-checkpoint
```

갱신 명령은 외부 API·자료 DB를 변경하므로 필요한 파일과 키를 준비한 뒤 직접 실행합니다.
체크포인트는 하루 동안 재사용하고 첫 페이지를 다시 검증합니다. 총행 수가 바뀌면 한 번 전체를 재수집합니다.
`--reset-checkpoint`는 선택 원천의 API 페이지를 지우고 수집하며 `--dry-run`은 임시 DB에서 파일을 검증합니다.
부분 원천의 첫 적재나 필요한 분기 수를 줄인 활성화는 허용하지 않습니다.
51업종 밀도 기준선은 `app/industries/data/density_percentiles.csv`입니다.
`build_density_baseline.py --industries --emit`은 완전한 표본만 이 CSV에 저장합니다.

## 자료 범위와 판단 한계

점포는 요청·비교 반경 안의 서울 CSV, 개폐업은 선택한 상권 폴리곤,
인구는 요청 반경과 겹치는 상권 자료를 사용합니다. 같은 반경이어도 모집단은 다릅니다.
지도는 조회 시점의 카카오 등록 표본이며 분기 점포 전수와 더하지 않습니다.
추천 점수는 성공 확률·매출·수익 예측이 아닙니다. 지역·기간·누락·매핑 한계를 결과에 남깁니다.

운영 예산은 입력 400k·출력 60k·모델 40회·활성 시간 600초·호출당 출력 최대 16k입니다.
읽기 전용 SQL에는 실행 시간·행 수·64KB 결과 한도가 있습니다.

## 검증과 참고

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m unittest discover -s tests
python scripts/verify_rubric_reproduction.py
```

자동 시험은 임시 DB와 API·모델 대역을 사용합니다.
실제 API와 모델 품질 검증은 별도 승인된 실행에서만 확인합니다.
[인구](app/agents/floating_population/README.md), [상권](app/agents/commercial_area/README.md),
[지도](app/agents/map_analysis/README.md), [채점표](../docs/decision-prompt-rubric.md)를 참고하세요.
[이전 설계 기록](../docs/archive/README.md)은 당시 구현의 기록입니다.
