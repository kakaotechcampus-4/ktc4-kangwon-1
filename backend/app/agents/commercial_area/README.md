# 상권 경쟁 분석 에이전트 (commercial_area)

주소와 좌표를 받아 **반경 안에 어떤 업종의 점포가 몇 개 있는지** 계산해 결정 에이전트에 넘긴다.

업종을 추천하거나 판단하지 않는다. 숫자와 그 숫자를 풀어 쓴 문장만 만든다.

## 무엇을 계산하나

집적·경쟁 지표 10종을 반경 50·100·200·300·500m로 나눠 계산한다.

| 지표 | 필드 |
| --- | --- |
| 점포 수 | `store_total`, `by_major[].count`, `by_middle[].count` |
| 동종 / 이종 업체 수 | `by_middle[].same_type_count` / `diff_type_count` |
| 업종별 밀도 + 2차항 | `by_middle[].density_per_km2` / `density_sq` |
| 음식점 밀도 | `restaurant_density` (단위 `stores_per_km2`) |
| 업종 다양성 | `diversity.hhi_major` / `hhi_middle` / `effective_categories` |
| 입지계수 LQ | `by_middle[].lq` (분석 반경 비중 ÷ 기준 반경 비중) |
| 마샬리안 / 제이코비안 | `by_middle[].marshallian` / `jacobian` |
| 프랜차이즈 비율 | `franchise` |
| 반경별 순위·해설 | `by_radius[]` |
| 사람이 읽는 요약 | `summary` |

업종은 소상공인 상권업종분류 **중분류 75종**을 쓴다. 결정 에이전트의 `category.middle`과 같은 단위다. 반경 안에 없는 업종도 0으로 채워 전달한다.

각 지표를 그렇게 정의한 논문 근거는 팀 문서 `부동산 agent/논문근거_경쟁지표.md`에 정리돼 있다.

## 준비

파이썬 **3.12**가 필요하다. `pyproject.toml`이 `>=3.12,<3.13`으로 고정한다.

```bash
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e .
```

`backend/.env`에 아래 값을 넣는다.

| 변수 | 용도 | 없으면 |
| --- | --- | --- |
| `COMMERCIAL_AREA_API_KEY` | 소상공인 상가정보 (필수) | `status: error` |
| `FRANCHISE_API_KEY` | 공정위 브랜드 목록 | 프랜차이즈 지표 생략 + `partial` |
| `ELICE_API_KEY` / `ELICE_BASE_URL` / `ELICE_MODEL` | 요약 생성 | 요약 생략 |
| `GEOCODING_API_KEY` | 주소→좌표 (카카오 REST 키) | 정확도가 낮은 대체 경로 사용 |
| `ANALYSIS_RADIUS_M` | 분석 반경 (기본 500) | 500m |

