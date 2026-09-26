# 상권 경쟁 분석 에이전트 (commercial_area)

주소와 좌표를 받아 **반경 안에 어떤 업종의 점포가 몇 개 있는지** 계산해 결정 에이전트에 넘긴다.

업종을 추천하거나 판단하지 않는다. 숫자와 그 숫자를 풀어 쓴 문장만 만든다.

**점수를 주지 않는다.** 개폐업 에이전트는 `score` 0~100을 주지만 이 에이전트는 지표와 순위·비율만
낸다. 내보내는 지표가 전부 트레이드오프라 가중치를 정하는 순간 그게 판단이 되고, 판단은 결정
에이전트 몫이기 때문이다. **세 에이전트의 점수를 평균 내는 식의 합산은 성립하지 않는다** — 개폐업의
`score`는 "개폐업 안정성"이고 우리가 점수를 만들면 그건 "경쟁 강도"라 축이 다르다.

## 무엇을 계산하나

집적·경쟁 지표 11종을 요청 반경으로 계산한다. 세부 반경은 50·200·500m 중
요청 반경 이하의 값과 요청 반경 자체를 사용한다.

공통 진입점에서는 `AnalysisTask.radius_m`이 기준이다. `ANALYSIS_RADIUS_M`은
단독 실행 예제의 입력 기본값이며 서비스 요청을 덮어쓰지 않는다.
주변 LQ는 요청 반경보다 큰 비교 반경만 사용한다. 없으면 주변 LQ를 비우고 partial로 반환한다.
서울 음식점 백분위는 500m 표본이므로 다른 요청 반경에서는 null이다. 밀도 자체는 계산한다.

| 지표 | 필드 |
| --- | --- |
| 점포 수 | `store_total`, `by_major[].count`, `by_middle[].count` |
| 동종 / 이종 업체 수 | `by_middle[].same_type_count` / `diff_type_count` |
| 업종별 밀도 + 2차항 | `by_middle[].density_per_km2` / `density_sq` |
| 음식점 밀도 | `restaurant_density` (단위 `stores_per_km2`) |
| 업종 다양성 | `diversity.hhi_major` / `hhi_middle` / `effective_categories` |
| 반경 대비 특화도 | `by_middle[].lq` (분석 반경 비중 ÷ 반경 2km 비중) |
| 자치구 대비 특화도 | `by_middle[].lq_district`, `district_specialization` |
| 마샬리안 / 제이코비안 | `by_middle[].marshallian` / `jacobian` |
| 누적 유인 (Nelson 2원칙) | `by_middle[].major_cluster_count` / `major_cluster_diversity` |
| 프랜차이즈 / 개인사업자 비율 | `franchise` |
| 반경별 순위·해설 | `by_radius[]` |
| 사람이 읽는 요약 | `summary` |

업종은 소상공인 상권업종분류 **중분류 75종**을 쓴다. 결정 에이전트의 `category.middle`과 같은 단위다. 반경 안에 없는 업종도 0으로 채워 전달한다.

각 지표를 그렇게 정의한 논문 근거는 팀 문서 `부동산 agent/논문근거_경쟁지표.md`에 정리돼 있다.

### 특화도 기준선이 둘인 이유

`반경 2km`만 기준으로 쓰면 **자리를 옮길 때 잣대도 같이 움직여 지역 간 비교가 안 된다.**

| | 500m 음식 비중 | 반경 2km 대비 | 자치구 대비 |
| --- | --- | --- | --- |
| 테헤란로 (강남구) | 19.4% | 1.13 | 1.11 |
| 위례광장로 (송파구) | 28.8% | 1.14 | **0.92** |
| 가락동 (송파구) | 28.7% | 1.33 | **1.39** |

한식 음식점 기준이다. 위례광장로는 **반경 2km 안에서는 많아 보이지만(1.14) 송파구 전체로 보면 평균 이하(0.92)** 다. 가락동은 두 기준 모두 1을 넘어 실제 밀집지다. 절대 비중이 28.8% vs 28.7%로 거의 같은 두 곳의 성격이 이렇게 갈린다.

