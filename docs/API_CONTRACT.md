# API 계약 — 단일 decision 도구 루프

공개 API는 로컬 자료 조회·코드 채점 → decision → 평가자 네 명 → 최종 보고서 순서로 실행한다.
프론트는 아래 새 DecisionResult를 기준으로 화면을 연결한다. 옛 추천 목록·agent/path 근거·
브리핑·재시도 엔드포인트는 제공하지 않는다. 숫자는 fact 슬롯을 서버가 렌더링한다.

| 엔드포인트 | 입력·응답 |
| --- | --- |
| GET /health, /api/v1/health | 상태 확인 |
| POST /api/v1/analyses?wait=false | address(최대 200자), radius_m(기본 500), allow_questions(기본 false), with_map, 선택 floor("4층"·"지하 1층")·exclusive_area_m2(0.01~100000). HTTP 202 request_id·status |
| POST /api/v1/analyses?wait=true | 최종 DecisionResult 또는 waiting_for_input. 기본 wait=true |
| GET /api/v1/analyses/{id} | 진행 상태, 대기 질문 또는 최종 DecisionResult·rendered |
| GET /api/v1/analyses/{id}/events?after=N | after 다음 순번의 이벤트. 클라이언트가 seq를 보존하여 중복 표시를 피한다 |
| GET /api/v1/analyses/{id}/facts | 리포트 차트용 요청 스냅샷 전체 fact. request_id·snapshot_id·facts(FactView 목록). 스냅샷 전에는 snapshot_id=null·빈 목록, 미존재 ID는 404 |
| POST /api/v1/analyses/{id}/answers | question_session_id와 answers 객체. 저장된 질문 field와 정확히 같은 항목, 값은 비어 있지 않은 문자열·최대 500자 |
| GET /api/v1/building-registry?address= | 상가 정보 확인 화면용 건축물대장 조회. 저장하지 않음. 아래 "건축물대장 조회" 참고 |

**인증이 필요한 엔드포인트** (아래 "인증" 절):

| 엔드포인트 | 요구 |
| --- | --- |
| POST /api/v1/analyses | 로그인 + 이메일 확인 |
| POST /api/v1/analyses/{id}/answers | 로그인 + 이메일 확인 + 소유자 |
| GET /api/v1/analyses/{id}, /events, /facts | 소유자 |
| GET /api/v1/building-registry | 로그인 |
| GET /health, /api/v1/health | 없음(공개) |

질문 대기는 request_id, status=waiting_for_input, question_session_id, questions로 표현한다.

floor·exclusive_area_m2는 상가 정보 확인 화면에서 확정한 층·전용면적이다. 보내면 분석 시작 때
source=user·unit="확인 화면 확정값" fact로 저장해 공간 비교(space_fit)에 바로 반영하고,
decision 첫 입력의 confirmed_space(values·fact_ids)로 전달한다. 형식이 틀리면 422다. exclusive_area_m2는 JSON 숫자만 받는다(문자열·불리언은 422). 이 두 필드는 extra="forbid" 요청 모델에 새로 생겼으므로 백엔드를 화면보다 먼저 배포한다(옛 백엔드는 floor를 받으면 422).

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
DecisionResult.facts는 보고서가 인용한 fact만 담는다. 유동인구·경쟁·개폐업 차트처럼 인용과 무관하게
지표 전체가 필요한 화면은 facts 엔드포인트를 쓴다. 상태가 unknown·not_applicable인 fact는 값이 null이다.
공간 비교(space_fit)는 현재 판정만 포함한다.
규제 조회 함수는 유지하고 check_regulation 도구로만 읽는다.

키 없이 확인할 때 MOCK_MODE=true 또는 ?mock=true를 쓴다. 실데이터·유료 호출은 발생하지 않는다.
측정·녹화는 서버 실행 인자로만 켜며 공개 HTTP 입력으로 제어하지 않는다.


## 인증 — 회원가입·로그인

세션은 **백엔드가 발급하는 쿠키**다. 토큰은 불투명 난수이며 서버에는 sha256 해시만 둔다.
프론트는 모든 호출에 `credentials: 'include'` 를 붙인다.

```
Set-Cookie: chaeum_session=<난수>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=1209600
```

`SameSite=Lax` 라 **프론트와 백엔드가 같은 사이트여야 한다.** 다른 사이트면 Safari 가
서드파티 쿠키로 보고 막아 로그인이 유지되지 않는다. 운영은 `app.`/`api.` 서브도메인으로 모은다.

