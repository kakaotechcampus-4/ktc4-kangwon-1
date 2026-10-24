'use client';

import {
  Camera,
  Coffee,
  Croissant,
  Dumbbell,
  Flame,
  Mic2,
  PawPrint,
  Scissors,
  Store,
  WashingMachine,
  type LucideIcon,
} from 'lucide-react';
import { mockReportData } from '@/lib/mockData/report';
import type {
  ConditionExcludedCandidate,
  FinalCandidate,
} from '@/lib/api/types';
import { conditionExcludedLines } from './conditionExcluded';
import { renderSegments, type FactIndex } from '@/lib/api/segments';

export function industrySymbol(name: string): LucideIcon {
  if (/반려|동물/.test(name)) return PawPrint;
  const rules: [RegExp, LucideIcon][] = [
    [/네일|뷰티|미용|이용/, Scissors],
    [/스튜디오|사진|촬영/, Camera],
    [/세탁/, WashingMachine],
    [/카페|커피|음료/, Coffee],
    [/베이커리|빵|제과/, Croissant],
    [/노래/, Mic2],
    [/헬스|체력/, Dumbbell],
    [/고깃|고기|음식점/, Flame],
  ];
  return rules.find(([pattern]) => pattern.test(name))?.[1] ?? Store;
}

type ReviewItem = {
  name: string;
  // 실제 결과는 이유가 긴 문장이라 오른쪽 좁은 칸 대신 아래 줄 전체에 놓는다.
  wide?: boolean;
  // 100점 환산 점수. 하한·상한이 다르면 구간으로 표시한다.
  score: number;
  scoreHigh?: number;
  badge?: string;
  reasons: string[];
  risks: string[];
};

/** 100점 환산 점수 구간. 적용 배점(A)이 0이면 점수를 매길 수 없다. */
export function candidateScore(candidate: FinalCandidate): {
  low: number;
  high: number;
} | null {
  if (candidate.lower_ratio === null || candidate.upper_ratio === null) {
    return null;
  }
  return {
    low: Math.round(candidate.lower_ratio * 100),
    high: Math.round(candidate.upper_ratio * 100),
  };
}

/** 입점 전 확인할 문장 — 위험 요인, 확인 조건 문장, 서버가 붙인 확인 조건 순서. */
export function candidateChecks(
  candidate: FinalCandidate,
  facts: FactIndex
): string[] {
  const sentences = [
    renderSegments(candidate.risks_segments, facts),
    renderSegments(candidate.confirmation_conditions_segments, facts),
    ...candidate.confirmation_conditions,
  ].map((text) => text.trim());
  return [...new Set(sentences.filter(Boolean))];
}

function toItem(candidate: FinalCandidate, facts: FactIndex): ReviewItem {
  const score = candidateScore(candidate);
  const reason = renderSegments(candidate.reasons_segments, facts).trim();
  return {
    name: candidate.industry_name,
    wide: true,
    score: score?.low ?? 0,
    scoreHigh: score && score.high !== score.low ? score.high : undefined,
    badge: candidate.badge,
    reasons: reason ? [reason] : [],
    risks: candidateChecks(candidate, facts),
  };
}

export default function IndustryReview({
  top5,
  excluded,
  conditionExcluded,
  facts,
}: {
  top5?: FinalCandidate[];
  excluded?: FinalCandidate[];
  conditionExcluded?: ConditionExcludedCandidate[];
  facts?: FactIndex;
}) {
  const index = facts ?? new Map();
  const conditionLines = conditionExcludedLines(conditionExcluded);
  const groups: {
    title: string;
    description: string;
    positive: boolean;
    items: ReviewItem[];
  }[] = [
    {
      title: '검토 후보 업종',
      description: '점수가 높은 순서입니다. 배지와 확인 조건을 함께 보세요',
      positive: true,
      items:
        top5?.map((item) => toItem(item, index)) ??
        mockReportData.recommended.map((item) => ({
          name: item.name,
          score: item.score,
          reasons: item.tags,
          risks: [] as string[],
        })),
    },
    {
      title: '제외한 업종',
      description: '위험 요인과 입점 조건을 먼저 확인하세요',
      positive: false,
      items:
        excluded?.map((item) => toItem(item, index)) ??
        mockReportData.notRecommended.map((item) => ({
          name: item.name,
          score: item.score,
          reasons: item.tags,
          risks: [] as string[],
        })),
    },
  ];
  return (
    <div className="industry-review">
      <div className="industry-columns">
        {groups.map((group) => (
          <div
            key={group.title}
            className={`industry-group ${group.positive ? 'positive' : 'negative'}`}
          >
            <header className="industry-group-header">
              <div className="industry-group-title">
                <h3>{group.title}</h3>
                <span>{group.items.length}개 업종</span>
              </div>
              <p>{group.description}</p>
            </header>
            {group.items.length === 0 && (
              <p className="p-6">해당하는 업종이 없습니다.</p>
            )}
            {group.items.map((item, index) => {
              const Icon = industrySymbol(item.name);
              const key = `${group.positive}-${index}`;
              return (
                <article
                  key={key}
                  className={`industry-item ${item.wide ? 'industry-item-wide' : ''}`}
                >
                  <div className="industry-row-summary">
                    <div className="industry-heading">
                      <span className="industry-rank">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <span className="industry-icon">
                        <Icon size={25} strokeWidth={1.8} aria-hidden="true" />
                      </span>
                      <div className="industry-name">
                        <h4>{item.name}</h4>
                        {item.badge && (
                          <span className="industry-badge">{item.badge}</span>
                        )}
                      </div>
                      <div className="industry-score">
                        {item.score}
                        <small>점</small>
                        <span>적합도</span>
                      </div>
                    </div>
                    <div
                      className="industry-score-track"
                      role="meter"
                      aria-label={`${item.name} 업종 적합도`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={item.score}
                    >
                      <div
                        style={{
                          width: `${Math.max(0, Math.min(100, item.score))}%`,
                        }}
                      />
                      {item.scoreHigh !== undefined && (
                        // 확인 못 한 항목이 모두 좋게 나오면 오를 수 있는 구간
                        <div
                          className="industry-score-potential"
                          style={{
                            width: `${Math.max(0, Math.min(100, item.scoreHigh - item.score))}%`,
                          }}
                        />
                      )}
                    </div>
                  </div>
                  <ul className="industry-reasons industry-reason-labels">
                    {item.reasons.map((reason, i) => (
                      <li key={i}>
                        {/감소|하락/.test(reason)
                          ? `${reason} ↓`
                          : /증가|상승/.test(reason)
                            ? `${reason} ↑`
                            : reason}
                      </li>
                    ))}
                  </ul>
                  {item.risks.length > 0 && (
                    <div className="industry-risks">
                      <strong>입점 전 확인</strong>
                      <ul>
                        {item.risks.map((risk, i) => (
                          <li key={i}>{risk}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        ))}
      </div>
      {conditionLines && (
        <div className="industry-risks">
          <strong>조건 때문에 뺀 업종</strong>
          <ul>
            {conditionLines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