그래서 두 기준을 모두 내보낸다.

| 답하는 질문 | 필드 |
| --- | --- |
| 이 자리가 **자기 동네 안에서** 유별난가 | `lq` (반경 2km 대비) |
| 이 자리가 **자치구 기준으로** 유별난가 | `lq_district` |

자치구는 반경 조회 응답의 `signguCd`에서 알아내므로 주소를 다시 조회하지 않는다. **가장 가까운 점포 10개의 다수결**로 정하는데, 위례신도시처럼 여러 자치구에 걸친 곳에서 주변 점포 다수결을 쓰면 엉뚱한 자치구(성남시 수정구)가 잡히기 때문이다.

## 준비

파이썬 **3.12**가 필요하다. `pyproject.toml`이 `>=3.12,<3.13`으로 고정한다.

```bash
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

`backend/.env`에 아래 값을 넣는다.

| 변수 | 용도 | 없으면 |
| --- | --- | --- |
| `COMMERCIAL_AREA_API_KEY` | 소상공인 상가정보 (필수) | `status: error` |
| `FRANCHISE_API_KEY` | 공정위 브랜드 목록 | 프랜차이즈 지표 생략 + `partial` |
| `ELICE_API_KEY` / `ELICE_BASE_URL` / `ELICE_MODEL` | 요약 생성 | 요약 생략 |
| `GEOCODING_API_KEY` | 공통 주소 도구의 카카오 REST 키 | 주소 설정 오류 |
| `ANALYSIS_RADIUS_M` | 분석 반경 (기본 500) | 500m |

공공데이터 키 2개는 [공공데이터포털](https://www.data.go.kr) 계정의 **일반 인증키 하나**를 양쪽에 넣으면 된다. 단 API마다 활용신청을 따로 해야 한다.

| 신청할 API | 링크 |
| --- | --- |
| 소상공인시장진흥공단 상가(상권)정보 | [data.go.kr/data/15012005](https://www.data.go.kr/data/15012005/openapi.do) |
| 공정거래위원회 브랜드별 가맹점 현황 | [data.go.kr/data/15110241](https://www.data.go.kr/data/15110241/openapi.do) |

**엘리스 모델 이름에는 접두어가 붙는다.** `claude-sonnet-5`가 아니라 `anthropic/claude-sonnet-5`다. 접두어 없이 쓰면 `model_not_found`가 난다.

## 쓰는 법

```python
import asyncio

from app.agents.commercial_area import analyze

