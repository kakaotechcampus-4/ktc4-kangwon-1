import { INDUSTRIES } from '@/lib/api/industries';
import type { LRecord } from '@/lib/api/types';

/** 백엔드 LRecord 계약을 따르는 51개 업종 순위 화면용 목업 데이터. */
export const mockIndustryRecords: LRecord[] = Object.keys(INDUSTRIES).map(
  (industry_code, index) => ({
    industry_code,
    selection: {
      basis: 'all_industries',
      code_score_snapshot_id: 'mock-industry-ranking',
      code_lower_rank: index + 1,
      reason: '전체 업종 순위 화면 확인을 위한 목업 데이터입니다.',
      reason_fact_ids: [],
    },
    review_state: 'unreviewed',
    advisor_unavailable: false,
    status: 'unknown',
    grade: null,
    new_factors: [],
    checked_questions: [],
    tool_call_ids: [],
    advisor_consult_ids: [],
    limitations: ['실제 분석 결과가 아닌 목업 데이터입니다.'],
  })
);
