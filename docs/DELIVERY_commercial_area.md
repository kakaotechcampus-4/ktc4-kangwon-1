# 경쟁업체 — 리포트 노출 지표와 전달 데이터

담당 최용빈(BE) · 기준일 2026-09-14 · PR #7까지 `develop` 반영 완료
예시 값은 **서울특별시 노원구 한글비석로 242 / 반경 500m** 실제 출력입니다.

> **2026-09-14 변경:** `description` · `sources` · `franchise.independent_*` · `franchise.base_year` ·
> `by_middle[].major_cluster_*`가 추가됐고 기준 시점 표기가 바뀌었습니다(§10). 전부 **필드 추가**라
> 기존에 읽던 경로는 그대로입니다. 팀 공용 `app/schemas.py`는 건드리지 않았습니다.

> **전달 경로:** 프론트는 이 `data`를 직접 읽지 않습니다. 결정 에이전트가 `source_analyses`에 실어 보내고
> **리포트 에이전트가 받아 화면용으로 가공**합니다. 경로 표기는 RFC 6901 JSON Pointer라
> 결정 에이전트의 `evidence.path`에도 그대로 씁니다.

> **이 에이전트는 점수를 주지 않습니다.** 개폐업 에이전트는 `score` 0~100을 주지만 우리는
> 지표와 순위·비율만 냅니다. 내보내는 지표가 전부 트레이드오프라 가중치를 정하는 순간 그게
> 판단이 되기 때문입니다. **세 에이전트의 점수를 평균 내는 합산은 성립하지 않습니다.**

지표별 정의·수식·논문 근거는 [`INDEX_commercial_area.md`](INDEX_commercial_area.md)에 있습니다.

```
점포 1,237개 · 업종 53종(중분류 75종 중 22종 0건) · 자치구 노원구(15,686개) · 기준선 2km(8,555개)
```

---

## 0. 회의 요구 대비 현황

회의 §7 "경쟁업체 (용빈 제공)" 항목 기준입니다.

| 회의 요구 | 상태 | 실제 제공 | 비고 |
| --- | --- | --- | --- |
| 반경별 점포 수 | 🟢 **완료** | `by_radius[]` **3단계**(50·200·500m) | 순위 4종 + 해설 문장. §4 참고 |
| LQ 지수 | 🟢 **완료** | `lq` + `lq_district` **2종** | 기준선이 둘 |
| HHI | 🟢 **완료** | `diversity.hhi_major` · `hhi_middle` | |
| 유효업종수 | 🟢 **완료** | `diversity.effective_categories` | 1 ÷ HHI |
| 마샬리안 | 🟢 **완료** | `by_middle[].marshallian` | 동종 밀도 |
| 제이코비안 | 🟢 **완료** | `by_middle[].jacobian` | 이종 다양성 |
| 음식점 밀도 | 🟢 **완료** | `restaurant_density` | 원시 개수 동봉 |
| 프랜차이즈 비율 | 🟢 **완료** | `franchise` | **`confidence: "low"`** |
| 개인사업자 비율 | 🟢 **완료** | `franchise.independent_count` · `independent_ratio` | 명시 필드로 나갑니다 |
| U자 임계값 | 🟢 **대체 완료** | `density_sq` + `restaurant_density.seoul_percentile` | 서울 상권 1,650곳 분포 대비 0~100 |
| 상권 유형 구분 | 🟢 **완료** | `trade_areas[]` | 골목·발달·전통시장·관광특구. **서울 밖은 빈 배열** |
| 누적 유인 | 🟢 **완료** | `by_middle[].major_cluster_count` · `major_cluster_diversity` | 원본값 2개. **합성 점수 없음** |

### 🟢 개인사업자 비율 — 명시 필드로 나갑니다

```
independent_count = store_total − franchise.count = 1,237 − 136 = 1,101
independent_ratio = 0.8901
```

FE가 뺄셈하지 않아도 됩니다. 서울시 리포트처럼 "프랜차이즈 vs 일반점포" 도넛을 바로 그릴 수 있습니다.
`count + independent_count == store_total`이 항상 성립합니다(시험으로 고정).

### 🟢 U자 임계값 — 백분위로 대체했습니다

논문 임계값(발달 2.96 / 골목 4.31)을 못 쓰는 이유가 셋입니다.

1. **단위 미확인** — 개/ha로 환산하면 노원 음식점이 3.03으로 2.96에 아주 가깝지만 원문 없이는 추측
2. **분모가 다름** — 논문은 **상권 폴리곤 면적**, 우리는 **반경 500m 원**(78.5ha). 원은 도로·주거·공원을
   포함해 밀도가 체계적으로 낮게 나옵니다. 단위를 맞춰도 어디를 찍든 "임계값 아래"가 나옵니다
3. **검증 불가** — 임계값은 **폐업 밀도**를 종속변수로 한 회귀식의 꼭짓점인데, 폐업 자료는 개폐업 파트

→ 절대 임계값 대신 **서울 상권 분포에서의 백분위**를 싣습니다(`restaurant_density.seoul_percentile`).
폐업 자료가 필요 없고, 추정이 아니라 관측 분포 자체라 틀릴 여지가 없습니다.
유동인구의 `scale_percentile`과 같은 방식입니다. **U자 형태 자체는 `density_sq`로 계속 전달합니다.**

**분포는 우리 분모로 만들었습니다.** 서울 상권 1,650곳 중심좌표에 우리와 똑같이 반경 500m 원을
씌워 음식점을 셌습니다. 상권 폴리곤 면적(중앙값 약 0.07km²)으로 만들면 우리 분모(0.7854km²)와
10배 넘게 달라 **어디를 찍든 최하위**가 나오기 때문입니다 — 위 2번이 백분위에서 그대로 재현됩니다.