result = asyncio.run(
    analyze(
        {
            "request_id": "request-001",
            "site": {
                "input_address": "서울특별시 송파구 위례광장로 120 155호",
                "road_address": "서울특별시 송파구 위례광장로 120",
                "detail_address": "155호",
                "latitude": 37.4748,
                "longitude": 127.1416,
            },
        }
    )
)
```

`analyze`는 **코루틴**이다. 서버 안에서는 `await analyze(task)`로 부른다.
`store_client`를 넘기지 않으면 함수가 직접 만들고 끝날 때 닫는다.

`AgentAnalysis`를 돌려주므로 `result.model_dump()`를 그대로 `DecisionRequest.analyses`에 넣으면 된다.

## `data` 안에 무엇이 들어가고, 왜 그것인가

`data`는 계약상 자유 형식이지만 **소비 경로가 둘**이다. 최종 판단은 업종과 근거를 만들고,
프론트엔드는 SQLite에 저장된 `DecisionResult.source_analyses`를 POST/GET API로 받아 차트와 표를
만든다. 별도 report 에이전트는 없다. 그래서 판단용 지표와 화면용 원시 시리즈를 둘 다 담는다.

| 키 | 소비자 | 내용 |
| --- | --- | --- |
| `description` | **결정** | 맨 앞. 숫자의 기준과 단위를 문장으로. 결정 프롬프트가 "필드 이름, 설명, 단위와 실제 값을 함께 읽는다"로 동작해서 넣었다 |
| `radius_m` · `store_total` | 결정·화면 | 분석 반경과 그 안의 총 점포 수 |
| `data_reference_date` | 결정 | 자료 기준일 `"2026-03-31"`. **API 응답에 날짜 필드가 0개라** `sources.py` 상수에서 온다 |
| `by_major` | 화면 | 대분류 10종 집계. 상권 성격을 한눈에 보여주는 용도 |
| `by_middle` | **결정** | 중분류 75종 전수. LQ·집적·특화 지표가 전부 여기 있다 |
| `by_radius` | 화면 | 반경 50~500m 5단계 순위와 해설 문장 |
| `diversity` | 결정 | HHI와 유효 업종수 |
| `restaurant_density` | 결정 | 음식점 밀도 + 원시 개수 |
| `franchise` | 결정·화면 | 프랜차이즈·개인사업자 수와 비율, 업종별 내역, 브랜드 기준 연도 |
| `lq_baseline` · `district_baseline` | 결정 | 두 기준선이 **무엇이었는지**. 배수를 해석하려면 분모를 알아야 한다 |
| `district_specialization` | 결정·화면 | 자치구 대비 특화 상위 10 |
| `summary` · `summary_text` | 화면 | 모델이 쓴 사람 읽는 문장 |
| `sources` | 결정·화면 | 맨 뒤. 공공누리 출처표시 의무라 화면이 하드코딩하지 않게 함께 싣는다. **쓴 자료만 들어가므로 길이를 가정하지 않는다** |

**기준선 정보를 함께 싣는 이유.** `lq: 4.21`만 주면 무엇과 비교한 4.21인지 알 수 없다.
`lq_baseline.applied_radius_m`(실제 적용된 반경)과 `district_baseline.signgu_name`(자치구 이름)이
있어야 "반경 2,000m 대비", "노원구 대비"로 문장을 만들 수 있다. 요청한 반경이 거부되면
`requested_radius_m`과 `applied_radius_m`이 달라지므로 **적용값을 반드시 읽는다.**

지표 하나하나의 정의·수식·해석 방향은 [`docs/INDEX_commercial_area.md`](../../../../docs/INDEX_commercial_area.md)에 있다.

## 화면에 무엇을 싣고, 무엇을 실으면 안 되는가

프론트엔드는 저장된 최종 판단의 `source_analyses`로 이 `data`를 받는다. 전부 보여줄 것은 아니다.

### 실어도 되는 것

| 키 | 화면에서의 역할 | 노원 실제 값 |
| --- | --- | --- |
| `store_total` | 대표 숫자 | 1,237개 |
| `by_major[].count` | 대분류 구성 파이 차트 | 교육 530 · 음식 238 · 소매 158 |
| `by_radius[].store_total` | 반경별 증가 곡선 | 46 → 206 → 569 → 985 → 1,237 |
| `by_radius[].top_by_count` | 반경별 상위 업종 막대 | 50m 일반 교육기관 21개 |
| `by_radius[].explanations` | 차트 옆 설명 문장 | 이미 사람이 읽는 문장으로 되어 있다 |
| `district_specialization` | "이 동네에 유난히 많은 업종" | 일반 교육기관 5.8배 |
| `diversity.effective_categories` | 다양성 지표 | 7.14종 |
| `restaurant_density.value` + `store_count` | 음식점 밀집도 | 303.0개/km² (238개) |
| `franchise.count` · `ratio` | 프랜차이즈 비율 | 136개 (11.0%) |
| `franchise.independent_count` · `independent_ratio` | 개인사업자 비율 (도넛 반대쪽) | 1,101개 (89.0%) |
| `description` | 숫자를 읽는 법 | 반경·모수·단위·배수의 분모까지 한 문단 |
| `sources` | 출처 표기 (공공누리 의무) | 1~2행. 길이를 가정하지 말 것 |
| `summary_text` | AI 요약 영역 | 반경별 5줄 + 종합 + 집적·특화 |

### 실으면 안 되는 것

- **`by_middle` 75행 전부를 차트로 그리면 안 된다.** ⚠️ **가장 위험한 자리다.**
  0건 업종이 22개 섞여 있어 축을 잡아먹고, 상위 3종이 전체의 절반을 차지해 나머지가 안 보인다.
  상위 N개만 자르거나 `by_radius[].top_by_count`(이미 순위로 잘려 있다)를 쓴다.
- **`marshallian` · `jacobian` · `density_sq`** — 사용자에게 보여줄 이름이 아니다.
  프롬프트에도 "마샬리안, 제이코비안은 쓰지 않는다"로 막아 두었다. 판단용 내부 지표다.
- **`lq` 를 기준 없이 "3배"로 표시하면 안 된다.** `lq`와 `lq_district`는 분모가 다르다.
  반드시 "반경 2km 안에서" / "노원구 전체와 비교하면"을 붙인다.
- **`major_cluster_count` · `major_cluster_diversity`** — 누적 유인의 재료 두 개다.
  둘을 곱하거나 더한 값을 우리가 만들지 않았다. 가중치를 정하는 순간 그게 판단이 되기 때문이다.
- `data_reference_date`(`"2026-03-31"`)와 `scope.period`(`"2026년 1분기"`)는 **같은 시점인데
  형식이 다르다.** 나란히 놓고 "둘이 다르다"고 읽지 않는다.

### 같은 500m인데 순위가 다를 수 있는 이유

`by_middle`(반경 500m 전체 기준 정렬)과 `by_radius[4]`(500m 슬라이스)는 같은 반경인데 값이 다를 수
있다. `by_radius`는 API가 준 좌표로 거리를 다시 계산해 자르므로, 좌표가 없는 점포가 빠진다.
화면에서 둘을 나란히 놓을 때는 출처를 밝힌다.

## 키 이름이 인터페이스다

결정 에이전트가 근거를 JSON Pointer 경로(`Evidence.path`)로 가리킨다. **키를 바꾸면 그 경로가
깨진다.** 바꿀 때는 결정 에이전트 담당과 함께 바꾼다.

실제로 결정 에이전트가 만들어 낸 경로들이다(노원 실행).

```
/store_total                              → 1237
/diversity/effective_categories           → 7.1406
/restaurant_density/value                 → 303.031
/franchise/ratio                          → 0.1099
/by_middle/0                              → 일반 교육기관 417개 lq 4.21
/district_specialization/1                → 도서관·여가 서비스업 3.79배
/by_radius/4/top_by_specialization/0      → 500m 특화 1위
/lq_baseline/applied_radius_m             → 2000
/district_baseline/signgu_name            → 노원구
```

## 기준 시점을 갱신하는 곳

분기가 바뀌면 [`sources.py`](sources.py)의 **두 줄만** 고친다.

```python
SBIZ_PERIOD = "2026년 1분기"
SBIZ_REFERENCE_DATE = "2026-03-31"
```

`scope.period` · `data_reference_date` · `sources[].period` · `description` 이 함께 따라간다.
최신 분기는 [공공데이터포털 파일데이터](https://www.data.go.kr/data/15083033/fileData.do)에서 확인한다.
**오픈API 응답에는 날짜 필드가 하나도 없어 API로는 알 수 없다**(39개 필드 전수 확인).

공정위 연도는 [`config.py`](config.py)의 `ftc_year` 하나에서 `sources[].period` 와
`franchise.base_year` 가 함께 나온다. 브랜드 캐시 파일명(`ftc_brands_<연도>.json`)에도 연도가 들어가
있어, 연도를 올리면 지난 연도 목록이 새 연도 이름표를 달고 읽히는 일이 없다.

## 아직 출력에 없는 필드

넣을지 합의한 뒤 구현한다. 근거와 수식은
[`docs/INDEX_commercial_area.md`](../../../../docs/INDEX_commercial_area.md)의 "남은 것" 절에 있다.

| 필드 | 내용 | 막는 것 |
| --- | --- | --- |
| `trade_area_kind` | 골목상권 / 발달상권 구분 | 유동인구 모듈 의존. **서울 밖은 `null`** |
| `restaurant_density.seoul_percentile` | 서울 상권 밀도 분포 대비 백분위 | 분포 1회 산출 선행. 서울 밖은 `null` |

## 터미널에서 확인

```bash
cd backend
python examples/run_commercial_area.py --address "서울특별시 송파구 위례광장로 120 155호"
python examples/run_commercial_area.py --lat 37.4748 --lon 127.1416 --out examples/commercial_area/response.json
```

좌표를 주지 않으면 공통 `app/address.py`가 카카오 주소 검색의 단일 후보를 검증한다. 상세주소(`155호`, `3층 302호`)는 검색에서 제외하고 `site.detail_address`에 보존한다. 지역·번지가 불명확하거나 후보가 여러 개면 주소를 확정하지 않는다.

출력 예시는 `examples/commercial_area/response.json`에 있다.

```
  50m : 점포 59개. 기타 간이 음식점업이 9개로 1위이며 반경 안에서 보면 약 2.7배 많습니다.
 100m : 점포 67개. 기타 간이 음식점업이 11개로 1위이며 반경 안에서 보면 약 2.9배 많습니다.
 200m : 점포 119개. 기타 간이 음식점업이 22개로 1위이고, 중식 음식점업은 반경 안에서 보면 약 5.9배로 가장 두드러집니다.
 300m : 점포 580개. 이용 및 미용업이 72개로 1위로 바뀌고, 도서관·여가 관련 서비스업이 반경 안에서 약 2.8배로 눈에 띕니다.
 500m : 점포 1241개. 이용 및 미용업이 123개로 1위를 유지하며, 기타 보건업이 반경 안에서 약 3.5배로 가장 두드러집니다.
