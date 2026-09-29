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
| `radius_m` | 양의 정수, 기본 500 | 공통 요청 반경. 실제 분석 범위는 각 결과의 scope로 확인 |
| `allow_questions` | boolean, 기본 false | 임대인에게 선택적으로 질문할 수 있도록 허용 |
| `with_map` | boolean, 기본 false | 필요할 때 카카오맵 조회 허용. 항상 실행하지는 않음 |

기존 주소만 보내는 요청은 유지됩니다. 반경에 문자열·소수·boolean·0을 보내면 422입니다.
실제 실행에는 등록된 분석 보완 도구를 전달합니다. 보완 요청 여부는 최종판단이 결정합니다.

**질의 문자열**

| 이름 | 기본 | 설명 |
| --- | --- | --- |
| `mock` | `false` | `true`면 외부 API·모델을 부르지 않고 고정 응답을 돌려줍니다 |

**응답 200** — `DecisionResult`

질문을 허용한 요청은 DecisionResult 대신 다음 WaitingForInput을 반환할 수 있습니다.
HTTP 요청은 이때 종료되며 서버는 답변이 올 때까지 연결을 붙잡지 않습니다.

```json
{
  "status": "waiting_for_input",
  "request_id": "요청 ID",
  "question_set_id": "질문 묶음 ID",
  "questions": [{
    "field": "floor",
    "text": "공실은 몇 층인가요?",
    "why_needed": "접근 조건을 확인해야 합니다.",
    "expected_impact": "보행 접근성이 중요한 후보의 판단에 반영합니다."
  }]
}
```

이 객체가 별도 리포트 단계를 거치지 않는 최종 판단 결과입니다. 응답 헤더 `X-Request-ID`로
같은 실행의 저장 상태를 조회할 수 있으며, 브라우저에서도 읽을 수 있도록 CORS에 노출합니다.

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
      "category": { "code": "I201", "major": "음식점업", "middle": "한식 음식점업" },
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

### `GET /api/v1/analyses/{request_id}`

새 최종판단의 `category`는 공통 업종 `code`와 기존 `major`·`middle`을 함께 제공합니다.
모델 입력은 코드만 사용할 수 있고 서버가 공식명을 채웁니다. 이름을 함께 보내면 코드와 일치해야 합니다.
코드 없는 과거 저장 결과도 조회할 수 있습니다. 요청 당시 업종표 버전이 현재와 다르거나
기록되지 않은 요청은 질문 재개·최종판단 재시도 대신 새 분석이 필요합니다.

POST의 `X-Request-ID`로 저장된 실행을 조회합니다. `status`는
`pending` / `running` / `waiting_for_input` / `completed` / `failed`이며 `site`, `result`, `error`는 JSON 객체 또는 null입니다.
과거 저장 결과의 업종명은 현재 75업종 규칙으로 다시 검증하거나 변환하지 않습니다.

추가 조회 필드:

| 필드 | 의미 |
| --- | --- |
| `questions` | 저장된 WaitingForInput 또는 null. 완료 뒤에도 질문 이력으로 남음 |
| `analyses` | `{attempt, analysis}` 목록. analysis는 AgentAnalysis 원본 |
| `supplements` | 분석 보완 이벤트 목록 |
| `map_status` | 지도 조회의 running / completed 또는 null |
| `map_observation` | 저장된 지도 관측 또는 null. 진행 중에는 null |

질문 입력창은 **요청 status가 waiting_for_input일 때만** 표시합니다.
요청 상태 completed와 최종 결과의 ok / partial / no_data는 서로 다른 상태입니다.

### `POST /api/v1/analyses/{request_id}/answers`

```json
{
  "request_id": "요청 ID",
  "question_set_id": "질문 묶음 ID",
  "answers": [{"field": "floor", "status": "answered", "value": "1층"}]
}
```

- 답변 상태는 answered / unknown / skipped. answered만 value가 필요합니다.
- `answers: []`는 전부 건너뛰기입니다. 미제출 항목도 skipped로 처리됩니다.
- 경로와 본문의 요청 ID가 다르면 422, 요청이 없으면 404입니다.
- 질문 ID·항목 불일치, 이미 제출한 답변 변경, 처리 중·실패한 재개는 409입니다.
- 같은 답변을 완료 후 재전송하면 저장된 최종 결과를 반환합니다.
- 응답 200은 DecisionResult. 기존 자료로 최종판단만 재개하며 재조회하지 않습니다.
- 대역 실행에서 시작했다면 답변에도 `?mock=true`를 유지하세요. 요청 간 실행 모드를 바꾸지 마세요.

