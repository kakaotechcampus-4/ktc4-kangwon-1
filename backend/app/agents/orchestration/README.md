# 오케스트레이터

서비스 진입점은 `app.services.analysis.execute_analysis()`입니다.
주소·요청 ID·반경·등록표를 확인하고 `run_graph()`로 실행합니다.

```text
prepare_address → run_analyses → evaluate_decision
                                ├─ 최종 결과 → 저장·종료
                                ├─ 필요한 보완 → 부분 작업 → 재판단
                                ├─ 지도 조회 → 관측 저장 → 재판단
                                └─ 질문 → SQLite 대기 → 답변 후 최종판단만 재개
```

- `workflow.py`: 주소 준비, 실제 분석 등록, 병렬 실행·공통 응답 검증.
- `graph.py`: 고정 순서와 선택 분기. `RunHooks`로 저장·관찰 콜백 전달.
- `tools.py`: 주소 도구 및 보완·지도 함수 계약.
- `supplement.py`: 등록된 부분 작업 실행·채택 검증.
- 순서 선택용 LLM·프롬프트는 없습니다. 모델은 최종판단과 필요한 지도 업종 매핑에만 사용합니다.
- 보완·지도는 각각 최대 1회, 질문은 최대 3개·1회입니다. 주소·반경을 임의 변경하지 않습니다.
- 질문 답변·판단 재시도는 저장된 자료를 복원해 `decision.evaluate()`를 직접 호출합니다.
- 실행 오류·계약 오류·DB 오류를 구분하며 잘못된 응답을 성공으로 바꾸지 않습니다.

## 실행

Python 3.12, backend 폴더 기준:

```powershell
python examples/run_orchestration.py --mock --offline --db storage/offline.sqlite3
python examples/run_orchestration.py --mock
```

첫 명령은 외부 호출 없는 대역입니다. 두 번째는 가상 주소·분석 자료로 실제 최종판단 LLM을 호출합니다.
실제 모델 호출에는 비용이 발생합니다. 가상 자료를 실서비스 입지 판단에 사용하지 않습니다.