⚠️ 서울 상권 분포라 **서울 밖은 `null`** 입니다.

### 🟢 상권 유형 구분 — `trade_areas`로 나갑니다

B2 논문이 요구한 발달/골목 구분입니다. **같은 LQ 값의 의미가 상권 유형에 따라 뒤집히기 때문에**
중요합니다 — B2 결론이 "특화(LQ 높음)는 발달상권에서 생존 위험을 높인다"입니다.

서울시 상권영역 1,650곳(골목 1,090 · 전통시장 305 · 발달 249 · 관광특구 6)을 **패키지에 동봉**해
런타임에는 서울시 API를 부르지 않습니다.

```json
"trade_areas": [
  {"code": "3001495", "name": "삼성역", "kind": "발달상권", "signgu": "강남구",
   "distance_m": 16.4, "area_m2": 183880.0, "equivalent_radius_m": 241.9}
]
```

**하나로 줄이지 않고 걸린 것을 전부 냅니다.** 영역 API가 폴리곤을 주지 않아 상권을 같은 면적의
원으로 근사하는데, 그 상태로 하나를 고르면 접경지에서 한 끗 차로 유형이 뒤집힙니다.

⚠️ 서울시 자료라 **서울 밖은 빈 배열**입니다. 서울 안이어도 위례처럼 상권 목록에 없는 신도시는
빈 배열이 나옵니다.

---

## 1. 지표 해석 방향 (화살표 표시용)

회의에서 "화살표(높으면 좋음/낮으면 좋음)" 표시를 합의했는데,
**경쟁업체 지표는 방향을 정할 수 있는 게 하나도 없습니다.**

| 지표 | 방향 | 이유 |
| --- | --- | --- |
| `lq` · `lq_district` | ⚖️ **트레이드오프** | 높으면 그 업종의 동네지만, 발달상권에선 과밀 신호(B2) |
| `marshallian` (동종 밀도) | ⚖️ **트레이드오프** | 집적 이익(B1 생존 2.57배) vs 경쟁 심화. 부호가 상권 유형에 따라 뒤집힘 |
| `jacobian` (이종 다양성) | ⚖️ **트레이드오프** | 대상지는 다양할수록 유리하나 인접지는 반대(B1) |
| `effective_categories` | ⚖️ **트레이드오프** | 다양성의 부호가 논문끼리 엇갈림 |
| `restaurant_density` | ⚖️ **U자형** | 최적점이 존재. 높아도 낮아도 불리 |
| `density_sq` | ⚖️ **U자 검증용** | 단독으로 읽는 값이 아님 |
| `same_type_count` | ⚖️ **트레이드오프** | **많다고 감점하면 논문과 정면 배치** |
| `franchise.ratio` | 🎯 **업종 의존** | 프랜차이즈가 많으면 검증된 상권이지만 개인 창업엔 불리 |
| `store_total` | ⚖️ **트레이드오프** | 점포가 많으면 유동도 많지만 임대료·경쟁도 높음 |

**핵심: 경쟁업체 지표는 그 자체로 좋고 나쁨이 없습니다.** "한식 LQ 0.52"는 한식을 하려는 사람에겐
"경쟁이 덜하다"일 수도 "수요가 없다"일 수도 있습니다. **업종과 상권 유형이 정해진 뒤에야 방향이 생기고,
업종을 정하는 건 결정 에이전트입니다.**

### 화면 제안

유동인구 문서와 같은 결론입니다.

1. **결정 에이전트가 업종을 고른 뒤** 그 업종 기준으로 방향을 붙인다 (권장)
2. 방향 없이 **"기준 대비 배수"로만 표시** — `1.0` 기준선을 긋고 위/아래로 보여줍니다

우리 지표 중 ⬆️/⬇️가 확정적인 건 **하나도 없습니다.**

---

## 2. 항상 오는 값 (null 체크 불필요)

`status`가 `ok`·`partial`이면 아래는 반드시 옵니다.

### 규모·대표 숫자

| 화면 항목 | 경로 | 타입 | 노원 값 |
| --- | --- | --- | --- |
| **읽는 법** | `/data/description` | string | 반경·모수·단위를 밝힌 한 문단 (아래) |
| **대표 숫자** | `/data/store_total` | int | `1237` 개 |
| 분석 반경 | `/data/radius_m` | int | `500` |
| 자료 기준일 | `/data/data_reference_date` | string | `2026-03-31` (§7) |
| **출처** | `/data/sources` | object[] | 1~2행 (§9) |

`description`은 유동인구와 같은 자리(`data` 맨 앞)에 있습니다. 결정 에이전트 프롬프트가
"필드 이름, 설명, 단위와 실제 값을 함께 읽는다"로 동작해서, 숫자의 기준을 글로도 박아 둔 것입니다.
값은 매번 실제 반경·모수로 조립됩니다.

> 반경 500m 안 점포 2,506개를 소상공인시장진흥공단 상가(상권)정보 2026년 1분기 자료로 집계했습니다.
> 밀도는 1km²당 점포 수, share·ratio는 0~1 비율, lq·lq_district는 배수로 1.0이 기준입니다.
> lq는 반경 2,000m 안의 업종 비중과 비교한 값입니다. lq_district는 강남구 전체와 비교한 값이라
> lq와 분모가 다릅니다. 프랜차이즈 비율은 공정거래위원회 2025년 브랜드명과 상호명을 문자열로
> 대조한 결과라 누락과 오탐이 있고 confidence가 low입니다. **업종을 추천하거나 점수를 매기지
> 않습니다. 판단은 결정 에이전트가 합니다.**

