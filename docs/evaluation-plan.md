# 평가자 에이전트 도입 + 도입 평가 구현 설계

작성 2026-10-01 · 대상 브랜치 `feature/multiagent_evaluator` · 구현 담당: 이 문서를 받은 에이전트 · 상태: **A-1~A-6 구현·검증 완료, B부 미진행**

이 문서만 읽고 구현할 수 있게 썼습니다. 문서와 코드가 다르면 **멈추고 사용자에게 묻습니다.** 추측으로 채우지 않습니다.
배경 자료: 팀 공유 덱 [chaeum_evaluate](https://www.figma.com/deck/JdWiRKEUIpDWh38ujcRaEv/chaeum_evaluate),
지표 정의·참고문헌 `D:\yubi\kdt\멀티에이전트_평가방법_레포트.md`.

---

## 0. 요약

2026-10-01 사용자 승인 변경: 평가자 사용 시 초안 되묻기 2라운드와 평가 후 별도 4라운드, 모델 호출 64회, 기본 전체 시간 1200초를 적용합니다. 평가자 꺼짐은 기존 한도를 유지합니다. 이를 위해 `SpecialistAnswer.round`·`QuestionSnapshotV2.consult_round` 상한을 6, `llm_calls` 상한을 64로 확장하고 해당 경계 테스트를 갱신합니다. 기존 `specialist_consults` 표의 라운드 제약도 이력을 보존하여 마이그레이션합니다. 기존 네 핵심 분석 계약은 변경하지 않습니다. 브리핑의 지도·보완은 기존 전문가 되묻기 경로로 수행합니다.


| 부 | 무엇을 | 어디에 | 비용 |
| --- | --- | --- | --- |
| **A부 제품** | 원래 흐름에 **평가자 에이전트 4명**을 추가. 판정관 초안 → 평가자 4명 평가(저장·표시) → 판정관이 **지적마다** 반영·일부 반영·반영 안 함을 정하고 최종 보고서 작성. 브리핑 에이전트와 평가자는 `.env`에서 각각 켜고 끔 | `backend/app` (제품 코드, 커밋 대상) | 개발·테스트는 무료(목업) |
| **B부 도입 평가** | 여러 구성(점수만 · 단독 판정 · 단독 판정 여러 번 · 브리핑 · 각각 평가자 켬)을 같은 입력으로 돌려, 정답이 있는 시험 · 심사위원(평가자 에이전트) · 비용·시간으로 채점하고 미리 정한 기준으로 기본 구성을 결정 | `validation_tool/eval/` (Git 제외) | 유료 실행은 사람 승인 후 |

구현 순서: **A부 전부 → (사용자 확인) → B부.**

### 0.1 이름

| 이 문서의 이름 | 옛 이름 | 실체 |
| --- | --- | --- |
| 단독 판정 | 2.0 | 판정관 혼자 원자료로 판단. `analysis_mode="single_decision"` |
| 브리핑 에이전트 | 3.0 | 전문가 LLM 3+1명이 브리핑·되묻기, 판정관이 판단. `analysis_mode="multi_agent"` |
| 평가자 에이전트 (평가자) | 새로 추가 | 제품 흐름 안에서 판정관 **초안**을 평가하는 LLM 4명 |
| 심사위원 | — | **A부 평가자 에이전트 4명을 B부에서 "심사 모드"로 부른 것.** 같은 `app/agents/evaluators` 코드를 쓰고, 완성된 보고서를 블라인드로 평가해 구성끼리 비교합니다(12장). 따로 만드는 심사 모델은 없음 |
| 판단 / 평가 / 심사 | — | 보고서를 만든다 / 초안에 의견을 단다(판정관이 반영 여부 결정) / 완성본에 점수를 매긴다(결정용) |

코드 식별자(`v20`, `v30` 등)에는 숫자가 남아도 됩니다. 사람이 읽는 문서·로그·화면 문구에는 위 이름을 씁니다.

### 0.2 지켜야 할 것 (AGENTS.md 재확인)

1. 키는 `backend/.env`만. `.env.example`에는 변수 이름만.
2. 외부 호출은 비동기(`AsyncOpenAI`, `httpx.AsyncClient`). 파일·SQLite는 `asyncio.to_thread`.
3. 모델 응답은 pydantic으로 검증하고 근거 경로는 원자료에서 확인.
4. 일반 실패는 결과로 수집(에이전트 `failed`), 계약·저장 오류는 전파.
5. 주석·문서·로그·화면 문구는 한국어.
6. `schemas.py`는 원칙적으로 **추가만** 합니다. 0장의 사용자 승인 범위에서 전문가 라운드·스냅샷 호출 상한만 확장합니다. 기존 `AnalysisTask`·`AgentAnalysis`·`DecisionRequest`·`DecisionResult`는 바꾸지 않습니다. 추가도 PR에 먼저 공유합니다.
7. `.github/workflows/assign-mentor.yml`·`notify-discord.yml`·`convention-check.yml`·`.github/CODEOWNERS`는 건드리지 않습니다.
8. **커밋·푸시는 사용자가 요청할 때만.** 유료 API·LLM 실행은 사용자 승인 후.
9. **법률·규제 확인은 다른 팀원이 만듭니다.** 규제 자료 수집·판정 코드를 만들지 않습니다(1.4).
10. 작업 전후로 `ruff check`, `ruff format --check`, `mypy`, `unittest discover -s tests`(현재 552개) 통과.

---

# A부. 제품: 평가자 에이전트 4명

## 1. 흐름과 분기 규칙

### 1.1 전체 흐름

```
prepare_address → run_analyses
  → [BRIEFING_ENABLED] write_briefs                                  (기존)
  → evaluate_decision  ── phase="draft"
       ├ supplement / map / consult 요청 → 실행 → evaluate_decision(같은 phase)    (기존 분기)
       └ 최종 판단(DecisionResult) 나옴
            ├ 평가자 꺼짐                         → END (지금과 동일)
            ├ 평가자 켜짐 + 건너뛰기 조건(1.3)     → END (초안 = 최종)
            └ 평가자 켜짐                         → evaluate_draft (평가자 4명 병렬)
                                                  → evaluate_decision ── phase="final"
                                                       ├ supplement / map / consult / ask_user → 실행 → evaluate_decision(phase="final")
                                                       └ 최종 판단 → END
```

- `phase`는 상태에 `evaluations` 키가 있으면 `"final"`, 없으면 `"draft"`입니다(평가자 꺼짐이면 phase 개념 없음).
- **평가는 요청당 정확히 한 번.** final 단계에서 지도·보완·되묻기를 해도 다시 평가하지 않습니다.
- 평가자 꺼짐일 때 그래프·호출 수·결과·이벤트는 **지금과 같아야** 합니다(회귀 테스트로 고정).

### 1.2 단계별 허용 행동

| 행동 | 평가자 꺼짐 | draft | final |
| --- | --- | --- | --- |
| 데이터 보완(supplement) | 지금 규칙 | 지금 규칙 | 아직 안 했으면 허용(1회 한도는 요청 전체 기준) |
| 지도 조회 | 지금 규칙(단독: 직접 `map_lookup` 1회 / 브리핑: 지도 전문가 되묻기) | 지금 규칙 | 아직 안 했으면 허용 |
| 전문가 되묻기(브리핑만) | 최대 2라운드 | 최대 2라운드 | **평가 후 별도 최대 4라운드** 허용(저장 번호는 draft와 합산) |
| 임대인 질문 | `allow_questions`면 허용 | **금지** | `allow_questions`면 허용 |

- draft에서 질문을 막는 이유: 평가자(특히 임대인 대변인)가 "임대인에게 물어야 할 것"을 지적할 수 있으므로, 질문은 평가를 본 뒤 한 번에 합니다.

### 1.3 평가 건너뛰기 조건 (초안 = 최종)

다음 중 하나면 평가자를 호출하지 않고 초안을 최종으로 씁니다. 판정관 2차 호출도 하지 않습니다.

| 조건 | 이벤트 detail |
| --- | --- |
| 초안 `status == "no_data"` | `{"skipped": "no_data"}` |
| 평가자 4명 몫이 없음: `budget.open_calls < 4` (평가자는 비최종 범위라 `FINAL_RESERVE`를 못 쓰고, final 1회는 `FINAL_RESERVE` 몫으로 남아 있음) | `{"skipped": "budget"}` |

다음 경우는 평가자는 호출하되 **판정관 2차 호출을 생략**하고 초안을 최종으로 씁니다(비용 절감).

| 조건 | 처리 |
| --- | --- |
| 4명 모두 `failed` | 로그 없음, 이벤트 `evaluate` completed `{"final_call": false, "reason": "all_failed"}` |
| `failed`가 아닌 평가자 전원이 `verdict="agree"`이고 지적 0개 | 로그 없음, `{"final_call": false, "reason": "no_comments"}` |

### 1.4 법률·규제와의 경계

| 항목 | 담당 | A부에서 할 일 |
| --- | --- | --- |
| 교육환경보호구역·용도지역·인허가 자료, 제한 업종 판정 | **다른 팀원** | 만들지 않음 |
| 규제 결과를 판정관 입력에 연결 | 규제 담당 + 오케스트레이션 담당 | 만들지 않음 |
| 평가자의 규제 지적 | A부 | 규제 자료가 판정관 입력에 **들어온 뒤에만** 지시문에서 허용. 그 전에는 임대인 대변인 지시문에 "규제는 판정하지 말 것" |

규제 담당에게 받을 형식(합의 전 가정): `AgentAnalysis.data` 안에서 제한 업종이 업종 코드와 원자료 경로로 구분될 것(예 `/restricted/0/industry_code`).

---

## 2. 설정 (`.env`)

### 2.1 변수

| 변수 | 값 | 기본 | 뜻 |
| --- | --- | --- | --- |
| `BRIEFING_ENABLED` | `true`/`false` (대소문자 무시, `1`/`0`도 허용) | 없음 | 브리핑 에이전트 사용 |
| `EVALUATORS_ENABLED` | 같음 | `false` | 평가자 4명 사용 |
| `EVALUATOR_LLM_MODEL`, `EVALUATOR_LLM_API_KEY`, `EVALUATOR_LLM_BASE_URL`, `EVALUATOR_LLM_MAX_TOKENS`, `EVALUATOR_LLM_REASONING_EFFORT`, `EVALUATOR_LLM_TIMEOUT_SECONDS` | — | 공통 값 | `LLMSettings.from_env("EVALUATOR")`가 읽는 이름. 없으면 기존 공통(`ELICE_*`, `LLM_*`) 값. 실제 읽는 이름은 `app/llm/config.py`에서 확인 |
| `ANALYSIS_MODE` (기존) | `single_decision`/`multi_agent` | `single_decision` | 호환용. 아래 우선순위 |

- 허용하지 않는 값(예 `BRIEFING_ENABLED=yes`)은 서버 시작 시 `ValueError`로 멈춥니다(조용히 기본값으로 바꾸지 않음).

### 2.2 우선순위 (`ExecutionSettings.from_env`, `app/services/settings.py`)

```
if BRIEFING_ENABLED 있음:
    analysis_mode = "multi_agent" if true else "single_decision"
    if ANALYSIS_MODE 있음 and 그 값 != analysis_mode:
        logger.warning("BRIEFING_ENABLED와 ANALYSIS_MODE가 다릅니다. BRIEFING_ENABLED를 따릅니다.")
else:
    analysis_mode = ANALYSIS_MODE 또는 "single_decision"   # 지금 동작
evaluators_enabled = EVALUATORS_ENABLED (기본 false)
```

### 2.3 `ExecutionSettings` 변경

```python
@dataclass(frozen=True)
class ExecutionSettings:
    ...
    analysis_mode: AnalysisMode = "single_decision"     # 기존 그대로 (브리핑 여부의 실체)
    evaluators_enabled: bool = False                    # 신규
    evaluator_llm: LLMSettings = field(default_factory=LLMSettings)   # 신규

    @property
    def briefing_enabled(self) -> bool:                 # 신규, 읽기 전용
        return self.analysis_mode == "multi_agent"
```

- `AnalysisMode` Literal과 DB `analysis_mode` CHECK 제약은 **바꾸지 않습니다.**
- 평가자 사용 여부는 요청마다 `execution_json.capabilities.evaluators`(bool)로 저장합니다(6.6). 재개·재시도는 저장값을 따르며 **현재 `.env`를 따르지 않습니다.**

---

## 3. 타입 (`app/schemas.py`에 추가, 승인된 기존 상한 확장은 0장 참조)

```python
EvaluatorId = Literal["examiner", "founder", "customer", "landlord_advocate"]
EVALUATOR_IDS = get_args(EvaluatorId)          # 순서 고정: 이벤트·저장·화면 순서
EvaluationRequest = Literal["none", "map_lookup", "supplement", "ask_specialists", "ask_user"]


class EvaluationComment(Schema):
    index: Annotated[int, Field(ge=0, le=3)]     # 코드가 매김(모델 값 무시). 판정관 로그가 이 번호를 씀
    industry_code: IndustryCode | None = None    # None = 동네 전체에 대한 지적
    comment: Annotated[str, Field(min_length=1, max_length=300)]
    evidence: list[Evidence] = Field(default_factory=list, max_length=3)   # 기존 Evidence(agent_id, path)
    request: EvaluationRequest = "none"


class Evaluation(Schema):
    request_id: Text
    evaluator: EvaluatorId
    source: Literal["model", "failed"]
    verdict: Literal["agree", "conditional", "oppose"] | None = None
    comments: list[EvaluationComment] = Field(default_factory=list, max_length=4)
    notes: list[Text] = Field(default_factory=list)   # 내부 기록(형식 오류로 뺀 수 등). 화면·limitations에 안 씀

    # 검증: source=="model" ⇔ verdict is not None / source=="failed"면 comments 비어 있음 /
    #       comments의 index가 0부터 빈틈없이 증가


class EvaluationLogEntry(Schema):
    evaluator: EvaluatorId
    index: Annotated[int, Field(ge=0, le=3)]
    decision: Literal["accepted", "partial", "rejected", "unreviewed"]
    applied: Annotated[str, Field(min_length=1, max_length=300)] | None = None   # 반영한 부분
    dropped: Annotated[str, Field(min_length=1, max_length=300)] | None = None   # 버린 부분
    reason: Annotated[str, Field(min_length=1, max_length=300)]

    # 검증 (model_validator):
    #   accepted   → applied 필수, dropped 없음
    #   partial    → applied·dropped 둘 다 필수
    #   rejected   → dropped 필수, applied 없음
    #   unreviewed → applied·dropped 없음 (코드만 만듦. 모델이 unreviewed를 내면 그 항목 버림)
```

- 평가 결과(`Evaluation`)와 반영 기록(`EvaluationLogEntry`)은 **`DecisionResult`에 넣지 않습니다.** 따로 저장하고 GET에서 따로 내보냅니다.

---

## 4. 평가자 에이전트 (`app/agents/evaluators/`)

### 4.1 파일

| 파일 | 내용 |
| --- | --- |
| `__init__.py` | 한 줄 설명 |
| `prompt.md` | 공통 지시문 + 페르소나 4개 (4.3 본문 그대로) |
| `agent.py` | `evaluate_draft()`, `evaluation_input()`, `check_comments()`, `generate_evaluation()` |

### 4.2 함수

```python
GenerateEvaluation = Callable[[str, str], Awaitable[dict]]   # (system_prompt, input_json) -> 모델 JSON

async def generate_evaluation(system_prompt: str, input_json: str, *, settings: LLMSettings) -> dict:
    return await app.llm.client.complete_json(system_prompt, input_json, settings)

def evaluation_input(request: DecisionRequest, draft: DecisionResult,
                     allowed: list[EvaluationRequest]) -> dict:
    """평가자에게 줄 입력. 원자료 전체는 주지 않는다."""

def check_comments(raw: object, request: DecisionRequest, allowed: list[EvaluationRequest],
                   *, request_id: str, evaluator: EvaluatorId) -> Evaluation:
    """모델 응답을 코드로 검증해 Evaluation으로 만든다(4.4 규칙)."""

async def evaluate_draft(evaluator: EvaluatorId, request: DecisionRequest, draft: DecisionResult, *,
                         generate: GenerateEvaluation, allowed: list[EvaluationRequest],
                         timeout: float) -> Evaluation:
    """실패는 Evaluation(source="failed")로 돌려주고 흐름을 멈추지 않는다.
    단, BudgetStorageError·OSError·CancelledError는 그대로 올린다."""
```

- 모델 호출은 `with llm_scope(current_scope()[0], "evaluator." + evaluator):` 안에서 합니다(비최종 범위 → `FINAL_RESERVE`를 못 씀).
- 호출마다 `asyncio.timeout(timeout)`(= `ExecutionSettings.agent_timeout`). 시간 초과 → `failed`, notes `["시간 초과"]`.
- 지시문 파일은 `asyncio.to_thread`로 읽습니다(기존 `specialists/agent.py`와 같은 방식).

**`evaluation_input` 구성 (키 이름 고정):**

```json
{
  "evaluator": "founder",
  "draft": {
    "summary": "...",
    "recommendations": [ {"category": {"code": "S201", "major": "...", "middle": "..."}, "score": 72,
                          "reasons": ["..."], "evidence": [{"agent_id": "...", "path": "..."}], "risks": ["..."]} ],
    "not_recommended": [ ... ]
  },
  "industry_digest": [ ... ],
  "neighborhood": [ ... ],
  "sources": [ ... ],
  "map_context": { ... },
  "allowed_requests": ["none", "map_lookup", "ask_user"]
}
```

- `industry_digest`·`neighborhood`·`sources`·`map_context`는 `app.agents.decision.context.build_context(request, briefs=[], answers=[])`의 같은 이름 값입니다. `industry_digest`는 **초안에 나온 업종 코드만** 남깁니다. `map_context`는 지도 조회가 없으면 `null`.
- 초안의 `limitations`·`source_analyses`·`map_observation`은 넣지 않습니다.
- `allowed_requests`는 그래프가 계산합니다: `"none"` + (지도 미사용이고 지도 도구 있음 → `map_lookup`) + (보완 미사용이고 보완 도구 있음 → `supplement`) + (브리핑 켜짐이고 남은 라운드 있음 → `ask_specialists`) + (`allow_questions` → `ask_user`).

### 4.3 지시문 (`prompt.md` 본문)

```markdown
# 평가자

당신은 빈 상가 업종 추천 보고서의 **초안**을 한 관점에서 평가합니다.
보고서를 다시 쓰지 말고 **지적만** 합니다. 당신의 지적은 판정관이 원자료로 확인한 뒤 반영 여부를 정합니다.
지적과 판정관의 결정은 임대인 화면에도 보입니다. 60대 임대인이 읽을 수 있는 쉬운 말로 씁니다.

## 입력
- evaluator: 당신의 관점
- draft: 판정관 초안 (summary, recommendations, not_recommended)
- industry_digest: 초안 업종의 원자료 값과 경로 (agent_id, path, value)
- neighborhood: 동네 공통 자료 · sources: 분석별 상태·기간·범위·경고 · map_context: 지도 조회 요약
- allowed_requests: 지금 요청할 수 있는 추가 행동

## 페르소나
- examiner 심사자 — "분석이 맞나?" 이유의 숫자·기간·단위가 근거 값과 맞는지, 서로 부딪치는 신호를 숨기지 않았는지,
  한두 개 값으로 지나치게 일반화하지 않았는지 봅니다.
- founder 예비 창업자 — "들어오면 버티나?" 폐업 흐름, 경쟁 과밀, 점포 수가 적은 업종을 확신하지 않았는지 봅니다.
- customer 동네 손님 — "누가, 언제 쓰나?" 상주·직장·유동 인구와 시간대가 업종 수요와 맞는지 봅니다.
- landlord_advocate 임대인 대변인 — "내 공간에 들어오나?" 층·면적·설비(배수·전기·환기)처럼 임대인이 확인하거나
  준비할 일을 봅니다. 자료에 없는 공간 조건은 임대인에게 물어야 한다고 지적합니다.
  법률·규제(보호구역·용도지역·인허가)는 판정하지 않습니다.

## 규칙
1. 지적은 최대 4개, 중요한 순서. 초안이 괜찮으면 지적 없이 agree로 끝내도 됩니다.
2. 숫자를 새로 계산하지 않습니다. 값이 필요하면 industry_digest·neighborhood의 agent_id와 path를 evidence에 그대로 복사합니다(최대 3개). 경로를 지어내지 않습니다.
3. industry_code는 지적하는 업종의 코드입니다. 동네 전체에 대한 지적이면 null.
4. request는 지적을 확인하는 데 필요한 행동이며 allowed_requests에 있는 것만 씁니다.
5. 한 지적은 한두 문장.

## 출력 (JSON 객체만)
{"verdict": "agree | conditional | oppose",
 "comments": [{"industry_code": "S201 또는 null", "comment": "...",
               "evidence": [{"agent_id": "business_lifecycle", "path": "/industries/4/metrics/recent_year_net_change"}],
               "request": "none"}]}
- agree: 이대로 괜찮음 · conditional: 확인하면 괜찮음 · oppose: 결론을 바꿔야 함
```

- 호출 시 시스템 지시문 = `prompt.md` 전체. 사용자 입력 = `{"evaluator": "...", ...}` JSON. 페르소나는 입력의 `evaluator`로 고릅니다(파일을 4개로 나누지 않음).

### 4.4 응답 검증 규칙 (`check_comments`)

| 상황 | 처리 |
| --- | --- |
| 응답이 dict가 아니거나 `verdict`가 3개 값 밖 | `source="failed"`, notes `["형식 오류"]` |
| `comments`가 list가 아님 | 지적 0개로 처리(실패 아님) |
| 지적 하나가 `EvaluationComment` 검증 실패(빈 문장, 300자 초과, 없는 업종 코드 등) | **그 지적만** 버림, notes에 `"형식 오류 지적 N개 제외"` |
| `evidence` 경로가 원자료에 없음 / 다른 업종 소유 | **그 경로만** 지움. 판정: 지도는 `valid_map_path(path, industry_code, map_data)`, 나머지는 `index_paths(data)`에 있고 소유 업종이 `None` 또는 `industry_code`와 같음 |
| `request`가 `allowed_requests` 밖 | `"none"`으로 바꿈 |
| 지적 5개 이상 | 앞 4개만 |
| `industry_code`가 초안 업종이 아님 | 유지(초안에 없는 업종을 추천해야 한다는 지적일 수 있음) |
| 모델이 준 `index` | 무시하고 코드가 0,1,2,3으로 다시 매김 |

- `failed`·notes는 **임대인에게 보이는 `limitations`에 넣지 않습니다**(브리핑 에이전트의 내부 경고 누수를 반복하지 않음). 화면에는 "이 평가자는 이번에 의견을 내지 못했습니다" 한 줄만 보입니다(6.5).

---

## 5. 판정관 final 단계 (`app/agents/decision/`)

### 5.1 `evaluate()` 인자 추가 (`agent.py`)

```python
async def evaluate(request, *, ..., deliberation=None,
                   evaluation: dict | None = None,                          # 신규: 5.2 형식
                   evaluation_log: list[EvaluationLogEntry] | None = None,  # 신규: 결과를 여기에 채움(out 인자)
                   ) -> DecisionResult | SupplementPlan | QuestionPlan | MapLookupPlan | ConsultPlan
```

- `evaluation is None`이면 지금과 완전히 같습니다.
- `evaluation`이 있으면 `_build_prompt`가 payload에 `"evaluation"` 키를 넣고 지시문(5.3)을 덧붙입니다.
- 최종 `DecisionContent`가 나오면 로그를 떼어 내(5.4) `evaluation_log` 리스트에 채우고, `DecisionResult`는 지금처럼 만듭니다.
- 행동(`SupplementPlan` 등)이 나오면 로그는 비워 둡니다(행동 뒤 다시 final이 돌 때 채움).

### 5.2 판정관 입력의 `evaluation` 키

```json
"evaluation": {
  "draft": {"summary": "...", "recommendations": [...], "not_recommended": [...]},
  "evaluations": [
    {"evaluator": "founder", "verdict": "conditional",
     "comments": [{"index": 0, "industry_code": "S201", "comment": "...",
                   "evidence": [{"agent_id": "business_lifecycle", "path": "..."}], "request": "map_lookup"}]}
  ],
  "failed_evaluators": ["examiner"]
}
```

- `source="failed"` 평가자는 `evaluations`에서 빼고 `failed_evaluators`에만 적습니다.
- `index`를 명시해서 넘깁니다(모델이 배열 번호를 세지 않게 — 브리핑 에이전트에서 겪은 문제).

### 5.3 final 단계 지시문 (코드에서 덧붙임, 문구 그대로)

```text
## 평가 반영 단계
evaluation.draft는 당신이 앞서 쓴 초안이고, evaluation.evaluations는 평가자 의견입니다
(examiner 심사자 · founder 예비 창업자 · customer 동네 손님 · landlord_advocate 임대인 대변인).
- 평가는 자료가 아니라 의견입니다. 지적이 가리킨 원자료 값을 직접 확인한 뒤 판단하세요.
- 평가자 단위가 아니라 지적 하나하나를 따로 판단합니다. 같은 평가자의 지적도 하나는 반영하고 하나는 버릴 수 있습니다.
- 한 지적 안에서도 원자료로 확인된 부분만 반영할 수 있습니다(일부 반영).
- 원자료로 뒷받침되지 않는 부분, 다른 업종을 가리키는 부분은 버립니다.
- 평가자끼리 부딪치면 원자료가 더 직접 뒷받침하는 쪽을 따르고, 남는 위험은 risks에 적습니다.
- 지적의 request가 허용된 행동이면 최종판단 전에 그 행동을 먼저 요청할 수 있습니다.
- 평가 문장을 근거(evidence)로 인용하지 마세요. 근거는 지금처럼 원자료 경로만 씁니다.
- 최종판단 JSON에 evaluation_log 배열을 추가합니다. 모든 지적마다 정확히 한 항목을 쓰고,
  evaluator와 index는 evaluation.evaluations에 적힌 값을 그대로 씁니다.
  decision: accepted(전부 반영) · partial(일부 반영) · rejected(반영 안 함)
  applied: 반영한 부분(accepted·partial) · dropped: 버린 부분(partial·rejected) · reason: 짧은 이유
  임대인 화면에 그대로 보이므로 쉬운 말로 씁니다.
```

뒤에 `EvaluationLogEntry`의 JSON 스키마를 붙입니다(`unreviewed`는 "코드 전용, 쓰지 말 것"으로 설명).

**예시 (일부 반영):** 임대인 대변인 지적 0 = "세탁소는 배수 설비와 전기 용량이 부족할 수 있습니다." 원자료에 공간 정보는 없음.
→ `{"evaluator": "landlord_advocate", "index": 0, "decision": "partial", "applied": "배수 설비 확인을 확인할 점에 추가",
"dropped": "전기 용량이 부족하다는 단정은 원자료에 근거가 없어 제외", "reason": "공간 조건은 자료에 없어 확인 항목으로만 남김"}`

### 5.4 로그 분리·보정 (`llm.py`의 `validate_content` 직전 단계)

`DecisionContent`는 `extra="forbid"`이므로 **검증 전에** `evaluation_log` 키를 떼어 냅니다(되돌린 이전 구현에서 이 부분 때문에 실패했음).

1. 모델 출력 dict에서 `evaluation_log`를 pop. dict가 아니면 무시.
2. 항목마다 `EvaluationLogEntry.model_validate`. 실패하거나 `decision=="unreviewed"`인 항목은 버림.
3. `(evaluator, index)`가 실제 평가(model 소스)의 지적과 맞지 않는 항목은 버림.
4. 같은 `(evaluator, index)`가 여러 번이면 첫 항목만.
5. 빠진 `(evaluator, index)`마다 `{"decision": "unreviewed", "reason": "판정관이 이 지적을 검토하지 않았습니다."}`를 채움.
6. 결과는 `EVALUATOR_IDS` 순서 → `index` 순서로 정렬.

- 로그 형식 오류는 **판단 실패가 아닙니다.** 판단(`DecisionContent`) 자체가 틀리면 지금의 교정 재시도 규칙 그대로.
- 교정 재시도(근거 오류) 때도 `evaluation`을 payload에 그대로 두고 로그를 다시 받습니다. 첫 시도 로그는 버립니다.
- 반환 경로를 하나로: `evaluate()` 안에서 dict든 검증된 객체든 같은 함수로 로그를 떼어 냅니다.
  저장 훅에는 항상 `list[EvaluationLogEntry]`(pydantic 객체)를 넘기고, 저장 직전에만 `model_dump(mode="json")`.
- `generate_decision`(실제 모델 경로)도 dict를 검증하기 전에 같은 분리 함수를 씁니다. 분리된 로그를 `evaluate()`로 돌려주는 방법은
  구현자가 고르되(예: 검증 전 원문 dict를 `evaluate()`에서 받는 구조), **`DecisionContent`·`DecisionResult` 필드는 바꾸지 않습니다.**

---

## 6. 그래프·저장·API·이벤트·화면

### 6.1 그래프 (`app/agents/orchestration/graph.py`)

- `run_graph(..., evaluators_enabled: bool = False, generate_evaluators: dict[EvaluatorId, GenerateEvaluation] | None = None)`
  - `evaluators_enabled`인데 `generate_evaluators`가 4개 모두 호출 가능하지 않으면 실행 전 `ValueError`.
- `GraphState`에 추가: `draft: DecisionResult`, `evaluations: list[Evaluation]`.
- `RunHooks`에 추가:
  - `on_evaluation(draft: DecisionResult, evaluations: list[Evaluation]) -> Awaitable[None]` — 평가 4개가 모두 끝난 뒤 한 번
  - `on_evaluation_log(entries: list[EvaluationLogEntry]) -> Awaitable[None]` — final 판단이 나올 때마다(덮어쓰기)
- 노드 추가: `evaluate_draft_node`. `evaluate_decision` 뒤 조건 분기는 **함수 하나**(`route(state) -> str`)로 정리:
  `consult → map → supplement → question → (평가자 켜짐 and "evaluations" 없음 → 건너뛰기 검사 → "evaluate") → final`.
- 평가자 4명은 `asyncio.gather`로 병렬. 저장·취소 예외는 전체로 전파, 일반 실패는 `failed` 결과.
- **예산:** 평가자 켜짐이면 단독 판정에도 `LLMBudget`을 만듭니다(지금은 브리핑만). 브리핑 켜짐 + 평가자 켜짐이면
  되묻기 배분에서 평가자 몫을 미리 뺍니다: `EVALUATOR_RESERVE = 4`(평가 4회. final 1회는 기존 `FINAL_RESERVE`가 이미 보장).
  기존 `budget.open_calls`를 쓰는 두 곳(되묻기 허용 판정 `< 3`, 전문가 몫 `share`)에 `open_calls - EVALUATOR_RESERVE`를 씁니다
  (평가가 이미 끝났으면 빼지 않음).
- 단독 판정 draft에서 `question_fields=None`. final에서만 질문 허용.
- 단독 판정에서 보완은 요청 전체 1회(지금 규칙). draft에서 안 했으면 final에서 `operations`를 다시 계산해 제시합니다.

### 6.2 DB (`app/db/schema.sql`, `initialize()`가 기존 DB에도 평가 표를 생성하고 전문가 라운드 제약을 확장)

```sql
CREATE TABLE IF NOT EXISTS evaluation_drafts (
    request_id TEXT PRIMARY KEY NOT NULL REFERENCES analysis_requests(request_id),
    draft_json TEXT NOT NULL CHECK (json_valid(draft_json)),
    created_at TEXT NOT NULL,
    CHECK (json_extract(draft_json, '$.request_id') IS request_id)
);

CREATE TABLE IF NOT EXISTS evaluations (
    request_id TEXT NOT NULL REFERENCES analysis_requests(request_id),
    evaluator_id TEXT NOT NULL CHECK (evaluator_id IN ('examiner','founder','customer','landlord_advocate')),
    source TEXT NOT NULL CHECK (source IN ('model','failed')),
    evaluation_json TEXT NOT NULL CHECK (json_valid(evaluation_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (request_id, evaluator_id),
    CHECK (json_extract(evaluation_json, '$.request_id') IS request_id),
    CHECK (json_extract(evaluation_json, '$.evaluator') IS evaluator_id),
    CHECK (json_extract(evaluation_json, '$.source') IS source)
);

CREATE TABLE IF NOT EXISTS evaluation_logs (
    request_id TEXT PRIMARY KEY NOT NULL REFERENCES analysis_requests(request_id),
    log_json TEXT NOT NULL CHECK (json_valid(log_json) AND json_type(log_json) = 'array'),
    updated_at TEXT NOT NULL
);
```

- `draft_json`은 `DecisionResult`에서 `request_id`·`summary`·`recommendations`·`not_recommended`만 저장합니다.
- 저장 함수(`app/db/repository.py`):
  - `save_evaluation(draft, evaluations, *, db_path)` — 초안+4개를 **한 트랜잭션**
  - `save_evaluation_log(request_id, entries, *, db_path)` — UPSERT
  - `get_evaluation(request_id, *, db_path) -> dict | None` — `{"draft", "evaluations", "log"}`
  - 저장 두 함수는 요청 상태가 `running`일 때만(아니면 `ValueError`). 기존 `_require_multi_running`은 브리핑 전용이라 쓰지 말고 상태만 보는 검사를 새로 둡니다.
  - `save_evaluation`이 두 번 불리면(이미 행 있음) `sqlite3.IntegrityError`를 그대로 올립니다(평가는 한 번).
- 저장 실패는 전파(실행 실패). 진행 이벤트 저장 실패만 지금처럼 무시.
- 기존 `analysis_requests` 테이블 정의와 CHECK 제약은 바꾸지 않습니다. 전문가 라운드 상한을 바꾸는 `specialist_consults`만 이력 보존 마이그레이션을 수행합니다.

### 6.3 API

- `GET /api/v1/analyses/{id}`: `execution_json.capabilities.evaluators`가 true인 요청에만 `evaluation` 키를 추가합니다.

```json
"evaluation": {
  "skipped": null,
  "draft": {"summary": "...", "recommendations": [...], "not_recommended": [...]},
  "evaluations": [
    {"evaluator": "founder", "source": "model", "verdict": "conditional",
     "comments": [{"index": 0, "industry_code": "S201", "comment": "...", "evidence": [...], "request": "map_lookup"}]},
    {"evaluator": "examiner", "source": "failed", "verdict": null, "comments": []}
  ],
  "log": [{"evaluator": "founder", "index": 0, "decision": "partial",
           "applied": "...", "dropped": "...", "reason": "..."}]
}
```

  - 평가를 건너뛴 요청: `{"skipped": "no_data" | "budget", "draft": null, "evaluations": [], "log": []}`.
    건너뛴 이유는 `execution_json.evaluation_skipped`에 저장해 두고 여기서 읽습니다.
  - `notes`는 응답에 넣지 않습니다(내부 기록).
- POST(`DecisionResult | WaitingForInput`) 응답 형식은 바꾸지 않습니다. 화면은 완료 뒤 GET으로 평가를 읽습니다.
- `?mock=true`: 목업 평가자를 씁니다. 고정 규칙 — 임대인 대변인만 초안 1순위 업종에 `conditional` 지적 1개
  ("설비 확인 필요", `ask_user`가 허용되면 `request="ask_user"`, 아니면 `"none"`), 나머지 3명은 `agree`·지적 0개.
  목업 판정관은 payload에 `evaluation`이 있으면 모든 지적에 `partial` 로그를 붙입니다
  (`applied`: "확인할 점에 설비 확인을 추가", `dropped`: "설비가 없다고 단정한 부분은 근거가 없어 제외", `reason`: "목업").
  답변 재개 목업 경로(`submit_answers`의 `mock`)도 같은 목업 판정관을 씁니다(지금은 `mock_generate` 직접 사용 → 교체).

### 6.4 진행 이벤트 (`docs/API_CONTRACT.md` 표에 추가)

| stage | event | detail | 화면 문구 예 |
| --- | --- | --- | --- |
| `decision` | started · completed | 기존 + `phase`(`draft`·`final`, 평가자 켜짐일 때만) | 판정관이 초안을 쓰고 있어요 / 평가를 보고 최종 보고서를 쓰고 있어요 |
| `evaluate.{evaluator}` | started · completed | `source`, `verdict`, `comments`(개수) | 예비 창업자가 초안을 평가하고 있어요 |
| `evaluate` | completed | `skipped`(`no_data`·`budget`) 또는 `final_call`(bool)·`reason` | 평가를 건너뛰었어요 |

- 이벤트 값 CHECK(`started`·`completed`·`failed`·`waiting`)는 그대로입니다. detail에 모델 원문(지적 문장)을 넣지 않습니다.

### 6.5 화면 (프론트엔드 요청 사항, `docs/API_CONTRACT.md`에 함께 적음)

- 결과 화면에 "평가자 의견" 영역. 평가자 순서는 `EVALUATOR_IDS`. **평가자 의견은 요약하거나 거르지 않고 전부 보여 줍니다**(사용자 결정, 2026-10-01): 판정, 지적 문장 원문, 근거 칸, 요청한 확인 행동. 숨기는 것은 내부 기록 `notes`뿐입니다.
- 평가자별: 이름(심사자·예비 창업자·동네 손님·임대인 대변인), 판정 배지(동의·조건부·반대), 지적 목록.
- 지적마다 판정관 결정 배지: **반영 / 일부 반영 / 반영 안 함 / 검토 안 됨**, 그 아래 `applied`(반영한 부분)·`dropped`(버린 부분)·`reason`.
- `failed` 평가자는 "이번에 의견을 내지 못했습니다" 한 줄.
- 영역 머리말 고정 문구: "평가자는 초안에 의견을 냅니다. 판정관이 원자료로 확인해 반영 여부를 정합니다."
- 진행 화면: 6.4 이벤트로 "평가자 4명이 초안을 보고 있어요" 단계 표시.

### 6.6 서비스·재개·재시도 (`app/services/analysis.py`)

- `execute_analysis(..., generate_evaluators: dict | None = None)` 추가. `settings.evaluators_enabled`면
  `build_evaluator_generators(settings, injected)`로 4개를 만듭니다(주입 시 4개 모두 있어야 함).
- 시작 시 `update_execution_state(capabilities={...기존..., "evaluators": bool})`를 **모든 모드에서** 저장합니다
  (지금은 브리핑만 저장). 기존 `capabilities` 비교 규칙(바뀌면 오류)은 유지.
- `_execution_scope`: 지금 조건 `analysis_mode != "multi_agent"`이면 예산 없음 → **단독 판정이고 평가자 꺼짐일 때만 예산 없음**으로.
- 저장 훅: `on_evaluation` → `save_evaluation`, `on_evaluation_log` → `save_evaluation_log`, 건너뛰기 → `execution_json.evaluation_skipped`.
- **질문 재개** (질문은 final에서만 나옴):
  - 단독 판정: 지금 `_evaluate_saved(bundle)` 경로에 `evaluation`(DB에서 읽어 5.2 형식으로 변환)과 `evaluation_log` 아웃 리스트를 넘기고, 끝나면 `save_evaluation_log`. 평가자 재호출 없음.
  - 브리핑: 지금 `run_graph(..., resume_state=...)` 경로에 `resume_state["draft"]`·`["evaluations"]`를 넣어 그래프가 final로 시작하게 합니다. 평가자 재호출 없음.
  - 재개 시 `capabilities.evaluators`가 true인데 평가 행도 `evaluation_skipped`도 없으면(데이터 손상) `ValueError`.
- **판정 재시도**(`retry_decision`, 사용자 승인): 평가 전 실패는 저장된 분석·브리핑으로 초안 → 평가 → 최종판단을 다시 실행합니다. 평가 후 실패는 저장된 평가로 final만 실행합니다. 원자료·브리핑·전문가 되묻기·지도·보완을 다시 호출하거나 새 질문을 발행하지 않습니다. 평가를 건너뛴 요청은 지금처럼 최종판단만 다시 실행합니다. 이미 평가를 저장한 표시가 있는데 평가 행이 사라진 경우에는 손상으로 거부합니다. 목업 재시도도 같은 반영 기록을 만듭니다.
- 평가자 사용 요청의 실제 전체 제한시간은 `execution_json.time_limit`에 저장해 재개·재시도에도 유지합니다. 명시한 시간 설정이 기본 1200초보다 우선합니다.
- `QuestionSnapshot`·`QuestionSnapshotV2` 형식은 바꾸지 않습니다(평가는 DB에서 읽음).

---

## 7. 수정·추가 파일 목록

| 파일 | 변경 |
| --- | --- |
| `app/schemas.py` | 3장 타입 추가 (기존 타입 변경 없음) |
| `app/agents/evaluators/__init__.py`, `agent.py`, `prompt.md` | 신규 |
| `app/agents/decision/agent.py` | `evaluate(evaluation=, evaluation_log=)`, `_build_prompt` 평가 키·지시문 |
| `app/agents/decision/llm.py` | 검증 전 `evaluation_log` 분리 |
| `app/agents/orchestration/graph.py` | 6.1 |
| `app/services/settings.py` | 2장 |
| `app/services/analysis.py` | 6.6 |
| `app/db/schema.sql`, `app/db/repository.py`, `app/db/connection.py` | 6.2, 기존 전문가 라운드 상한 마이그레이션 |
| `app/llm/budget.py`, `backend/pyproject.toml` | 평가자 사용 시 호출 상한, 지시문 배포 파일 등록 |
| `app/api/v1/routes.py`, `app/api/v1/mock.py` | 6.3 |
| `backend/.env.example` | 2.1 변수 (값 비움, 주석 한국어) |
| `backend/README.md` | 환경변수 표, 구성 4가지 표, 테이블 목록 |
| `docs/API_CONTRACT.md` | GET `evaluation`, 이벤트 표, 화면 요청 사항 |
| `docs/multi-agent-design.md` | 상태 줄에 평가자 추가 사실과 이 문서 링크 |
| `tests/test_evaluators_*.py` | 신규 (8장) |

---

## 8. A부 테스트 (네트워크 차단, `tests/test_llm_common.py`의 `socket.socket.connect` 차단 패턴)

**회귀**
- [x] 평가자 꺼짐 × (단독, 브리핑): 모델 호출 수·결과 JSON·이벤트 목록이 기존 테스트 기대값과 같음
- [x] 기존 552개 테스트 통과(승인된 상한 변경에 해당하는 계약 경계 테스트만 갱신)

**설정**
- [x] `ANALYSIS_MODE`만 / `BRIEFING_ENABLED`만 / 둘 다(충돌 시 경고 1회, `BRIEFING_ENABLED` 우선) / 잘못된 값 → `ValueError`
- [x] `EVALUATORS_ENABLED` 기본 false

**흐름**
- [x] 평가자 켜짐 × (단독, 브리핑) 목업 끝까지: 평가자 4명 각 1회, draft 입력엔 `evaluation` 없음, final 입력엔 있음
- [x] 이벤트 순서: `decision(draft)` → `evaluate.*` 4개 → `decision(final)`
- [x] 초안 `no_data` → 평가자 0회, 판정관 2차 0회, `evaluate` skipped
- [x] 예산 부족 → skipped `budget`
- [x] 4명 모두 실패 → final 호출 없음, 초안 = 최종
- [x] 전원 agree + 지적 0 → final 호출 없음
- [x] draft에서는 `question_fields` 없음, final에서만 있음
- [x] final에서 지도 요청 → 지도 실행 → final 재실행, **평가자 재호출 없음**
- [x] 브리핑 + 평가자: 되묻기 배분이 `EVALUATOR_RESERVE`를 남김(남은 호출이 적을 때 되묻기 대신 평가가 실행됨)

**평가자 검증**
- [x] 평가자 하나 예외 → `failed`, 나머지 진행, `limitations`에 평가자 관련 문장 0개
- [x] 시간 초과 → `failed`
- [x] 없는 경로·다른 업종 경로만 지워짐, 허용 안 된 `request` → `none`, 형식 오류 지적만 빠짐, 5개 → 4개, index 재매김

**반영 기록 (부분 반영)**
- [x] 같은 평가자의 지적 3개가 `accepted`·`partial`·`rejected`로 각각 저장됨
- [x] `partial`인데 `dropped` 없음 → 그 항목만 버리고 `unreviewed`로 채움
- [x] 모델이 `unreviewed`를 냄 → 버리고 코드가 `unreviewed` 채움
- [x] 없는 `(evaluator,index)` 항목 버림, 중복은 첫 항목만, 빠진 지적은 `unreviewed`
- [x] 로그 형식이 전부 틀려도 판단은 성공
- [x] 교정 재시도 시 첫 시도 로그는 버려지고 두 번째 로그가 저장됨
- [x] `DecisionResult` JSON에 `evaluation_log` 키가 없음

**저장·API·재개**
- [x] 초안+4개 한 트랜잭션 저장, 두 번 저장 시 오류, 로그 UPSERT
- [x] GET: 평가자 켠 요청만 `evaluation`, `notes` 없음, 건너뛴 요청은 `skipped` 표시
- [x] 단독+평가자: final 질문 → 대기 → 답변 재개 → 평가자 재호출 0, 로그 저장
- [x] 브리핑+평가자: 같은 시나리오
- [x] 재개 시 `.env`의 `EVALUATORS_ENABLED`를 바꿔도 저장된 `capabilities.evaluators`를 따름
- [x] `?mock=true` 생성·재개 모두 평가·로그가 나옴

---

## 9. A부 단계와 완료 조건

| 단계 | 할 일 | 완료 조건 |
| --- | --- | --- |
| A-1 | 2장 설정, 3장 타입 | 설정 테스트, `EvaluationLogEntry` 4가지 규칙 테스트 통과 |
| A-2 | 4장 평가자 에이전트 | 평가자 검증 테스트 통과 |
| A-3 | 5장 판정관 final, 로그 분리 | 반영 기록 테스트 통과 |
| A-4 | 6.1 그래프, 6.6 서비스, 6.2 DB | 흐름·저장·재개 테스트 통과 |
| A-5 | 6.3 API·목업, 6.4 이벤트 | API 테스트 통과 |
| A-6 | 7장 문서들 | 문서 반영, 전체 검사(ruff·format·mypy·unittest) 통과 |
| **확인** | 사용자에게 변경 요약·테스트 결과 보고 | 사용자가 B부 진행 승인 |

유료 실측(실제 모델로 평가자 켜서 돌려 보기)은 사용자가 요청할 때만 합니다.

### 9.1 구현·검증 결과 (2026-10-01)

브랜치: `feature/multiagent_evaluator`. 커밋·푸시·유료 모델 호출 없이 작업했습니다.
프론트엔드 화면 연결 요구는 6.5와 `API_CONTRACT.md`에 반영했으며 화면 컴포넌트 구현은 이 단계의 변경 목록에 포함하지 않습니다.

| 단계 | 검증 | 결과 |
| --- | --- | --- |
| A-1 | `tests.test_evaluators_settings` | 4개 통과: 설정 우선순위·잘못된 값·평가 및 반영 기록 계약 |
| A-2 | `tests.test_evaluators_agent` | 3개 통과: 입력 제한·지적/근거 필터·실패/시간 초과 |
| A-3 | `tests.test_evaluators_decision` | 2개 통과: 실제 전송 대역의 로그 분리·부분 반영·교정 재시도 |
| A-4 | `tests.test_evaluators_flow` | 13개 통과: 두 모드·평가 생략·지도·2+4라운드·저장 원자성·DB 마이그레이션·재개·평가 전후 재시도 |
| A-5 | `tests.test_evaluators_api` | 3개 통과: 목업 생성/답변/재시도·GET 원문과 notes 제외·이벤트 순서 |
| A-6 | 백엔드 `ruff check .`, `ruff format --check .`, `mypy`, `unittest discover -s tests` | 전부 통과, 전체 577개(기존 552 + 평가자 25) |

기존 테스트는 승인된 라운드·호출 상한 변경에 해당하는 `test_specialist_contract.py` 경계값만 갱신했습니다.
프론트엔드 `format:check`·`lint`·`build`도 통과했습니다. 빌드 시 누락된 개발 의존성은 잠금 파일 기준으로 설치했고 소스·잠금 파일은 변경하지 않았습니다.
리뷰에서 찾은 환경변수 변경 후 시간 한도 축소, 평가 전 실패 재시도 누락, 목업 재시도 로그 불일치는 회귀 테스트와 함께 수정했습니다.
평가자를 켠 요청은 초기 전체 제한시간을 저장해 재개·재시도에도 사용합니다. 평가가 이미 저장된 표시와 실제 행이 불일치하면 손상으로 처리합니다.

A-6까지 완료했으며 B부 구현과 유료 실측은 진행하지 않았습니다.


---

# B부. 도입 평가 (어떤 구성을 기본으로 할지)

## 10. 원칙

1. **B부는 제품 코드를 바꾸지 않습니다.** 코드는 모두 `validation_tool/eval/`(Git 제외). `backend/app`은 호출만.
2. **심사위원 = A부 평가자 에이전트.** B부는 심사 코드를 새로 만들지 않고 `app.agents.evaluators.evaluate_draft`를 **완성된 보고서**에 부릅니다.
   심사 모드에서는 보고서를 바꾸지 않습니다(판정관 2차 호출 없음). 출력은 평가 결과뿐이고 B부가 점수로 바꿉니다.
   자기 채점 문제(평가자 의견이 이미 반영된 `v20e`·`v30e`를 같은 평가자가 다시 채점)는 12.4 규칙으로 막습니다.
3. **심사위원 점수는 보조 증거.** 주 증거는 정답이 있는 시험(11장). 심사위원 점수만 좋고 정답 시험이 그대로면 도입하지 않습니다.
4. **기준은 실행 전에 고정**(`criteria.json` + 규칙 파일 커밋 해시).
5. **유료 명령은 `--dry-run`(예상 호출 수 출력)이 기본, `--confirm`이 있어야 실행.**
6. 규제 자료가 없을 때도, 생긴 뒤에도 같은 방식으로 돌고, 규제 항목은 자료가 있을 때만 채점(`null` = 판단 불가).
   `manifest.csv`에 `regulation_source`(없음/버전)를 남겨 도입 전후 결과를 섞지 않습니다.

## 11. 채점 갈래 ① 정답이 있는 시험 (주 증거)

### 11.1 숫자 대조 (무료)

`validation_tool/eval/seed_eval_runs.py`(이전 레포트에 쓴 읽기 전용 스크립트)를 `offline.py`로 옮겨 함수로 쪼갭니다.

| 지표 | 정의 |
| --- | --- |
| a1 인용 숫자 일치율 | 이유 문장 숫자 중 같은 항목 `evidence` 값과 일치하는 비율 |
| a2 원자료 추적률 | 같은 숫자가 원자료 어디에든 있는 비율 |
| a3 근거 경로 유효율 | `index_paths()`·업종 소유·지도 규칙 통과 비율 |
| a4 교정 발생률 | 판정 교정 재시도가 있었던 실행 비율 |
| a5 브리핑 주장 폐기율 | 브리핑·답변 주장 중 검증기에서 버려진 비율(브리핑만) |
| a6 평가 반영률 (평가자 켬) | 지적 중 accepted·partial·rejected·unreviewed 비율 |

- 문맥 숫자 제거 규칙은 seed의 `CTX` 정규식, 버전을 `criteria.json`에 기록.
- 브리핑 최종 `limitations`의 `"전문가 근거 제외"`로 시작하는 문장은 한계 문장 수에서 뺍니다(알려진 누수).

### 11.2 백테스트 (유료, 가장 강한 증거)

| 입력 | 시점 이동 | 비고 |
| --- | --- | --- |
| 개폐업 | `BUSINESS_LIFECYCLE_BASE_QUARTER`, `BUSINESS_LIFECYCLE_QUARTER_COUNT` (`app/agents/business_lifecycle/config.py`) | 예 `20252`, `12` |
| 인구 | `floating_population.analyze(task, client=SeoulOpenDataClient(settings, today=date(...)))` | `client.py`의 `today` |
| 상권 점포 수 | **불가**(현재 스냅샷) → 주 실험은 `status="error"` 대역으로 끔 | 이후 실적이 섞여 들어 브리핑에 유리 |
| 지도 | 끔 | 현재 영업 장소 |

- 민감도 실험: 상권 켠 채로 한 번 더. 결론이 다르면 주 실험만 인정.
- 라벨(LLM 없음, T 시점 개폐업): `y_net = recent_year_net_change ÷ T−4 점포 수`, `healthy = y_net > 같은 상권 전 업종 중앙값`. 점포 5개 이상만, coverage 보고.
- 지표: Precision@k, NR-Precision, 분리도 Δ = mean(y_net|추천) − mean(y_net|비추천), Spearman ρ, Hit@5.
- 기준선 B0(LLM 없음): T−4 `lifecycle_score` 상위 5 / 하위 5. B0를 못 이기면 "AI가 예측력을 더한다"고 말하지 않음.
- 기준 시점 2개 이상(예 20252, 20244). 라벨은 "업종 건강도의 대리 지표"이지 개별 창업 성공이 아님(결과 문서에 그대로).

### 11.3 주입 시험 (유료)

| ID | 심는 사실 | 통과(코드 채점) |
| --- | --- | --- |
| E1 숨은 경쟁 | 지도 대역이 반경 100m 안 동종 8곳 | X가 추천 상위 3에서 빠지거나 X 근거에 `map_analysis` 경로 |
| E2 복구 가능한 LQ 실패 | `lq_retryable=true`, `retry_lq_baseline` 대역이 X의 LQ=3.0 | X의 LQ 경로 인용 + X 비추천 또는 risks에 과밀 |
| E3 소표본 고득점 | 점포 2개·`confidence=low` 업종 점수 90 | X가 1위 아님 또는 risks에 표본 경고 |
| E4 최근 급변 | `fetch_quarter_details` 대역에서 최근 2분기 폐업 급증 | X 강등 + 분기 상세 경로 인용 |
| E5 공간 조건 (평가자 효과) | 설비가 필요한 업종 X가 1위, 공간 정보 없음 | `allow_questions` 실행에서 X 관련 임대인 질문이 나오거나 X risks에 설비 확인 |
| E0 음성 대조 | 없음 | E1~E5 판정이 켜지지 않아야 함(오경보율) |

- 시나리오·판정 규칙은 `scenarios/*.json`, 실행 전 커밋 해시를 `criteria.json`에 기록.

### 11.4 안정성 (유료)

같은 입력으로 구성별 5회: 추천 집합 Jaccard, 1위 일치율, 추천↔비추천 뒤집힘, 실패율. **구성 간 차이 > 구성 내 반복 차이**인지 먼저 확인.

## 12. 채점 갈래 ② 심사위원 = 평가자 에이전트 (보조 증거)

### 12.1 무엇을 부르나

- 함수: A부의 `app.agents.evaluators.agent.evaluate_draft(evaluator, request, report, generate=..., allowed=["none"], timeout=...)`.
  - `report`는 **최종 보고서**(`DecisionResult`)입니다. 이름은 draft지만 같은 형식이라 그대로 넣습니다.
  - `allowed=["none"]`: 심사 모드에서는 추가 행동을 요청하지 않습니다(`request`는 모두 `none`으로 바뀜).
  - 지시문·검증 규칙(4.3·4.4)은 A부와 **같은 것**을 씁니다. 심사용 지시문을 따로 만들지 않습니다.
- 평가자 4명 × 보고서마다 1회. 결과는 A부의 `Evaluation` 그대로 `judge.csv`에 기록합니다.
- 판정관 2차 호출, 반영 기록, DB 저장(`evaluations` 표)은 **하지 않습니다**(심사는 제품 실행이 아님). 결과는 CSV에만 남깁니다.

### 12.2 블라인드 (코드로 강제)

- 심사 입력을 만들기 전에 보고서에서 구성 흔적을 지웁니다: `deliberation`, `analysis_mode`, `evaluation`(평가 기록), `"전문가 근거 제외"`로 시작하는 `limitations` 문장, `source_analyses`.
- `evaluation_input()`은 원래 `limitations`를 넣지 않으므로 추가 처리 없이 흔적이 대부분 빠집니다. 그래도 직렬화한 입력에 위 문자열이 남았는지 검사하고 남았으면 실행을 멈춥니다.
- 같은 주소의 구성별 보고서는 **섞은 순서**(시드 고정)로 심사합니다. 한 보고서씩 따로 평가하므로 A/B 순서 효과는 없습니다.

### 12.3 점수로 바꾸는 법 (코드, 고정)

보고서 하나 × 평가자 하나마다:

| 항목 | 계산 |
| --- | --- |
| `verdict_score` | agree 1.0 · conditional 0.5 · oppose 0.0 · failed = 결측 |
| `valid_comments` | 검증을 통과한 지적 수(0~4) |
| `grounded_comments` | 그중 `evidence`가 1개 이상 남은 지적 수(원자료로 확인 가능한 지적) |

- 보고서 점수 = 4명 `verdict_score` 평균(결측 제외), 보조로 `grounded_comments` 합(적을수록 문제 지적이 적음).
- 비교는 **주소마다 짝지어** 후보 − 기준선(`v20`) 차이로 냅니다(16장 통계).
- 해석 주의: 지적 수가 적다고 좋은 보고서라는 보장은 없습니다(평가자가 놓쳤을 수 있음). 그래서 12.5 시험을 통과한 평가자 결과만 씁니다.

### 12.4 자기 채점 방지

`v20e`·`v30e`는 보고서를 만들 때 이미 같은 평가자 의견을 반영했습니다. 같은 평가자가 다시 심사하면 점수가 부풀 수 있습니다.

- **결정에 쓰는 심사 비교는 평가자를 끈 구성끼리만**: `v20` vs `v30` (+ `b0`, `v20k` 참고).
- `v20e`·`v30e`의 심사 점수는 표에 **참고로만** 싣고 16장 결정에는 쓰지 않습니다. 이 두 구성은 정답이 있는 시험(11장)으로만 판정합니다.
- 선택 실험(21장에서 결정): 심사 때만 평가자 모델을 다른 모델로 바꿔(`JUDGE_LLM_*` → `LLMSettings.from_env("JUDGE")`) `v20e`·`v30e`도 심사 비교에 넣는 방식.

### 12.5 평가자 시험 (심사위원도 검증받음)

실제 보고서를 코드로 변형해 정답을 아는 보고서를 만들고, 일반 심사 입력에 **몰래 섞습니다**. 이 시험은 A부 평가자의 품질 검증도 겸합니다.

| 변형 | 만드는 법 | 잡았다고 보는 조건(코드) |
| --- | --- | --- |
| D1 숫자 틀림 | 이유 문장 숫자 하나를 근거 값과 다르게(×1.5) | 심사자(`examiner`)가 그 업종 코드로 지적 1개 이상 + verdict가 agree가 아님 |
| D2 위험 숨김 | `recent_year_net_change < 0` 추천 업종의 폐업 관련 risks 삭제 | 예비 창업자(`founder`)가 그 업종 코드로 지적 |
| D3 확인할 점 삭제 | 설비 필요 업종(`eval/facility_codes.json`)의 설비 문장 삭제 | 임대인 대변인(`landlord_advocate`)이 그 업종 코드로 지적 |
| D0 멀쩡함 | 변형 없음 | 위 조건이 켜지면 오경보 |

- 지표: 변형별 탐지율(TPR), D0 오경보율(FPR). 합격선은 `criteria.json`(초안 TPR ≥ 0.8, FPR ≤ 0.1).
- **합격선 미달 평가자의 심사 점수는 결정에서 뺍니다.** 뺀 사실을 결과에 적고, A부 지시문 개선 과제로 사용자에게 보고합니다.
- 변형 보고서는 심사 입력의 15~20%. 입력에 변형 표시 없음.
- 일치도: 같은 보고서를 2회 심사해 verdict 일치율(자기 일관성)을 냅니다. 0.6 미만인 평가자는 결정에서 뺍니다.

## 13. 채점 갈래 ③ 비용·시간

- 실행당 시간 p50·p90, LLM 호출 수, 입력·출력 토큰(`execution_json.budget`, trace `elapsed_ms`).
- 파레토 그림: 가로 호출 수, 세로 백테스트 Δ·주입 탐지율.

## 14. 비교 구성 (선수)

| ID | 구성 | 설정 |
| --- | --- | --- |
| `b0` | 점수만 (LLM 없음) | 저장된 개폐업 결과에서 계산 |
| `v20` | 단독 판정 | `ExecutionSettings(analysis_mode="single_decision")` |
| `v20k` | 단독 판정 k번 다수결 (k = 브리핑 평균 호출 수에 맞춤, 기본 5) | 업종별 추천 등장 ≥ k/2 → 추천, 점수 평균, 근거는 최빈 실행의 것 |
| `v30` | 브리핑 에이전트 | `analysis_mode="multi_agent"` |
| `v20e` | 단독 판정 + 평가자 | `analysis_mode="single_decision", evaluators_enabled=True` |
| `v30e` | 브리핑 + 평가자 | `analysis_mode="multi_agent", evaluators_enabled=True` |

- 입력 고정(`frozen.py`): 지정 실행의 `analysis.sqlite3`에서 `AgentAnalysis`를 읽어 `agents=`로 돌려주는 대역, 지도·보완도 저장 관측 대역. 모든 구성이 같은 입력을 봄.
- 실행 기록은 기존 `validation_tool/run.py` 형식(`runs/<id>/result.json`, `trace.jsonl`, `analysis.sqlite3`)으로 남겨 `validation_tool.web`에서 열리게.
- `.env`를 바꾸지 말고 `ExecutionSettings(...)`로 직접 넘깁니다.

## 15. 파일·명령·출력

```
validation_tool/eval/
  README.md · config.py · seed_eval_runs.py(참고용, 수정 금지)
  frozen.py · players.py · run_matrix.py · offline.py · backtest.py · inject.py · scenarios/E0~E5.json
  judging.py(평가자 에이전트를 심사 모드로 호출) · blind.py · defects.py · facility_codes.json
  stats.py · criteria.json · report.py · tests/
```

명령(저장소 루트에서, `conda activate chaeum`):

```powershell
python -m validation_tool.eval.offline --runs 266682fa,32d3e2c8,19655c43,50548eb1,abc5a942,efc80d9c
python -m validation_tool.eval.run_matrix --addresses addresses.csv --players b0,v20,v20k,v30,v20e,v30e --repeat 1 --dry-run
python -m validation_tool.eval.run_matrix ... --confirm
python -m validation_tool.eval.judging --manifest manifest.csv --dry-run
python -m validation_tool.eval.report --criteria validation_tool/eval/criteria.json
```

- `addresses.csv`: `address, district_type(도심|주거|대학가|오피스), radius_m`, 유형별 5곳. 주소는 사람이 정함.
- CSV 열(고정):
  - `manifest.csv`: `run_id, address, player, repeat, base_quarter, frozen_from, regulation_source, status, elapsed_ms, llm_calls, input_tokens`
  - `metrics_offline.csv`: `run_id, a1_num, a1_den, a2_num, a2_den, a3_num, a3_den, a4, a5_num, a5_den, a6_accept, a6_partial, a6_reject, a6_unreviewed`
  - `backtest.csv`: `address, player, base_quarter, precision_at_k, nr_precision, delta, spearman, hit5, coverage`
  - `inject.csv`: `scenario, player, trial, detected, false_alarm, evidence_ok`
  - `judge.csv`: `run_id, address, player, evaluator, repeat, source, verdict, verdict_score, valid_comments, grounded_comments, commented_codes, is_defect, defect_id, detected`
  - `summary.md`: 기준별 통과/실패, 숫자는 `값 [95% CI], n=주소 수`

## 16. 통계와 결정

- 분석 단위는 주소. 업종 단위는 주소 묶음 부트스트랩(1만 회, 시드 고정). 짝지은 차이 + Wilcoxon, 승패 부호 검정, 주입 시행 McNemar.
- `criteria.json` 초안(숫자는 팀 합의 후 확정, 실행 전 커밋):

```json
{
  "version": 1,
  "rules_hash": "<scenarios·defects·CTX 커밋 해시>",
  "baseline": "v20",
  "not_worse": {"a1_diff_ci_low_min": -0.03, "failure_rate_diff_max": 0.02,
                "stability_jaccard_diff_min": -0.05, "time_p50_ratio_max": 1.5},
  "better_any_of": {"backtest_delta_ci_low_gt": 0.0, "backtest_must_beat_b0": true,
                    "inject_detection_gain_min": 0.20, "inject_false_alarm_gain_max": 0.05},
  "structure_check": "후보가 통과한 better 지표에서 v20k도 이겨야 함",
  "judges": {"defect_tpr_min": 0.8, "clean_fpr_max": 0.1, "self_agreement_min": 0.6,
             "decision_players": ["v20", "v30"]}
}
```

- 후보(`v30`, `v20e`, `v30e`)마다 기준선 `v20`과 비교:
  1. `not_worse` 하나라도 실패 → 그 후보 탈락
  2. `better_any_of` 하나 이상 통과 + `structure_check` 통과 → 채택 후보
  3. 특정 주소 유형에서만 통과 → "그 유형에만" 후보
  4. 채택 후보가 여럿이면 호출 수가 적은 쪽. 없으면 `v20` 유지
  - 심사위원(평가자 에이전트) 점수는 1~4를 바꾸지 않습니다. 설명에만 씁니다. `v20e`·`v30e` 점수는 참고로만(12.4).

## 17. 제품 코드 변경이 필요한 곳 (B부 담당이 혼자 바꾸지 말 것)

| 필요 | 이유 | 처리 |
| --- | --- | --- |
| 브리핑 `limitations`의 내부 경고 분리 | 임대인용 문장 아님 + 비교 왜곡 | B부는 접두어로 걸러 냄. 제품 수정은 별도 PR |
| 브리핑 "되묻기 없음" 변형 | 향상 원인 분리 | 선택 실험, PR 합의 후 |
| 상권 시점 이동 | 백테스트 누수 | 불가, 제외로 대응 |
| 규제 도구 연결 | 다른 팀원 담당 | 만들지 않음 |

## 18. B부 단계

| 단계 | 할 일 | 비용 | 완료 조건 |
| --- | --- | --- | --- |
| B-0 | README·config·테스트 뼈대, seed → `offline.py` | 무료 | 기존 6회로 이전 레포트 표(83.4%/89.9%, 폐기 33/100) 재현 |
| B-1 | `frozen.py`·`players.py` 6구성(대역 LLM) | 무료 | 같은 입력에서 6구성 결과 파일, 네트워크 차단 테스트 |
| B-2 | `judging.py`·`blind.py`·`defects.py` (A부 평가자 호출, 대역 모델) | 무료 | 흔적 제거·변형·점수 변환·자기 채점 제외 테스트 |
| B-3 | `stats.py`·`report.py`·`criteria.json` 초안 | 무료 | 가짜 CSV로 결정 1~4가 각각 나옴 |
| **승인** | 주소 20곳, 기준 숫자, 비용 | — | `criteria.json` 확정(커밋은 사용자 요청 시) |
| B-4 | 소규모: 3곳 × 6구성 × 1회 + 심사 + 심사위원 시험 | 소액 | `summary.md` 생성, 비용 실측으로 아래 추정 갱신 |
| B-5 | 백테스트 20곳 × 2시점 × 6구성 | 유료 | `backtest.csv` |
| B-6 | 주입 E0~E5 × 5회 × (v20, v30, v20e, v30e), 안정성 5곳 × 5회 | 유료 | `inject.csv`, 안정성 표 |
| B-7 | 전체 심사(평가자 에이전트) + 평가자 시험 | 유료 | `judge.csv`, 탐지율·오경보율·자기 일치율 |
| B-8 | `report.py`로 결정 | 무료 | `summary.md`에 기준별 통과/실패와 결정 한 줄 |

예상 호출(단독 약 2 · 브리핑 약 13 · 평가자 +5 기준, B-4에서 갱신): 백테스트 360회 실행 약 1,900 · 주입 120회 약 1,100 · 안정성 약 375 · 심사 약 380 → **약 3,700회**.

## 19. B부 테스트 (네트워크 없이)

- [ ] 흔적 제거 후 심사 입력에 `multi_agent`·`single_decision`·`deliberation`·`evaluation`·`전문가 근거 제외` 문자열 0건
- [ ] 심사는 `app.agents.evaluators`를 호출하고(별도 심사 지시문 없음) `allowed=["none"]` · 판정관 2차 호출·DB 저장 없음
- [ ] 점수 변환(verdict_score·grounded_comments) · `v20e`·`v30e`가 결정 비교에서 빠짐 · D1은 숫자 하나만 바꿈, D0는 원본과 동일
- [ ] b0는 LLM 0회 · `v20k` 다수결 동률·중복을 시드로 결정적 처리 · `--confirm` 없이 유료 실행 안 됨
- [ ] `criteria.json` 결정 1~4 각각
- 실행: 저장소 루트 `python -m unittest discover -s validation_tool/eval/tests`, `backend`에서 기존 테스트.

---

## 20. 넘겨받을 때 주의

- 예전에 시도한 검토자 모드 코드는 **2026-10-01 되돌렸습니다.** A부는 처음부터 구현합니다. 되돌린 구현에서 겪은 함정:
  ① 판정 출력에 로그 키가 붙으면 `extra="forbid"`로 검증 실패 → 검증 **전에** 분리(5.4),
  ② 저장 훅에 dict와 pydantic 객체가 섞여 `model_dump` 오류 → 훅에는 항상 pydantic 객체(5.4),
  ③ 평가자 함수 4개 등록 여부를 실행 전에 검사(6.1).
- 서버 설정은 시작 시 한 번 읽습니다. `.env`를 바꾸면 서버를 다시 시작해야 합니다.
- SSL 환경변수(`SSL_CERT_FILE`, `SSL_CERT_DIR`)가 있으면 주소 조회가 실패했던 적이 있습니다. 실측 전에 해제합니다.
- 기존 실측 실행 ID: 단독 `266682fa`(송파)·`32d3e2c8`(강남)·`19655c43`(성동), 브리핑 `50548eb1`·`abc5a942`·`efc80d9c` (`validation_tool/runs/`).
- 법률·규제는 다른 팀원 담당. 필요해 보여도 만들지 말고 필요한 형식을 사용자에게 전달합니다.
- 문서와 코드가 다르거나 이 문서가 정하지 않은 결정이 필요하면 **멈추고 묻습니다.**

## 21. 이 문서가 정하지 않은 것 (검토 때 결정 필요)

| 항목 | 지금 문서의 가정 | 다른 선택지 |
| --- | --- | --- |
| 평가자 모델 | 공통 모델(`EVALUATOR_LLM_*` 없으면 `ELICE_*`) | 판정관과 다른 모델로 고정 |
| 평가자 전원 agree일 때 | 판정관 2차 호출 생략 | 항상 2차 호출 |
| 최종 단계 되묻기(브리핑) | **결정됨: 평가 후 별도 4라운드** | — |
| ~~화면에 평가 원문 노출~~ | **결정됨(2026-10-01): 평가자 의견 전부 노출** (판정·지적 문장·근거·요청 + 판정관 결정) | — |
| `EVALUATOR_RESERVE` | 4 | 측정 후 조정 |
| 심사 때 평가자 모델 | 제품과 같은 모델(평가자 켠 구성은 심사 비교에서 제외) | 심사 때만 다른 모델(`JUDGE_LLM_*`)로 바꿔 평가자 켠 구성도 비교 |
