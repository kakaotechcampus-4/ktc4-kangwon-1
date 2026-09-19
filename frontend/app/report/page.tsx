'use client';

import { useEffect, useState } from 'react';
import { DM_Mono } from 'next/font/google';
import Header from '@/components/layout/Header';
import ReportHeader from '@/components/report/ReportHeader';
import RecommendationSection from '@/components/report/RecommendationSection';
import AIAnalysisSummary from '@/components/report/AIAnalysisSummary';
import DetailAnalysisTabs from '@/components/report/DetailAnalysisTabs';
import Button from '@/components/ui/Button';
import { colors } from '@/styles/tokens';
import { mockReportData } from '@/lib/mockData/report';
import type {
  BusinessLifecycleData,
  CommercialAreaData,
  FloatingPopulationData,
} from '@/lib/mockData/report';
import { loadAnalysisResult } from '@/lib/api/resultStore';
import type {
  AgentAnalysis,
  AgentId,
  DecisionResult,
  IndustryAssessment,
} from '@/lib/api/types';
import { adaptCommercialArea } from '@/lib/api/adapters/commercialArea';
import { adaptBusinessLifecycle } from '@/lib/api/adapters/businessLifecycle';
import { adaptFloatingPopulation } from '@/lib/api/adapters/floatingPopulation';

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

function findAgent(
  result: DecisionResult,
  agentId: AgentId
): AgentAnalysis | undefined {
  return result.source_analyses.find((agent) => agent.agent_id === agentId);
}

/**
 * agent.data는 백엔드 계약상 Record<string, unknown>이고, 어떤 필드를
 * 담을지는 각 분석 에이전트가 정한다(backend/app/schemas.py 주석 참고).
 *
 * 세 에이전트(floating_population, commercial_area, business_lifecycle)
 * 모두 default_agents()(backend/app/agents/orchestration/workflow.py)에
 * 등록돼 있어 실호출로 진짜 데이터가 온다. 각자 전용 어댑터
 * (lib/api/adapters/floatingPopulation.ts, commercialArea.ts,
 * businessLifecycle.ts)로 실제 snake_case 출력을 화면 타입으로 옮긴다.
 * status/warnings는 data 안이 아니라 AgentAnalysis 봉투에 있어 envelope
 * 인자로 따로 넘긴다.
 */
function extractFloatingPopulationData(
  agent: AgentAnalysis | undefined
): FloatingPopulationData | null {
  if (!agent) {
    return null;
  }
  return adaptFloatingPopulation(agent.data, {
    status: agent.status,
    warnings: agent.warnings,
    errorMessage: agent.error?.message,
  });
}

function extractCommercialAreaData(
  agent: AgentAnalysis | undefined
): CommercialAreaData | null {
  if (!agent) {
    return null;
  }
  return adaptCommercialArea(agent.data, {
    status: agent.status,
    warnings: agent.warnings,
    errorMessage: agent.error?.message,
  });
}

// 결정 에이전트의 recommendations/not_recommended에서 업종명(category.middle)만
// 뽑는다 — adaptBusinessLifecycle이 개폐업 에이전트의 70여 개 업종 중 이
// 리포트가 다루는 10개만 골라내는 데 쓴다.
function industryNames(items: IndustryAssessment[]): string[] {
  return items.map((item) => item.category.middle);
}

function extractBusinessLifecycleData(
  agent: AgentAnalysis | undefined,
  recommendedNames: string[],
  notRecommendedNames: string[]
): BusinessLifecycleData | null {
  if (!agent || agent.status === 'error') {
    return null;
  }
  return adaptBusinessLifecycle(
    agent.data,
    recommendedNames,
    notRecommendedNames
  );
}

export default function ReportPage() {
  const [analysisResult, setAnalysisResult] = useState<DecisionResult | null>(
    null
  );

  useEffect(() => {
    // sessionStorage는 브라우저 전용이라 서버 렌더에서는 접근할 수 없다.
    // 마운트 후 한 번만 읽어 온다 — 이 첫 렌더 이후의 추가 렌더 한 번은
    // 페이지 진입 시 결과를 채워 넣는 데 불가피하다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAnalysisResult(loadAnalysisResult());
  }, []);

  const floatingPopulationData = analysisResult
    ? extractFloatingPopulationData(
        findAgent(analysisResult, 'floating_population')
      )
    : undefined;
  const competitorData = analysisResult
    ? extractCommercialAreaData(findAgent(analysisResult, 'commercial_area'))
    : undefined;
  const businessLifecycleData = analysisResult
    ? extractBusinessLifecycleData(
        findAgent(analysisResult, 'business_lifecycle'),
        industryNames(analysisResult.recommendations),
        industryNames(analysisResult.not_recommended)
      )
    : undefined;

  const analyzedDate = analysisResult
    ? new Date().toLocaleDateString('ko-KR')
    : mockReportData.analyzedDate;
  const address = analysisResult?.address ?? '춘천시 후평동 234-5';

  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />
      <ReportHeader />

      {analysisResult?.status === 'partial' &&
        analysisResult.limitations.length > 0 && (
          <div
            className="mx-8 mt-4 flex flex-col gap-1 rounded-lg px-4 py-3 text-xs"
            style={{
              backgroundColor: colors.neutral.background,
              color: 'var(--color-gray-500)',
            }}
          >
            {analysisResult.limitations.map((note) => (
              <p key={note}>※ {note}</p>
            ))}
          </div>
        )}

      <RecommendationSection
        recommendations={analysisResult?.recommendations}
        notRecommended={analysisResult?.not_recommended}
      />
      <AIAnalysisSummary />
      <DetailAnalysisTabs
        floatingPopulation={
          analysisResult
            ? {
                data: floatingPopulationData ?? undefined,
                unavailable: !floatingPopulationData,
              }
            : undefined
        }
        competitor={
          analysisResult
            ? {
                data: competitorData ?? undefined,
                unavailable: !competitorData,
                recommendations: analysisResult.recommendations,
                notRecommended: analysisResult.not_recommended,
              }
            : undefined
        }
        openClose={
          analysisResult
            ? {
                data: businessLifecycleData ?? undefined,
                unavailable: !businessLifecycleData,
              }
            : undefined
        }
      />

      <div
        className="mx-8 mt-10 mb-10 flex items-center justify-between pt-6"
        style={{ borderTop: `1px solid ${colors.neutral.border}` }}
      >
        <p className={`${dmMono.className} text-xs text-gray-400`}>
          chum.ai · 분석일 {analyzedDate} · {address}
        </p>
        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="outline"
            className="text-gray-600"
            style={{ padding: '10px 16px', fontSize: '12px' }}
          >
            리포트 다운로드 (PDF)
          </Button>
          <Button
            type="button"
            variant="outline"
            className="text-gray-600"
            style={{ padding: '10px 16px', fontSize: '12px' }}
          >
            공유 링크 복사
          </Button>
        </div>
      </div>
    </div>
  );
}
