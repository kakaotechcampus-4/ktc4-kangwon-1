'use client';

import type { ReactNode } from 'react';
import { Footprints, CalendarDays, Activity, Users } from 'lucide-react';
import { colors } from '@/styles/tokens';
import { reportPalette } from '@/styles/reportPalette';
import type {
  FactCompetition,
  FactCompetitionRow,
  DensityKind,
  FactFloatingPopulation,
  FactLifecycle,
  FactShare,
} from '@/lib/api/adapters/facts';

/**
 * 실제 분석 결과와 예시 리포트가 함께 쓰는 fact 기반 리포트 차트
 * (유동인구·경쟁·개폐업). 값이 없는 칸은 0이 아니라 "자료 없음"으로 표시한다.
 */

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
    largestAge
      ? {
          key: 'age',
          content: (
            <>
              가장 많이 오가는 연령대는{' '}
              <strong className="story-mobile-emphasis">
                {largestAge.label}
              </strong>
              로, 전체의{' '}
              <strong className="story-mobile-emphasis">
                {percent(largestAge.share)}
              </strong>
              예요.
            </>
          ),
        }
      : null,
    data.weekendIndex !== null
      ? {
          key: 'weekend',
          content: (
            <>
              주말 유동인구가 서울 평균의{' '}
              <strong className="story-mobile-emphasis">
                {times(data.weekendIndex)}
              </strong>
              로,
              {data.weekendIndex >= 1
                ? ' 주말에 더 붐비는 편이에요.'
                : ' 평일 중심 상권이에요.'}
            </>
          ),
        }
      : null,
    data.yoyChange !== null
      ? {
          key: 'yoy',
          content: (
            <>
              전년 같은 분기보다 유동인구가{' '}
              <strong className="story-mobile-emphasis">
                {signed(data.yoyChange * 100)}%
              </strong>{' '}
              {data.yoyChange >= 0 ? '늘었어요.' : '줄었어요.'}
            </>
          ),
        }
      : null,
  ].filter(
    (insight): insight is NonNullable<typeof insight> => insight !== null
  );

  // 리포트용 읽기형 구성 — 결론 → 핵심 숫자 → 근거(질문별 행) → 각주.
  // 스타일은 app/report/report.css의 .story 블록을 목업 경로와 함께 쓴다.
  return (
    <div className="fp-root fp-root-story flex w-full flex-col">
      <div className="story">
        <header className="story-lead">
          <p className="story-peak-label">가장 붐비는 시간</p>
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
              {insights.map((insight) => (
                <li key={insight.key}>{insight.content}</li>
              ))}
            </ul>
          )}
        </header>

        <dl className="story-stats">
          <div>
            <dt>
              <span className="story-stat-icon" aria-hidden="true">
                <Footprints size={18} strokeWidth={2} />
              </span>
              상권 1곳 하루 평균
            </dt>
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
            <dt>
              <span className="story-stat-icon" aria-hidden="true">
                <CalendarDays size={18} strokeWidth={2} />
              </span>
              주말 (서울 평균 대비)
            </dt>
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
            <dt>
              <span className="story-stat-icon" aria-hidden="true">
                <Activity size={18} strokeWidth={2} />
              </span>
              전년 같은 분기 대비
            </dt>
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
            {data.yoyChange !== null && (
              <p className="story-mobile-note">
                전년 같은 분기보다 유동인구가{' '}
                {data.yoyChange >= 0 ? '늘었어요' : '줄었어요'}
              </p>
            )}
          </div>
          {largestAge && (
            <div>
              <dt>
                <span className="story-stat-icon" aria-hidden="true">
                  <Users size={18} strokeWidth={2} />
                </span>
                가장 많은 연령대
              </dt>
              <dd>
                {largestAge.label}
                <small>{percent(largestAge.share)}</small>
              </dd>
              <p className="story-mobile-note">
                주변 상권 방문객 중 가장 큰 비중
              </p>
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

const DENSITY_GUIDANCE: Record<DensityKind, string> = {
  모임형:
    '서울 평균보다 동종 업종 밀도가 높으면 긍정적으로 반영됩니다. 단, 상위 5%를 넘는 과밀은 감점될 수 있습니다.',
  근처형:
    '주변 비교권역보다 유동을 반영한 동종 업종 밀도가 낮을수록 긍정적으로 반영됩니다.',
  무관: '동종 업종 밀집도를 입지 점수에 반영하지 않습니다.',
};

function densityKindClass(kind: DensityKind) {
  if (kind === '모임형') return 'is-gathering';
  if (kind === '근처형') return 'is-nearby';
  return 'is-neutral';
}

// 표 숫자는 진하게, 단위(개·배)만 회색으로 보여준다.
function WithUnit({ value, unit }: { value: string; unit: string }) {
  return (
    <>
      {value}
      <span className="competition-unit">{unit}</span>
    </>
  );
}

function CompetitionTable({
  rows,
  groupTitle,
  description,
}: {
  rows: FactCompetitionRow[];
  groupTitle: string;
  description: string;
}) {
  const isExcludedGroup = groupTitle.startsWith('제외 후보');

  return (
    <section
      className={`competition-candidate-group${isExcludedGroup ? ' is-excluded' : ''}`}
    >
      <header className="competition-candidate-group-head">
        <div>
          <h4>{groupTitle}</h4>
          <p>{description}</p>
        </div>
        <span className="competition-candidate-count">
          {rows.length}개 업종
        </span>
      </header>
      <p className="report-mobile-table-hint">
        표를 좌우로 밀어 더 자세히 볼 수 있어요{' '}
        <span aria-hidden="true">↔</span>
      </p>
      <div className="competition-table-scroll">
        <table className="competition-table">
          <caption className="sr-only">{groupTitle} 경쟁 지표 비교</caption>
          <thead>
            <tr>
              <th scope="col" className="competition-rank-column">
                순위
              </th>
              <th scope="col">업종</th>
              <th scope="col" className="is-numeric">
                점포 수
              </th>
              <th scope="col" className="is-numeric">
                밀도 <small>개/km²</small>
              </th>
              <th scope="col" className="is-numeric">
                서울 대비 <small>1.0배 = 서울 평균</small>
              </th>
              <th scope="col" className="is-numeric">
                주변 대비 <small>1.0배 = 비교권역 평균</small>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.code} className="competition-table-row">
                <td
                  className="competition-rank-column"
                  aria-label={`${index + 1}순위`}
                >
                  {String(index + 1).padStart(2, '0')}
                </td>
                <td>
                  <span className="competition-industry-cell">
                    <span>{row.name}</span>
                    {row.densityKind && (
                      <span
                        className={`competition-industry-kind ${densityKindClass(row.densityKind)}`}
                      >
                        {row.densityKind}
                      </span>
                    )}
                  </span>
                </td>
                <td className="is-numeric">
                  {row.storeCount === null ? (
                    '자료 없음'
                  ) : (
                    <WithUnit
                      value={Math.round(row.storeCount).toLocaleString('ko-KR')}
                      unit="개"
                    />
                  )}
                </td>
                <td className="is-numeric">
                  {row.densityPerKm2 === null
                    ? '자료 없음'
                    : row.densityPerKm2.toFixed(1)}
                </td>
                <td className="is-numeric">
                  {row.competitionIndex !== null ? (
                    <WithUnit
                      value={row.competitionIndex.toFixed(2)}
                      unit="배"
                    />
                  ) : row.densityKind === '무관' ? (
                    '—'
                  ) : (
                    '자료 없음'
                  )}
                </td>
                <td className="is-numeric">
                  {row.lq === null ? (
                    '비교 불가'
                  ) : (
                    <WithUnit value={row.lq.toFixed(2)} unit="배" />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function FactCompetitionSection({
  data,
  recommendedCodes,
}: {
  data: FactCompetition;
  recommendedCodes?: ReadonlySet<string>;
}) {
  const selected = new Set(data.selected.map((row) => row.code));
  const densityKinds = [
    ...new Set(
      data.selected
        .map((row) => row.densityKind)
        .filter((kind): kind is DensityKind => kind !== null)
    ),
  ];
  const recommendedRows = recommendedCodes
    ? data.selected.filter((row) => recommendedCodes.has(row.code))
    : data.selected;
  const excludedRows = recommendedCodes
    ? data.selected.filter((row) => !recommendedCodes.has(row.code))
    : [];
  return (
    <div className="competition-story">
      <div className="competition-overview">
        <div className="competition-total">
          <p>반경 안 전체 점포</p>
          <strong>
            {data.storeTotal.toLocaleString('ko-KR')}
            <small>개</small>
          </strong>
          <span>
            {data.radiusM === null
              ? '분석 반경 자료 없음'
              : `반경 ${data.radiusM}m`}
            {' · '}51개 업종 기준
          </span>
        </div>
        <div className="competition-diversity">
          <p className="competition-kicker">업종 구성</p>
          <strong>
            {data.effectiveCategories === null
              ? '자료 없음'
              : data.effectiveCategories.toFixed(1)}
            {data.effectiveCategories !== null && <small>개 업종 수준</small>}
          </strong>
          <span>점포가 여러 업종에 얼마나 고르게 나뉘는지 나타내요.</span>
        </div>
      </div>

      {data.selected.length > 0 && (
        <section className="competition-editorial-section">
          <header className="competition-section-head">
            <div>
              <p className="competition-kicker">추천 업종을 중심으로</p>
              <h3>검토 후보 업종의 경쟁 상황</h3>
            </div>
          </header>
          {densityKinds.length > 0 && (
            <aside className="competition-reading-guide competition-type-guide">
              <p className="competition-type-guide-title">
                업종 유형별 읽는 법
              </p>
              <ul>
                {densityKinds.map((kind) => (
                  <li key={kind}>
                    <span
                      className={`competition-industry-kind ${densityKindClass(kind)}`}
                    >
                      {kind}
                    </span>
                    <span>{DENSITY_GUIDANCE[kind]}</span>
                  </li>
                ))}
              </ul>
            </aside>
          )}
          {recommendedCodes ? (
            <>
              {recommendedRows.length > 0 ? (
                <CompetitionTable
                  rows={recommendedRows}
                  groupTitle="상위 추천 업종"
                  description="먼저 검토할 업종의 경쟁 지표입니다."
                />
              ) : (
                <div className="competition-candidate-group">
                  <header className="competition-candidate-group-head">
                    <h4>상위 추천 업종</h4>
                  </header>
                  <p className="competition-candidate-empty">
                    표시할 상위 추천 업종이 없습니다.
                  </p>
                </div>
              )}
              {excludedRows.length > 0 && (
                <CompetitionTable
                  rows={excludedRows}
                  groupTitle="제외 후보 업종"
                  description="추천 기준에 포함되지 않은 업종도 참고할 수 있도록 따로 모았습니다."
                />
              )}
            </>
          ) : (
            <CompetitionTable
              rows={data.selected}
              groupTitle="검토 후보 업종"
              description="분석 대상 업종의 경쟁 지표입니다."
            />
          )}
        </section>
      )}

      <div className="competition-chart-grid">
        <section className="competition-editorial-section">
          <header className="competition-section-head competition-section-head-stacked">
            <div>
              <p className="competition-kicker">어떤 업종이 많을까요?</p>
              <h3>점포가 많은 업종 10개</h3>
            </div>
            <p>파란 막대는 검토 후보 업종입니다.</p>
          </header>
          <div className="competition-chart-bars">
            <Bars
              rows={data.topByCount.map((row) => ({
                key: row.code,
                label: row.name,
                value: row.storeCount,
              }))}
              format={count}
              highlight={(code) => selected.has(code)}
            />
          </div>
        </section>
        <section className="competition-editorial-section">
          <header className="competition-section-head competition-section-head-stacked">
            <div>
              <p className="competition-kicker">큰 업종 묶음으로</p>
              <h3>대분류별 점포 수</h3>
            </div>
            <p>주변 상권의 업종 구성을 넓게 살펴봅니다.</p>
          </header>
          <div className="competition-chart-bars">
            <Bars
              rows={data.byMajor.map((row) => ({
                label: row.major,
                value: row.count,
              }))}
              format={count}
            />
          </div>
        </section>
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

type LifecycleChartRow = {
  key: string;
  label: string;
  value: number | null;
};

// 0(가장 작은 값)이면 연한 파랑, 1(가장 큰 값)이면 남색 — 그 사이는 섞어서 칠한다.
function shadeColor(strength: number) {
  const light = [168, 190, 242]; // #A8BEF2
  const dark = [16, 35, 58]; // #10233A
  const mix = light.map((c, i) => Math.round(c + (dark[i] - c) * strength));
  return `rgb(${mix.join(', ')})`;
}

function LifecycleMetricChart({
  rows,
  format,
  diverging = false,
  shadeByValue = false,
  lollipop = false,
  renderValue,
}: {
  rows: LifecycleChartRow[];
  format: (value: number) => string;
  /** 0을 가운데 두고 양쪽으로 뻗는 막대. 늘면 빨강, 줄면 파랑. */
  diverging?: boolean;
  /** 값이 클수록 막대를 진하게 칠한다(가장 큰 값 = 남색 그대로). */
  shadeByValue?: boolean;
  /** 막대 대신 가는 선 + 끝 점(롤리팝)으로 그린다. */
  lollipop?: boolean;
  /** 주면 줄 끝에 수치를 보여준다. 없으면 수치는 화면 낭독기용으로만 둔다. */
  renderValue?: (value: number) => ReactNode;
}) {
  const max = Math.max(0, ...rows.map((row) => Math.abs(row.value ?? 0)));
  const showValues = renderValue !== undefined;

  return (
    <div className={`lifecycle-chart-wrap${showValues ? ' has-values' : ''}`}>
      <ul
        className={`lifecycle-chart${diverging ? ' is-diverging' : ''}${
          lollipop ? ' is-lollipop' : ''
        }`}
      >
        {rows.map((row) => {
          const value = row.value;
          const width =
            value === null || max === 0
              ? 0
              : (Math.abs(value) / max) * (diverging ? 50 : 100);
          const offset = diverging
            ? value !== null && value < 0
              ? 50 - width
              : 50
            : 0;

          return (
            <li key={row.key}>
              <span className="lifecycle-chart-label" title={row.label}>
                {row.label}
              </span>
              <span
                className="lifecycle-chart-track"
                title={value === null ? '자료 없음' : format(value)}
                aria-hidden="true"
              >
                {diverging && <span className="lifecycle-chart-zero" />}
                {value !== null && max > 0 && (
                  <span
                    className="lifecycle-chart-bar"
                    style={{
                      left: `${offset}%`,
                      width: `${width}%`,
                      backgroundColor: shadeByValue
                        ? shadeColor(Math.abs(value) / max)
                        : diverging
                          ? value >= 0
                            ? '#d6383b'
                            : '#2453d6'
                          : reportPalette.navy,
                    }}
                  />
                )}
                {lollipop && value !== null && max > 0 && (
                  <span
                    className="lifecycle-chart-dot"
                    style={{ left: `${width}%` }}
                  />
                )}
              </span>
              <span
                className={`lifecycle-chart-value${showValues ? '' : ' sr-only'}`}
              >
                {value === null
                  ? '자료 없음'
                  : renderValue
                    ? renderValue(value)
                    : format(value)}
              </span>
            </li>
          );
        })}
      </ul>
      {diverging && (
        // 막대 줄과 같은 칸 나눔을 써서 '0'이 기준선 바로 아래에 오게 한다.
        <div className="lifecycle-chart-legend-row" aria-hidden="true">
          <span />
          <div className="lifecycle-chart-legend">
            <span>감소</span>
            <span>0</span>
            <span>증가</span>
          </div>
          {showValues && <span />}
        </div>
      )}
    </div>
  );
}

// 순증감률: 늘면 빨간 ▲, 줄면 파란 ▼, 0이면 회색 –
function NetChange({ value }: { value: number }) {
  const rounded = Number(value.toFixed(1));
  const kind = rounded > 0 ? 'is-up' : rounded < 0 ? 'is-down' : 'is-flat';
  const mark = rounded > 0 ? '▲' : rounded < 0 ? '▼' : '–';
  return (
    <span className={`lifecycle-net ${kind}`}>
      <span aria-hidden="true">{mark}</span>
      <span className="sr-only">
        {rounded > 0 ? '증가' : rounded < 0 ? '감소' : '변화 없음'}
      </span>
      {Math.abs(rounded).toFixed(1)}%
    </span>
  );
}

// 폐업률과 서울 평균을 한 줄에 — 막대(이 지역) + 세로선(서울 같은 업종 평균).
// 서울보다 높으면 빨강, 낮으면 파랑. 서울 대비가 높은 업종부터 보여준다.
function CloseRateComparison({ rows }: { rows: FactLifecycle['rows'] }) {
  const items = rows
    .filter(
      (row) =>
        row.recentCloseRate !== null &&
        row.closeRateRatio !== null &&
        row.closeRateRatio > 0
    )
    .map((row) => {
      const local = row.recentCloseRate as number;
      const ratio = row.closeRateRatio as number;
      return {
        code: row.code,
        name: row.name,
        local,
        ratio,
        seoul: local / ratio,
      };
    })
    .sort((a, b) => b.ratio - a.ratio);
  const max =
    Math.max(0, ...items.flatMap((item) => [item.local, item.seoul])) * 1.08;
  const missing = rows.length - items.length;

  return (
    <div className="close-compare">
      <div className="close-compare-legend" aria-hidden="true">
        <span>
          <i className="close-compare-swatch" /> 이 지역 폐업률
        </span>
        <span>
          <i className="close-compare-swatch is-seoul" /> 서울 같은 업종 평균
        </span>
      </div>
      <ul>
        {items.map((item) => {
          const tone =
            item.ratio >= 1.005
              ? 'is-high'
              : item.ratio <= 0.995
                ? 'is-low'
                : 'is-even';
          const verdict =
            tone === 'is-high'
              ? '서울보다 높음'
              : tone === 'is-low'
                ? '서울보다 낮음'
                : '서울과 비슷';
          return (
            <li key={item.code} className={tone}>
              <span className="close-compare-name" title={item.name}>
                {item.name}
              </span>
              <span className="close-compare-track" aria-hidden="true">
                <span
                  className="close-compare-bar"
                  style={{
                    width: `${max > 0 ? (item.local / max) * 100 : 0}%`,
                  }}
                />
                <span
                  className="close-compare-seoul"
                  style={{ left: `${max > 0 ? (item.seoul / max) * 100 : 0}%` }}
                />
              </span>
              <span className="close-compare-value">
                <strong>{rate(item.local)}</strong>
                <small>서울 {rate(item.seoul)}</small>
              </span>
              <span className="close-compare-verdict">
                {verdict} <b>{times(item.ratio)}</b>
              </span>
            </li>
          );
        })}
      </ul>
      {missing > 0 && (
        <p className="close-compare-missing">
          자료가 없어 비교하지 못한 업종 {missing}개는 위 표에서 확인할 수
          있어요.
        </p>
      )}
    </div>
  );
}

export function FactLifecycleSection({ data }: { data: FactLifecycle }) {
  const chartRows = (
    pick: (row: FactLifecycle['rows'][number]) => number | null
  ): LifecycleChartRow[] =>
    data.rows
      .map((row) => ({
        key: row.code,
        label: row.name,
        value: pick(row),
      }))
      .sort((a, b) => {
        if (a.value === null) return b.value === null ? 0 : 1;
        if (b.value === null) return -1;
        return b.value - a.value;
      });
  return (
    <div className="story lifecycle-story">
      <section className="story-row lifecycle-detail-row">
        <div className="story-row-text">
          <p className="story-question">업종별로 비교해요</p>
          <h4>개폐업 지표</h4>
          <p>
            서울 대비 폐업률은 같은 업종의 서울 평균과 비교한 배수예요. 회전율은
            개업과 폐업이 함께 잦은 정도를 보여줍니다.
          </p>
        </div>
        <div className="story-row-figure">
          <p className="report-mobile-table-hint">
            표를 좌우로 밀어 더 자세히 볼 수 있어요{' '}
            <span aria-hidden="true">↔</span>
          </p>
          <div className="lifecycle-table-scroll overflow-x-auto">
            <table className="lifecycle-table w-full min-w-[38rem] text-left text-sm">
              <thead>
                <tr>
                  <th scope="col" className="lifecycle-rank-column">
                    순위
                  </th>
                  <th scope="col" className="lifecycle-industry-column">
                    업종
                  </th>
                  <th>평균 점포 수</th>
                  <th>최근 1년 폐업률</th>
                  <th>서울 대비</th>
                  <th>회전율</th>
                  <th>순증감률</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row, index) => (
                  <tr key={row.code}>
                    <td
                      className="lifecycle-rank-column"
                      aria-label={`${index + 1}순위`}
                    >
                      {String(index + 1).padStart(2, '0')}
                    </td>
                    <td className="lifecycle-industry-column">{row.name}</td>
                    <td>
                      {row.avgStoreCount === null
                        ? '자료 없음'
                        : row.avgStoreCount.toFixed(1)}
                    </td>
                    <td>
                      {row.recentCloseRate === null
                        ? '자료 없음'
                        : rate(row.recentCloseRate)}
                    </td>
                    <td>
                      {row.closeRateRatio === null
                        ? '비교 불가'
                        : times(row.closeRateRatio)}
                    </td>
                    <td>
                      {row.turnoverRate === null
                        ? '자료 없음'
                        : rate(row.turnoverRate)}
                    </td>
                    <td>
                      {row.netChangeRate === null ? (
                        '자료 없음'
                      ) : (
                        <NetChange value={row.netChangeRate} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <div className="lifecycle-metric-comparisons">
        <header className="lifecycle-comparison-head">
          <h4>지표별로 차이를 비교해요</h4>
          <p>
            막대는 업종 간 상대 크기를 보여주고, 정확한 수치는 위 표에서 확인할
            수 있어요.
          </p>
        </header>
        <p className="lifecycle-chart-note">
          그래프는 지표별로 큰 값부터 정렬했습니다. 정확한 수치는 위 표에서
          확인할 수 있어요.
        </p>
        <section className="story-row lifecycle-metric-row">
          <div className="story-row-text">
            <p className="story-question">점포 규모</p>
            <h4>평균 점포 수</h4>
            <p>
              분석 기간 동안 업종별로 관측된 평균 점포 수예요. 주변 업종의
              규모를 함께 비교해 보세요.
            </p>
          </div>
          <div className="story-row-figure">
            <LifecycleMetricChart
              rows={chartRows((row) => row.avgStoreCount)}
              format={(value) => value.toFixed(1)}
              shadeByValue
            />
          </div>
        </section>

        <section className="story-row lifecycle-metric-row">
          <div className="story-row-text">
            <p className="story-question">최근 1년</p>
            <h4>폐업률과 서울 평균 비교</h4>
            <p>
              막대는 이 지역의 최근 1년 폐업률, 세로선은 같은 업종의 서울
              평균이에요. 막대가 선을 넘으면 서울보다 문을 닫는 가게가 많은
              편이에요.
            </p>
          </div>
          <div className="story-row-figure">
            <CloseRateComparison rows={data.rows} />
          </div>
        </section>

        <section className="story-row lifecycle-metric-row">
          <div className="story-row-text">
            <p className="story-question">사업자 교체</p>
            <h4>회전율</h4>
            <p>
              개업과 폐업이 함께 발생하는 정도예요. 값이 높을수록 점포 교체가
              잦았다는 뜻입니다.
            </p>
          </div>
          <div className="story-row-figure">
            <LifecycleMetricChart
              rows={chartRows((row) => row.turnoverRate)}
              format={rate}
              lollipop
              renderValue={rate}
            />
          </div>
        </section>

        <section className="story-row lifecycle-metric-row">
          <div className="story-row-text">
            <p className="story-question">점포 수 변화</p>
            <h4>순증감률</h4>
            <p>
              관측 기간의 개업과 폐업을 반영한 점포 수 변화예요. 가운데 0을
              기준으로 왼쪽(파랑)은 감소, 오른쪽(빨강)은 증가입니다.
            </p>
          </div>
          <div className="story-row-figure">
            <LifecycleMetricChart
              rows={chartRows((row) => row.netChangeRate)}
              format={(value) => `${signed(value)}%`}
              diverging
              renderValue={(value) => <NetChange value={value} />}
            />
          </div>
        </section>
      </div>

      <SourceNote>자료: 서울시 상권분석서비스 점포 · {data.period}</SourceNote>
    </div>
  );
}
