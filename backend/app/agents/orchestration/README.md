# 오케스트레이터

- `workflow.py`: 기존 고정 실행과 `run_react` 도구 호출 루프.
- `tools.py`: 도구 설명과 기존 주소 변환 진입점.
- `llm.py`: 엘리스 호환 모델에 메시지·도구 목록 전달.
- `prompt.md`: 역할, 실행 순서, 자료 해석 제한.

`run_react`는 주소 변환 함수와 세 분석 에이전트 등록표를 필수로 받습니다.
주소 준비 → 분석 병렬 실행 → 최종판단 순서를 코드가 검증합니다.
잘못된 도구 선택은 관찰 결과로 전달하고 최대 6회에서 종료합니다.
최종 결과는 오케스트레이터 LLM 문장이 아니라 최종판단의 `DecisionResult`입니다.
주소 변환·모델 연결·응답 검증 실패는 호출자에게 전달하며 성공으로 대체하지 않습니다.

## 실행

백엔드 폴더에서 Python 3.12로 실행합니다.

```powershell
python examples/run_orchestration.py --mock --offline
python examples/run_orchestration.py --mock
```

첫 명령은 모든 외부 호출이 없는 대역 실행입니다.
두 번째는 주소·세 분석 입력만 목업이며 오케스트레이터와 최종판단은 실제 LLM을 호출합니다.
`ELICE_MODEL`, `ELICE_API_KEY`, `ELICE_BASE_URL`과 기존 `LLM_MAX_TOKENS`,
`LLM_TIMEOUT_SECONDS`를 사용합니다. 선택 모델의 도구 호출 지원이 필요합니다.
실제 모델 사용에는 요금이 발생할 수 있습니다. 키와 실제 설정값을 공유하지 마세요.

카카오 API는 예제에 연결하지 않았으며 좌표는 가상 값입니다.
실서비스 연결 시 검증된 주소 변환 함수와 실제 분석 어댑터를 전달해야 합니다.
기존 HTTP API는 고정 흐름을 유지하며 ReAct로 자동 전환하지 않습니다.
부분 재요청은 최종판단의 보완 요청 계약을 정한 뒤 추가합니다.
현재 세 도구만 사용하는 제한된 실행 루프이며 임의의 계획·재조회는 지원하지 않습니다.

도구 호출 형식 참고: https://developers.openai.com/api/docs/guides/function-calling
