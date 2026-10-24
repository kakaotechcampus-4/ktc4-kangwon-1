/**
 * backend/app/schemas.py(DecisionResult 2.0)와 backend/app/agentic/contracts.py가
 * 원본이다. 그쪽이 바뀌면 여기도 같이 고친다(docs/API_CONTRACT.md).
 */

// ---------------------------------------------------------------------------
// fact — 서버가 계산한 숫자 하나. 문장 속 숫자는 모두 fact 슬롯으로 들어온다.
// ---------------------------------------------------------------------------

export type FactSource =
  | 'floating_population'
  | 'resident_population'
  | 'worker_population'
  | 'commercial_area'
  | 'business_lifecycle'
  | 'map'
  | 'regulation'
  | 'user'
  | 'baseline'
  | 'industry_profile';

export type FactStatus = 'observed' | 'unknown' | 'not_applicable';

export type JsonValue =
  string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface FactView {
  fact_id: string;
  source: FactSource;
  // 백엔드 Metric 목록(by_time, density_per_km2 ...). 화면은 쓰는 것만 골라 읽는다.
  metric: string;
  // observed가 아니면 null이다.
  value: JsonValue;
  unit: string;
  period: string;
  spatial_scope: Record<string, JsonValue>;
  industry_code: string | null;
  status: FactStatus;
  citable: boolean;
  calc_version: string;
  provenance_ref: string;
}

export interface TextSegment {
  type: 'text';
  text: string;
}

export interface FactReferenceSegment {
  type: 'fact';
  fact_id: string;
  format: 'count' | 'percent' | 'rate' | 'distance' | 'text';
}

// 문장 조각. text는 그대로, fact는 facts에서 값을 찾아 숫자로 바꿔 이어 붙인다.
export type FactSegment = TextSegment | FactReferenceSegment;

// ---------------------------------------------------------------------------
// 최종 결과
// ---------------------------------------------------------------------------

export type Badge = '추천' | '조건부' | '보류' | '비추천';
export type RegulationStatus = '금지' | '조건부' | '해당 없음' | 'unknown';
export type ReviewState = 'reviewed' | 'unreviewed';

/** 검토 후보 한 업종. 점수는 코드 기여(최대 90) + 판단 L(최대 10)이다. */
export interface FinalCandidate {
  industry_code: string;
  industry_name: string;
  code_points: number;
  // L 미확인이면 null이다(0점이 아니다).
  L_points: number | null;
  L_status: 'observed' | 'unknown';
  // A: 적용 배점, B: 점수 하한, H: 점수 상한 (B ≤ H ≤ A)
  A: number;
  B: number;
  H: number;
  // A가 0이면 세 비율은 null이다.
  lower_ratio: number | null;
  upper_ratio: number | null;
  coverage: number | null;
  demand_coverage: number | null;
  competition_coverage: number | null;
  G: RegulationStatus;
  badge: Badge;
  confirmation_conditions: string[];
  reasons_segments: FactSegment[];
  risks_segments: FactSegment[];
  confirmation_conditions_segments: FactSegment[];
  fact_ids: string[];
  review_state: ReviewState;
}

export type FacilityKey = 'kitchen' | 'ventilation' | 'water_supply';
export type FacilityState =
  'present' | 'installable' | 'unavailable' | 'unknown';

export interface ConditionExcludedCandidate {
  industry_code: string;
  industry_name: string;
  reasons: string[];
  score_rank: number;
}

export interface NewFactor {
  direction: 'favorable' | 'adverse' | 'neutral';
  claim: string;
  fact_ids: string[];
  major_constraint: boolean;
  space_fit_component:
    'floor' | 'area' | 'kitchen' | 'ventilation' | 'water_supply' | null;
}

/** 51개 업종 각각의 판단(L) 기록. */
export interface LRecord {
  industry_code: string;
  selection: {
    basis: 'all_industries';
    code_score_snapshot_id: string;
    code_lower_rank: number;
    reason: string;
    reason_fact_ids: string[];
  };
  review_state: ReviewState;
  advisor_unavailable: boolean;
  status: 'observed' | 'unknown';
  grade: number | null;
  new_factors: NewFactor[];
  checked_questions: string[];
  tool_call_ids: string[];
  advisor_consult_ids: string[];
  limitations: string[];
}

// 평가자 네 명: 심사위원·창업자·고객·임대인 대변인
export type EvaluatorActor =
  'examiner' | 'founder' | 'customer' | 'landlord_advocate';