```

두 기준선을 구분해 말한다.

> 이 자리는 여러 업종이 비교적 고르게 섞여 있어 한쪽으로 심하게 쏠린 상권은 아닙니다. 다만 기준을 다르게 보면 차이가 있는데, 기타 보건업은 반경 500m 안에서는 약 3.5배로 많이 보이지만 송파구 전체와 비교해도 약 3.2배로 비슷하게 많은 편입니다. 반대로 서양식 음식점업은 200m 반경 안에서는 약 4.3배로 눈에 띄지만 송파구 전체와 비교하면 약 1.8배 정도로 평범한 수준이니, 좁은 범위에서만 두드러진 업종이라는 점을 알아두시면 좋습니다.

## 업종 코드 마스터

반경 안에 **없는 업종까지 0으로 채우려면** 중분류 75종 목록이 필요하다. 이 목록은 팀 공통 업종
어휘가 되면서 [`app/industries/data/industries.csv`](../../industries/README.md)로 옮겨졌다.
LQ·HHI·부재 업종 수의 분모가 이 75칸이라, 다른 체계로 바꾸면 값이 통째로 달라진다.

갱신하려면 [상권업종분류 코드](https://www.data.go.kr/data/15067631/fileData.do)를 받아 아래를 실행한다.

```bash
python examples/build_upjong_master.py --official-csv <받은파일.csv>
python examples/build_industry_links.py --force    # has_seoul·note 를 다시 채운다
python scripts/build_industry_catalog.py          # catalog.py 재생성
```

**세 줄을 같이 돌려야 한다.** 첫 줄이 마스터를 4개 컬럼으로만 다시 쓰기 때문에 `has_seoul`·`note`가
사라지고, 그대로 두면 `build_industry_catalog.py` 검증이 실패한다.

원본 파일 인코딩이 CP949다. 스크립트가 자동으로 처리한다.

## 반경 상한 확인

```bash
python examples/probe_radius.py
```

소상공인 API가 몇 m까지 받는지 공개돼 있지 않다. 실측으로 2,000m까지 되는 것을 확인했다.

## status 규칙

| status | 언제 | `data` |
| --- | --- | --- |
| `ok` | 반경 조회 성공 + 지표 전부 계산 | 있음 |
| `partial` | 반경 2km 기준선 실패, 자치구 기준선 실패, 프랜차이즈 실패, 업종 마스터 없음, 페이지 상한 초과 중 하나 | 있음 |
| `no_data` | 조회는 됐으나 반경 내 점포 0건 | 비어 있음 |
| `error` | 인증 실패·타임아웃·파싱 실패 | 비어 있음 |

`partial`이어도 `data`는 채워진다. 왜 partial인지는 항상 `warnings`에 적힌다.

## 알아둘 제약

- **모든 외부 호출은 비동기다.** 첫 페이지에서 전체 건수를 확인한 뒤 나머지 페이지를 동시에 받아온다.
  동시 요청 수는 `SBIZ_MAX_CONCURRENCY`(기본 4)로 제한한다. 쿼터와 429 때문이다.
- **API 쿼터가 하루 10,000건이다.** 같은 좌표 요청은 `backend/cache/`에 저장해 재사용한다. 강남 500m는 1회 분석에 5페이지, LQ용 2km는 48페이지가 나간다. LQ 기준 조회는 좌표를 250m 격자로 반올림해 같은 동네끼리 캐시를 공유한다.
- **반경 3개를 위해 API를 3번 부르지 않는다.** 500m 한 번 받아 좌표로 안쪽 반경을 직접 계산한다. API 실측값과 오차 0~2건으로 일치하는 것을 확인했다.
- **프랜차이즈 판정은 정확하지 않다.** 공정위 API에 반경 검색이 없어 브랜드명과 상호명을 문자열로 대조한다. 누락과 오탐이 있어 `confidence: "low"`로 표시한다.
- **`scope.period`는 조회일이다.** 소상공인 API가 원천 기준 분기를 응답에 담지 않는다. 세 에이전트의 `scope` 표기가 다르면 결정 에이전트가 "기준 기간이 다르다"는 한계를 자동으로 붙이므로 형식을 맞춰야 한다.
- **특화도는 점포 5개 미만 업종을 제외한다.** 표본이 1~2개면 배수가 튀어 순위가 무의미해진다. 두 기준선 모두에 같은 하한을 적용한다.
- **자치구 조회는 한 번에 35~67페이지가 나간다.** 송파구 34,860건, 강남구 66,269건이다. 자치구 자료는 분기 단위라 캐시를 90일 유지한다(`district_cache_ttl_hours`). 자치구 조회에 실패해도 분석은 계속되고 `lq_district`만 `None`이 된다.
- **서울 전체 기준선은 아직 없다.** 서울시 상권분석서비스는 생활밀접업종 100종만 다뤄 컨설팅·법무·회계가 빠지므로 기준선으로 쓸 수 없다. 넣는다면 소상공인 분기 CSV로 만들어야 한다.
- **모델 요약이 실패해도 전체는 실패하지 않는다.** `summary`가 비고 `warnings`에 사유가 남는다. 숫자가 본체다.
- **좌표 정확도가 결과를 바꾼다.** 지번 주소는 번지를 못 찾고 동 중심점으로 잡히는 경우가 있어 50~100m 결과가 흔들린다. `GEOCODING_API_KEY`에 카카오 REST 키를 넣으면 도로명·지번 모두 정확해진다.

## 테스트

```bash
cd backend
python -m unittest discover -s tests
```

네트워크 없이 돈다. 가짜 응답으로 계약 형식, status 전이, 모델 응답 파싱, 주소 분리,
자치구 기준선 계산과 캐시 재사용을 검증한다. 주소부터 중재까지 이어지는 통합 시험은
`tests/test_orchestrator_e2e.py`에 있다.

## 데이터 출처

상가(상권)정보 — 소상공인시장진흥공단 (2026), data.go.kr
가맹정보 — 공정거래위원회 (2026), data.go.kr

공공누리 및 이용허락범위 제한없음 데이터는 **출처표시가 의무**다. 리포트와 화면에 위 문구를 넣는다.
