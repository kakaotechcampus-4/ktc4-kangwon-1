# 효율화 설계 — 모델 입력 줄이기(E1~E3)와 근거 색인 한 번에 만들기(E4)

작성: 2026-10-02 · 상태: 설계(구현 전) · 기준 브랜치: `refactor/pre-report`(`4d5a1c8`) 위에서 새 브랜치
관련: `docs/refactor-plan.md`(동작 보존 리팩터링, 완료), `docs/report-plan.md`(이 작업 **다음**)

구현자는 이 문서만 보고 고칠 수 있어야 합니다. 문서와 코드가 다르거나 문서가 정하지 않은 결정이 필요하면 **멈추고 질문**합니다.

---

## 0. 왜 하나 (실측)

실행 `validation_tool/runs/59205f79d9874292b77c01c9535819a2`(오금로 404, 브리핑 + 평가자 + 지도, LLM 23회, 91.7초):

- **입력 토큰 664,223 / 출력 12,486.** 비용과 대기 시간의 98%가 입력입니다.
- 브리핑 근거 제외 경고는 **2건**입니다(유동인구 1·상권 1·개폐업 0).

| 역할 | 호출 | 입력 토큰 | 비중 | 호출당 입력 |
| --- | --- | --- | --- | --- |
| 판정관 | 3 | 220,339 | 33% | 55k → 78k → 87k |
| 상권 전문가 | 3 | 163,600 | 25% | 58k · 58k · 47k |
| 개폐업 전문가 | 3 | 135,309 | 20% | 44k · 44k · 47k |
| 지도 전문가 | 9 | 65,701 | 10% | 2k → 4k → 9k → 16k → 28k (계속 커짐) |
| 평가자 4명 | 4 | 72,294 | 11% | 각 18k |
| 유동인구 전문가 | 1 | 6,980 | 1% | — |

**원인 세 가지 (코드로 확인)**

| # | 위치 | 낭비 |
| --- | --- | --- |
| E1 | `specialists/agent.py::write_brief` | 입력에 원자료 전체(`analysis`)와, 같은 값을 경로마다 다시 적은 `industry_paths`를 **둘 다** 넣음. `industry_paths`가 원자료보다 큼(상권 37k자 vs 78k자, 보완 후 개폐업 72k자 vs 150k자). 경로 문자열(`/by_middle/12/count`)이 값마다 반복되기 때문 |
| E2 | `specialists/agent.py::answer_query` | 판정관이 업종 4개만 물어도 원자료 전체 + 75개 업종 `industry_paths`를 다시 보냄. 다른 업종은 필요하면 읽는 도구(`get_industry_metrics` 등)가 이미 있음 |
| E3 | `orchestration/consult.py::_map_tools.search`의 `result_data()` | 검색할 때마다 **지도 자료 전체**(`data`)와 전체 `citations`를 돌려줌. 대화가 쌓이므로 검색 k번이면 입력이 k²에 비례해 커짐 |

**코드 쪽 (E4)**: `decision/context.py::build_context` 한 번에 `index_paths`가 9번(원자료마다 2~3번) 다시 계산되고, `scalar_records`는 방금 만든 경로를 다시 문자열 파싱해서 값을 찾습니다(4,625번). 지금 33ms라 모델 시간에 비하면 작지만, 같은 일을 반복하는 구조라 같이 고칩니다.

**목표**: 같은 주소·같은 설정에서 **입력 토큰 40% 이상 감소**(664k → 400k 이하, 기대치 약 300k), 근거 채택률은 나빠지지 않을 것.

---

## 1. 원칙

1. **검증은 지금과 같은 원자료로 합니다.** 모델에게 보여 주는 양만 줄이고, `validate_findings`·`can_cite`는 계속 원자료 전체로 검사합니다. 그래서 줄인 입력 때문에 틀린 근거가 통과하는 일은 없습니다.
2. **모델에게 보여 주는 인용 경로는 모두 검증을 통과해야 합니다.** (지도 때 세운 "안내 ⊆ 검증" 원칙을 전 전문가로 확장, 테스트로 강제)
3. **계약은 바꾸지 않습니다.** `schemas.py`, API 응답, DB 표, 판정관 입력은 그대로입니다. 바뀌는 것은 **전문가 모델에게 보내는 입력과 도구 결과의 모양**, 그리고 그에 맞춘 `specialists/prompt.md`뿐입니다.
4. **판정관 입력은 이번에 건드리지 않습니다.** 판정관 입력은 리포트 개편(`report-plan.md`)에서 출력 형식과 함께 다시 짭니다. 여기서 줄이면 개편 효과를 따로 잴 수 없습니다. (측정치는 9장에 남김)
5. 이 작업은 모델 입력을 바꾸므로 **결과가 달라질 수 있습니다.** 그래서 리팩터링과 별도 브랜치·PR이고, 유료 비교 실행으로 확인합니다.