| 엔드포인트 | 입력·응답 |
| --- | --- |
| POST /api/v1/auth/signup | email·password(10자 이상)·display_name. 201 `{user_id, verification_sent}`. 세션 쿠키를 함께 내려준다 |
| POST /api/v1/auth/login | email·password. 200 `{status}`. 실패 401, 시도 과다 429 |
| POST /api/v1/auth/logout | 세션 폐기. 200 |
| GET /api/v1/auth/me | `{user_id, email, display_name, profile_image_url, email_verified, needs_verification, created_at}`. 비로그인 401 |
| DELETE /api/v1/auth/me | 탈퇴. 200 |
| POST /api/v1/auth/verify-email | `{token}`. 만료·재사용 400 |
| POST /api/v1/auth/verification/resend | 로그인 필요. `{verification_sent}` |
| POST /api/v1/auth/password/forgot | `{email}`. **계정 유무와 무관하게 항상 200** |
| POST /api/v1/auth/password/reset | `{token, new_password}`. 성공 시 그 사용자의 **모든 세션을 끊는다** |
| GET /api/v1/auth/kakao/login?next= | 카카오 동의 화면으로 302 |
| GET /api/v1/auth/kakao/callback | 세션 쿠키를 심고 `FRONTEND_BASE_URL + next` 로 302 |
| GET /api/v1/me/analyses?limit&offset | 내 분석 기록. `{items, total, limit, offset}` |

**메일 확인과 분석 실행.** 이메일로 가입한 계정은 확인 전까지 분석을 시작할 수 없다(403).
로그인 자체는 되므로 화면은 "인증 메일 다시 보내기"를 띄운다.
카카오로 들어온 계정은 비밀번호가 없어 확인을 요구하지 않는다.

**카카오 콜백은 실패해도 JSON 을 돌려주지 않는다.** 브라우저 최상위 이동이라 전부 302다.

| 상황 | 이동 |
| --- | --- |
| 사용자가 동의 취소 | `/login?error=cancelled` |
| state 만료·재사용 | `/login?error=expired` |
| 토큰 교환·프로필 거절 | `/login?error=failed` |
| 카카오 장애·설정 누락 | `/login?error=unavailable` |

`next` 는 `/` 로 시작하는 내부 경로만 받는다. 그 외에는 `/` 로 바꾼다(오픈 리다이렉트 차단).
메일 토큰은 쿼리스트링이 아니라 **본문**으로 받는다. access 로그에 토큰이 남지 않게 하기 위함이다.

| 인증 오류 | 의미 |
| --- | --- |
| 401 | 로그인 필요, 또는 세션 만료 |
| 403 | 이메일 미확인, 또는 허용되지 않은 Origin |
| 404 | 남의 요청 조회(존재 여부를 숨긴다. 403 이 아니다) |
| 409 | 이미 가입된 이메일 |
| 422 | 이메일 형식·비밀번호 길이 |
| 429 | 로그인 시도 과다(최근 15분 실패 5회) |

**쓰기 요청은 `Origin` 헤더를 본다.** 쿠키 인증이라 CORS 만으로는 모자란다
(CORSMiddleware 는 브라우저에 알려줄 뿐 요청을 막지 않는다). 헤더가 없으면 거절이 기본이고,
카카오 콜백만 예외다(최상위 이동이라 Origin 이 없고, state 1회용 소비가 대신 막는다).

**배포 순서.** 보호가 걸리는 백엔드를 프론트보다 먼저 배포한다. 반대로 하면 화면이 로그인을
보내지 못해 분석이 전부 401 이 된다.

## 건축물대장 조회 — `GET /api/v1/building-registry`

상가 정보 확인 화면(`/building-confirm`)이 건축물대장 값을 채울 때 씁니다. 분석 요청과 별개이며 결과를 저장하지 않습니다.
건축HUB 건축물대장정보 서비스의 표제부·층별개요·전유공용면적·오수정화시설 네 항목을 한 번에 조회합니다.

**질의 문자열**

| 이름 | 기본 | 설명 |
| --- | --- | --- |
| `address` | 필수 (1~200자) | 건물 주소. `4층` 같은 상세주소가 붙어 있어도 됩니다. 서버가 떼어 냅니다 |
| `mock` | `false` | `true`면 외부 API를 부르지 않고 고정 응답(성희프라자)을 돌려줍니다 |

**응답 200** — 아래는 `?mock=true` 응답입니다. 성희프라자 실호출 응답에서 행 일부만 옮겼습니다(층별개요 19행 중 5행, 호실 83개 중 3개).

