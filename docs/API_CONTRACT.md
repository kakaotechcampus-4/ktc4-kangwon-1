# API 계약 — 단일 decision 도구 루프

공개 API는 로컬 자료 조회·코드 채점 → decision → 평가자 네 명 → 최종 보고서 순서로 실행한다.
프론트는 아래 새 DecisionResult를 기준으로 화면을 연결한다. 옛 추천 목록·agent/path 근거·
브리핑·재시도 엔드포인트는 제공하지 않는다. 숫자는 fact 슬롯을 서버가 렌더링한다.

| 엔드포인트 | 입력·응답 |
| --- | --- |
| GET /health, /api/v1/health | 상태 확인 |
| POST /api/v1/analyses?wait=false | address(최대 200자), radius_m(기본 500), allow_questions(기본 false), with_map. HTTP 202 request_id·status |
| POST /api/v1/analyses?wait=true | 최종 DecisionResult 또는 waiting_for_input. 기본 wait=true |
| GET /api/v1/analyses/{id} | 진행 상태, 대기 질문 또는 최종 DecisionResult·rendered |
| GET /api/v1/analyses/{id}/events?after=N | after 다음 순번의 이벤트. 클라이언트가 seq를 보존하여 중복 표시를 피한다 |
| POST /api/v1/analyses/{id}/answers | question_session_id와 answers 객체. 저장된 질문 field와 정확히 같은 항목, 값은 비어 있지 않은 문자열·최대 500자 |

질문 대기는 request_id, status=waiting_for_input, question_session_id, questions로 표현한다.

POST wait=false는 요청 행을 pending으로 저장한 뒤202를 반환한다. 동시 작업 슬롯은 저장 전에
확보하며 상한 초과는429이고 요청 행을 만들지 않는다. 202의 status는 pending이다.
접수된 ID의 GET은 pending/running/waiting_for_input/completed/failed 상태를200으로 반환한다.
자료가 아직 없으면 site/result/error/rendered/questions는 null이다. 미존재 ID만404다.
답변 뒤 같은 요청 ID로 재개하며 자료 버전·모델 예산·이전 대화를 유지한다.
wait=false 작업은 이벤트와 GET으로 확인한다. 헤더 X-Request-ID를 오류 추적에 쓴다.

| 오류 | 의미 |
| --- | --- |
| 400 | 주소 변환 오류 |
| 404 | 요청 없음 |
| 409 | 답변 세션 불일치·이미 처리·동시 작업 충돌 |
| 422 | 입력 스키마·답변 항목 검증 오류 |
| 502 | 외부 서비스·실행 실패 |
| 500 | 내부 오류 |
| 429 | 동시 작업 수용 상한 또는 종료 중 |

평가자는 항상 네 슬롯이다. 실패 슬롯도 유지하며 평가 미완료를 표시한다.
프론트 담당은 rendered 문장, 검토 후보 Top 5, 코드·L 점수와 구간·coverage,
배지, 확인 조건, 평가 상태를 새 계약에 맞춰 표시한다. 옛 결과 DB를 읽는 호환 경로는 없다.
규제 조회 함수는 유지하고 check_regulation 도구로만 읽는다.

키 없이 확인할 때 MOCK_MODE=true 또는 ?mock=true를 쓴다. 실데이터·유료 호출은 발생하지 않는다.
측정·녹화는 서버 실행 인자로만 켜며 공개 HTTP 입력으로 제어하지 않는다.


## 새 결과 형태(PR7 전환 후)

현재 문서의 기존 결과·질문·stage 계약은 **PR7 전환 전까지 유효**합니다. PR1은 실행 경로를 연결하지 않습니다. PR1~PR6에는 새 계약을 `backend/app/agentic/contracts.py`에 두고, PR7에서 DecisionRequest·DecisionResult·Evidence·QuestionSnapshot을 `schemas.py`로 옮겨 교체합니다. V2 접미사는 쓰지 않습니다.

전환 후 GET `/api/v1/analyses/{id}`의 `result`는 다음 DecisionResult입니다. URL과 status/site/result/error envelope는 유지합니다. 구 결과·질문 세션은 DB 초기화로 폐기하며 변환/reader는 제공하지 않습니다. 다음 값은 실제 주소 분석이 아닌 목업이고, 평가자 전체 실패 시에도 평가 미완료를 표시해 검증된 결과를 제공하는 예입니다.