---

## 2. E4 — 근거 색인을 한 번에 만들기 (`app/evidence/index.py`)

E1·E2의 압축 입력이 이 색인을 쓰므로 **먼저** 합니다. 동작은 바뀌지 않습니다(리팩터링 성격).

### 2.1 새 타입

```python
@dataclass(frozen=True)
class SourceRecord:
    path: str                 # JSON Pointer
    value: str | int | float  # 스칼라 값(bool 제외)
    owner: str | None         # 업종 코드, 공통 자료는 None

@dataclass(frozen=True)
class SourceIndex:
    owners: dict[str, str | None]      # 지금 index_paths()의 반환값과 같음(객체 경로 포함)
    records: tuple[SourceRecord, ...]  # 지금 scalar_records()와 같은 순서·내용
    radii: frozenset[Decimal]          # 지금 findings._radii(data)와 같음

    @classmethod
    def build(cls, data: dict) -> "SourceIndex": ...
```

- `build`는 **트리를 한 번만** 훑습니다. 지금 `index_paths.visit`이 경로·소유 업종을 정할 때 값도 이미 손에 있으므로, 그 자리에서 스칼라면 `SourceRecord`를 만들고 `*radius_m` 키면 `radii`에 넣습니다. `resolve_pointer`를 다시 부르지 않습니다.
- 판정 규칙(`citable`, `data_available`, `confidence == "none"`, `score_available`, 업종 충돌, `industry_counts` 특례)은 **한 글자도 바꾸지 않고** 옮깁니다.

### 2.2 기존 함수는 얇은 껍데기로

```python
def index_paths(data):    return SourceIndex.build(data).owners
def scalar_records(data): return [{"path": r.path, "value": r.value, "industry_code": r.owner} for r in SourceIndex.build(data).records]
```

- 이름·반환형을 유지해 기존 호출부와 테스트가 그대로 돕니다.
- 그다음 **같은 자료를 여러 번 색인하는 호출부**가 `SourceIndex`를 한 번 만들어 넘기게 바꿉니다:
  - `decision/context.py::build_context` — 원자료마다 한 번 만들어 `digest`·`neighborhood`·`industry_catalog`·`validate_findings`에 같이 넘김
  - `evidence/findings.py::validate_findings(..., index: SourceIndex | None = None)` — 없으면 만들고, 있으면 그것을 씀(`index_paths`·`_radii` 재계산 제거)
  - `evidence/index.py::industry_catalog`, `can_cite(..., indexed=)` — 이미 받는 인자가 있으면 `SourceIndex.owners`를 넘김
  - `specialists/agent.py::industry_paths` — E1에서 대체(3장)

### 2.3 확인
- **동등성 테스트**: 실측 고정 자료(`tests/fixtures/`의 지도 자료 + 이번에 추가할 상권·개폐업·유동인구 축약 자료)로 `SourceIndex.build(d).owners == 옛 index_paths(d)`, `records == 옛 scalar_records(d)`, `radii == 옛 _radii(d)`.
  옛 구현은 테스트 안에 복사해 두지 말고, **바꾸기 전 커밋에서 결과를 JSON으로 떠서** 고정 기대값으로 씁니다.
- 측정: `build_context` 1회 시간과 `index_paths` 호출 횟수(cProfile)를 커밋 본문에 전후 비교로 적습니다. 목표: 색인 계산은 원자료당 1번.

---

## 3. E1 — 브리핑 입력에서 중복 제거

### 3.1 새 입력 모양 (`write_brief`)

