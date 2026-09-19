import type {
  BusinessLifecycleConfidence,
  BusinessLifecycleData,
  BusinessLifecycleDataStatus,
  BusinessLifecycleIndustryResult,
  BusinessLifecycleMetrics,
  BusinessLifecycleSourceCoverage,
} from '@/lib/mockData/report';
import {
  asArray,
  asNullableNumber,
  asNumber,
  asRecord,
  asString,
  asStringArray,
} from './shared';

/**
 * business_lifecycle 에이전트의 실제 출력
 * (feature/mvp1-refact의 input_builder.py build_agent_input() →
 * formatter.py format_for_mediator()가 만드는 AgentAnalysis.data 형태)을
 * 화면이 쓰는 BusinessLifecycleData로 옮긴다.
 *
 * commercial_area(lib/api/adapters/commercialArea.ts)와 다른 점: 백엔드가
 * 이미 camelCase 아닌 snake_case 그대로 화면에 쓸 문장(evidence)·배지
 * 라벨(type)까지 만들어 내려주므로, 필드명을 바꾸지 않고 원본 구조를
 * 그대로 쓴다(lib/mockData/report.ts의 BusinessLifecycleData 타입 참고).
 * 그래서 이 어댑터가 실제로 하는 일은 두 가지뿐이다: (1) raw를 안전하게
 * 파싱하고 (2) industries(공통 업종 코드 75개)를 이 리포트가 다루는 10개
 * 업종(recommendedNames/notRecommendedNames)으로 필터링하는 것.
 */

// metrics는 점수 계산 업종(17개 키)과 판단 보류 업종(11개 키)이 서로 다른
// 키 집합을 갖는다(lib/mockData/report.ts의 BusinessLifecycleMetrics 주석
// 참고) — 그래서 모든 키를 개별적으로 "있으면 숫자, 없으면 undefined"로
// 옮긴다. 없는 키에 0을 채우면 "관측됐는데 값이 0"과 "원래 이 필드가 없음"이
// 구분이 안 된다.
function mapMetrics(raw: unknown): BusinessLifecycleMetrics {
  const r = asRecord(raw);
  const pick = (key: string): number | null | undefined =>
    key in r ? asNullableNumber(r[key]) : undefined;

  return {
    observed_quarters: pick('observed_quarters'),
    latest_store_count: pick('latest_store_count'),
    avg_store_count: pick('avg_store_count'),
    period_open_count: pick('period_open_count'),
    period_close_count: pick('period_close_count'),
    period_net_change: pick('period_net_change'),
    avg_open_rate: pick('avg_open_rate'),
    avg_close_rate: pick('avg_close_rate'),
    net_change_rate: pick('net_change_rate'),
    turnover_rate: pick('turnover_rate'),
    recent_year_open_count: pick('recent_year_open_count'),
    recent_year_close_count: pick('recent_year_close_count'),
    recent_year_net_change: pick('recent_year_net_change'),
    recent_year_close_rate: pick('recent_year_close_rate'),
    recent_year_net_change_rate: pick('recent_year_net_change_rate'),
    oldest_year_close_rate: pick('oldest_year_close_rate'),
    close_rate_trend: pick('close_rate_trend'),
  };
}

function mapSourceCoverage(
  raw: unknown
): BusinessLifecycleSourceCoverage | undefined {
  if (!raw) {
    return undefined;
  }
  const r = asRecord(raw);
  return {
    expected_source_count: asNullableNumber(r.expected_source_count),
    observed_source_rows: asNullableNumber(r.observed_source_rows),
    expected_source_rows: asNullableNumber(r.expected_source_rows),
    observed_quarters: asNullableNumber(r.observed_quarters),
  };
}

function asConfidence(value: unknown): BusinessLifecycleConfidence {
  return value === 'high' ||
    value === 'medium' ||
    value === 'low' ||
    value === 'none'
    ? value
    : 'none';
}

function asDataStatus(value: unknown): BusinessLifecycleDataStatus | undefined {
  return value === 'observed' ||
    value === 'unsupported' ||
    value === 'missing' ||
    value === 'incomplete'
    ? value
    : undefined;
}

