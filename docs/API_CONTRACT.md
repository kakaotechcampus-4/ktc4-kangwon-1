# API 계약 — 프론트엔드 ↔ 백엔드

**살아 있는 문서는 Swagger입니다.** 백엔드를 띄우고 <http://127.0.0.1:8000/docs>를 보세요.
이 문서는 그 위에서 합의한 약속과 화면이 알아야 할 사정을 적습니다.

## 서버 주소

| 환경 | 주소 |
| --- | --- |
| 로컬 백엔드 | `http://127.0.0.1:8000` |
| 로컬 프론트 | `http://localhost:3000` |

CORS는 `CORS_ALLOW_ORIGINS` 환경변수로 정합니다. 기본값이 `http://localhost:3000`이라
로컬 개발은 설정 없이 됩니다. 배포 주소가 생기면 쉼표로 이어 붙입니다.

## 엔드포인트

### `GET /health`, `GET /api/v1/health`

```json
{ "status": "ok" }
```

### `POST /api/v1/analyses`

주소 하나로 분석 전체를 돌립니다.

**요청**

```json
{ "address": "서울특별시 노원구 한글비석로 242 삼부프라자 1층" }
```

| 필드 | 형 | 설명 |
| --- | --- | --- |
| `address` | string (1~200자) | 상세주소가 붙어 있어도 됩니다. 서버가 떼어 냅니다 |

**질의 문자열**

| 이름 | 기본 | 설명 |
| --- | --- | --- |
| `mock` | `false` | `true`면 외부 API·모델을 부르지 않고 고정 응답을 돌려줍니다 |

**응답 200** — `DecisionResult`

```json
{
  "schema_version": "1.0",
  "agent_id": "decision",
  "request_id": "37cbeec60f8f409bb32164661eaa49eb",
  "address": "서울특별시 노원구 한글비석로 242 삼부프라자 1층",
  "status": "ok",
  "summary": "점심 직장인 수요가 뚜렷하고 커피·음료는 이미 포화에 가깝습니다.",
  "recommendations": [
    {
      "category": { "major": "음식점업", "middle": "한식 음식점업" },
      "score": 72,
      "reasons": ["직장인 비중이 41%로 점심 수요를 기대할 수 있습니다."],
      "evidence": [
        { "agent_id": "floating_population", "path": "/office_worker_share" },
        { "agent_id": "commercial_area", "path": "/by_middle/0" }
      ],
      "risks": ["점포 수가 이미 96개로 경쟁이 적지 않습니다."]
    }
  ],
  "not_recommended": [ "… 같은 형태" ],
  "limitations": ["목업 자료로 만든 결과입니다."],
  "source_analyses": [ "… 세 에이전트의 원본 분석" ]
}
```

## 화면이 알아야 할 것

**1. `status`는 세 가지입니다.**

| status | 화면 처리 |
| --- | --- |
| `ok` | 그대로 보여 줍니다 |
| `partial` | 결과를 보여 주되 `limitations`를 함께 노출합니다 |
| `no_data` | 추천 목록이 빕니다. `limitations`로 이유를 보여 줍니다 |

**2. `score`는 성공 확률이 아닙니다.**
0~100의 **적합성 판단 점수**입니다. "성공률 72%"처럼 보이지 않게 표기합니다.
숫자만 크게 띄우지 말고 옆에 근거(`reasons`)를 같이 놓습니다.

**3. `recommendations`와 `not_recommended`는 각각 최대 5개**입니다.
정렬은 서버가 합니다(추천은 점수 내림차순, 비추천은 오름차순).
1차 MVP 리포트는 앞의 3개(Top 3 / Worst 3)만 씁니다.

**4. `evidence.path`는 JSON Pointer입니다.**
`source_analyses`에서 같은 `agent_id`를 찾아 그 `data`를 그 경로로 따라가면 실제 숫자가 나옵니다.
"근거 보기"를 만들 때 씁니다.

**5. `source_analyses`는 큽니다.**
상권 에이전트 하나가 약 100KB입니다. 목록 화면에서는 받지 말고 상세에서만 씁니다.

**6. 응답이 느립니다.**
실제 호출은 공공데이터 API를 100회 넘게 부르고 모델도 부릅니다. 수십 초가 걸릴 수 있습니다.
화면에는 진행 표시가 필요하고, `fetch` 타임아웃을 넉넉히 잡아야 합니다.

## 오류

| 상태 | 언제 | 본문 |
| --- | --- | --- |
| 400 | 주소를 찾지 못함, 입력이 잘못됨 | `{"detail": "주소를 찾지 못했습니다: …"}` |
| 422 | 본문 형식이 틀림 (빈 주소 등) | FastAPI 기본 형식 |
| 502 | 외부 API·모델 실패 | `{"detail": "…"}` |

## 키 없이 화면 붙이기

백엔드 키가 아직 없어도 화면 작업은 막히지 않습니다.

```bash
cd backend
MOCK_MODE=1 .venv/Scripts/python -m uvicorn app.main:app --reload
```

또는 요청마다 `?mock=true`를 붙입니다. **목업도 진짜 오케스트레이터와 중재 에이전트를 그대로 지나가므로
응답 형태가 실제와 같습니다.** 좌표는 고정이고 `address`만 요청한 값이 돌아옵니다.

```ts
const res = await fetch('http://127.0.0.1:8000/api/v1/analyses?mock=true', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ address }),
});
const result: DecisionResult = await res.json();
```

## 타입을 옮길 때

`frontend/types/`에 손으로 옮겨 적지 말고, 가능하면 `openapi.json`에서 생성합니다.

```bash
curl http://127.0.0.1:8000/openapi.json -o openapi.json
```

손으로 옮긴다면 **`backend/app/schemas.py`가 원본**입니다. 그쪽이 바뀌면 같이 고칩니다.