```json
{
  "agent_id": "commercial_area",
  "task": "브리핑",
  "source": {"status": "ok", "scope": {...}, "warnings": [...], "description": "..."},
  "facts": {
    "shared": {"": {"store_total": 878, "radius_m": 500}, "/by_radius/0": {"radius_m": 50, "store_total": 52}},
    "industries": {
      "I201": {"/by_middle/0": {"count": 82, "share": 0.093394, "lq": 1.0807, "density_per_km2": 104.4056}},
      "S209": {"/by_middle/41": {"count": 11, "lq": 1.4138}}
    }
  }
}
```

- `analysis`(원자료 전체)와 `industry_paths`를 **둘 다 빼고** `facts` 하나로 보냅니다.
- `facts`는 `SourceIndex.records`를 **부모 경로로 묶은 것**입니다. 값 하나의 인용 경로 = `묶음 키 + "/" + 필드명`. 예: `"/by_middle/0" + "/" + "count"` → `/by_middle/0/count`.
  - 묶음 키 = 레코드 경로에서 마지막 토큰을 뺀 부분, 필드명 = 마지막 토큰(이스케이프된 그대로).
  - 최상위 필드의 부모 경로는 빈 문자열 `""`입니다. 같은 규칙으로 `"" + "/" + "store_total"` → `/store_total`을 만듭니다.
  - 한 묶음 안에서 같은 필드가 중복되지 않으므로 정보 손실이 없습니다(원자료의 스칼라 전부, 경로 전부 복원 가능).
- `shared`에는 소유 업종이 없는 레코드(`owner is None`), `industries[코드]`에는 그 업종 레코드.
- `source`에는 원자료 바깥 봉투(`status`, `scope`, `warnings`)와 원자료의 최상위 문자열 중 설명 성격 필드(`description`, `summary`, `summary_text`, `interpretation`)만 넣습니다. 이 목록은 상수 `BRIEF_CONTEXT_KEYS`로 둡니다.
  - 단, `citable`로 막힌 값은 `facts`에 들어가지 않습니다(색인 규칙상 이미 제외). 설명 필드도 `citable: false`면 `source`에만 들어가고 인용 경로로는 안 보입니다.
- 생성 함수: `specialists/facts.py::build_facts(index: SourceIndex, *, codes: set[str] | None = None) -> dict` (E2에서 `codes`로 거름).

### 3.2 지시문 (`specialists/prompt.md`)
지우는 줄:
- "지도가 아닌 전문가의 업종 행 경로는 industry_paths[업종 코드]에 있는 path를 그대로 복사합니다. 배열 번호를 직접 세지 않습니다."

넣는 줄(같은 자리):
```markdown
- 지도가 아닌 전문가의 근거 경로는 facts에서 만듭니다. 경로 = 묶음 키 + "/" + 필드명입니다.
  예: facts.shared[""]["store_total"] → "/store_total", facts.industries["I201"]["/by_middle/0"]["count"] → "/by_middle/0/count". 최상위 부모 경로는 빈 문자열이며 배열 번호를 직접 세지 않습니다.
- 업종 주장은 facts.industries[그 업종 코드] 안의 경로만, 동네 공통 주장은 facts.shared의 경로만 씁니다.
  facts에 없는 업종은 업종별 주장을 만들지 않습니다.
```
"문장의 숫자는 복사한 항목의 value와 같아야 합니다" 류의 기존 줄은 "그 필드의 값과 같아야 합니다"로 바꿉니다.

### 3.3 왜 안전한가
- 모델이 볼 수 있는 숫자 집합은 지금과 같습니다(`industry_paths`·`analysis`에 있던 스칼라 = `facts`의 스칼라). 빠지는 것은 **중복 표현**과 **인용 불가 값**뿐입니다.
- 검증은 여전히 원자료로 하므로, 모델이 잘못 이어 붙인 경로는 지금처럼 "경로·업종 불일치"로 제외됩니다.

---

## 4. E2 — 되묻기 입력을 질문 업종으로 좁히기 (`answer_query`, 지도 제외)

- 입력 `data`·`industry_paths`를 빼고 `facts = build_facts(index, codes=set(query.industry_codes))`를 넣습니다.
  - `shared`는 항상 전부, `industries`는 질문 업종만.
  - `query.industry_codes`가 비어 있으면(동네 공통 질문) `industries`는 빈 객체.
- 지시문에 한 줄 추가:
  `- 되묻기 입력의 facts에는 질문한 업종만 있습니다. 다른 업종 비교가 꼭 필요하면 도구(get_industry_metrics·compare_industries 등)로 읽습니다.`
