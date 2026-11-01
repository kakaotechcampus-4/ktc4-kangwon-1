# 백엔드 검증 안내

Python 3.12, `conda activate chaeum` 환경을 사용한다. 아래 명령은 `backend/` 기준이다.

```powershell
python -m pip install -e ".[dev]"
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m coverage run -m unittest discover -s tests -v
python -m coverage report
```

## 범위별 테스트

| 분류 | 대표 파일 (`backend/tests/`) | 검증 범위 |
| --- | --- | --- |
| 단위·계약 | `test_agentic_runtime.py` | 도구 입력·권한, L 검증, 대체 결과, 예산 |
| 기능 | `test_agentic_recording.py` | 모델 기록·재생 계약 |
| API 통합 | `test_agentic_public_api.py` | TestClient와 임시 SQLite로 접수·조회·재개 검증. 외부 호출 차단 |
| 동시성 | `test_agentic_runtime.py` 및 별칭·저장소 테스트 | 병렬 평가와 요청 상태·저장 경합 회귀 |
| 성능 도구 | `test_load_harness.py` | 부하 측정 도구 자체의 동작. 운영 처리량 측정이 아님 |
| 구조 | `test_dependency_boundaries.py` | 모듈 의존 방향·옛 실행 경로 재유입 방지 |

분류는 서로 겹친다. 전체 `unittest` 결과를 공식 개수로 삼는다. 브라우저 E2E는 이 검증에 포함하지 않는다. 실제 API·LLM 품질 검증은 [별도 실측 기록](quality-summary.md)이며 자동 테스트 통과와 구분한다.

## 측정 기준

2026-10-26 최종 검사에서 전체 **775개 테스트 통과**(102.567초). `app` 구문 커버리지는 7,673 / 8,560문장, **89.64%**였다. 분기 커버리지·추천 품질을 뜻하지 않는다. CI는 같은 구문 커버리지를 출력하며 실패 임계값은 아직 두지 않는다. `cache/.coverage`는 로컬 산출물이다.

인젝션 형태의 입력 테스트는 악의적 문장을 사용자 fact로 보존한 뒤, 모델이 그 지시를 따랐다고 가정해 권한 없는 도구와 임의 grade를 제출한다. 서버가 이를 거절하고 점수·원문을 보존하는지를 검증한다. 실제 LLM이 악성 지시를 따르지 않는다는 증명은 아니다.

단독 테스트 통과 뒤 프로세스 안에서 `LInput.model_validate`가 미허용 grade 필드를 무시하도록 대역을 주입했다. 이때 행이 채택되어 테스트가 실패했다. 소스 계약은 변경하지 않았고 대역 해제 후 전체 검사를 통과했다. API 문서 예시를 검증하는 테스트 2개도 바뀐 제목에 맞춰 유지했다.

## 복잡도·타입 측정

- Ruff 기본 기준(C901 복잡도 10, PLR0915 문장 수 50)으로 백엔드 전체를 측정했을 때 33개 파일에서 C901 41건·PLR0915 11건이었다. 별도 상한을 정하지 않았다.
- 이번에는 위반 파일만 `pyproject.toml`의 `per-file-ignores`에 기록하고 두 규칙을 켠다. **예외 파일 안에 새로 생긴 동일 위반도 차단하지 못한다.** 파일 정리 시 예외를 제거해야 한다.
- `app.agentic.*`에만 `disallow_untyped_defs=true`를 임시 적용해 측정하면 112개 소스 검사에서 **26개 파일·172건 오류**다. 정식 mypy 설정에는 적용하지 않는다.

타입 강화 재측정은 기존 mypy 설정을 유지한 임시 설정 파일에 아래 override를 추가해 `python -m mypy --config-file <임시 파일> --no-incremental`로 수행한다. 배포·CI 기준 변경이 아니다.

```toml
[[tool.mypy.overrides]]
module = ["app.agentic.*"]
disallow_untyped_defs = true
```

## 기술 부채 목록

AST의 함수 시작~끝 물리 행 수(주석·빈 줄 포함), 100줄 초과 함수 15개다. Ruff 문장 수와 다른 지표다. 줄 번호는 2026-10-26 기준이며 함수 이름으로 찾을 수 있다.

| 파일 (`backend/`) | 함수 | 시작 행 | 길이 |
| --- | --- | ---: | ---: |
| app/agentic/scoring.py | score_item | 78 | 282 |
| app/agents/business_lifecycle/preprocess.py | aggregate_rows | 67 | 189 |
| app/agentic/inputs.py | format_inputs | 106 | 188 |
| app/agentic/sql_tool.py | _query | 234 | 173 |
| app/agentic/facts.py | register_fact | 15 | 162 |
| app/agentic/evaluators.py | review | 156 | 155 |
| app/agentic/report.py | finalize | 403 | 139 |
| app/agentic/report.py | validate_l_records | 133 | 138 |
| app/agentic/snapshot.py | persist_report | 213 | 137 |
| app/local_data/adapter.py | analyze | 125 | 131 |
| app/agentic/landlord.py | review_packet | 63 | 115 |
| app/storage/raw.py | _save_response | 82 | 113 |
| app/agentic/runtime.py | submit_l | 428 | 110 |
| app/agentic/sql_tool.py | local_views | 124 | 108 |
| app/agentic/runtime.py | __init__ | 118 | 103 |

함수 분해·모듈 삭제는 이번 범위가 아니다. 채점·보고서·평가·스냅샷 담당자와 동작 보존 기준을 합의한 뒤 진행한다.
