# 멀티에이전트 전환 설계 (MVP 3.0 제안)

> 상태: **제안 — 팀 합의 필요**. `schemas.py` 공통 계약을 바꾸므로 AGENTS.md 규칙 1에 따라 PR 합의 후 구현합니다.
> 관련 문서: [TECH_DECISIONS.md](TECH_DECISIONS.md) (ADR-02 · 03 · 09를 이 설계로 갱신 예정), [mvp20-progress.md](mvp20-progress.md)

## 1. 왜 바꾸나

MVP 2.0에서 분석 경로의 LLM을 결정론적 계산으로 바꾼 결과, 숫자는 정확해지고 빨라졌지만 **서비스가 에이전트처럼 동작하지 않습니다.**

| 관찰 | 근거 |
| --- | --- |
| 실제 실행 trace가 `세 분석(계산) → decision_model 1번 → completed`뿐이다 | 오금로 404 · 500m 실제 실행(33.9초) |
| 판정관의 보완 · 지도 · 질문 사용률 0/3 | 실측 3곳 (`mvp20-progress.md`) |
| 판정관이 "확인이 필요하다"고 **적어 놓고 확인하지 않는다** | 세탁업 주의: "세탁 설비 · 배수 · 인근 직접 경쟁 위치 확인 필요" — 질문 항목(`space_condition`, `existing_facilities`)과 지도 조회가 준비돼 있었음 |
| 판정 입력이 세 보고서 원형 약 100KB + 경로 목록 | 인구 8KB · 개폐업 56KB(점수 없는 47개 업종 포함) · 상권 36KB |
| 에이전트 사이 대화가 없다 | 분석 → 판정 단방향, 보완은 등록된 2개 작업뿐 |

지시문(`decision/prompt.md`)도 도구 사용을 억제합니다 ("질문은 필수가 아닙니다", "요청 의무가 아닙니다", "partial이나 빈 필드만으로 질문하지 마세요"). 0/3은 "도구가 필요 없다"의 증거라기보다 **도구를 쓰지 않게 설계된 결과**입니다.

## 2. 목표와 비목표

**목표**
1. 도메인별 **전문가 에이전트 4개**(인구 · 개폐업 · 상권 · 지도)와 **판정 에이전트(감독) 1개**가 대화하며 판단하는 구조
2. 판정관이 **되묻기(전문가) · 질문(임대인)**으로 부족한 정보를 스스로 채우고, 그 과정이 trace에 보인다
3. 판정 입력을 "원형 보고서 전부"에서 "브리핑 + 코드가 만든 업종 요약표 + 필요한 상세"로 줄인다
4. MVP 2.0의 강점 유지 — **숫자는 코드가 계산**, 근거 경로 검증, 실패 격리, 횟수 상한

**비목표**
- 계산을 LLM에게 되돌리지 않는다 (폐업률 · LQ · 점수 · 인구 지표는 계속 코드)
- 실행 순서를 고르는 "진행자 LLM"을 되살리지 않는다 (순서가 고정인 곳은 LangGraph 엣지)
- 무제한 루프 · 에이전트끼리의 자유 대화 (모든 대화는 판정관을 거치고 라운드 상한이 있다)

## 3. 구조

```
                ┌──────────────────── 판정 에이전트 (감독, LLM) ────────────────────┐
                │ 브리핑 · 업종 요약표를 읽고 후보를 좁힘 → 되묻기 / 질문 → 최종판단        │
                └────┬────────────┬─────────────┬─────────────┬─────────────┬────┘
                  되묻기·답변    되묻기·답변     되묻기·답변     되묻기·답변      질문·답변
                     │            │             │             │             │
               인구 에이전트   개폐업 에이전트   상권 에이전트   지도 에이전트     임대인(사람)
                  (LLM)         (LLM)          (LLM)         (LLM)
                     │            │             │             │
          ─── 도구 = 지금의 결정론적 코드 (API 수집 · 집계 · 폐업률 · LQ · 지도 검색 · 매핑) ───
```

### 역할 분담