function mapIndustryResult(raw: unknown): BusinessLifecycleIndustryResult {
  const r = asRecord(raw);
  return {
    industry_id: asString(r.industry_id),
    industry_name: asString(r.industry_name),
    score: asNullableNumber(r.score),
    type: asString(r.type, '판단 보류'),
    confidence: asConfidence(r.confidence),
    data_available: r.data_available === true,
    score_available: r.score_available === true,
    data_status: asDataStatus(r.data_status),
    data_complete:
      typeof r.data_complete === 'boolean' ? r.data_complete : undefined,
    metrics: mapMetrics(r.metrics),
    source_coverage: mapSourceCoverage(r.source_coverage),
    evidence: asStringArray(r.evidence),
    warning: typeof r.warning === 'string' ? r.warning : null,
  };
}

/**
 * industries 중 recommendedNames/notRecommendedNames(결정 에이전트의
 * recommendations/not_recommended에서 뽑은 업종명 10개)와 industry_name이
 * 일치하는 것만 남긴다. 일치하지 않는 이름이 있으면(commercial_area의
 * "무인점포" 케이스와 같은 성격의 문제 — 결정 에이전트는 자유 문자열을,
 * 개폐업은 공통 업종 코드 75종의 표준명을 쓴다) 콘솔에 한 번만(모아서)
 * 경고한다. 컴포넌트는 반환된 배열의 길이가 10보다 적은 걸로 매칭 실패를
 * 감지해 안내를 보여준다(OpenCloseTrendSection.tsx의 matchedShortfall).
 */
function filterByRecommendedNames(
  results: BusinessLifecycleIndustryResult[],
  recommendedNames: string[],
  notRecommendedNames: string[]
): BusinessLifecycleIndustryResult[] {
  const targetNames = new Set([...recommendedNames, ...notRecommendedNames]);
  const byName = new Map(results.map((item) => [item.industry_name, item]));

  const matched: BusinessLifecycleIndustryResult[] = [];
  const unmatchedNames: string[] = [];

  for (const name of targetNames) {
    const found = byName.get(name);
    if (found) {
      matched.push(found);
    } else {
      unmatchedNames.push(name);
    }
  }

  if (unmatchedNames.length > 0) {
    console.warn(
      `[adaptBusinessLifecycle] 다음 업종은 개폐업 데이터에 매칭되지 않았습니다(업종 분류 체계 불일치): ${unmatchedNames.join(', ')}`
    );
  }

  return matched;
}

export function adaptBusinessLifecycle(
  raw: Record<string, unknown>,
  recommendedNames: string[],
  notRecommendedNames: string[]
): BusinessLifecycleData | null {
  // status가 error/no_data면 data={}라 이 조건에서 걸린다. industries 키
  // "만" 확인하면 부족하다 — backend/app/mocks.py의 옛 스텁도 우연히
  // industries라는 배열 키를 갖고 있어서(항목 모양은 전혀 다름:
  // {middle, open_count, close_count}), 그것만으로는 걸러지지 않는다.
  // coverage/scoring_method는 그 스텁에 전혀 없으므로 같이 확인한다.
  if (
    !raw ||
    !Array.isArray(raw.industries) ||
    !raw.coverage ||
    !raw.scoring_method
  ) {
    return null;
  }

  const allResults = asArray(raw.industries).map(mapIndustryResult);
  const coverage = asRecord(raw.coverage);
  const scoringMethod = asRecord(raw.scoring_method);
  const weights = asRecord(scoringMethod.weights);

  return {
    summary: typeof raw.summary === 'string' ? raw.summary : undefined,
    metadata: raw.metadata ? asRecord(raw.metadata) : undefined,
    taxonomy: raw.taxonomy ? asRecord(raw.taxonomy) : undefined,
    coverage: {
      target_industries: asNumber(coverage.target_industries),
      scored_industries: asNumber(coverage.scored_industries),
      unscored_industries: asNumber(coverage.unscored_industries),
    },
    scoring_method: {
      description: asString(scoringMethod.description),
      score_type: asString(scoringMethod.score_type),
      weights: {
        recent_year_close_rate: asNumber(weights.recent_year_close_rate),
        net_change_rate: asNumber(weights.net_change_rate),
        turnover_stability: asNumber(weights.turnover_stability),
        close_rate_trend: asNumber(weights.close_rate_trend),
      },
      notes: asStringArray(scoringMethod.notes),
    },
    industries: filterByRecommendedNames(
      allResults,
      recommendedNames,
      notRecommendedNames
    ),
  };
}
