# 팀 공통 업종 어휘 — 서비스 통합 업종 51개

commercial_area, business_lifecycle, map_analysis, decision이 공유하는 최종 추천
taxonomy다. 서비스 업종은 원천 코드와 구분되는 `SV001`~`SV051`을 사용하며,
`taxonomy.id`는 `service-industry-51`이다. floating_population은 업종별 분석이
아니므로 이 taxonomy에 의존하지 않는다.

## 쓰는 법

```python
from app.industries import lookup

lookup.find_by_name("한식 음식점")
lookup.from_seoul("CS100005")  # 서울시 코드 → SV024
lookup.as_category("SV020")  # ("음식점업", "한식 음식점")
```

런타임 기준은 자동 생성된 `catalog.py`다. 원본 CSV와 역할은 다음과 같다.

| 파일 | 내용 |
| --- | --- |
| `data/industries.csv` | 51개 서비스 Master |
| `data/public_to_industry.csv` | 소상공인 원천 중·소분류 → 서비스 업종 |
| `data/seoul_to_industry.csv` | 서울시 생활밀접업종 → 서비스 업종 |
| `data/legacy70_to_industry.csv` | 과거 70업종 조회 호환용 원천표 |

```bash
cd backend
python scripts/build_industry_catalog.py
python scripts/build_industry_catalog.py --check
```

CSV는 BOM 있는 UTF-8만 허용한다. `catalog.py`는 직접 수정하지 않는다.

## 원천 매핑 원칙

- commercial_area는 점포 원자료를 서비스 업종으로 먼저 매핑하고 count, share,
  LQ, 반경 집계를 다시 계산한다.
- G213과 G215는 중분류 전체를 복제하지 않는다. `indsSclsCd`를 사용해 각각
  `SV002`/`SV009`, `SV010`/`SV011`로 한 번만 배정한다. 알 수 없는 소분류는
  `unmapped_store_count`로 남긴다.
- business_lifecycle는 분기별 CS 원천 count를 서비스 업종별로 먼저 합산한 뒤
  rate, trend, score를 다시 계산한다. 원천 score나 rate를 평균하지 않는다.
- `SV046`~`SV051`은 서울시 Lifecycle 직접 대응이 없다. 0으로 채우지 않고
  `unsupported`, `score_available=false`, 지표 `null`로 유지한다.
- 지원 업종의 원천·분기 일부가 빠지면 `incomplete`, 전혀 관측되지 않으면
  `missing`, 완전한 관측은 `observed`다. 실제 관측 0과 결측은 구분한다.

서울시 연결은 팀 확정표 90행이며, 지정되지 않은 10개 서울시 업종은 명시적으로
제외한다. `N110`의 Lifecycle 대응은 `CS200046 의류임대`만 사용한다.

과거 `legacy70` 연결은 저장 결과 조회 호환용일 뿐 신규 Lifecycle 계산 경로가
아니다. 과거 점수를 51개 점수로 복제하거나 평균하지 않는다.

`taxonomy.version`은 원본 CSV 내용에서 만든 `CATALOG_VERSION`이다. Master가
바뀌면 catalog 생성 스크립트를 실행하고 전체 테스트로 세 Agent와 Decision의
code/name 집합이 일치하는지 확인한다.
