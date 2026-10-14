# 인구 계산·수집 모듈

유동·상주·직장 인구의 규모·분포·서울 비교·추세를 계산합니다.
공개 분석은 [로컬 자료 어댑터](../../local_data/adapter.py)가 고정한 분기 원문으로 계산하며,
이 폴더의 클라이언트는 자료 갱신·연구용입니다. 요청마다 서울 기본 자료 API를 호출하지 않습니다.

유동은 연속 5분기, 상주·직장은 유동의 최신 분기와 맞춥니다.
상권 선택과 분모를 공유하지만 세 모집단의 인원을 합산하지 않습니다.
반경과 겹치는 상권 전체를 포함할 수 있으므로 실제 범위와 결측을 결과에 남깁니다.

| 모듈 | 역할 |
| --- | --- |
| [models.py](models.py) · [schemas.py](schemas.py) | 원문 파싱과 계산 자료 형태 |
| [metrics.py](metrics.py) · [population.py](population.py) | 규모·분포·추세·상주/직장 계산 |
| [geo.py](geo.py) | 반경과 상권 겹침 |
| [baseline.py](baseline.py) | 서울 규모·시간대·연령 기준선 |
| [client.py](client.py) · [config.py](config.py) | 서울 비동기 수집과 설정 |

숫자는 결정론적 코드로 계산합니다. 업종 51종의 D 채점은 `app/agentic/scoring.py`,
새 근거와 최종 설명은 단일 decision이 담당합니다.
실제 영·자료 없음·잘못된 원문·미적용을 구분하고, 유동 분포로 주거·직장 인구를 임의 대체하지 않습니다.

갱신은 백엔드의 `python scripts/refresh_local_data.py`를 사용합니다.
요청 DB와 자료 DB의 구분·환경변수·전체 검사 명령은 [백엔드 README](../../../README.md)를 따릅니다.