- 도구 결과도 같은 압축 형식으로: `consult.py::build_specialist_tools`의 읽기 도구들이 돌려주는 `records`(경로·값·업종 목록)를 `build_facts` 모양으로 바꿉니다. 같은 값이 경로 문자열과 함께 반복되는 문제가 도구 결과에도 있기 때문입니다.
- 보완 도구(`fetch_quarter_details` 등)가 원자료를 갱신한 뒤의 결과도 갱신된 원자료로 새 `SourceIndex`를 만들어 같은 모양으로 돌려줍니다.

---

## 5. E3 — 지도 도구 결과를 "이번 검색분"만 (`consult.py::_map_tools`)

`result_data()`가 매번 전체 `data`와 전체 `citations`를 돌려주는 것을 바꿉니다.

### 5.1 검색 도구 결과

```json
{
  "query_id": "q3",
  "query": "보습학원",
  "industry_code": "P105",
  "status": "ok",
  "total_count": 8,
  "match_summary": {"same": 5, "different": 3, "unclear": 0},
  "citations": {"P105": [{"path": "/industries/P105/sampled_count", "value": 13}, {"path": "/places/11575083/name", "value": "뉴멘토보습학원"}, ...]},
  "adopted": true
}
```

- `query_id`: 이번 검색이 관측에서 받은 `q{n}`.
- `citations`: **이번 검색의 질문 업종**(시설 검색이면 `_facility`)에 대한 `map_citations` 항목만. 같은 업종을 여러 검색어로 찾았다면 그 업종의 누적 동종 장소가 들어가므로 마지막 결과만 보면 됩니다.
- `data`(지도 자료 전체)는 **넣지 않습니다.** `different`·`unclear` 장소, 원본 카테고리 문자열은 모델이 인용할 수 없으므로 보여 줄 필요가 없습니다.
- 이미 같은 검색을 했으면(`cached`) 지금처럼 다시 조회하지 않고, 위 모양에 `"cached": true`.
- 실패·미채택이면 `{"query_id", "status", "error", "adopted": false}`만.

### 5.2 지도 전문가 첫 입력 (`answer_query`, 지도)
- `data`(이전 라운드 관측 전체)를 빼고 `queries` 요약(검색어·업종·건수·match_summary)을 넣습니다. `industry_terms`는 그대로.
- 이전 관측이 있으면 citations는 질문 업종 + _facility(시설 근거)를 넣는다. 시설 질문은 industry_codes가 비어 있으므로 시설 근거가 필요하다.

### 5.3 지시문
- 지도 전문가 절의 "도구 결과의 citations에 있는 path만 그대로 복사합니다" 줄은 유지.
- 추가: `- 검색 결과에는 그 검색의 업종 인용 목록만 옵니다. 앞선 검색의 인용 목록은 앞의 도구 결과에 그대로 남아 있습니다.`

---

## 6. 테스트 (모두 대역, 네트워크·유료 호출 없음)

새 파일 `backend/tests/test_specialist_payload.py` + 기존 테스트 갱신.

- [ ] **E4 동등성**: 고정 자료 4종으로 `SourceIndex`가 바꾸기 전 `index_paths`·`scalar_records`·`_radii`와 같음(2.3).
- [ ] **E4 호출 횟수**: `build_context` 1회에 원자료당 `SourceIndex.build`가 1번만 불림(patch로 셈).
- [ ] **안내 ⊆ 검증 (전 전문가)**: `build_facts` 결과의 모든 "묶음 키/필드"가 `can_cite(원자료, 경로, 그 업종 또는 None) is None`. 지도는 `map_citations`의 모든 경로가 `valid_map_path` 통과(기존 테스트 유지).
- [ ] **정보 보존**: `build_facts(index)`를 펼친 경로·값 집합 == `index.records`의 경로·값 집합(codes 없음).
- [ ] **E2 좁히기**: `codes={"I201"}`이면 `industries`에 I201만, `shared`는 전부.
- [ ] **E3 증분**: 검색 3번 후 마지막 도구 결과 크기가 첫 결과의 2배 이하(고정 자료), 결과에 `data` 키 없음, 그 검색 업종의 citations만 있음.
- [ ] **크기 상한 회귀**: 고정 자료로 만든 브리핑 입력 JSON 길이가 바꾸기 전 대비 **개폐업·상권은 50% 이하, 유동인구는 110% 이하**(기대값은 바꾸기 전 커밋에서 떠 둔 숫자). 전체 입력 400k 토큰 목표는 유료 비교에서 그대로 확인합니다.
  - 유동인구는 원래 중복 목록이 없고 배열 묶음 키가 늘어 입력이 증가하지만, 실행당 1회라 전체 입력에 미치는 영향은 미미합니다.