| 역할 | LLM이 하는 일 | 코드가 하는 일 |
| --- | --- | --- |
| **전문가 에이전트** (4) | ① 자기 도구 선택(상세 분기 조회, 기준 반경 재조회 등) ② 브리핑 작성 ③ 판정관 되묻기에 도구로 확인해 답변 | 원자료 수집 · 계산(`analyze()` 그대로), 도구 실행, 브리핑 근거 검증 |
| **판정 에이전트** (1) | 후보 좁히기, 되묻기 · 질문 선택, 최종 추천과 이유 문장 | 입력 구성(업종 요약표), 근거 경로 검증 · 교정, 저장 |
| **LangGraph** | — | 고정 단계 + 판정 뒤 분기, 라운드 · 호출 예산, 타임아웃 |

**원칙: LLM은 숫자를 만들지 않는다.** 전문가 · 판정관 모두 도구 결과와 계산된 자료를 읽고 해석 · 선택만 합니다. 모든 주장은 계산된 자료의 JSON Pointer 경로를 근거로 붙이고 코드가 확인합니다.

## 4. 실행 흐름

```
prepare_address
  → run_analyses        # 변경 없음: 세 분석 계산을 병렬 실행, AgentAnalysis 저장
  → write_briefs        # 신규: 인구 · 개폐업 · 상권 전문가가 병렬로 브리핑 작성 (지도는 되묻기 때만)
  → evaluate_decision   # 판정관: 브리핑 + 업종 요약표 입력
       ├─ final            → 근거 검증 → 저장 → END
       ├─ ask_specialists  → consult (전문가 병렬 답변) → evaluate_decision   # 최대 2라운드
       └─ ask_user         → 질문 저장 → 대기 → (답변) → evaluate_decision
```

- 기존 `execute_supplement`, `execute_map`은 **`consult`로 흡수**합니다. 판정관은 "무엇이 궁금한지"만 묻고, 어떤 도구(보완 조회 · 지도 검색)를 쓸지는 전문가가 고릅니다.
- `write_briefs` 실패는 분석 실패가 아닙니다. 해당 전문가 브리핑은 **코드가 만든 대체 요약**(§5.4)으로 바꾸고 `limitations`에 남깁니다.
- 임대인 답변 뒤에도 남은 라운드·예산이 있으면 **전문가 되묻기는 할 수 있습니다.** 임대인에게 다시 묻는 것(재질문)은 금지합니다.
- 판정관이 같은 전문가에게 질문을 여러 개 보내면 **첫 질문만 남깁니다.** 허용되지 않은 전문가 질문은 빼고, 남는 질문이 없을 때만 오류로 처리합니다.

### 예산 (구현값, 2026-09-29 실측 후 조정)

| 항목 | 상한 | 비고 |
| --- | --- | --- |
| 브리핑의 도구 호출 | 2회 + 정리 1회 | `graph.py`의 `BRIEF_STEPS=3` |
| 되묻기 답변의 도구 호출 | 최대 4회 + 정리 1회 | 남은 호출을 질문받은 전문가 수로 나눠 배정. 마지막 차례는 `finish`만 허용 |
| 되묻기 라운드 | 2 | 라운드당 전문가 최대 3명(전문가별 1질문). 남은 호출이 3회 미만이면 되묻기 불가 |
| 임대인 질문 | 1회 · 최대 3항목 | 답변 후 재질문 없음 |
| 요청 전체 LLM 호출 | 24회 | 교정·지도 매핑 포함. 마지막 2회는 최종판단·교정 몫 |
| 전체 시간 | 600초 | 기존 `ANALYSIS_TIMEOUT_SECONDS` 유지, 질문 대기 제외 |
| `recursion_limit` | 32 | 기존 유지 |