마지막 문장은 항상 붙습니다. §1의 "우리는 점수를 주지 않는다"를 `data` 안에서도 못 박기 위해서입니다.

### 업종 구성

| 화면 항목 | 경로 | 타입 | 노원 값 |
| --- | --- | --- | --- |
| 대분류 구성 | `/data/by_major` | object[] | 10행 — 교육 530 · 음식 238 · 소매 158 · 수리개인 98 … |
| 중분류 전수 | `/data/by_middle` | object[] | **75행** (0건 22종 포함) ⚠️ §5 참고 |

`by_major[i]`: `code` · `name` · `count` · `share` · `density_per_km2`
`by_middle[i]`: `code` · `name` · `major_code` · `major_name` · `count` · `share` ·
`density_per_km2` · `density_sq` · `lq` · `lq_district` · `same_type_count` · `diff_type_count` ·
`marshallian` · `jacobian` · `major_cluster_count` · `major_cluster_diversity`

정렬은 **점포 수 내림차순**입니다.

### 반경별 (핵심 차트 재료)

| 화면 항목 | 경로 | 타입 | 노원 값 |
| --- | --- | --- | --- |
| 반경별 점포 수 | `/data/by_radius[i]/store_total` | int | 46 → 569 → 1,237 |
| 있는 업종 수 | `…/category_count` | int | 15 → 38 → 53 |
| 없는 업종 수 | `…/absent_category_count` | int | 60 → 37 → 22 |
| 상위 업종 막대 | `…/top_by_count` | object[] | 최대 **5** |
| 하위 업종 | `…/bottom_by_count` | object[] | 최대 **5** |
| 밀집 상위 | `…/top_by_concentration` | object[] | 최대 **5** |
| 특화 상위 | `…/top_by_specialization` | object[] | 최대 **5** |
| **해설 문장** | `…/explanations` | object | 5문장 — 그대로 써도 됨 |

`category_count + absent_category_count = 75` 로 항상 맞습니다.

순위 항목 `top_by_count[i]`: `rank` · `code` · `name` · `count` · `density_per_km2` · `note`
특화 항목 `top_by_specialization[i]`: `rank` · `code` · `name` · `count` · `times_vs_surroundings` · `note`

`note`는 **이미 사람이 읽는 문장**입니다 — `"417개 · 이 반경 점포의 33.7%"`,
`"주변 2,000m 평균보다 4.2배 많습니다"`.

`explanations` 5개 키: `store_total` · `top` · `bottom` · `concentration` · `specialization`.
차트 옆 캡션으로 쓰라고 만든 문장입니다.

> 반경 50m 예시
> `"반경 50m 안에 점포가 46개 있습니다."`
> `"가장 많은 업종은 일반 교육기관(21개), 한식 음식점업(4개), 기타 교육기관(3개) 순입니다."`
> `"이 반경에 아예 없는 업종이 60개입니다."`

### 집적·다양성

| 화면 항목 | 경로 | 타입 | 노원 값 |
| --- | --- | --- | --- |
| 업종 다양성(중분류) | `/data/diversity/hhi_middle` | number | `0.140044` |
| 업종 다양성(대분류) | `/data/diversity/hhi_major` | number | `0.250798` |
| **유효 업종수** | `/data/diversity/effective_categories` | number | `7.1406` 종 |
| 음식점 밀도 | `/data/restaurant_density/value` | number | `303.031` 개/km² |
| 음식점 개수 | `/data/restaurant_density/store_count` | int | `238` |
| 단위 문자열 | `/data/restaurant_density/unit` | string | `stores_per_km2` |
| **서울 분포 백분위** | `/data/restaurant_density/seoul_percentile` | number \| null | 0~100 · **서울 밖은 `null`** |
| **겹치는 상권** | `/data/trade_areas` | object[] | 최대 8행 · **서울 밖은 빈 배열** |

53종이 집계됐는데 유효 업종수가 7.14인 건 **일반 교육기관 하나가 33.7%**라서입니다.
"53종이 있다"보다 "사실상 7종이 나눠 갖고 있다"가 실상에 가깝습니다.

### 프랜차이즈

| 화면 항목 | 경로 | 타입 | 노원 값 |
| --- | --- | --- | --- |
| 프랜차이즈 수 | `/data/franchise/count` | int | `136` |
| 프랜차이즈 비율 | `/data/franchise/ratio` | number | `0.1099` |
| **개인사업자 수** | `/data/franchise/independent_count` | int | `1101` |
| **개인사업자 비율** | `/data/franchise/independent_ratio` | number | `0.8901` |
| 업종별 내역 | `/data/franchise/by_middle` | object[] | `code`·`name`·`count`·`ratio` |
| 판정 방식 | `/data/franchise/method` | string | `brand_name_match` |
| **신뢰도** | `/data/franchise/confidence` | `"low"` | **항상 `low`** |
| **브랜드 기준 연도** | `/data/franchise/base_year` | int \| null | `2025` |

⚠️ **`confidence`가 항상 `low`입니다.** 공정위 API에 반경 검색이 없어 브랜드명 11,724개와 상호명을
문자열로 대조합니다. 누락과 오탐이 구조적입니다. **단독 근거로 쓰지 마세요.**

> 표의 노원 값은 2024년 브랜드 목록(11,602개)으로 측정한 것입니다. 지금은 2025년 목록(11,724개)을
> 쓰므로 `count`가 조금 달라집니다. `independent_count`와의 합이 `store_total`인 건 그대로입니다.

업종별 1위는 기타 간이 음식점업 36개 / 40.9%입니다.

### 기준선 (배수를 해석하려면 필수)

