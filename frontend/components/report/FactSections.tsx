'use client';

import type { ReactNode } from 'react';
import { colors } from '@/styles/tokens';
import { reportPalette } from '@/styles/reportPalette';
import type {
  FactCompetition,
  FactCompetitionRow,
  FactFloatingPopulation,
  FactLifecycle,
  FactShare,
} from '@/lib/api/adapters/facts';

/**
 * 실제 분석 결과의 fact로 그리는 리포트 차트(유동인구·경쟁·개폐업).
 * 목업 미리보기는 기존 FloatingPopulationSection 등이 그대로 그린다 —
 * 그쪽은 예전 에이전트 출력 구조를 기준으로 만들어져 새 fact와 모양이 다르다.
 * 값이 없는 칸은 0이 아니라 "자료 없음"으로 표시한다.
 */

function Card({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section
      className="w-full rounded-xl border bg-white"
      style={{ borderColor: reportPalette.line }}
    >
      <header
        className="border-b px-6 py-4"
        style={{ borderColor: reportPalette.line }}
      >
        <h3 className="text-lg font-bold" style={{ color: reportPalette.ink }}>
          {title}
        </h3>
        {description && (
          <p
            className="mt-1 text-sm leading-6"
            style={{ color: colors.text.secondary }}
          >
            {description}
          </p>
        )}
      </header>
      <div className="px-6 py-5">{children}</div>
    </section>
  );
}

function Stat({
  label,
  value,
  unit,
  note,
}: {
  label: string;
  value: string | null;
  unit?: string;
  note?: string;
}) {
  return (
    <div
      className="flex flex-col gap-1 rounded-xl px-5 py-4"
      style={{ backgroundColor: reportPalette.canvas }}
    >
      <span className="text-sm" style={{ color: colors.text.secondary }}>
        {label}
      </span>
      <strong className="text-2xl" style={{ color: reportPalette.navy }}>
        {value ?? '자료 없음'}
        {value !== null && unit && (
          <span className="ml-1 text-base font-medium">{unit}</span>
        )}
      </strong>
      {note && (
        <span className="text-sm" style={{ color: colors.text.tertiary }}>
          {note}
        </span>
      )}
    </div>
  );
}