처음 초안은 12회였습니다. 실측에서 브리핑 4회 + 판정 1회 + 전문가 도구 5회 만에 예산이 바닥나
되물은 전문가 3명이 모두 답변을 정리하지 못했습니다. 그래서 24회로 늘리고 차례를 미리 배정하도록 바꿨습니다.
지도 전문가는 검색 한 번이 매핑 호출을 한 번 더 쓰므로 같은 몫에서 차례를 적게 받습니다.
측정 결과는 [진행 기록](multi-agent-progress.md#실측과-수정-2026-09-29)에 있습니다.

## 5. 계약 초안 (`schemas.py` 추가분)

기존 `AnalysisTask` · `AgentAnalysis` · `DecisionResult`는 **바꾸지 않습니다.** 모두 추가형입니다.

### 5.1 브리핑

```python
SpecialistId = Literal["floating_population", "business_lifecycle", "commercial_area", "map_analysis"]

class EvidenceRef(Schema):
    path: Text                       # 자기 AgentAnalysis.data 안의 JSON Pointer

class Finding(Schema):
    claim: Annotated[str, Field(min_length=1, max_length=200)]
    signal: Literal["positive", "negative", "caution", "context"]
    industry_code: Text | None = None      # 업종 신호면 공통 코드, 동네 성격이면 None
    evidence: list[EvidenceRef] = Field(min_length=1, max_length=3)

class AgentBrief(Schema):
    request_id: Text
    agent_id: SpecialistId
    source: Literal["model", "fallback"]   # fallback = 코드가 만든 대체 요약
    headline: Annotated[str, Field(min_length=1, max_length=200)]
    findings: list[Finding] = Field(max_length=8)
    limitations: list[Text] = Field(default_factory=list)
    tool_calls: list["ToolCallRecord"] = Field(default_factory=list)
```

### 5.2 되묻기와 답변

```python
class SpecialistQuery(Schema):
    agent_id: SpecialistId
    question: Annotated[str, Field(min_length=1, max_length=300)]
    industry_codes: list[Text] = Field(default_factory=list, max_length=5)
    why_needed: Text
    expected_impact: Text

class ConsultPlan(Schema):                 # 판정관 출력의 새 분기 (MapLookupPlan · SupplementPlan 대체)
    action: Literal["ask_specialists"]
    queries: list[SpecialistQuery] = Field(min_length=1, max_length=3)   # 에이전트별 1개

class SpecialistAnswer(Schema):
    request_id: Text
    round: Annotated[int, Field(ge=1, le=2)]
    query: SpecialistQuery
    status: Literal["answered", "partial", "unavailable"]
    findings: list[Finding] = Field(max_length=5)
    analysis: AgentAnalysis | None = None  # 도구로 자료가 추가됐으면 갱신된 분석(기존 보완 채택 규칙 적용)
    tool_calls: list["ToolCallRecord"] = Field(default_factory=list)

class ToolCallRecord(Schema):
    tool: Text
    arguments: dict[str, JsonValue]
    status: Literal["ok", "error", "rejected"]
    elapsed_ms: Annotated[int, Field(ge=0)]
```

### 5.3 판정관 입력

| 항목 | 내용 |
| --- | --- |
| `briefs` | 전문가 브리핑 3개(지도는 되묻기 후 추가) |
| `industry_digest` | **코드가 만드는** 75개 업종 한 줄 요약표 — 업종별 점포 수 · LQ · 석 달 평균 폐업률 · 순증감률 · 점수 · 신뢰도 · 인용 가능 경로. 전문가가 빠뜨린 업종도 판정관이 볼 수 있게 하는 안전장치 |
| `neighborhood` | 인구 요약 · 서울 비교 · 유형 등 업종과 무관한 동네 정보(인용 가능 경로 포함) |
| `answers` | 되묻기 답변 · 임대인 답변 |
| `industry_evidence` | 후보 업종(브리핑 · 요약표 상위 · 답변에 등장)에 한정한 경로 목록 |

원형 `AgentAnalysis.data`는 저장만 하고 판정 입력에서 뺍니다. 판정관의 `Evidence.path`는 지금처럼 원형 자료를 가리키므로 **근거 검증 · 프론트 근거 보기는 변경이 없습니다.**

### 5.4 대체 요약 (fallback)

브리핑 LLM이 실패 · 시간 초과 · 검증 실패하면, 코드가 `industry_digest` 상 · 하위 업종과 경고로 `AgentBrief(source="fallback")`를 만듭니다. 판정은 계속 진행하고 `limitations`에 "전문가 브리핑 없이 요약표로 판단"을 남깁니다.

## 6. 전문가별 도구

도구는 **모두 기존 코드의 래퍼**입니다. 대부분 이미 계산된 `AgentAnalysis.data`를 읽는 읽기 전용 도구라 외부 호출 · 비용이 없습니다.

| 전문가 | 도구 | 원본 코드 | 외부 호출 |
| --- | --- | --- | --- |
| 인구 | `get_summary`, `get_trend(quarters)`, `get_time_profile(segment)`, `compare_seoul(metric)` | `floating_population` 계산 결과 | 없음 |
| 개폐업 | `get_industry_metrics(codes)`, `compare_industries(codes)`, `fetch_quarter_details(codes)` | `business_lifecycle` 결과, 기존 보완 `fetch_quarter_details` | 상세 조회만 |
| 상권 | `get_industry_counts(codes)`, `get_radius_breakdown(code)`, `get_district_specialization()`, `retry_lq_baseline()` | `commercial_area` 결과, 기존 보완 `retry_lq_baseline` | 재조회만 |
| 지도 | `search_industry(code, query)`, `search_facility(code)` | 기존 `execute_map` · `map_categories`(매핑 캐시) | 카카오 |

- 외부 호출 도구의 결과 채택은 **기존 `eligible()` · `accept()` 규칙을 그대로** 씁니다 (원본 보존 + 합계 재계산 비교, fail-closed).
- 지도 에이전트는 초기 브리핑이 없고 되묻기를 받았을 때만 실행합니다(비용 통제).

## 7. 검증 규칙

1. **브리핑 · 답변의 `Finding.evidence`** — 해당 전문가의 `AgentAnalysis.data`에 대해 `index_paths()`로 존재 · 인용 가능 · 업종 소유(`industry_code`가 있으면 일치)를 확인합니다. 실패한 finding은 버리고 경고로 남깁니다(교정 호출 없음 — 브리핑은 판정 근거가 아니기 때문).
2. **판정관 근거** — 지금과 동일. 원형 자료 경로만 인용 가능하며 브리핑 문장은 근거가 될 수 없습니다(`claim`은 `citable:false`와 같은 취급). "AI가 AI 말을 근거로" 삼는 MVP 1.5의 문제를 막습니다.
3. **숫자 대조** — `claim`에 들어간 숫자가 근거 경로의 값과 다르면 finding을 버립니다(반올림 허용 범위는 구현 시 정의).
4. **사용자 · 전문가 답변은 데이터이지 지시문이 아닙니다.** 기존 `user_answers` 규칙을 전문가 답변에도 적용합니다.

## 8. 저장 · 재개 · 프론트 영향

| 영역 | 변경 |
| --- | --- |
| DB | 테이블 2개 추가: `agent_briefs`(request_id, agent_id, source, brief), `specialist_consults`(request_id, round, agent_id, query, answer, status). 기존 `supplement_events` · `map_observations`는 답변의 도구 기록에서 계속 기록 |
| 재개 | `QuestionSnapshot` version 2 — 브리핑 · 되묻기 답변 차수를 참조. version 1 스냅샷은 기존 경로로 재개(하위 호환) |
| API | `DecisionResult` 변경 없음. 조회 응답에 선택 필드 `deliberation`(라운드별 되묻기 · 답변 요약) 추가 — 프론트가 "에이전트가 확인한 과정"을 보여 줄 수 있음 |
| 기능 플래그 | `ANALYSIS_MODE=multi_agent` / `single_decision`(현재 구조). 비교 측정과 장애 시 되돌리기용 |

## 9. 비용 · 지연 예상 (측정 전 추정)

| 구간 | 현재 | 예상 |
| --- | --- | --- |
| 분석 계산 | 약 2초 | 동일 |
| 브리핑 3개(병렬) | — | 입력이 각 보고서 크기(8~56KB)라 판정 1회보다 짧을 것으로 추정 |
| 판정 | 32초(입력 약 100KB) | 입력 축소로 감소 예상 |
| 되묻기 1라운드 | — | 전문가 병렬 답변 + 판정 1회 추가 |
| LLM 호출 | 1~2회 | 4~8회(상한 12) |

전문가에는 작고 빠른 모델, 판정관에는 현재 모델을 쓰는 구성을 기본으로 제안합니다. **모든 수치는 §10 측정으로 확정합니다.**

## 10. 측정 계획 (도입 판단 기준)

같은 주소(기존 3곳 + 추가 2곳, 반경 500m)를 `single_decision`과 `multi_agent`로 각각 실행합니다. 유료 호출이므로 실행 전 비용 승인을 받습니다.

| 지표 | 기준 |
| --- | --- |
| 전체 시간 · LLM 호출 수 · 입력/출력 토큰 · 비용 | 역할별(전문가 · 판정) 분리 기록 |
| 판정 입력 크기 | 현재 대비 감소 여부 |
| 근거 검증 실패율 | 판정 · 브리핑 각각 |
| 도구 사용률 | 되묻기 · 임대인 질문 · 외부 도구 호출이 일어난 주소 비율 |
| 판단 변화 | 되묻기 · 답변 후 추천 순위나 보류가 바뀐 사례와 이유 |
| 사람 평가 | 팀원이 두 결과를 이름을 가리고 비교(근거 설득력 · 임대인 이해도) |

**도입 조건(초안):** 근거 검증 실패율이 늘지 않고, 전체 시간이 현재의 1.5배 이내이며, 사람 평가에서 멀티에이전트 쪽이 우세. 조건을 못 넘으면 원인을 기록하고 플래그 기본값을 바꾸지 않습니다.

## 11. 단계별 계획

| 단계 | 내용 | 완료 기준 | 담당(안) |
| --- | --- | --- | --- |
| P0 | 판정 지시문을 도구 우선으로 수정: 공간 조건에 달린 후보는 먼저 임대인에게 질문, 경쟁 위치가 중요하면 지도 조회 | 대역 테스트에 "질문 · 지도 선택" 사례 추가, 실제 1회 확인 | 판정 담당 |
| P1 | 계약 PR (§5) + 합의 | `schemas.py` · 테스트 · API_CONTRACT 반영, 리뷰 승인 | 전원 |
| P2 | 전문가 브리핑 3종 + 대체 요약 + 브리핑 검증 | 에이전트별 대역 LLM 테스트, 검증 실패 finding 제거 테스트 | 분석 담당 3명 병렬 |
| P3 | 판정 입력 전환(`industry_digest` · `neighborhood`) + `ask_specialists` · `consult` 루프 | 라운드 · 예산 상한 테스트, 기존 근거 검증 테스트 전부 통과 | 오케스트레이션 · 판정 |
| P4 | 지도 에이전트 전환 (`execute_map` 흡수) | 기존 지도 관측 저장 유지 | 지도 담당 |
| P5 | 저장 · 재개 version 2, `deliberation` 응답 | v1 스냅샷 재개 테스트 | 서비스 · DB |
| P6 | 측정(§10) → TECH_DECISIONS ADR 갱신 → 발표자료 | 측정 결과 문서화 | 전원 |

P0은 계약 변경이 없어 즉시 진행할 수 있고, P3 이후에도 그대로 쓰입니다.

## 12. 합의가 필요한 결정

1. §5 계약 추가(브리핑 · 되묻기 · 답변)와 `SpecialistId`에 `map_analysis` 포함 여부
2. §4 예산 수치
3. 역할별 모델(전문가용 소형 모델 사용 여부)과 비용 상한
4. 기능 플래그 기본값 — 측정 전까지 `single_decision` 유지 제안
5. `deliberation`을 화면에 보여 줄지(프론트)

## 13. 위험과 대응

| 위험 | 대응 |
| --- | --- |
| 지연 · 비용 증가 | 브리핑 병렬, 전문가 소형 모델, 예산 상한, 지도는 되묻기 때만 |
| 전문가가 중요한 업종을 빠뜨림 | 코드가 만든 `industry_digest`를 판정관에게 항상 제공 |
| 브리핑 문장이 근거처럼 쓰임 | 브리핑은 인용 불가, 판정 근거는 원형 경로만 |
| 브리핑의 숫자 오기 | 근거 경로 값과 숫자 대조, 불일치 finding 폐기 |
| 비결정성으로 회귀 테스트가 어려움 | 대역 LLM(주입 `generate`) 테스트 + 실제 실행은 측정 절차로만 평가 |
| 계약 변경으로 팀 코드 충돌 | 추가형 변경, 기능 플래그, v1 재개 호환 |
