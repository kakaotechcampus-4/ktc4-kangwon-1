# 카카오맵 선택적 조회 도구

최종판단이 주변 업종·시설 확인을 요청하면 오케스트레이터가 실행한다.
기존 세 분석을 대체하지 않는다. 실제 영업 여부·입점 가능성을 보증하지 않는다.

## 진입점

- `observe(task, plan, ...)`: 서비스 연결용. 장소 원본·질문별 동종 판단·관측을 반환.
- 서비스에는 `execute_analysis(..., map_lookup=observe)`로 명시적으로 주입한다.
- 최종판단은 직접 API를 호출하지 않는다. 질문 답변 후에는 저장된 관측만 재사용한다.

## 처리

1. 업종 코드와 검색 표현 또는 시설 코드를 검증한다.
2. 최대 8개 요청의 첫 페이지를 병렬 조회한다. 검색당 최대 15건이다.
3. 장소 ID를 중복 제거하고 원본 분류를 보존한다.
4. 카카오 카테고리와 업종 검색어 규칙으로 category_match·name_match·unknown을 판단한다.
5. 기존 계약은 category_match/name_match를 same, unknown을 unclear로 연결해 질문별 표본을 집계한다.

일치 상태는 코드 규칙이며 실제 경쟁점 확정 판정이 아니다. LLM·모델별 매핑 캐시를 사용하지 않는다.
검색어는 생성된 industry_terms의 소분류 설명을 보고 업종당 일상어 1~3개로 선택한다.
카카오 분류 제한은 P105(AC5), Q102(HP8)에 적용한다.

## 결과 해석

| 필드                     | 의미                                                                 |
| ------------------------ | -------------------------------------------------------------------- |
| queries.total_count      | 카카오 검색 결과 건수. 실제 영업 점포 전수가 아님                    |
| queries.matches          | 질문 업종 기준 장소별 same·different·unclear. 시설·옛 기록은 빈 값   |
| queries.place_ids        | 반환된 조회 표본. 다른 검색과 중복될 수 있음                         |
| places                   | 장소 ID로 중복 제거한 원본. mapping_*·industry_code는 옛 기록 호환용 |
| industries.sampled_count | 질문 업종의 동종 표본 수. 전체 점포 수가 아님                        |
| queried_at               | UTC 조회 시각. 분기 통계 기준일과 다름                               |

관측 근거는 `map_analysis` 출처와 관측 data 내부 경로로 인용한다.
다른 업종·불확실 장소도 원본은 보존하며 동종 표본 수에서만 제외한다.
검색할 때마다 map_citations가 검증을 통과하는 경로만 제공한다. 장소 이름·거리는 업종별 가까운 10곳까지 안내한다.
문자열 일치율로 전체 검색 건수를 보정하지 않는다.
최근접은 반환된 유효 표본 안의 장소다. 거리를 도보 시간으로 환산하지 않는다.
전체 학교 분류 조회를 초등학교만의 결과로 해석하지 않는다.
카카오 등록 누락이 있을 수 있어 검색 0건을 실제 점포 없음으로 단정하지 않는다.

## 설정

- `GEOCODING_API_KEY`: 기존 주소 변환과 같은 카카오 REST 키.
- `MAP_ANALYSIS_MAX_CONCURRENCY`: 기본 4.

키·외부 API 원문 오류는 관측에 저장하지 않는다. API 오류와 정상 0건은 구분한다.
시설 예제는 `python examples/run_map_analysis.py --address "서울 송파구 오금로 404" --query 지하철역`이다.
업종 키워드는 `--industry-code I212 --query 커피`처럼 공통 코드를 함께 전달하며 카테고리·이름 규칙으로 일치 상태를 판단하며 LLM을 호출하지 않는다.
전체 옵션은 `python examples/run_map_analysis.py --help`로 확인한다.
대역 검증은 백엔드에서 `python -m unittest discover -s tests -p "test_map*.py"`로 실행한다.