- [ ] **기존 흐름**: 목업 분석 → 질문 → 답변 → 완료(브리핑·평가자 켬)에서 전문가 답변 상태와 근거 채택 수가 바꾸기 전과 같음. 목업 전문가(`api/v1/mock.py::specialist`)가 새 입력 모양에서 인용 경로를 고르도록 함께 수정.
- [ ] 전체: `ruff check`, `ruff format --check`, `mypy`, `unittest discover`, `scripts/build_industry_catalog.py --check`.

---

## 7. 측정 도구 (무료, 커밋 대상)

`backend/scripts/measure_payloads.py`:
- 인자: 실행 폴더(`validation_tool/runs/<id>`).
- 저장된 원자료·관측으로 브리핑·되묻기·지도 도구 결과 입력을 **지금 코드로** 만들어 역할별 글자 수와 JSON 크기를 표로 출력. 모델을 부르지 않습니다.
- 각 커밋(E1·E2·E3) 본문에 `59205f79` 기준 전후 표를 붙입니다.

---

## 8. 커밋 순서 (브랜치 `perf/specialist-inputs`, `refactor/pre-report`에서 분기)

| # | 커밋 메시지(예) | 내용 | 동작 변화 |
| --- | --- | --- | --- |
| P1 | `test: 근거 색인·전문가 입력 기준값 고정` | 바꾸기 전 결과를 고정 자료·기대값으로 저장, `measure_payloads.py` 추가 | 없음 |
| P2 | `perf: 근거 색인을 한 번에 만들고 재사용` | E4 (`SourceIndex`, 호출부 재사용) | 없음 |
| P3 | `perf: 브리핑 입력을 묶음 경로 facts로 압축` | E1 + 지시문 + 목업 전문가 | **모델 입력 변경** |
| P4 | `perf: 되묻기 입력과 읽기 도구 결과를 질문 업종으로 좁힘` | E2 | **모델 입력 변경** |
| P5 | `perf: 지도 도구 결과를 이번 검색분만 돌려줌` | E3 | **모델 입력 변경** |
| P6 | `docs: 효율화 측정 결과와 전문가 입력 형식 기록` | `backend/README.md`·`multi-agent-design.md`의 전문가 입력 설명 갱신, 이 문서 10장에 결과 | 없음 |

- 커밋마다 6장 검사 전부 통과 후 커밋.
- P3·P4·P5 뒤에는 목업 끝까지 흐름 1회.
- **유료 비교(사용자 승인 후, P5 뒤 1회)**: 오금로 404, 브리핑 + 평가자 + 지도, `59205f79`와 같은 설정. 확인:
  1. 입력 토큰 합계 400k 이하
  2. 브리핑 3개 모두 `source=model`, 근거 제외 경고 수가 `59205f79`(2건)보다 많지 않음
  3. 지도 답변 `answered/partial`, 지도 근거 제외 0
  4. 소요 시간
  추천 결과가 달라지는 것 자체는 실패가 아닙니다(실행 간 변동은 B부 안정성 시험에서 따로 다룸, 사용자 결정 2026-10-02).

---

## 9. 이번에 하지 않는 것

| 항목 | 이유·시기 |
| --- | --- |
| 판정관 입력 축소(55k → 87k로 커지는 문제) | 리포트 개편에서 출력 형식과 함께 재설계. 측정치는 이 문서 0장 |
| 평가자 입력 축소(각 18k) | 평가자 페르소나·지시문 정비 때 |
| 프롬프트 캐시(공급자 기능) 활용 | 공급자·BASE_URL별 지원 확인 후 별도 |
| 숫자 정규식 → 구조화 수치 | 리포트 개편 R-3 |
| 실행 간 결과 변동 조정 | 리팩터링 → 리포트 → 평가자 정비 이후(사용자 결정) |

## 10. 결과 (구현 후 기록)
_(P6에서 채움: 커밋별 입력 크기 전후, 유료 비교 결과)_
