# 오케스트레이터

서비스 진입점은 `app.services.analysis.execute_analysis()`입니다.
주소·요청 ID·반경·등록표를 확인하고 `run_graph()`로 실행합니다. 전체 구조는 [backend/README.md](../../../README.md)를 봅니다.

`ANALYSIS_MODE`로 두 모드 중 하나를 고릅니다.

```text
single_decision(기본)
prepare_address → run_analyses → evaluate_decision
                                ├─ 최종 결과 → 저장·종료
                                ├─ 보완 → execute_supplement → 재판단
                                ├─ 지도 조회 → execute_map → 재판단
                                └─ 질문 → ask_user(SQLite 대기) → 답변 후 최종판단만 재개

multi_agent
prepare_address → run_analyses → write_briefs → evaluate_decision
                                              ├─ 전문가 되묻기 → consult → 재판단
                                              └─ 나머지 분기는 위와 같음
```

- `workflow.py`: 주소 준비, 실제 분석 등록, 병렬 실행·공통 응답 검증.
- `graph.py`: 고정 순서와 선택 분기. `RunHooks`로 저장·관찰 콜백 전달.
- `consult.py`: 전문가 도구를 기존 읽기·보완·지도 실행에 연결(multi_agent 전용).
- `tools.py`: 보완 도구·지도 조회 함수 계약.
- `supplement.py`: 등록된 부분 작업 실행·채택 검증.
- 실행 순서를 고르는 LLM은 없습니다. 모델은 최종판단·전문가 브리프·되묻기·지도 업종 매핑에만 씁니다.
- 실행 오류·계약 오류·DB 오류를 구분하며 잘못된 응답을 성공으로 바꾸지 않습니다.

## 실행

Python 3.12, backend 폴더 기준:

```powershell
python examples/run_orchestration.py --mock --offline --db storage/offline.sqlite3
python examples/run_orchestration.py --mock
```

첫 명령은 외부 호출 없는 대역입니다. 두 번째는 가상 자료로 실제 최종판단 LLM을 호출하며 비용이 발생합니다.
가상 자료를 실서비스 입지 판단에 사용하지 않습니다.