```json
{
  "schema_version": "2.0",
  "rubric_version": "v0.8",
  "tool_contract_version": "3",
  "request_id": "request-demo",
  "run_id": "run-demo",
  "report_id": "report-demo",
  "snapshot_id": "snapshot-demo",
  "score_snapshot_id": "scores-demo",
  "summary_segments": [
    {
      "type": "text",
      "text": "검토 후보와 확인 조건을 함께 제시합니다."
    }
  ],
  "top5": [
    {
      "industry_code": "I201",
      "industry_name": "한식 음식점업",
      "code_points": 50.0,
      "L_points": null,
      "L_status": "unknown",
      "A": 65.0,
      "B": 50.0,
      "H": 60.0,
      "lower_ratio": 0.7692307692307693,
      "upper_ratio": 0.9230769230769231,
      "coverage": 0.8461538461538461,
      "demand_coverage": 1.0,
      "competition_coverage": 1.0,
      "G": "해당 없음",
      "badge": "추천",
      "confirmation_conditions": [
        "판단 미확인",
        "건축물 용도 확인 필요"
      ],
      "reasons_segments": [
        {
          "type": "text",
          "text": "주변 동종 점포 밀도는 "
        },
        {
          "type": "fact",
          "fact_id": "f_12345678-1234-4234-8234-123456789abc",
          "format": "rate"
        },
        {
          "type": "text",
          "text": "입니다."
        }
      ],
      "risks_segments": [],
      "confirmation_conditions_segments": [
        {
          "type": "text",
          "text": "건축물 용도는 별도 확인합니다."
        }
      ],
      "fact_ids": [
        "f_12345678-1234-4234-8234-123456789abc"
      ],
      "review_state": "unreviewed"
    }
  ],
  "excluded_candidates": [],
  "facts": [
    {
      "fact_id": "f_12345678-1234-4234-8234-123456789abc",
      "source": "commercial_area",
      "metric": "density_per_km2",
      "value": 10.0,
      "unit": "개/km²",
      "period": "2026Q2",
      "spatial_scope": {
        "radius_m": 500
      },
      "industry_code": "I201",
      "status": "observed",
      "citable": true,
      "calc_version": "demo-1",
      "provenance_ref": "raw-demo"
    }
  ],
  "L_records": [
    {
      "industry_code": "G202",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 1,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G203",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 2,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G204",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 3,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G205",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 4,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G208",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 5,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G209",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 6,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G210",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 7,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G211",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 8,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G213",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 9,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G215",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 10,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G215B",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 11,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G216",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 12,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G217",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 13,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G218",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 14,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G219",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 15,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G220",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 16,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "G222",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 17,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "I101",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 18,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "I102",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 19,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "I201",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 20,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "I202",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 21,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "I203",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 22,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "I204",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 23,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "I207",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 24,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "I210",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 25,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "I211",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 26,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "I212",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 27,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "L102",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 28,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "M103",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 29,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "M104",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 30,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "M107",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 31,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "M111",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 32,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "M113",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 33,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "M114",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 34,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "N102",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 35,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "N105",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 36,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "N109",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 37,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "N110",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 38,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "P105",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 39,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "Q102",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 40,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "R102",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 41,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "R103",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 42,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "R104",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 43,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "S201",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 44,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "S202",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 45,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "S203",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 46,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "S204",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 47,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "S205",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 48,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "S207",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 49,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "S208",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 50,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    },
    {
      "industry_code": "S209",
      "selection": {
        "basis": "all_industries",
        "code_score_snapshot_id": "scores-demo",
        "code_lower_rank": 51,
        "reason": "전체 업종 동일 검토"
      },
      "review_state": "unreviewed",
      "status": "unknown",
      "grade": null,
      "limitations": [
        "판단 미제출"
      ]
    }
  ],
  "evaluator_reviews": [
    {
      "actor": "examiner",
      "status": "failed",
      "review_id": null,
      "verdict": null,
      "issues": [],
      "error_code": "TIMEOUT"
    },
    {
      "actor": "founder",
      "status": "failed",
      "review_id": null,
      "verdict": null,
      "issues": [],
      "error_code": "TIMEOUT"
    },
    {
      "actor": "customer",
      "status": "failed",
      "review_id": null,
      "verdict": null,
      "issues": [],
      "error_code": "TIMEOUT"
    },
    {
      "actor": "landlord_advocate",
      "status": "failed",
      "review_id": null,
      "verdict": null,
      "issues": [],
      "error_code": "TIMEOUT"
    }
  ],
  "review_completeness": 0.0,
  "review_resolutions": [],
  "confirmation_conditions_segments": [
    {
      "type": "text",
      "text": "실제 영업 전 건축물 용도를 확인해야 합니다."
    }
  ],
  "limitations_segments": [
    {
      "type": "text",
      "text": "평가 미완료: 이 예시는 평가자 전체 실패와 판단 미확인을 보여 주는 목업입니다."
    }
  ]
}
```

