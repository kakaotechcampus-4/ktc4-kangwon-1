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

export type AnalysisStoredStatus =
  'pending' | 'running' | 'completed' | 'failed';

export interface StoredAnalysis {
  status: AnalysisStoredStatus;
  site: Record<string, unknown> | null;
  result: DecisionResult | null;
  error: AgentError | null;
}