| 화면 항목 | 경로 | 타입 | 노원 값 |
| --- | --- | --- | --- |
| 요청 반경 | `/data/lq_baseline/requested_radius_m` | int | `2000` |
| **실제 적용 반경** | `/data/lq_baseline/applied_radius_m` | int\|null | `2000` |
| 기준선 점포 수 | `/data/lq_baseline/store_total` | int\|null | `8555` |

**`requested`와 `applied`가 다를 수 있습니다.** API가 반경을 거부하면 2,000 → 1,500 → 1,000으로
줄여 가며 재시도합니다. **문장을 만들 땐 반드시 `applied`를 쓰세요.**

### 자치구 기준선·특화

| 화면 항목 | 경로 | 타입 | 노원 값 |
| --- | --- | --- | --- |
| 자치구 이름 | `/data/district_baseline/signgu_name` | string\|null | `노원구` |
| 자치구 점포 수 | `/data/district_baseline/store_total` | int | `15686` |
| **자치구 대비 특화** | `/data/district_specialization` | object[] | 상위 10 |

`district_specialization[i]`: `rank` · `code` · `name` · `count` · `times_vs_surroundings` · `note`

| 순위 | 업종 | 점포 | 배수 |
| --- | --- | --- | --- |
| 1 | 일반 교육기관 | 417 | **5.83** |
| 2 | 도서관, 사적지 및 유사 여가관련 서비스업 | 41 | 3.79 |
| 3 | 사무 지원 서비스업 | 7 | 2.11 |

⚠️ **`district_baseline`은 `null`일 수 있습니다** — §3 참고.

### 메타

| 화면 항목 | 경로 | 타입 | 노원 값 |
| --- | --- | --- | --- |
| 분석 범위 | `/scope/area` | string | `서울특별시 노원구 한글비석로 242 삼부프라자 1층 반경 500m` |
| 기준 시점 | `/scope/period` | string | `2026-09-11 조회` ⚠️ §7 |
| 한계 문구 | `/warnings` | string[] | 정상 실행이면 **빈 배열** |

`/status`: `ok` · `partial`(기준선·프랜차이즈·업종 마스터 중 일부 실패) ·
`no_data`(반경 내 점포 0건) · `error`(인증 실패·타임아웃).
**`no_data`·`error`면 `data`가 비어 있습니다.**

---

## 3. `null`일 수 있는 값 — 반드시 분기 처리

우리는 **블록 선별 기능이 없습니다**(§4). `null`이 되는 건 **조회 실패나 조건 미충족**일 때뿐입니다.

| 화면 항목 | 경로 | `null`이 되는 때 |
| --- | --- | --- |
| 자치구 기준선 | `/data/district_baseline` | 점포 자료에 자치구 코드가 없거나 자치구 조회 실패 |
| 자치구 대비 특화 | `/data/district_specialization` | 위와 같음 (빈 배열 `[]`) |
| 업종별 `lq` | `/data/by_middle[i]/lq` | **기준지역에도 그 업종이 없을 때** |
| 업종별 `lq_district` | `/data/by_middle[i]/lq_district` | 자치구 기준선이 없을 때 |
| 기준선 적용 반경 | `/data/lq_baseline/applied_radius_m` | 2km·1.5km·1km 모두 거부 |
| 모델 요약 | `/data/summary` · `summary_text` | 모델 키 없음·호출 실패 |

### ⚠️ `lq`의 `null`과 `0.0`은 뜻이 다릅니다

| 값 | 뜻 | 화면 |
| --- | --- | --- |
| `null` | **기준지역에도 없어 비교 자체가 불가능** | "비교 불가" 또는 숨김 |
| `0.0` | 기준지역엔 있는데 **이 반경에만 없다** | "이 자리엔 없음" — 유의미한 정보 |

**노원 실행에서 두 경우가 실제로 섞여 나왔습니다.** 0건 업종 22종 중

| | 개수 | 예 |
| --- | --- | --- |
| `lq: 0.0` | **20종** | 가구 소매업, 병원 … — 노원 2km 안에는 있는데 이 500m 안에만 없음 |
| `lq: null` | **2종** | 기타 외국식 음식점업, 시장 조사 및 여론 조사업 — 2km 안에도 없음 |

`기타 외국식 음식점업`은 `lq`·`lq_district` 둘 다 `null`이고,
`시장 조사 및 여론 조사업`은 `lq`는 `null`인데 `lq_district`는 `0.0`입니다
(2km엔 없지만 노원구 전체엔 있다는 뜻).

⚠️ **`if (!lq)` 같은 falsy 체크를 쓰면 `0.0`과 `null`이 한 덩어리가 됩니다.**
`lq === null`로 명시 비교하세요.

### 모델 요약 `/data/summary`

| 경로 | 타입 | 노원 값 |
| --- | --- | --- |
| `…/radius_notes` | object[] | 5개 — `radius_m` + `text` |
| `…/overall` | string\|null | 종합 평가 2~3문장 |
| `…/concentration` | string\|null | 집적·특화 평가 2~3문장 |
| `/data/summary_text` | string\|null | 위 셋을 이어 붙인 통짜 문자열 |

`summary_text`는 AI 요약 영역에 그대로 넣으라고 만든 값입니다.

> `"50m: 점포 46개 중 일반 교육기관이 21개로 가장 많아, 반경 2km 안 평균보다 약 5.7배 많습니다."`
> `"종합 평가: 이 자리는 50m부터 500m까지 거리와 상관없이 일반 교육기관이 계속 1위를 지키는 곳으로…"`

---

## 4. 결정 에이전트 입력 크기 — 줄였습니다

### 실측된 장애

같은 주소(송파구 개롱역)로 결정 에이전트를 호출한 결과입니다.