export interface ReviewIssue {
  issue_id: string;
  industry_code: string | null;
  target: 'fact' | 'score' | 'L' | 'claim' | 'condition';
  kind:
    | 'factual_error'
    | 'duplicate_score'
    | 'missing_evidence'
    | 'scope_mismatch'
    | 'action_condition';
  comment: string;
  fact_ids: string[];
  suggested_check: string;
}

export interface EvaluatorReview {
  actor: EvaluatorActor;
  // failed는 동의로 보지 않는다.
  status: 'completed' | 'failed';
  review_id: string | null;
  verdict: 'agree' | 'conditional' | 'oppose' | null;
  issues: ReviewIssue[];
  error_code: string | null;
}

export interface ReviewResolution {
  issue_id: string;
  disposition: 'accepted' | 'partial' | 'rejected';
  reason: string;
  fact_ids: string[];
  applied: string[];
  not_applied: string[];
}

export interface DecisionResult {
  schema_version: '2.0';
  rubric_version: string;
  tool_contract_version: string;
  request_id: string;
  run_id: string;
  report_id: string;
  snapshot_id: string;
  score_snapshot_id: string;
  summary_segments: FactSegment[];
  top5: FinalCandidate[];
  excluded_candidates: FinalCandidate[];
  condition_excluded?: ConditionExcludedCandidate[];
  // 보고서가 인용한 fact만 담는다. 차트용 전체 fact는 getAnalysisFacts로 받는다.
  facts: FactView[];
  L_records: LRecord[];
  evaluator_reviews: EvaluatorReview[];
  review_completeness: number;
  review_resolutions: ReviewResolution[];
  confirmation_conditions_segments: FactSegment[];
  limitations_segments: FactSegment[];
}

/** GET /analyses/{id}/facts — 요청 스냅샷의 전체 fact(리포트 차트용). */
export interface RequestFacts {
  request_id: string;
  // 자료 조회 전이면 null이고 facts는 빈 목록이다.
  snapshot_id: string | null;
  facts: FactView[];
}

// ---------------------------------------------------------------------------
// 진행 상태·질문
// ---------------------------------------------------------------------------

// 요청 처리 상태 — GET /analyses/{id}와 events 응답의 status
export type AnalysisStoredStatus =
  'pending' | 'running' | 'waiting_for_input' | 'completed' | 'failed';

// 임대인에게 물을 수 있는 항목 — backend/app/schema_types.py QuestionField
export type QuestionField =
  | 'floor'
  | 'exclusive_area'
  | 'space_condition'
  | 'existing_facilities'
  | 'industry_preferences';

export interface UserQuestion {
  field: QuestionField;
  question: string;
  reason: string;
}

/** 분석이 질문 대기로 멈췄을 때. 화면은 이 모양 하나로 다룬다. */
export interface WaitingForInput {
  status: 'waiting_for_input';
  request_id: string;
  question_session_id: string;
  questions: UserQuestion[];
}

/**
 * POST /answers 본문. 저장된 질문 field와 정확히 같은 항목에
 * 비어 있지 않은 문자열(500자 이내)을 넣는다.
 */
export interface AnswerSubmission {
  request_id: string;
  question_session_id: string;
  answers: Partial<Record<QuestionField, string>>;
}

// POST ?wait=false 의 202 응답
export interface AcceptedAnalysis {
  request_id: string;
  status: 'pending' | 'running';
}

export interface AnalysisEvent {
  seq: number;
  at: string;
  stage: string;
  event: string;
  detail: Record<string, unknown>;
}

export interface AnalysisEvents {
  request_id: string;
  status: AnalysisStoredStatus;
  finished: boolean;
  events: AnalysisEvent[];
  next_after: number;
}

export interface AnalysisError {
  code: string;
  message: string;
}

// GET /analyses/{id}의 질문 칸 — WaitingForInput과 달리 request_id가 없다.
export interface StoredQuestions {
  question_session_id: string;
  questions: UserQuestion[];
  status: string;
}

// 최종 결과에서 서버가 미리 이어 붙인 문장
export interface RenderedReport {
  summary: string;
  top5: { industry_code: string; reasons: string }[];
}

// GET /analyses/{id} — 화면에서 쓰는 필드만 적는다(나머지는 백엔드가 더 준다).
export interface StoredAnalysis {
  request_id: string;
  status: AnalysisStoredStatus;
  site: Record<string, unknown> | null;
  result: DecisionResult | null;
  error: AnalysisError | null;
  questions: StoredQuestions | null;
  rendered: RenderedReport | null;
}
