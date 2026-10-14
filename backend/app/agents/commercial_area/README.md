# 상권 계산·수집 모듈

고정된 서울 상가 CSV에서 요청 반경의 점포 수·업종 구성·밀도·LQ·프랜차이즈 지표를 계산합니다.
공개 분석 진입점은 [로컬 자료 어댑터](../../local_data/adapter.py)이며 수집 클라이언트는 갱신·연구용으로 유지합니다.

공통 서비스 업종은 [51종 카탈로그](../../industries/README.md)를 사용합니다.
반경에 없는 업종의 실제 영과 매핑 불완전·조회 실패를 구분합니다.
LQ는 업종 구성비의 비교이며 점포 수나 매출의 배수가 아닙니다.
요청 반경·비교 반경·자치구 기준선의 분모를 함께 표시하고 서울 밖 점포 누락을 알립니다.

| 모듈 | 역할 |
| --- | --- |
| [metrics.py](metrics.py) | 거리·집계·밀도·경쟁 지표 |
| [industries.py](industries.py) | 원문 업종 매핑·분할 누락 검사 |
| [baseline.py](baseline.py) | 음식점·51업종 서울 밀도 백분위 |
| [franchise.py](franchise.py) | 공정위 브랜드 캐시·문자열 판정 |
| [client.py](client.py) · [config.py](config.py) | 비동기 수집과 설정 |
| [trade_areas.py](trade_areas.py) | 밀도 기준선의 서울 상권 중심점 |

51업종 밀도 경계표는 [density_percentiles.csv](../../industries/data/density_percentiles.csv)에서 읽습니다.
기존 음식점 전체 경계표와 업종별 표는 별도입니다.
완전한 표본을 준비한 뒤 `python scripts/build_density_baseline.py --industries --emit`으로 갱신합니다.
부분 수집·분할 매핑 누락은 운영 CSV를 덮어쓰지 않습니다.

C 채점은 `app/agentic/scoring.py`에서 수행합니다. 새 근거를 해석하는 L 판단은 decision이 담당합니다.
지도 검색 표본을 서울 CSV 전수와 더하거나 검색 영을 실제 점포 없음으로 단정하지 않습니다.
분기·공간 범위와 좌표 정확도가 결과에 영향을 주며 브랜드 판정은 누락·오탐이 있을 수 있습니다.

실행·자료 적재·검사는 [백엔드 README](../../../README.md)를 따릅니다.
[기존 지표 명세](../../../../docs/INDEX_commercial_area.md)의 과거 실행값은 현재 자료 계약과 구분해 읽으세요.