| 입력 | 프롬프트 토큰 | 응답 | 결과 |
| --- | --- | --- | --- |
| 상권 분석 전량 | 32,585 | `{}` (2자) | **실패** |
| 상권 분석 전량 (재시도) | 40,153 | `{}` (2자) | **실패** |
| `by_radius` 제외 | **7,479** | 3,168자 | 성공 |

`finish_reason`은 `stop`입니다. 잘린 게 아니라 모델이 빈 객체를 냅니다. 두 번 다 같았습니다.

### 왜 우리가 줄여야 했나

`decision/agent.py`가 `request.model_dump_json()` **한 줄로 전량을 프롬프트에 넣습니다.**
자르거나 요약하는 코드가 저장소 어디에도 없습니다.

그래서 "`digest`를 따로 낸다"·"결정이 필요한 필드만 읽는다"는 **효과가 없습니다** — 우리가
무엇을 더 내든 결정 에이전트는 전량을 넣습니다. **우리 `data`를 실제로 작게 만드는 것만** 듣습니다.

### 무엇을 줄였나

반경 단계를 5개(50·100·200·300·500) → **3개(50·200·500)**, 순위 배열 길이를 10 → **5**로 줄였습니다.
집계 로직은 그대로고 배열 길이만 짧아집니다.

| | 전 | 후 |
| --- | --- | --- |
| `by_radius` | 23,251자 (44.0%) | **7,876자 (21.3%)** |
| `by_middle` | 24,816자 | 24,816자 (그대로) |
| **`data` 전체** | **52,882자** | **36,925자** (−30%) |

**`by_middle`은 건드리지 않았습니다.** 75행 전수가 계약이고 LQ·집적 지표가 전부 여기 있어
**결정 에이전트가 실제로 읽는 유일한 블록**입니다.

### 실측 결과

줄인 뒤 같은 조건으로 다시 돌렸습니다.

```
경쟁업체 data 37,485자 · 요청 전체 38,912자
→ status partial · 추천 5건 · 근거 12건        (이전엔 {})
```

⚠️ **지역에 따라 다시 커질 수 있습니다.** `by_middle`이 이제 67%를 차지하는데 이건 못 줄입니다.
더 필요하면 각 슬라이스의 `bottom_by_count`(0건 업종 나열 — `absent_category_count`와 정보 중복)를
빼는 게 다음 수단입니다.

> **참고 — 중복 필드 2개**
> `by_middle[].marshallian`은 `density_per_km2`와, `same_type_count`는 `count`와 **값이 완전히 같습니다.**
> 행당 약 40자 × 75행 = 3,000자가 중복인데, `marshallian`이 `INDEX` 지표 4로 문서화돼 있어
> 제거는 스펙 변경이라 그대로 뒀습니다.

---

## 5. 🚫 화면에 쓰면 안 되는 값

### `/data/by_middle` 75행 전부 — 가장 위험

0건 업종이 **22종** 섞여 있어 축을 잡아먹고, **상위 3종이 전체의 49.2%**를 차지해 나머지가 안 보입니다.

| 업종 | 점포 | 누적 비중 |
| --- | --- | --- |
| 일반 교육기관 | 417 | 33.7% |
| 기타 교육기관 | 104 | 42.1% |
| 기타 간이 음식점업 | 88 | **49.2%** |
| … 나머지 72종 | 628 | 100% |

→ 상위 N개만 자르거나, 이미 순위로 잘려 있는 **`by_radius[i]/top_by_count`를 쓰세요.**

### `marshallian` · `jacobian` · `density_sq` — 사용자에게 보여줄 이름이 아닙니다

판단용 내부 지표입니다. 모델 프롬프트에도 "마샬리안, 제이코비안은 쓰지 않는다"로 막아 두었습니다.
`density_sq`는 단독으로 의미가 없습니다(U자 검증용 2차항).

### `major_cluster_count` · `major_cluster_diversity` — 두 값을 곱하거나 더하지 마세요

누적 유인(Nelson 2원칙)의 재료입니다. 앞은 **그 업종이 속한 대분류의 점포 수**,
뒤는 **그 대분류 안의 유효 중분류 수**입니다.

```
한식 음식점업 → major_cluster_count 487 (음식점업 전체) · major_cluster_diversity 4.4981
```

"음식점이 487개 모여 있고, 그 안이 사실상 4.5종으로 나뉜다"로 읽습니다.
**우리는 이 둘을 합친 점수를 만들지 않았습니다.** 가중치를 정하는 순간 그게 판단이 되기 때문입니다.
합칠지 말지는 결정 에이전트가 정하세요.

0건 업종도 이 두 값은 채워져 옵니다 — 그 업종이 없어도 **대분류가 어떤 상태인지는 말할 수 있어서**입니다.

### `lq`를 기준 없이 "3배"로 표시하기

`lq`와 `lq_district`는 **분모가 다릅니다.** 반드시 기준을 붙이세요.

```
lq          →  "반경 2,000m 안에서 보면 약 4.2배"
lq_district →  "노원구 전체와 비교하면 약 5.8배"
```

기준을 빼면 읽는 사람이 **서울 전체 기준으로 오해합니다.**

### `data_reference_date`와 `scope.period`는 형식이 다릅니다

같은 시점인데 `data_reference_date`는 `"2026-03-31"`(날짜), `scope.period`는 `"2026년 1분기"`(분기)입니다.
나란히 놓고 "둘이 다르다"고 읽지 마세요. §7 참고.

### 같은 500m인데 순위가 다를 수 있습니다

