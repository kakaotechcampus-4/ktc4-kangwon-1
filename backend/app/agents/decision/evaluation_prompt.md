## 평가 반영 단계
evaluation.draft는 당신이 앞서 쓴 초안이고, evaluation.evaluations는 평가자 의견입니다
(examiner 심사자 · founder 예비 창업자 · customer 동네 손님 · landlord_advocate 임대인 대변인).
- 평가는 자료가 아니라 의견입니다. 지적이 가리킨 원자료 값을 직접 확인한 뒤 판단하세요.
- 평가자 단위가 아니라 지적 하나하나를 따로 판단합니다. 같은 평가자의 지적도 하나는 반영하고 하나는 버릴 수 있습니다.
- 한 지적 안에서도 원자료로 확인된 부분만 반영할 수 있습니다(일부 반영).
- 원자료로 뒷받침되지 않는 부분, 다른 업종을 가리키는 부분은 버립니다.
- 평가자끼리 부딪치면 원자료가 더 직접 뒷받침하는 쪽을 따르고, 남는 위험은 risks에 적습니다.
- 지적의 request가 허용된 행동이면 최종판단 전에 그 행동을 먼저 요청할 수 있습니다.
- 평가 문장을 근거(evidence)로 인용하지 마세요. 근거는 지금처럼 원자료 경로만 씁니다.
- 최종판단 JSON에 evaluation_log 배열을 추가합니다. 모든 지적마다 정확히 한 항목을 쓰고,
  evaluator와 index는 evaluation.evaluations에 적힌 값을 그대로 씁니다.
  decision: accepted(전부 반영) · partial(일부 반영) · rejected(반영 안 함)
  applied: 반영한 부분(accepted·partial) · dropped: 버린 부분(partial·rejected) · reason: 짧은 이유
  임대인 화면에 그대로 보이므로 쉬운 말로 씁니다.
