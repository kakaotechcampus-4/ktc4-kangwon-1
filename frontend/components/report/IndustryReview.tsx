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
import type { IndustryAssessment } from '@/lib/api/types';

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

export default function IndustryReview({
  recommendations,
  notRecommended,
}: {
  recommendations?: IndustryAssessment[];
  notRecommended?: IndustryAssessment[];
}) {
  const groups = [
    {
      title: '추천 업종',
      description: '적합도와 추천 근거를 함께 확인하세요',
      positive: true,
      items:
        recommendations?.map((item) => ({
          name: item.category.middle,
          score: item.score,
          reasons: item.reasons,
          risks: item.risks,
        })) ??
        mockReportData.recommended.map((item) => ({
          name: item.name,
          score: item.score,
          reasons: item.tags,
          risks: [] as string[],
        })),
    },
    {
      title: '비추천 업종',
      description: '위험 요인과 입점 조건을 먼저 확인하세요',
      positive: false,
      items:
        notRecommended?.map((item) => ({
          name: item.category.middle,
          score: item.score,
          reasons: item.reasons,
          risks: item.risks,
        })) ??
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
                <article key={key} className="industry-item">
                  <div className="industry-row-summary">
                    <div className="industry-heading">
                      <span className="industry-rank">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <span className="industry-icon">
                        <Icon size={25} strokeWidth={1.8} aria-hidden="true" />
                      </span>
                      <h4>{item.name}</h4>
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
    </div>
  );
}