`by_middle`(반경 전체 기준)과 `by_radius[4]`(500m 슬라이스)는 같은 반경인데 값이 다를 수 있습니다.
`by_radius`는 API가 준 좌표로 거리를 다시 계산해 자르므로 **좌표가 없는 점포가 빠집니다.**
나란히 놓을 땐 출처를 밝혀 주세요.

---

## 6. TypeScript 타입

```ts
export interface CommercialArea {
  request_id: string;
  agent_id: "commercial_area";
  status: "ok" | "partial" | "no_data" | "error";
  scope: { area: string; period: string } | null;
  warnings: string[];
  error: { code: string; message: string } | null;
  data: CommercialAreaData | Record<string, never>;   // no_data·error 면 빈 객체
}

export interface CommercialAreaData {
  radius_m: number;                    // 500
  description: string;                 // 맨 앞. 숫자를 읽는 법을 문장으로
  store_total: number;                 // 1237 — 대표 숫자
  data_reference_date: string | null;  // "2026-03-31" — 자료 기준일

  by_major: MajorCategory[];           // 대분류 10종
  by_middle: MiddleCategory[];         // ⚠️ 중분류 75종 전수 (0건 포함)
  by_radius: RadiusSlice[];            // 50·200·500m

  diversity: {
    hhi_major: number;
    hhi_middle: number;
    effective_categories: number;      // 1 ÷ HHI
  };

  restaurant_density: {
    value: number;                     // 개/km²
    squared: number;                   // U자 검증용
    unit: "stores_per_km2";
    store_count: number;               // 원시 개수
    seoul_percentile: number | null;   // 0~100 · 서울 밖은 null
  };

  franchise: {
    count: number;
    ratio: number;                     // 0~1
    independent_count: number;         // count + independent_count === store_total
    independent_ratio: number;         // 0~1
    by_middle: Array<{ code: string; name: string; count: number; ratio: number }>;
    method: "brand_name_match";
    confidence: "low" | "medium" | "high";   // ⚠️ 현재 항상 "low"
    base_year: number | null;          // 2025 — 상가정보와 원천이 다름
  } | null;

  lq_baseline: {
    requested_radius_m: number;        // 2000
    applied_radius_m: number | null;   // ⚠️ 문장에는 이 값을 쓸 것
    store_total: number | null;
  };

  district_baseline: {
    signgu_code: string;
    signgu_name: string | null;
    store_total: number;
  } | null;                            // ⚠️ null 가능

  district_specialization: SpecializationRank[];   // 상위 10 · 빈 배열 가능

  trade_areas: Array<{                 // 겹치는 서울시 상권 · 서울 밖은 []
    code: string; name: string;
    kind: string | null;               // "골목상권" | "발달상권" | "전통시장" | "관광특구"
    signgu: string | null;
    distance_m: number; area_m2: number; equivalent_radius_m: number;
  }>;

  sources: Array<{ name: string; url: string; license: string; period: string }>;

  summary: {
    radius_notes: Array<{ radius_m: number; text: string }>;
    overall: string | null;
    concentration: string | null;
  } | null;
  summary_text: string | null;         // AI 요약 영역에 그대로
}

export interface MajorCategory {
  code: string; name: string; count: number;
  share: number; density_per_km2: number;
}

export interface MiddleCategory {
  code: string;                // "P105" — 소상공인 중분류
  name: string;                // "일반 교육기관"
  major_code: string; major_name: string;
  count: number; share: number;
  density_per_km2: number;
  density_sq: number;          // ⚠️ 화면에 쓰지 말 것
  lq: number | null;           // 반경 2km 대비 · null ≠ 0.0
  lq_district: number | null;  // 자치구 대비
  same_type_count: number;
  diff_type_count: number;
  marshallian: number;         // ⚠️ 화면에 쓰지 말 것
  jacobian: number;            // ⚠️ 화면에 쓰지 말 것
  major_cluster_count: number;      // 이 업종이 속한 대분류의 점포 수
  major_cluster_diversity: number;  // 그 대분류 '안'의 유효 중분류 수
}

export interface RadiusSlice {
  radius_m: number;                    // 50 200 500
  store_total: number;                 // y축
  category_count: number;
  absent_category_count: number;       // category_count + absent = 75
  top_by_count: CategoryRank[];
  bottom_by_count: CategoryRank[];
  top_by_concentration: CategoryRank[];
  top_by_specialization: SpecializationRank[];
  explanations: {                      // 캡션으로 그대로 사용 가능
    store_total: string; top: string; bottom: string;
    concentration: string; specialization: string;
  };
}

export interface CategoryRank {
  rank: number; code: string; name: string;
  count: number; density_per_km2: number;
  note: string;                        // "417개 · 이 반경 점포의 33.7%"
}

export interface SpecializationRank {
  rank: number; code: string; name: string; count: number;
  times_vs_surroundings: number;
  note: string;                        // "노원구 전체보다 5.8배 많습니다"
}
```

### 쓰는 예

```ts
const d = res.data;
if (res.status === "no_data" || res.status === "error") return <Empty msg={res.warnings[0]} />;

// 대표 숫자
d.store_total.toLocaleString();                       // "1,237"

// 반경별 증가 곡선
d.by_radius.map(s => ({ x: s.radius_m, y: s.store_total }));

// 상위 업종 막대 — by_middle 전체가 아니라 이것
d.by_radius.at(-1)!.top_by_count.map(r => ({ label: r.name, value: r.count }));

// 대분류 도넛
d.by_major.filter(m => m.count > 0).map(m => ({ label: m.name, value: m.count }));

// 자치구 대비 특화 (빈 배열 가능)
d.district_specialization.length
  ? d.district_specialization.map(r => ({ label: r.name, value: r.times_vs_surroundings }))
  : null;

// LQ — null 과 0.0 을 구분할 것
const lqText = (r: MiddleCategory) =>
  r.lq === null ? "비교 불가"
  : `반경 ${d.lq_baseline.applied_radius_m?.toLocaleString()}m 대비 ${r.lq.toFixed(1)}배`;

// 프랜차이즈 vs 개인 — 그대로 씁니다
const fr = d.franchise;
const donut = fr ? [fr.count, fr.independent_count] : null;   // [136, 1101]

// 출처 (길이를 가정하지 말 것 — 브랜드 목록 실패 시 1건)
d.sources.map(s => `${s.name} (${s.period}, ${s.license})`);

// AI 요약 (null 가능)
d.summary_text ?? null;
```

