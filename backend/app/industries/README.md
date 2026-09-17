# 팀 공통 업종 어휘 — 소상공인 중분류 75종

세 에이전트가 같은 업종을 가리킬 코드가 없어서 만들었다.

| 에이전트 | 예전에 쓰던 표현 |
| --- | --- |
| 경쟁업체 | 소상공인 중분류 코드 `I201` |
| 개폐업 | 자체 정수 `industry_id` 1~70 |
| 유동인구 | 업종 개념 없음 |
| 결정 | `Category(major, middle)` 자유 문자열 |

`app/schemas.py`의 `Category`가 유일한 접점인데 둘 다 제약 없는 문자열이라, 같은 한식이
`한식음식점` / `한식 음식점업` / `중식` 으로 갈려 있었다. 이 어휘가 그 기준을 세운다.

## 쓰는 법

```python
from app.industries import lookup

lookup.find_by_name("한식음식점")  # 표기가 달라도 같은 업종으로 찾는다
lookup.from_seoul("CS100005")  # 서울시 생활밀접업종 코드 → 우리 업종
lookup.from_legacy70(33)  # 개폐업 70업종 ID → 우리 업종 (여럿일 수 있다)
lookup.as_category("I201")  # ("음식점업", "한식 음식점업") — Category 에 그대로 넣는다
```

표 자체가 필요하면 `catalog.py`를 직접 읽는다. 개폐업 `mapping.py`와 이름을 맞춰 두었다.

| `mapping.py` | 여기 |
| --- | --- |
| `SERVICE_INDUSTRIES` (75, 공통 상수 별칭) | `INDUSTRIES` (75) |
| `SEOUL_TO_SERVICE` | `SEOUL_TO_INDUSTRY` |
| `EXCLUDED_SEOUL_INDUSTRIES` | `EXCLUDED_SEOUL_INDUSTRIES` |
| `UNSUPPORTED_SERVICE_INDUSTRIES` | `INDUSTRIES_WITHOUT_SEOUL` (25) |

## 구성

```
75종
 ├─ 50종  서울시 생활밀접업종 99개가 여기로 접힌다
 └─ 25종  소상공인 단독 — 서울시 100대에 없다
```

단독 25종에 광고 · 시장조사 · 경영컨설팅 · 엔지니어링 · 병원 · 기타 보건 · 마사지 · 장례가 들어 있다.
서울시 자료가 "생활밀접"만 다뤄 빠진 자리를 우리 전국 자료가 메운다.

서울시 `CS300043 전자상거래업`은 **제외**한다. 무점포라 상가 자료에 잡히지 않는다.

## 고치는 법

원본은 `data/*.csv` 셋이고, `catalog.py` 와 `data/industry_master.json` 은 **자동 생성물**이다.
생성물은 직접 고치지 않는다.

| 파일 | 내용 |
| --- | --- |
| `data/industries.csv` | 75종 마스터 |
| `data/seoul_to_industry.csv` | 서울시 99 → 중분류 |
| `data/legacy70_to_industry.csv` | 개폐업 70 → 중분류 (마이그레이션용) |
| `data/industry_master.json` | **생성물.** 개폐업 `industry_master.json` 과 같은 모양 |

```bash
cd backend
python scripts/build_industry_catalog.py            # 검증 후 catalog.py · industry_master.json 재생성
python scripts/build_industry_catalog.py --check    # 검증만. CI 가 이걸 돌린다
```

### ⚠️ CSV 를 엑셀로 저장하지 말 것

엑셀에서 열었다 저장하면 인코딩이 cp949 로 바뀌고 행이 날아간다. 실제로 175행짜리 파일이
131행이 된 적이 있다. 빌드가 BOM 없는 파일을 거부하므로 런타임까지 번지지는 않지만,
**보기만 하고 닫거나 복사본을 열자.**

## 알아둘 것

**서울시가 우리보다 잘게 쪼개져 있다.** 99개가 50개 중분류로 접히므로 **합산은 맞지만 되돌릴 수 없다.**

```
제과점 · 패스트푸드점 · 치킨전문점 · 분식전문점  →  I210 기타 간이 음식점업
일반의원 · 치과의원 · 한의원                   →  Q102 의원
```

`I210` 점포 수를 보고 그게 치킨집이었는지 제과점이었는지는 알 수 없다.

**개폐업 점수는 그대로 옮기면 안 된다.** 개폐업이 주는 건 개수가 아니라 0~100 점수인데,
70 → 75 변환이 양방향 N:M 이다. `from_legacy70(33)` 이 셋을 돌려주고, 반대로 `Q102` 에는
개폐업 3업종이 몰린다. 점수 3개를 산술평균하면 점포 1개짜리와 100개짜리를 같은 무게로 섞는다.
신규 개폐업 분석은 원본 서울시 건수를 75개 업종으로 먼저 합산한 뒤 기존 상대 점수를
재계산한다. 비율은 합산 분자/분모에서 계산하고 분모 0은 null이다.
`lookup.from_legacy70()`는 과거 결과 조회용 연결만 제공하며 과거 점수를 신규 점수로 변환하지 않는다.

신규 `AgentAnalysis.data.taxonomy.id`는 `sbiz-middle-75`이며 카탈로그 버전을 함께 기록한다.
`taxonomy.version`은 생성 카탈로그의 `CATALOG_VERSION`(원본 CSV 내용의 해시)이며 분석 실행 버전이 아니다.
공통 `Category` 계약은 기존 `major`/`middle` 두 문자열을 유지한다.
개폐업 `industry_id`는 `I201` 같은 문자열이다. 25개 미지원 업종은 `unsupported`,
지원되지만 조회되지 않은 업종은 `missing`, 원천 업종·분기·건수 일부 누락은 `incomplete`,
완전한 관측은 `observed`로 구분한다. 관측 0은 유지하며 부분 합계를 완전 집계로 표시하지 않는다.
동일 분기·상권·원본 업종 행은 완전히 같은 행만 중복 제거하고 상충 행은 오류로 처리한다.

상권 분석은 운영 마스터 누락·구조 오류를 설정 오류로 반환한다. 알 수 없는 중분류는
`coverage.unmapped_store_count`로 표시하며 75개 업종에 추정 배분하지 않는다.
테스트 등에서 주입한 별도 마스터는 `custom-middle`로 표시한다.

`examples/fixtures/business_lifecycle_*.json`은 70개 어휘를 쓰던 과거 예제다.
신규 formatter에는 사용할 수 없고 기존 DB 기록도 자동 변환하지 않는다.

**서울시 연결 99건 중 53건이 모델 판정이다.** `data/seoul_to_industry.csv` 의 `match_method` 가
`모델` 인 행은 사람 검수를 거치지 않았다. `근거 소분류`(`evidence_small`) 칸을 보면
무엇을 보고 판단했는지 알 수 있다.