공공데이터 키 2개는 [공공데이터포털](https://www.data.go.kr) 계정의 **일반 인증키 하나**를 양쪽에 넣으면 된다. 단 API마다 활용신청을 따로 해야 한다.

| 신청할 API | 링크 |
| --- | --- |
| 소상공인시장진흥공단 상가(상권)정보 | [data.go.kr/data/15012005](https://www.data.go.kr/data/15012005/openapi.do) |
| 공정거래위원회 브랜드별 가맹점 현황 | [data.go.kr/data/15110241](https://www.data.go.kr/data/15110241/openapi.do) |

**엘리스 모델 이름에는 접두어가 붙는다.** `claude-sonnet-5`가 아니라 `anthropic/claude-sonnet-5`다. 접두어 없이 쓰면 `model_not_found`가 난다.

## 쓰는 법

```python
from app.agents.commercial_area import analyze

result = analyze({
    "request_id": "request-001",
    "site": {
        "input_address": "서울특별시 송파구 위례광장로 120 155호",
        "road_address": "서울특별시 송파구 위례광장로 120",
        "detail_address": "155호",
        "latitude": 37.4748,
        "longitude": 127.1416,
    },
})
```

`AgentAnalysis`를 돌려주므로 `result.model_dump()`를 그대로 `DecisionRequest.analyses`에 넣으면 된다.

## 터미널에서 확인

```bash
cd backend
python examples/run_commercial_area.py --address "서울특별시 송파구 위례광장로 120 155호"
python examples/run_commercial_area.py --lat 37.4748 --lon 127.1416 --out examples/commercial_area/response.json
```

좌표를 주지 않으면 `geocode.py`가 주소를 좌표로 바꿔서 실행한다. 상세주소(`155호`, `3층 302호`)는 자동으로 떼어내 `site.detail_address`로 넣는다.

출력 예시는 `examples/commercial_area/response.json`에 있다.

```
  50m : 점포 59개. 기타 간이 음식점업이 9개로 1위이며 주변보다 약 2.7배 많습니다.
 100m : 점포 67개. 기타 간이 음식점업이 11개로 1위이며 주변보다 약 2.9배 많습니다.
 200m : 점포 119개. 중식 음식점업이 주변보다 약 5.9배로 가장 튀는 업종입니다.
 300m : 점포 580개. 이용 및 미용업이 72개로 1위입니다.
 500m : 점포 1241개. 기타 보건업이 주변보다 약 3.5배로 가장 두드러집니다.
```

## 업종 코드 마스터

반경 안에 **없는 업종까지 0으로 채우려면** 중분류 75종 목록이 필요하다. `data/upjong_codes.csv`로 동봉돼 있고, 갱신하려면 [상권업종분류 코드](https://www.data.go.kr/data/15067631/fileData.do)를 받아 아래를 실행한다.

```bash
python examples/build_upjong_master.py --official-csv <받은파일.csv>
```

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
| `partial` | LQ 기준 반경 실패, 프랜차이즈 실패, 업종 마스터 없음, 페이지 상한 초과 중 하나 | 있음 |
| `no_data` | 조회는 됐으나 반경 내 점포 0건 | 비어 있음 |
| `error` | 인증 실패·타임아웃·파싱 실패 | 비어 있음 |

`partial`이어도 `data`는 채워진다. 왜 partial인지는 항상 `warnings`에 적힌다.

## 알아둘 제약

- **API 쿼터가 하루 10,000건이다.** 같은 좌표 요청은 `backend/cache/`에 저장해 재사용한다. 강남 500m는 1회 분석에 5페이지, LQ용 2km는 48페이지가 나간다. LQ 기준 조회는 좌표를 250m 격자로 반올림해 같은 동네끼리 캐시를 공유한다.
- **반경 5개를 위해 API를 5번 부르지 않는다.** 500m 한 번 받아 좌표로 안쪽 반경을 직접 계산한다. API 실측값과 오차 0~2건으로 일치하는 것을 확인했다.
- **프랜차이즈 판정은 정확하지 않다.** 공정위 API에 반경 검색이 없어 브랜드명과 상호명을 문자열로 대조한다. 누락과 오탐이 있어 `confidence: "low"`로 표시한다.
- **`scope.period`는 조회일이다.** 소상공인 API가 원천 기준 분기를 응답에 담지 않는다. 세 에이전트의 `scope` 표기가 다르면 결정 에이전트가 "기준 기간이 다르다"는 한계를 자동으로 붙이므로 형식을 맞춰야 한다.
- **특화도는 점포 5개 미만 업종을 제외한다.** 표본이 1~2개면 배수가 튀어 순위가 무의미해진다.
- **모델 요약이 실패해도 전체는 실패하지 않는다.** `summary`가 비고 `warnings`에 사유가 남는다. 숫자가 본체다.
- **좌표 정확도가 결과를 바꾼다.** 지번 주소는 번지를 못 찾고 동 중심점으로 잡히는 경우가 있어 50~100m 결과가 흔들린다. `GEOCODING_API_KEY`에 카카오 REST 키를 넣으면 도로명·지번 모두 정확해진다.

## 테스트

```bash
cd backend
python -m unittest discover -s tests
```

36건이 네트워크 없이 돈다. 가짜 응답으로 계약 형식, status 전이, 모델 응답 파싱, 주소 분리를 검증한다.

## 데이터 출처

상가(상권)정보 — 소상공인시장진흥공단 (2026), data.go.kr
가맹정보 — 공정거래위원회 (2026), data.go.kr

공공누리 및 이용허락범위 제한없음 데이터는 **출처표시가 의무**다. 리포트와 화면에 위 문구를 넣는다.