/** 가로 막대 목록. 막대 길이는 목록 최댓값 대비 비율이다. */
function Bars({
  rows,
  format,
  highlight,
}: {
  rows: { label: string; value: number | null; key?: string }[];
  format: (value: number) => string;
  highlight?: (key: string) => boolean;
}) {
  const max = Math.max(0, ...rows.map((row) => row.value ?? 0));
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((row) => {
        const key = row.key ?? row.label;
        const strong = highlight?.(key) ?? false;
        return (
          <li
            key={key}
            className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)_5.5rem] items-center gap-3"
          >
            <span className="truncate text-sm" title={row.label}>
              {row.label}
            </span>
            <span
              className="h-3 overflow-hidden rounded-full"
              style={{ backgroundColor: reportPalette.blueWash }}
              aria-hidden="true"
            >
              {row.value !== null && max > 0 && (
                <span
                  className="block h-full rounded-full"
                  style={{
                    width: `${(row.value / max) * 100}%`,
                    backgroundColor: strong
                      ? reportPalette.brand
                      : reportPalette.navy,
                  }}
                />
              )}
            </span>
            <span className="text-right text-sm font-semibold tabular-nums">
              {row.value === null ? '자료 없음' : format(row.value)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

const percent = (share: number) => `${(share * 100).toFixed(1)}%`;
const times = (value: number) => `${value.toFixed(2)}배`;
const count = (value: number) =>
  `${Math.round(value).toLocaleString('ko-KR')}개`;
const rate = (value: number) => `${value.toFixed(1)}%`;

function signed(value: number, digits = 1) {
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}`;
}

function peak(shares: FactShare[]): FactShare | undefined {
  return shares.reduce<FactShare | undefined>(
    (best, item) => (!best || item.share > best.share ? item : best),
    undefined
  );
}

function SourceNote({ children }: { children: ReactNode }) {
  return (
    <p className="text-sm" style={{ color: colors.text.tertiary }}>
      {children}
    </p>
  );
}

// ---------------------------------------------------------------------------
// 유동인구
// ---------------------------------------------------------------------------

export function FactFloatingPopulationSection({
  data,
}: {
  data: FactFloatingPopulation;
}) {
  const busiest = peak(data.timeBands);
  const largestAge = peak(data.ageShares);
  const insights = [
    largestAge &&
      `가장 많이 오가는 연령대는 ${largestAge.label}로, 전체의 ${percent(largestAge.share)}예요.`,
    data.weekendIndex !== null &&
      (data.weekendIndex >= 1
        ? `주말 유동인구가 서울 평균의 ${times(data.weekendIndex)}로, 주말에 더 붐비는 편이에요.`
        : `주말 유동인구가 서울 평균의 ${times(data.weekendIndex)}로, 평일 중심 상권이에요.`),
    data.yoyChange !== null &&
      `전년 같은 분기보다 유동인구가 ${signed(data.yoyChange * 100)}% ${data.yoyChange >= 0 ? '늘었어요' : '줄었어요'}.`,
  ].filter((line): line is string => Boolean(line));

  // 리포트용 읽기형 구성 — 결론 → 핵심 숫자 → 근거(질문별 행) → 각주.
  // 스타일은 app/report/report.css의 .story 블록을 목업 경로와 함께 쓴다.
  return (
    <div className="fp-root fp-root-story flex w-full flex-col">
      <div className="story">
        <header className="story-lead">
          <h3>
            {busiest ? (
              <>
                이 주변은 <em>{busiest.label}</em>에 가장 붐벼요
              </>
            ) : (
              '주변 유동인구를 요약했어요'
            )}
          </h3>
          {insights.length > 0 && (
            <ul className="story-insights">
              {insights.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
        </header>

        <dl className="story-stats">
          <div>
            <dt>상권 1곳 하루 평균</dt>
            <dd>
              {data.dailyPerTradeArea === null ? (
                '자료 없음'
              ) : (
                <>
                  {Math.round(data.dailyPerTradeArea).toLocaleString('ko-KR')}
                  <small>명</small>
                </>
              )}
            </dd>
            {data.tradeAreaCount !== null && (
              <p>주변 상권 {data.tradeAreaCount}곳 평균</p>
            )}
          </div>
          <div>
            <dt>주말 (서울 평균 대비)</dt>
            <dd>
              {data.weekendIndex === null ? (
                '자료 없음'
              ) : (
                <>
                  {data.weekendIndex.toFixed(2)}
                  <small>배</small>
                </>
              )}
            </dd>
            <p>1.0배보다 높으면 주말에 더 붐벼요</p>
          </div>
          <div>
            <dt>전년 같은 분기 대비</dt>
            <dd>
              {data.yoyChange === null ? (
                '자료 없음'
              ) : (
                <>
                  {signed(data.yoyChange * 100)}
                  <small>%</small>
                </>
              )}
            </dd>
          </div>
          {largestAge && (
            <div>
              <dt>가장 많은 연령대</dt>
              <dd>
                {largestAge.label}
                <small>{percent(largestAge.share)}</small>
              </dd>
            </div>
          )}
        </dl>

        <section className="story-row">
          <div className="story-row-text">
            <p className="story-question">언제 붐비나요?</p>
            <h4>시간대별 유동인구</h4>
            <p>
              시간대마다 구간 길이가 달라 한 시간당 비중으로 맞춰 비교해요. 파란
              막대가 가장 붐비는 시간대예요.
            </p>
          </div>
          <div className="story-row-figure">
            {data.timeBands.length === 0 ? (
              <p>시간대 자료가 없습니다.</p>
            ) : (
              <Bars
                rows={data.timeBands.map((band) => ({
                  label: band.label,
                  value: band.share,
                }))}
                format={percent}
                highlight={(key) => key === busiest?.label}
              />
            )}
          </div>
        </section>

        <section className="story-row">
          <div className="story-row-text">
            <p className="story-question">누가 오가나요?</p>
            <h4>연령대별 구성</h4>
            <p>주변 상권을 오가는 사람의 연령대 비율이에요.</p>
          </div>
          <div className="story-row-figure">
            {data.ageShares.length === 0 ? (
              <p>연령대 자료가 없습니다.</p>
            ) : (
              <Bars
                rows={data.ageShares.map((age) => ({
                  label: age.label,
                  value: age.share,
                }))}
                format={percent}
                highlight={(key) => key === largestAge?.label}
              />
            )}
          </div>
        </section>
      </div>

      <p className="fp-source">
        자료: 서울시 상권분석서비스 길단위인구 · {data.period}
        {data.radiusM !== null && ` · 반경 ${data.radiusM}m`}
        <br />
        상가 앞 통행량이나 중복을 뺀 방문자 수가 아니라 주변 상권의 추정
        통행량입니다.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 경쟁 점포
// ---------------------------------------------------------------------------

function CompetitionTable({ rows }: { rows: FactCompetitionRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[34rem] text-left text-sm">
        <thead style={{ color: colors.text.secondary }}>
          <tr>
            <th className="py-2 pr-3 font-medium">업종</th>
            <th className="py-2 pr-3 text-right font-medium">점포 수</th>
            <th className="py-2 pr-3 text-right font-medium">밀도(개/km²)</th>
            <th className="py-2 pr-3 text-right font-medium">경쟁 부담</th>
            <th className="py-2 text-right font-medium">주변 대비 집중도</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.code}
              className="border-t"
              style={{ borderColor: reportPalette.line }}
            >
              <td className="py-3 pr-3 font-semibold">{row.name}</td>
              <td className="py-3 pr-3 text-right tabular-nums">
                {row.storeCount === null ? '자료 없음' : count(row.storeCount)}
              </td>
              <td className="py-3 pr-3 text-right tabular-nums">
                {row.densityPerKm2 === null
                  ? '자료 없음'
                  : row.densityPerKm2.toFixed(1)}
              </td>
              <td className="py-3 pr-3 text-right tabular-nums">
                {row.competitionIndex === null
                  ? '자료 없음'
                  : times(row.competitionIndex)}
              </td>
              <td className="py-3 text-right tabular-nums">
                {row.lq === null ? '비교 불가' : times(row.lq)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function FactCompetitionSection({ data }: { data: FactCompetition }) {
  const selected = new Set(data.selected.map((row) => row.code));
  return (
    <div className="flex w-full flex-col gap-5">
      {data.selected.length > 0 && (
        <Card
          title="검토 후보 업종의 경쟁 상황"
          description="경쟁 부담은 유동인구 규모를 감안해 서울 같은 업종 밀도와 비교한 값으로, 1.0배보다 높을수록 경쟁이 셉니다. 주변 대비 집중도는 넓은 주변 지역보다 이 반경에 그 업종이 얼마나 몰려 있는지입니다."
        >
          <CompetitionTable rows={data.selected} />
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Stat
          label={`반경 안 점포 수 (51개 업종)`}
          value={data.storeTotal.toLocaleString('ko-KR')}
          unit="개"
        />
        <Stat
          label="업종 다양성"
          value={
            data.effectiveCategories === null
              ? null
              : data.effectiveCategories.toFixed(1)
          }
          unit="개 업종 수준"
          note="점포가 이만큼의 업종에 고르게 나뉜 것과 같습니다"
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="점포가 많은 업종 10개">
          <Bars
            rows={data.topByCount.map((row) => ({
              key: row.code,
              label: row.name,
              value: row.storeCount,
            }))}
            format={count}
            highlight={(code) => selected.has(code)}
          />
        </Card>
        <Card title="대분류별 점포 수">
          <Bars
            rows={data.byMajor.map((row) => ({
              label: row.major,
              value: row.count,
            }))}
            format={count}
          />
        </Card>
      </div>

      <SourceNote>
        자료: 소상공인시장진흥공단 상가(상권)정보 · {data.period}
        {data.radiusM !== null && ` · 반경 ${data.radiusM}m`}
        {data.comparisonRadiusM !== null &&
          ` · 집중도 비교 반경 ${data.comparisonRadiusM.toLocaleString('ko-KR')}m`}
      </SourceNote>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 개폐업
// ---------------------------------------------------------------------------

export function FactLifecycleSection({ data }: { data: FactLifecycle }) {
  return (
    <div className="flex w-full flex-col gap-5">
      <Card
        title="최근 1년 폐업률"
        description="최근 1년 동안 문을 닫은 점포의 비율입니다. 점포 수가 적으면 몇 건의 변화에도 비율이 크게 달라집니다."
      >
        <Bars
          rows={data.rows.map((row) => ({
            key: row.code,
            label: row.name,
            value: row.recentCloseRate,
          }))}
          format={rate}
        />
      </Card>

      <Card
        title="업종별 개폐업 흐름"
        description="서울 대비 폐업률이 1.0배보다 높으면 서울 같은 업종보다 더 많이 문을 닫았습니다. 회전율은 개업과 폐업이 함께 잦은 정도입니다."
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <thead style={{ color: colors.text.secondary }}>
              <tr>
                <th className="py-2 pr-3 font-medium">업종</th>
                <th className="py-2 pr-3 text-right font-medium">
                  평균 점포 수
                </th>
                <th className="py-2 pr-3 text-right font-medium">
                  서울 대비 폐업률
                </th>
                <th className="py-2 pr-3 text-right font-medium">회전율</th>
                <th className="py-2 text-right font-medium">순증감률</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr
                  key={row.code}
                  className="border-t"
                  style={{ borderColor: reportPalette.line }}
                >
                  <td className="py-3 pr-3 font-semibold">{row.name}</td>
                  <td className="py-3 pr-3 text-right tabular-nums">
                    {row.avgStoreCount === null
                      ? '자료 없음'
                      : row.avgStoreCount.toFixed(1)}
                  </td>
                  <td className="py-3 pr-3 text-right tabular-nums">
                    {row.closeRateRatio === null
                      ? '비교 불가'
                      : times(row.closeRateRatio)}
                  </td>
                  <td className="py-3 pr-3 text-right tabular-nums">
                    {row.turnoverRate === null
                      ? '자료 없음'
                      : rate(row.turnoverRate)}
                  </td>
                  <td
                    className="py-3 text-right tabular-nums"
                    style={{
                      color:
                        row.netChangeRate !== null && row.netChangeRate < 0
                          ? reportPalette.caution
                          : undefined,
                    }}
                  >
                    {row.netChangeRate === null
                      ? '자료 없음'
                      : `${signed(row.netChangeRate)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <SourceNote>자료: 서울시 상권분석서비스 점포 · {data.period}</SourceNote>
    </div>
  );
}