```json
{
  "road_address": "서울 송파구 위례광장로 199",
  "jibun_address": "서울 송파구 장지동 880-1",
  "titles": [{
    "dong_name": null,
    "building_name": "성희프라자",
    "main_use": "제2종근린생활시설",
    "ground_floors": 7,
    "underground_floors": 2,
    "total_area_m2": 12301.78,
    "parking_spaces": 82
  }],
  "floors": [
    { "dong_name": null, "floor": "지하 1층", "use": "기타제2종근린생활시설", "use_detail": "지하주차장/MDF실/방재센터", "area_m2": 1925.34 },
    { "dong_name": null, "floor": "4층", "use": "일반음식점", "use_detail": "제2종근린생활시설", "area_m2": 275.49 },
    { "dong_name": null, "floor": "4층", "use": "의원", "use_detail": "제1종근린생활시설", "area_m2": 498.12 },
    { "dong_name": null, "floor": "4층", "use": "사무소", "use_detail": "업무시설", "area_m2": 220.8 },
    { "dong_name": null, "floor": "4층", "use": "학원", "use_detail": "교육연구시설", "area_m2": 252.59 }
  ],
  "units": [
    { "dong_name": null, "unit_name": "401호", "floor": "4층", "use": "학원", "use_detail": "교육연구시설(학원)", "area_m2": 100.8 },
    { "dong_name": null, "unit_name": "404호", "floor": "4층", "use": "의원", "use_detail": "제1종근린생활시설(의원)", "area_m2": 93.6 },
    { "dong_name": null, "unit_name": "410호", "floor": "4층", "use": "일반음식점", "use_detail": "제2종근린생활시설(일반음식점)", "area_m2": 57.04 }
  ],
  "sewage": [{ "method": "하수종말처리장 연결", "method_name": "하수종말처리장연결" }]
}
```

| 항목 | 필드 | 설명 |
| --- | --- | --- |
| `titles` (표제부) | `building_name`, `main_use`, `ground_floors`, `underground_floors`, `total_area_m2`, `parking_spaces`, `dong_name` | 건물마다 한 행. 연면적이 큰 건물부터 보냅니다. `parking_spaces`는 옥내·옥외 기계식·자주식 주차 대수의 합 |
| `floors` (층별개요) | `floor`, `use`, `use_detail`, `area_m2`, `dong_name` | 한 층에 용도가 여럿이면 여러 행. `use`는 세부 용도(예: 일반음식점), `use_detail`은 대장의 기타용도 원문(예: 제2종근린생활시설) |
| `units` (호실) | `unit_name`, `floor`, `use`, `use_detail`, `area_m2`, `dong_name` | 전유 부분만 호수별로 더한 전용면적. 공용 면적은 뺍니다. 일반건축물은 호실이 없어 `[]`입니다 |
| `sewage` (오수정화시설) | `method`, `method_name` | `method`는 화면 선택지(`하수종말처리장 연결`·`정화조`·`오수처리시설`)로 맞춘 값, 맞출 수 없으면 null. `method_name`은 대장 원문(예: 부패탱크방법, 접촉폭기방법) |

- 목록이 `null`이면 그 항목 조회가 실패한 것이고, `[]`이면 대장에 등록된 행이 없는 것입니다. 네 항목 모두 실패하면 502이며, 대표 오류가 호출 한도 초과이면 429입니다.
- 각 항목은 페이지를 순차 조회합니다. 호실 조회가 30쪽으로 끝나지 않으면 부분 목록을 반환하지 않고 `units=null`로 처리하며, 정상 조회된 표제부·층별개요·오수정화시설은 유지합니다.
- 주소의 지역·번지가 카카오 반환 주소와 일치하지 않으면 허브를 호출하지 않고 400을 반환합니다.
- 확인 화면에서 확정한 층·전용면적은 분석 중 질문 후보에서 제외하며, 모델이 재질문을 시도해도 질문 세션을 만들지 않습니다. 미확인 설비 질문과 기존 공간 판정 규칙은 유지합니다.
- 건축HUB 게이트웨이의 일시 오류(503·빈 응답·시간 초과)는 항목마다 두 번까지 다시 요청합니다. 보통 1초 안에 끝나고, 막히면 최대 30여 초 걸립니다.
- 지하층은 건축HUB의 `지1층`을 화면 표기 `지하 1층`으로 바꿔 보냅니다. 지상층은 `4층`입니다.
- 대장에 비어 있는 값(건물명 등)은 `null`입니다. 오수 형식이 비어 있는 행은 보내지 않습니다.
- `접촉폭기방법`·`살수여상방법`처럼 처리 방식 이름만 있으면 정화조인지 오수처리시설인지 정할 수 없어 `method`가 null입니다.

**화면 연결** — `frontend/lib/api/building.ts`의 `BuildingInfo`를 이렇게 채웁니다.

