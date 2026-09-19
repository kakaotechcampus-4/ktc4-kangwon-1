import type {
  AgentStatus,
  CommercialAreaData,
  CommercialAreaCategoryRank,
  CommercialAreaDistrictBaseline,
  CommercialAreaDiversity,
  CommercialAreaFranchise,
  CommercialAreaLqBaseline,
  CommercialAreaMajorCategory,
  CommercialAreaMiddleCategory,
  CommercialAreaRadiusSlice,
  CommercialAreaSpecializationRank,
} from '@/lib/mockData/report';
import { asArray, asNumber, asRecord, asString } from './shared';

/**
 * commercial_area 에이전트의 실제 출력(backend/app/agents/commercial_area/schemas.py의
 * CommercialAreaData.model_dump(), snake_case)을 화면이 쓰는 camelCase
 * CommercialAreaData(lib/mockData/report.ts)로 옮긴다.
 *
 * status/warnings/errorMessage는 이 함수가 받는 raw(=AgentAnalysis.data)
 * 안에 없다 — AgentAnalysis 봉투(envelope) 쪽 필드라 구조적으로 raw 하나만
 * 가지고는 만들어낼 수 없다. 그래서 envelope 인자로 따로 받는다(호출부인
 * app/report/page.tsx가 이미 agent.status/agent.warnings를 들고 있다).
 */
type Envelope = {
  status: AgentStatus;
  warnings?: string[];
  errorMessage?: string;
};

function mapMajor(raw: unknown): CommercialAreaMajorCategory {
  const r = asRecord(raw);
  return {
    code: asString(r.code),
    name: asString(r.name),
    count: asNumber(r.count),
    share: asNumber(r.share),
    densityPerKm2: asNumber(r.density_per_km2),
  };
}

function mapCategoryRank(raw: unknown): CommercialAreaCategoryRank {
  const r = asRecord(raw);
  return {
    rank: asNumber(r.rank),
    code: asString(r.code),
    name: asString(r.name),
    count: asNumber(r.count),
    densityPerKm2: asNumber(r.density_per_km2),
    note: asString(r.note),
  };
}

function mapRadiusSlice(raw: unknown): CommercialAreaRadiusSlice {
  const r = asRecord(raw);
  return {
    radiusM: asNumber(r.radius_m),
    storeTotal: asNumber(r.store_total),
    categoryCount: asNumber(r.category_count),
    absentCategoryCount: asNumber(r.absent_category_count),
    topByCount: asArray(r.top_by_count).map(mapCategoryRank),
  };
}

function mapSpecializationRank(raw: unknown): CommercialAreaSpecializationRank {
  const r = asRecord(raw);
  return {
    rank: asNumber(r.rank),
    code: asString(r.code),
    name: asString(r.name),
    count: asNumber(r.count),
    timesVsSurroundings: asNumber(r.times_vs_surroundings),
    note: asString(r.note),
  };
}

// by_middle 전체를 그대로 옮긴다 — "추천 업종 10개만 미리 골라둔 것"이라는
// 목업 시절 의도(RECOMMENDED_NAME_TO_MIDDLE_CODE 매핑용)는 여기서 다시
// 만들지 않는다. 그 매핑 테이블 자체가 목업 업종명 기준이라 실제
// category.middle 값과 맞지 않는 건 이미 알려진 별도 이슈고
// (CompetitorAnalysisSection.tsx의 IndustryCompetitionGrid 주석 참고),
// 이 어댑터가 그걸 대신 해결하려 하면 스코프가 커진다. 컴포넌트는 이미
// code로 .find()만 하므로, 배열이 10개로 줄어 있지 않아도 동작은 같다.
function mapMiddleCategory(raw: unknown): CommercialAreaMiddleCategory {
  const r = asRecord(raw);
  return {
    code: asString(r.code),
    name: asString(r.name),
    sameTypeCount: asNumber(r.same_type_count),
    diffTypeCount: asNumber(r.diff_type_count),
    lq: typeof r.lq === 'number' ? r.lq : null,
    lqDistrict: typeof r.lq_district === 'number' ? r.lq_district : null,
  };
}

function mapDiversity(raw: unknown): CommercialAreaDiversity {
  const r = asRecord(raw);
  return { effectiveCategories: asNumber(r.effective_categories) };
}

function mapFranchise(raw: unknown): CommercialAreaFranchise | null {
  if (!raw) {
    return null;
  }
  const r = asRecord(raw);
  const confidence = r.confidence;
  return {
    count: asNumber(r.count),
    ratio: asNumber(r.ratio),
    confidence:
      confidence === 'high' || confidence === 'medium' || confidence === 'low'
        ? confidence
        : 'low',
  };
}

function mapLqBaseline(raw: unknown): CommercialAreaLqBaseline {
  const r = asRecord(raw);
  return {
    requestedRadiusM: asNumber(r.requested_radius_m),
    appliedRadiusM:
      typeof r.applied_radius_m === 'number' ? r.applied_radius_m : null,
  };
}

// signgu_name이 없으면(백엔드 스키마상 nullable) "자치구 비교 자료 없음"과
// 동등하게 다룬다 — CompetitorAnalysisSection.tsx가 districtBaseline이
// null일 때 이미 '자치구'라는 대체 문구를 쓰고 있어(코드 참고), 이름 없는
// 객체를 그대로 넘기면 그 대체 로직이 못 걸리고 빈 이름이 그대로 노출된다.
function mapDistrictBaseline(
  raw: unknown
): CommercialAreaDistrictBaseline | null {
  if (!raw) {
    return null;
  }
  const r = asRecord(raw);
  const signguName = r.signgu_name;
  return typeof signguName === 'string' && signguName.length > 0
    ? { signguName }
    : null;
}

export function adaptCommercialArea(
  raw: Record<string, unknown>,
  envelope: Envelope = { status: 'ok', warnings: [] }
): CommercialAreaData {
  return {
    status: envelope.status,
    errorMessage: envelope.errorMessage,
    warnings: envelope.warnings ?? [],
    radiusM: asNumber(raw.radius_m),
    storeTotal: asNumber(raw.store_total),
    // 백엔드 스키마상 nullable(data_reference_date: Text | None)인데 화면
    // 타입은 필수 string이다 — 없으면 빈 문자열로 채우고, 화면 쪽 문구는
    // "OO일 조회" 형태라 빈 문자열이면 그 문구 자체가 통째로 안 보이는
    // 쪽이 "조회일 미상"을 어설프게 표기하는 것보다 낫다.
    dataReferenceDate: asString(raw.data_reference_date),
    byMajor: asArray(raw.by_major).map(mapMajor),
    byRadius: asArray(raw.by_radius).map(mapRadiusSlice),
    diversity: mapDiversity(raw.diversity),
    franchise: mapFranchise(raw.franchise),
    lqBaseline: mapLqBaseline(raw.lq_baseline),
    districtBaseline: mapDistrictBaseline(raw.district_baseline),
    districtSpecialization: asArray(raw.district_specialization).map(
      mapSpecializationRank
    ),
    byMiddleForRecommendations: asArray(raw.by_middle).map(mapMiddleCategory),
  };
}
