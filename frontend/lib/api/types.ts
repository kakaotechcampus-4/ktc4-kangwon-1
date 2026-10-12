/**
 * backend/app/schemas.py가 원본이다. 그쪽이 바뀌면 여기도 같이 고친다.
 * (docs/API_CONTRACT.md: 가능하면 openapi.json에서 생성하는 쪽을 권장하지만,
 * 백엔드 분석 에이전트가 아직 없어 지금은 손으로 옮겨 적는다.)
 */

export type AgentId =
  'floating_population' | 'business_lifecycle' | 'commercial_area';

export interface Scope {
  area: string;
  period: string;
}

export interface AgentError {
  code: string;
  message: string;
}

export interface AgentAnalysis {
  request_id: string;
  agent_id: AgentId;
  status: 'ok' | 'partial' | 'no_data' | 'error';
  scope: Scope | null;
  data: Record<string, unknown>;
  error: AgentError | null;
  warnings: string[];
}

export interface Evidence {
  agent_id: AgentId;
  path: string;
}

export interface Category {
  major: string;
  middle: string;
}

export interface IndustryAssessment {
  category: Category;
  score: number;
  reasons: string[];
  evidence: Evidence[];
  risks: string[];
}

export interface DecisionResult {
  schema_version: '1.0';
  agent_id: 'decision';
  request_id: string;
  address: string;
  status: 'ok' | 'partial' | 'no_data';
  summary: string;
  recommendations: IndustryAssessment[];
  not_recommended: IndustryAssessment[];
  limitations: string[];
  source_analyses: AgentAnalysis[];
}

// 요청 처리 상태 — GET /analyses/{id}와 events 응답의 status
// (pending은 202 직후 아직 저장 전일 때 events에서만 나온다)
export type AnalysisStoredStatus =
  'pending' | 'running' | 'waiting_for_input' | 'completed' | 'failed';

// 임대인에게 물을 수 있는 항목 — backend/app/schemas.py QuestionField
export type QuestionField =
  | 'floor'
  | 'exclusive_area'
  | 'space_condition'
  | 'existing_facilities'
  | 'industry_preferences';

export interface LandlordQuestion {
  field: QuestionField;
  text: string;
  why_needed: string;
  expected_impact: string;
}

// 분석이 질문 대기로 멈췄을 때 — backend/app/schemas.py WaitingForInput
export interface WaitingForInput {
  status: 'waiting_for_input';
  request_id: string;
  question_set_id: string;
  questions: LandlordQuestion[];
}

export interface LandlordAnswer {
  field: QuestionField;
  status: 'answered' | 'unknown' | 'skipped';
  // answered일 때만 넣는다(1000자 이내)
  value?: string;
}

export interface AnswerSubmission {
  request_id: string;
  question_set_id: string;
  answers: LandlordAnswer[];
}

// POST ?wait=false 의 202 응답
export interface AcceptedAnalysis {
  request_id: string;
  status: 'running';
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

// GET /analyses/{id} — 화면에서 쓰는 필드만 적는다(나머지는 백엔드가 더 준다).
export interface StoredAnalysis {
  request_id: string;
  status: AnalysisStoredStatus;
  site: Record<string, unknown> | null;
  result: DecisionResult | null;
  error: AgentError | null;
  questions: WaitingForInput | null;
}