| BuildingInfo | 응답 |
| --- | --- |
| `address` | `road_address` |
| `buildingName` | `titles[0].building_name` |
| `mainUse` | `titles[0].main_use` |
| `totalAreaM2` | `titles[0].total_area_m2` |
| `floors` | `ground_floors`로 `지상 7층`처럼 만들고, 지하가 있으면 `underground_floors`로 ` · 지하 2층`을 붙입니다 |
| `floorUse` | `floors`에서 `floor`가 입력 층과 같은 행의 `use`. 여러 행이면 겹치지 않게 이어 붙입니다(예: `일반음식점 · 의원 · 사무소 · 학원`) |
| `exclusiveAreaM2` | `units`에서 같은 층 행. 입력에 호수가 있으면 `unit_name`으로 찾고, 그 층 호실이 하나뿐이면 그 `area_m2`. 못 정하면 null로 두고 사용자가 적습니다 |
| `parking` | `parking_spaces`가 1 이상이면 `'possible'`. 0이거나 null이면 지금처럼 사용자가 고릅니다 |
| `facility` | `main_use`로 기존 `facilityFromMainUse` 그대로 |
| `sewage` | `sewage`에서 `method`가 있는 첫 값. 없으면 사용자가 고릅니다 |

- 조회 진행 표시(`LookupId`)는 `title`↔`titles`, `floor`↔`floors`, `exclusiveArea`↔`units`, `sewage`↔`sewage`입니다. 값이 `null`이면 `failed`, 아니면 `done`입니다.
- 입력 층은 `normalizeFloor`로 `4층`·`지하 1층` 모양으로 맞춘 뒤(`지1층`·`B1층`은 `지하 1층`, `-1층`·`1.5층`·`중1층`은 읽지 않음) 공백을 빼고 비교합니다. 층을 읽을 수 없으면 층 용도·전용면적은 비워 둡니다.
- 한 지번에 건물이 여럿이면 `titles`가 여러 행입니다(예: 인사동 대일빌딩 옆 단독주택). 입력에 동 이름("상가동"·"B동")이 있으면 같은 `dong_name`의 표제부를 고르고 층·호실도 그 동 행만 씁니다. 동이 여럿인데 맞는 동을 못 찾으면 층 용도·전용면적은 비웁니다.
- 프론트 목업의 `전용 275.49㎡`는 4층 층별개요 중 일반음식점 행의 면적입니다. 호실 하나의 전용면적이 아닙니다.

**오류**

| 상태 | 언제 | 본문 |
| --- | --- | --- |
| 400 | 주소를 찾지 못함, 여러 후보 | `{"detail": "주소를 확인해 주세요."}` |
| 422 | `address`가 없거나 200자 초과 | FastAPI 기본 형식 |
| 502 | 주소 조회 실패 | `{"detail": "주소 조회 서비스에 실패했습니다."}` |
| 502 | 네 항목 모두 실패, 건축HUB 키 미설정 | `{"detail": "건축물대장 조회에 실패했습니다."}` |
| 502 | 건축HUB 인증·권한 오류로 전체 실패 | `{"detail": "건축물대장 인증키 또는 사용 권한을 확인해 주세요."}` |
| 429 | 건축HUB 호출 한도 오류로 전체 실패 | `{"detail": "건축물대장 조회 한도를 초과했습니다."}` |

실제 조회에는 `.env`의 `BUILDING_REGISTRY_API_KEY`(공공데이터포털 「국토교통부_건축HUB_건축물대장정보 서비스」 활용신청 후 받은 일반 인증키,
Encoding·Decoding 두 개가 보이면 Decoding)와 주소 검색용 `GEOCODING_API_KEY`가 필요합니다.

MOCK_MODE 또는 `?mock=true`면 외부 호출 없이 주소와 상관없이 성희프라자 고정 응답을 돌려줍니다.


## 현재 결과 형태

공개 결과는 `backend/app/schemas.py`의 DecisionResult, 도구 계약은 `backend/app/agentic/contracts.py`를 따릅니다. 현재 `schema_version=2.0`, `rubric_version=v0.8`, `tool_contract_version=3`입니다. 과거 전환 계획의 계약 버전은 이력 문서에 남깁니다.

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

도구 계약3은 decision용 9개와 평가자 제출용 `submit_review` 1개를 정의한다. 행별 L 근거를 제출하여 종료한 뒤
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

get_facts/map_search의 배타 조건·상세 limit는 Pydantic 경계에서 검증합니다. 이는 엘리스 OpenAI 호환 **요청 형태의 로컬 검증**이며 공급자가 모든 JSON Schema 키워드를 지원한다는 실호출 증명이 아닙니다. SQL 권한·시간은 `sql_tool.py`, fact 소유·숫자 슬롯·L 정합성과 점수 재계산은 `report.py`에서 별도로 검증합니다.

ReportProposal에는 review_resolutions를 두지 않습니다. 제출 입력 SubmitDraftInput에만 두며 서버가 채택한 반영 기록은 최종 DecisionResult.review_resolutions로 제공합니다.