---

## 7. 숫자 표기 주의

| | 규칙 |
| --- | --- |
| 단위 | 밀도는 전부 **개/km²**. `restaurant_density.unit`에 문자열로도 옵니다 |
| 비중 | `share`·`ratio`는 0~1. 화면에 쓸 땐 ×100 |
| 배수 | `lq`·`lq_district`·`times_vs_surroundings`는 배수. **1.0이 기준** |
| 반올림 | 밀도는 소수 4자리(`530.9409`), 비중은 6자리(`0.337106`)까지 옵니다. 화면에는 줄여서 |
| **기준 시점** | `scope.period`는 `"2026년 1분기"`, `data_reference_date`는 `"2026-03-31"`. 아래 참고 |

### 기준 시점 표기 — 형식은 맞췄고, 시점은 원래 다릅니다

| 에이전트 | `scope.period` | 원천 최신 |
| --- | --- | --- |
| 유동인구 | `"2026년 2분기"` | 서울시 길단위인구 |
| 개폐업 | `"2025Q2"` | 서울시 상권분석 |
| **경쟁업체 (우리)** | `"2026년 1분기"` | 소상공인 상가정보 **2026-03-31** |

**소상공인 API 응답에는 날짜 필드가 하나도 없습니다** — 실제 응답 39개 필드를 전수 확인했습니다.
예전에는 그 자리를 조회일(`"2026-09-11 조회"`)로 채웠는데, 이건 자료의 기준 시점이 아니었습니다.
지금은 코드에 박은 분기 상수를 씁니다. 원천이 나중에 날짜 필드를 추가하면 그 값이 우선합니다.

**형식을 맞춰도 시점은 여전히 다릅니다** — 세 원천의 최신 분기가 실제로 다르기 때문입니다.
결정 에이전트가 기간 차이를 지적하는 건 **정상**이고, 형식 불일치로 생기던 가짜 경고만 사라집니다.

프랜차이즈는 원천 연도가 또 다릅니다(**2025년**). `franchise.base_year`로 따로 표기합니다.

> 분기 갱신은 `backend/app/agents/commercial_area/sources.py`의 `SBIZ_PERIOD`·`SBIZ_REFERENCE_DATE`
> 두 줄만 고치면 `scope.period`·`data_reference_date`·`sources`가 함께 따라갑니다.

---

## 8. 알려진 한계 (리포트 각주 후보)

정상 실행이면 `/warnings`가 **빈 배열**입니다. 실패했을 때만 문장이 들어옵니다.

| 언제 | 문장 |
| --- | --- |
| 자치구 코드 없음 | 점포 자료에 자치구 코드가 없어 자치구 대비 배수를 계산하지 못했습니다. |
| 기준선 조회 실패 | LQ 기준 반경 조회 실패로 LQ를 계산하지 못했습니다: … |
| 페이지 상한 초과 | 점포 N건 중 M건만 조회했습니다. 페이지 상한에 걸려 집계가 일부 누락됐습니다. |
| 브랜드 목록 실패 | 공정위 브랜드 목록을 확보하지 못해 프랜차이즈 비율을 계산하지 못했습니다. |
| 업종 마스터 없음 | 업종 코드 마스터 파일이 없어 조회된 업종만 집계했습니다. |
| 모델 요약 실패 | ELICE_MODEL이 설정되지 않아 요약을 생략했습니다. |

**개수를 가정하지 말고 배열을 그대로 순회**하세요.

### 방법론상의 한계 (경고가 아니라 상시)

- **좌표 정확도가 결과를 바꿉니다.** 지번 주소는 동 중심점으로 잡히는 경우가 있어 50~100m 결과가
  흔들립니다. 현재 카카오 키가 유효하지 않아 OSM 폴백으로 도는데, 실측상 "오금로 404"가
  **2.9km 어긋난** 사례가 있습니다.
- **반경 3개를 API 3번으로 받지 않습니다.** 500m를 한 번 받아 좌표로 안쪽 반경을 직접 계산합니다
  (실측 오차 0~2건). 그래서 좌표가 없는 점포는 안쪽 반경에서 빠집니다.
- **LQ 기준선 좌표가 250m 격자로 반올림됩니다.** 캐시 공유를 위해서인데, 기준선 중심이 최대 125m 이동합니다.
- **LQ 기준선이 분석 반경을 포함합니다.** 500m ⊂ 2km이라 분모에 분자가 들어갑니다.

---

## 9. 출처 표기 (의무)

공공누리 **출처표시** 대상입니다.

| 이름 | URL | 기준 |
| --- | --- | --- |
| 소상공인시장진흥공단 상가(상권)정보 | https://www.data.go.kr/data/15012005/openapi.do | 2026-03-31 |
| 공정거래위원회 브랜드별 가맹점 현황 | https://www.data.go.kr/data/15110241/openapi.do | 2025년 |

### `data/sources`로 함께 갑니다

유동인구와 같은 자리(`/data/sources`)에 배열로 실립니다. 리포트에서 출처를 하드코딩하지 마세요.