| 필드 | 의미 |
| --- | --- |
| schema_version / rubric_version / tool_contract_version | 결과 2.0·채점표 v0.8·도구 계약 3. 모델 이름에 V2를 붙이지 않음 |
| request_id / run_id / report_id / snapshot_id / score_snapshot_id | 요청·실행·보고서·원문·채택 점수의 참조 |
| top5 / excluded_candidates | 최대 5개 후보/제외 항목. Top 5는 금지 제외·B 내림차순→coverage→코드 정렬, 부족하면 미충원 |
| code_points / L_points / L_status | 코드 기여점수 최대90·판단 최대10. L 미확인은 null이며 0점이 아님 |
| A / B / H | 적용 배점(n.a. 제외·unknown 포함)·하한·상한 |
| lower_ratio / upper_ratio / coverage | B/A·H/A·observed 배점/A. A=0이면 null. D/C 묶음 coverage는 별도 제공 |
| G / badge | 규제 금지/조건부/해당 없음/unknown, 추천/조건부/보류/비추천. 규제 금지는 점수로 상쇄 불가 |
| *_segments / facts | text 또는 fact_id 슬롯. 숫자는 facts 레지스트리 값·단위로 렌더링. `{i}`·agent/path 인용 없음 |
| L_records / review_state | 전체 51업종의 새 근거·질문·도구·자문 기록. 최대51·최종은 정확히51개, unknown에는 개별 이유. basis=all_industries |
| evaluator_reviews / review_completeness | 항상 4명 실행. completed 수/4, 실패는 동의로 간주하지 않음 |
| review_resolutions | 지적별 수용·일부·기각과 근거/이유 |
| confirmation_conditions_segments / limitations_segments | 영업 전 확인 조건·시점/공간/예산/평가 한계. 건축물 용도는 확인 조건 |

### 진행 이벤트 stage 변경

| 단계 | stage·event | detail |
| --- | --- | --- |
| 주소·로컬 자료 | address / local_data started·completed | 고정 자료 버전·자료 기간 |
| 계산·채점 | local_data completed | 조회·코드 점수 저장 완료 |
| 판정 | decision completed | tool·status |
| 필수 평가 | evaluation started·completed | 네 평가자 상태·완료 수 |
| 질문·종료 | question waiting / final started·completed·failed | 질문 세션·feedback_round·평가 완료 여부 |

seq 폴링을 유지합니다. 프론트 리포트·진행 화면은 이 단일 경로의 결과와 이벤트로 연결합니다. 키·SQL·원문·fact 값은 이벤트에 넣지 않습니다.

### 도구 function 정의의 내보내기

도구 계약3은 열 개 function이다. 행별 L 근거를 제출하여 종료한 뒤
보고서 후보 최대5개를 별도 submit_draft로 낸다. 평가자는 세 읽기 도구+submit_review만 받는다.

도구 계약3: submit_l은 업종·factors(fact_id 별칭/direction/severe)·neutral/fact_ids·note만 받는다.
등급·상태는 서버가 계산하며 묶음 상한 없이 행별로 채택·거절한다. 중복 업종은 무시한다.
응답에는 accepted/ignored/rejected(이유·수정법)/unsubmitted가 있다. 기존 최종 L_records 형태는 유지한다.
모델 경계의 fact 별칭은 요청별8자이며 DB·GET의 fact_id는 기존 불변ID다.
없는 별칭은 해당 L 행 또는 보고서 인용 문장만 제외하고 알림을 반환한다.
평가자 입력은 Top5·후보 L요인·등급 분포·한계·핵심 fact의 약6k토큰 검토 패킷이다.
지적 근거는 최대5개이며 제출 오류는 추가 두 번 수정할 수 있다.
G·C4는 채점 전 코드가 관측한다. 외부 실패는 해당 항목만 unknown으로 남긴다.
현재 구현 순서·공통 공간 fact·측정 예산은 [단순 L 계획](simple-l-input-plan.md)을 따른다.
아래 내보내기 규칙은 계약3에서도 유지한다.

`tool_definitions()`는 Chat Completions의 `{type:"function", function:{name,description,parameters,strict:false}}` 10개를 반환합니다. Pydantic `$defs/$ref`를 로컬로 펼치고 title/default/discriminator를 제거하며, discriminator의 oneOf를 anyOf로 바꿉니다. enum·pattern·길이·개수·숫자 상한·additionalProperties:false는 유지합니다. optional 필드와 params 자유형 때문에 공급자의 엄격 스키마 모드를 강제하지 않습니다.

get_facts/map_search의 배타 조건·상세 limit·L/평가 정합성은 Pydantic 경계에서 검증합니다. 이는 엘리스 OpenAI 호환 **요청 형태의 로컬 검증**이며 공급자가 모든 JSON Schema 키워드를 지원한다는 실호출 증명이 아닙니다. 이번 PR에서는 API·LLM 호출을 하지 않습니다. SQL 내용/권한/시간·fact 소유/숫자 슬롯·점수 재계산·정렬의 실제 검증은 PR4~PR6 범위입니다.

ReportProposal에는 review_resolutions를 두지 않습니다. 제출 입력 SubmitDraftInput에만 두며 서버가 채택한 반영 기록은 최종 DecisionResult.review_resolutions로 제공합니다.