지도 관측은 최종 결과의 `map_observation`에도 포함됩니다. map_analysis 근거 경로는
이 객체의 data 안에서 해석하며, 기본 세 분석 source_analyses와 구분합니다.

POST는 기본(`wait=true`)으로 실행 완료 또는 질문 대기까지 기다립니다.
진행 화면이 필요하면 아래 [비동기 실행과 진행 이벤트](#비동기-실행과-진행-이벤트)를 씁니다.

## 비동기 실행과 진행 이벤트

진행 중 화면(주소 확인 → 세 분석 → 전문가 → 판정 …)을 보여 줄 때 쓰는 흐름입니다. 폴링 방식이며 새 연결 방식(SSE·웹소켓)은 없습니다.

```text
POST /api/v1/analyses?wait=false        → 202 {request_id, status:"running"}
GET  /api/v1/analyses/{id}/events?after=0 → 1초마다 반복, next_after를 다음 after로
     finished=true가 되면 멈춤
GET  /api/v1/analyses/{id}              → 결과(completed) · 질문(waiting_for_input) · 오류(failed)
POST /api/v1/analyses/{id}/answers?wait=false → 202, 다시 events 폴링
```

`?mock=true`와 함께 쓰면 외부 호출 없이 같은 이벤트가 나옵니다. 중간 페이지는 이것으로 먼저 만듭니다.

### `GET /api/v1/analyses/{request_id}/events?after=N`

```json
{
  "request_id": "5f0c...",
  "status": "running",
  "finished": false,
  "events": [
    { "seq": 1, "at": "2026-09-30T02:10:01+00:00", "stage": "address", "event": "started", "detail": {} },
    { "seq": 2, "at": "2026-09-30T02:10:01+00:00", "stage": "address", "event": "completed",
      "detail": { "road_address": "서울 송파구 오금로 404" } }
  ],
  "next_after": 2
}
```

- `status`: `pending`(202 직후 아직 저장 전) · `running` · `waiting_for_input` · `completed` · `failed`.
- `finished`가 true면 폴링을 멈춥니다. 답변 재개 직후처럼 DB 상태가 바뀌기 전이어도 작업이 살아 있으면 `running`, `finished=false`입니다.
- `seq`는 요청마다 1부터 빈틈없이 늘어납니다. 받은 마지막 `seq`를 `after`로 넘기면 새 이벤트만 옵니다.

| stage | event | detail | 화면 문구 예 |
| --- | --- | --- | --- |
| `address` | started · completed | `road_address` | 주소를 확인하고 있어요 |
| `floating_population` · `business_lifecycle` · `commercial_area` | started · completed | `status`(ok·partial·no_data·error) | 유동인구 / 개폐업 / 주변 상권을 계산하고 있어요 |
| `brief.{전문가}` | started · completed | `source`(model·fallback), `findings` 수 | 인구 전문가가 자료를 요약하고 있어요 (multi_agent만) |
| `decision` | started · completed | `action`: final · ask_specialists · supplement · map_lookup · ask_user | 판정관이 종합하고 있어요 |
| `consult.{전문가}` | started · completed | `round`, `question`(300자 이내), `status`, `tools`(사용한 도구 이름) | 판정관이 상권 전문가에게 되묻고 있어요 (multi_agent만) |
| `supplement` | started · completed | `agents` | 부족한 자료를 다시 조회하고 있어요 |
| `map` | started · completed | `queries` 수, `status` | 주변 가게를 지도에서 찾고 있어요 |
| `questions` | waiting | `count` | 임대인 질문 화면으로 이동 |
| `run` | completed · failed | `status` 또는 `code` | 완료 / 실패 |

- 전문가 이름: `floating_population`, `business_lifecycle`, `commercial_area`, `map_analysis`.
- 세 분석은 동시에 돌기 때문에 started 셋이 먼저 오고 completed는 끝난 순서대로 옵니다.
- `decision`은 여러 번 올 수 있습니다(되묻기·보완 뒤 재판단). 마지막 `action`이 `final`이면 곧 `run completed`가 옵니다.
- detail에는 코드가 만든 요약만 있습니다. 모델 원문·근거 경로·키는 없습니다. 결과 화면 자료는 GET으로 받습니다.
- 이벤트는 진행 표시용입니다. 이벤트 저장에 실패해도 분석은 계속되므로, 최종 상태는 항상 GET 결과를 기준으로 합니다.

```ts
async function follow(id: string, onEvent: (e: AnalysisEvent) => void) {
  let after = 0;
  for (;;) {
    const page = await fetch(`${API}/api/v1/analyses/${id}/events?after=${after}`).then(r => r.json());
    page.events.forEach(onEvent);
    after = page.next_after;
    if (page.finished) return page.status; // completed | failed | waiting_for_input
    await new Promise(r => setTimeout(r, 1000));
  }
}
```

**제한과 오류**

- 서버 한 대에서 백그라운드 분석은 동시에 `ANALYSIS_MAX_CONCURRENCY`개(기본 2)까지입니다. 넘으면 **429** + `Retry-After: 30`.
- 서버가 다시 시작되면 끊긴 실행 중 요청은 `failed`, `error.code = "INTERRUPTED"`가 됩니다. 같은 주소로 다시 요청합니다.
- 작업표는 서버 프로세스 메모리에 있습니다. 서버를 여러 대 띄우는 배포에서는 외부 큐가 필요합니다.

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
진행 화면은 `wait=false`와 events 폴링을 씁니다. 기다리는 방식을 쓴다면 `fetch` 타임아웃을 넉넉히 잡습니다.

## 오류

| 상태 | 언제 | 본문 |
| --- | --- | --- |
| 400 | 주소를 찾지 못함, 여러 후보, 입력 오류 | `{"detail": "주소를 확인해 주세요."}` |
| 422 | 본문 형식이 틀림 (빈 주소 등) | FastAPI 기본 형식 |
| 404 | GET 요청 ID가 없음 | `{"detail": "분석 요청을 찾을 수 없습니다."}` |
| 409 | 질문 상태·답변 충돌 | 고정된 안전 메시지 |
| 429 | `wait=false` 동시 실행 상한 초과 | `{"detail": "동시에 실행할 수 있는 분석 수를 넘었습니다. …"}` |
| 502 | 주소·외부 API·모델 실패 | 고정된 안전 메시지 |
| 500 | 결과 계약·저장 또는 저장 결과 조회 실패 | 고정된 안전 메시지 |

POST가 요청 ID를 만든 뒤 처리한 오류 응답에도 `X-Request-ID`가 있습니다. 본문 검증 422와
공백 주소 400처럼 저장 시작 전 실패에는 조회할 행이 없습니다. 키·외부 URL·원문 예외는 반환하지 않습니다.

## 키 없이 화면 붙이기

백엔드 키가 아직 없어도 화면 작업은 막히지 않습니다.

```bash
cd backend
MOCK_MODE=1 .venv/Scripts/python -m uvicorn app.main:create_app --factory --reload
```

또는 요청마다 `?mock=true`를 붙입니다. **목업도 진짜 오케스트레이터와 최종판단 에이전트를 그대로 지나가므로
응답 형태가 실제와 같습니다.** 좌표는 고정이고 `address`만 요청한 값이 돌아옵니다.

대역에서 with_map을 켜면 외부 호출 없는 0건 지도 관측을 만들고,
allow_questions를 켜면 층수 질문을 고정 반환합니다. 이는 흐름 검증용이며 추천 품질 시험이 아닙니다.

현재 API에는 사용자 인증·요청 소유권 검사가 없습니다. 이 변경을 공개 서비스 배포 준비 완료로
보면 안 됩니다. 외부 공개 전 인증·권한·호출량 제한과 목업 옵션 정책을 별도 적용해야 합니다.

```ts
const res = await fetch('http://127.0.0.1:8000/api/v1/analyses?mock=true', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ address }),
});
const result: DecisionResult = await res.json();
```

## 실패한 최종판단 재시도

`GET /api/v1/analyses/{request_id}`의 `completed_at`을 확인한 뒤 호출합니다.

```http
POST /api/v1/analyses/{request_id}/retry-decision
Content-Type: application/json

{"failed_at": "조회에서 받은 completed_at"}
```

- 저장된 분석·채택된 보완·지도 관측·제출 답변으로 **최종판단만** 실행합니다.
- 분석 API는 다시 호출하지 않습니다. 실제 모드에서는 최종판단 LLM 비용이 발생합니다.
- 상태나 실패 시각이 바뀌었거나 저장 입력이 불완전하면 `409`입니다. 중복 실행하지 않습니다.
- 근거 검증은 동일합니다. 자동 교정은 한 번이며, 다시 실패하면 사용자 재시도가 필요합니다.
- 조회의 `decision_failures`에 실패 시각·오류·잘못된 경로·실제 경로 후보를 보존합니다.
  후보는 문자열 유사도로 제시할 뿐 업종·의미 일치를 보증하지 않습니다.
- 과거 실패는 모델 경로가 저장되지 않아 진단 목록이 비어 있을 수 있습니다.
- 대역 실행은 재시도에도 `?mock=true`를 유지하세요. 기존 API와 동일하게 인증 적용 전에는 외부 공개하지 않습니다.

## 타입을 옮길 때

`frontend/types/`에 손으로 옮겨 적지 말고, 가능하면 `openapi.json`에서 생성합니다.

```bash
curl http://127.0.0.1:8000/openapi.json -o openapi.json
```

손으로 옮긴다면 **`backend/app/schemas.py`가 원본**입니다. 그쪽이 바뀌면 같이 고칩니다.
## 멀티에이전트 모드 추가 계약

서버 설정 `ANALYSIS_MODE=multi_agent`에서만 사용합니다. 기본값은 `single_decision`입니다.
`AnalysisTask`, `AgentAnalysis`, `DecisionResult` 필드는 변경하지 않았습니다.
POST 주소 분석·답변·최종판단 재시도 경로와 기존 응답 형태도 유지합니다.

### 내부 메시지

| 모델 | 주요 필드 | 제약 |
| --- | --- | --- |
| `AgentBrief` | 요청·전문가 ID, `source`, `headline`, `findings`, `limitations`, `tool_calls` | 초기 3개 전문가, 근거 최대 8개 |
| `Finding` | `claim`, `signal`, `industry_code`, `evidence[].path` | 공통 75개 코드, 자기 원자료 경로만 인용 |
| `ConsultPlan` | `action=ask_specialists`, `queries` | 라운드당 서로 다른 전문가 최대 3명 |
| `SpecialistQuery` | 전문가, 질문, 업종 코드, 필요 이유·판단 영향 | 임의 주소·반경 변경 불가 |
| `SpecialistAnswer` | 요청·라운드·질문, 상태, 근거, 도구 이력, 선택형 분석·지도 관측 | 최대 2라운드, 근거 최대 5개 |
| `QuestionSnapshotV2` | 기존 task·질문·분석 차수 + 브리핑 ID·라운드·지도 차수·소비 예산·활성 시간 | 기존 v1 대기 자료도 재개 가능 |

전문가 문장은 최종 근거가 아닙니다. 원자료 경로·소유 업종·직접 수치를 재검증합니다.
문장의 의미·사업 적합성까지 자동 보증하지 않습니다. 폐업률 단위·기간·공간 범위는 원자료를 유지합니다.

### 저장과 조회

`GET /api/v1/analyses/{request_id}`에는 `analysis_mode`가 추가됩니다.
멀티 모드에만 선택형 `deliberation`이 포함됩니다.

| 필드 | 내용 |
| --- | --- |
| `briefs` | 최초 전문가 브리핑과 fallback 여부 |
| `answers` | 라운드별 질문·답변·도구 실행 상태. 원본 분석·지도 중복 본문은 제외 |
| `consult_round` | 소비한 되묻기 라운드 |
| `map_attempt` | 최신 채택 지도 차수 |
| `budget.used`, `budget.calls` | 실제 모델 요청 시도 누계, 역할·성공 여부·입출력 토큰·입력 문자 수·시간 |
| `elapsed_seconds` | 사람 답변 대기를 제외한 활성 실행 누계 |

모델이 usage를 주지 않으면 토큰은 `null`입니다. 대역은 실제 전송이 없어 호출 누계가 0입니다.
최종 `source_analyses`와 지도 관측은 채택된 원자료입니다. 새 관측을 거절해도 이력은 남습니다.
질문 후 환경변수가 달라져도 저장한 모드·도구 등록 범위·예산으로 이어갑니다.
최종판단 재시도는 저장 자료만 쓰며 전문가·데이터 API는 재호출하지 않습니다.

### DB 추가·변경

| 테이블 | 키·추가 컬럼 | 의미 |
| --- | --- | --- |
| `analysis_requests` | `analysis_mode`, `execution_json` | 실행 모드, 소비 예산·활성 시간·등록 도구 범위 |
| `agent_briefs` | PK `(request_id, agent_id)`, `brief_json`, `created_at` | 최초 브리핑, 덮어쓰기 금지 |
| `specialist_consults` | PK `(request_id, round, agent_id)`, `status`, `answer_json`, `created_at` | 라운드별 전문가 답변 |
| `map_observations` | PK `(request_id, attempt)`, `adopted` | 반복 관측과 채택 이력. 최종 결과는 최신 채택 관측 |
| `supplement_events` | `analysis_attempt` | 이벤트의 분석 이력 차수. 결과 없는 시도는 NULL |

기존 DB는 명시적 초기화 때 마이그레이션합니다. 기존 요청은 단일판정 모드,
기존 지도 행은 1차로 보존합니다. 보완은 원본 이력과 대조 가능한 차수만 복원합니다.
호출 예산 초과는 `LLM_BUDGET_EXHAUSTED`로 실패하며 유효하지 않은 판정을 성공으로 만들지 않습니다.