```json
"sources": [
  {"name": "소상공인시장진흥공단 상가(상권)정보",
   "url": "https://www.data.go.kr/data/15012005/openapi.do",
   "license": "공공누리 출처표시", "period": "2026년 1분기"},
  {"name": "공정거래위원회 브랜드별 가맹점 현황",
   "url": "https://www.data.go.kr/data/15110241/openapi.do",
   "license": "공공누리 출처표시", "period": "2025년"}
]
```

**브랜드 목록을 못 받으면 공정위 항목은 빠집니다** — 쓰지 않은 자료를 출처에 적지 않기 때문입니다.
배열 길이를 2로 가정하지 말고 그대로 순회하세요.

---

## 10. 팀 결정이 필요한 것

### ✅ 우리 쪽에서 끝난 것 (2026-09-14 반영)

외부 의존이 없어 먼저 넣었습니다. **팀 공용 `app/schemas.py`는 건드리지 않았습니다** —
전부 `data` 안쪽 변경이라 받는 쪽 코드를 고칠 필요가 없습니다.

| 항목 | 결과 |
| --- | --- |
| **`description` 필드** | `data` 맨 앞. 반경·모수·단위·배수의 분모까지 한 문단으로 |
| **`sources` 필드** | `data` 맨 뒤(§9). 쓴 자료만 실립니다 |
| **`scope.period` 표기** | `"2026-09-11 조회"` → `"2026년 1분기"`. 조회일 폴백 제거(§7) |
| **`data_reference_date`** | `"2026-03-31"`. `scope.period`와 형식이 다릅니다(날짜 vs 분기) |
| **개인사업자 필드** | `franchise.independent_count`·`independent_ratio` |
| **누적 유인** | `by_middle[].major_cluster_count`·`major_cluster_diversity`. **합성 점수는 만들지 않았습니다** |
| **`franchise.base_year`** | `2025`. 브랜드 캐시 파일명에도 연도를 넣어 지난 연도 목록이 새 연도로 표시되지 않게 했습니다 |
| **`ftc_year` 갱신** | `2024` → `2025`. 실제로 받아보니 브랜드 11,724건(2024년은 11,602건) |
| **업종 체계 매핑** | 아래 별도 절 |

### ✅ 업종 체계 매핑 — `app/industries` (2026-09-15)

세 에이전트가 같은 업종을 가리킬 코드가 없던 문제입니다. 우리 중분류 `I201`, 개폐업 정수 `1`,
결정 `category.middle` 자유 문자열이 서로 못 알아들었습니다.

**소상공인 중분류 75종을 공통 어휘로 삼고** 나머지를 거기로 접었습니다.

```
소상공인 상가정보 (전국) ─┐
서울시 상권분석 (서울)    ─┼─→  중분류 75종  ─→  Category(major, middle)
개폐업 70업종           ─┘
```

| | 연결 |
| --- | --- |
| 서울시 생활밀접업종 99종 → 중분류 | 50종에 접힘 (`CS300043 전자상거래업`은 무점포라 제외) |
| 개폐업 70업종 → 중분류 | 84행. 1:1 55 · 쪼개짐 8 · 직결 7 |
| 소상공인 단독 | 25종 — 광고·시장조사·경영컨설팅·엔지니어링·병원·마사지·장례 등 |

**서울시가 못 만든다던 업종을 우리가 메웁니다.** 제후님이 `UNSUPPORTED_SERVICE_INDUSTRIES`로
빼둔 7종의 대상이 대부분 이 25종에 있습니다(`G212 생활용품`만 예외 — 서울시 악기·조명용품이 붙습니다).

⚠️ **두 가지는 아직 확정이 아닙니다.**
- 서울시 연결 99건 중 **53건이 모델 판정**입니다. `match_method=모델` 행은 사람 검수 전입니다
- **개폐업 점수는 그대로 옮기면 안 됩니다.** 70↔75가 양방향 N:M이라 산술평균하면 점포 1개짜리와
  100개짜리를 같은 무게로 섞습니다. 연결표만 제공하고 가중 방식은 미정입니다

자세한 건 [`backend/app/industries/README.md`](../backend/app/industries/README.md).

### ✅ 2026-09-15 추가로 끝난 것

| 항목 | 결과 |
| --- | --- |
| **결정 에이전트 입력 크기** | 반경 5→3단계, 순위 10→5. `data` 52,882 → 36,925자(−30%). **실측으로 통과 확인**(§4) |
| **상권 유형 구분** | `trade_areas[]` — 서울시 상권 1,650곳 동봉. 런타임에 서울시 API를 부르지 않습니다(§0) |
| **음식점 밀도 백분위** | `restaurant_density.seoul_percentile` — 서울 상권 1,650곳을 **우리 분모로** 재표본(§0) |

### ⏳ 아직 남은 것

| 항목 | 내용 | 막는 것 |
| --- | --- | --- |
| **업종 매핑 검수** | 서울시 99종 중 53건이 모델 판정 | 사람 검수 |
| **개폐업 점수 가중** | 70→75 N:M이라 산술평균하면 틀립니다 | 개폐업·결정 담당과 합의 |
| **결정 에이전트 어휘** | 결정이 `중식`·`베이커리`처럼 우리 75종과 다른 이름을 냅니다 | `decision/`은 다른 소유자 |
| **화살표 방향** | 우리 지표는 ⬆️/⬇️가 확정적인 게 하나도 없습니다(§1) | 결정 담당 판단 |
| **입력 크기 재발 가능성** | `by_middle`이 이제 67%인데 못 줄입니다. 지역에 따라 다시 커질 수 있습니다 | §4 참고 |
