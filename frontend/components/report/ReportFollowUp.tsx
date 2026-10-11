import type { BuildingInfo } from '@/lib/api/building';
import type { DecisionResult } from '@/lib/api/types';

export type AnswerRecord = { label: string; answer: string; detail?: string };

export function ReportConditions({
  building,
  answers,
  note,
  isExample,
}: {
  building: BuildingInfo | null;
  answers: AnswerRecord[];
  note: string;
  isExample: boolean;
}) {
  const sourceLabel = {
    registry: '조회 예시',
    user: '사용자 확인',
    missing: '미확인',
  };
  const fields = building
    ? ([
        ['전용면적', building.exclusiveAreaM2.source],
        ['주차', building.parking.source],
        ['시설 용도', building.facility.source],
        ['오수정화시설', building.sewage.source],
      ] as const)
    : [];
  return (
    <aside
      className="mx-8 mt-4 border-l-2 border-gray-300 pl-5 text-base leading-7 text-gray-600"
      aria-label="상가 확인 정보와 분석 범위"
    >
      <h2 className="font-semibold text-gray-900">확인한 상가 조건</h2>
      {isExample && (
        <p>
          미리보기입니다. 표시된 수치와 추천 결과는 실제 주소의 조회 결과가 아닌
          예시입니다.
        </p>
      )}
      <p>
        주소·층·분석 반경은 입력값 또는 미리보기 예시입니다. 건축물 조회는 현재
        예시 데이터이며, 상가 확인값과 추가 답변은 확인 기록으로 표시됩니다.
        분석 서버 반영 여부는 아직 확인되지 않았습니다.
      </p>
      {fields.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-x-6 gap-y-1">
          {fields.map(([label, source]) => (
            <li key={label}>
              {label} · {sourceLabel[source]}
            </li>
          ))}
        </ul>
      )}
      {answers.length > 0 && (
        <ul className="mt-3 space-y-1">
          {answers.map((item, i) => (
            <li key={i}>
              <span className="font-medium text-gray-800">{item.label}: </span>
              {item.answer}
              {item.detail ? ` — ${item.detail}` : ''}
            </li>
          ))}
        </ul>
      )}
      {note && <p className="mt-2">추가 전달 사항: {note}</p>}
      {!building?.parking.value || building.parking.value === 'unknown' ? (
        <p className="mt-2">
          주차는 미확인입니다. 차량 방문이 중요한 업종은 실제 이용 조건을 먼저
          확인하세요.
        </p>
      ) : null}
    </aside>
  );
}

export default function ReportFollowUp({
  result,
  building,
  answers,
  floorUnit,
}: {
  floorUnit?: string;
  result: DecisionResult | null;
  building: BuildingInfo | null;
  answers: AnswerRecord[];
}) {
  const candidates = result?.recommendations
    .slice(0, 3)
    .map((item) => item.category.middle);
  const checks = [
    {
      title: `${floorUnit || '매장'} 접근성과 시설`,
      who: '건물 관리사무소 · 예비 임차인',
      body: '엘리베이터 이용, 간판 노출, 급·배수·전력·환기·하중 조건을 후보 업종에 맞춰 확인하세요.',
    },
    ...(!building?.parking.value || building.parking.value === 'unknown'
      ? [
          {
            title: '주차 이용 조건',
            who: '건물 관리사무소',
            body: '방문 고객 주차 가능 여부, 요금과 이용 시간을 확인하세요.',
          },
        ]
      : []),
    {
      title: '공사 허용 범위',
      who: '건물 소유자 · 관리사무소 · 시공업체',
      body: answers.some((item) => item.detail)
        ? '아래 확인 기록의 제한사항을 시공업체에 전달하고 필요한 공사가 허용되는지 확인하세요.'
        : '공사 범위와 건물 관리규정을 확인하세요. 입력하지 않은 시설 조건은 확인된 것으로 보지 않습니다.',
    },
    {
      title: '학교 주변 규제',
      who: '관할 교육지원청 · 인허가 담당 부서',
      body: '이 리포트의 지도는 규제 예시입니다. 실제 보호구역과 후보 업종의 적용 여부를 별도로 확인하세요.',
    },
  ];
  return (
    <section
      className="mx-8 mt-8 rounded-2xl bg-[#EAF5F3] p-8"
      aria-labelledby="follow-up-title"
    >
      <h2 id="follow-up-title" className="text-2xl font-bold text-gray-900">
        임차인 모집 전 확인할 것
      </h2>
      <p className="mt-3 text-lg leading-7 text-gray-700">
        {candidates?.length
          ? `우선 검토 후보: ${candidates.join(' · ')}`
          : result
            ? '추천 결과가 없어 후보를 확정할 수 없습니다.'
            : '예시의 우선 검토 후보: 네일·뷰티 · 무인점포 · 소형 스튜디오'}
      </p>
      <p className="mt-1 text-base leading-7 text-gray-600">
        추천은 입점 허가나 수익 보장이 아닙니다. 확인 결과에 따라 후보를 다시
        검토하세요.
      </p>
      <div className="mt-6 grid grid-cols-2 gap-x-10 gap-y-6">
        {checks.map((item) => (
          <div key={item.title} className="border-t border-[#BCD8D1] pt-4">
            <h3 className="text-lg font-semibold text-gray-900">
              {item.title}
            </h3>
            <p className="mt-1 text-sm font-medium text-[#006B65]">
              확인할 곳 · {item.who}
            </p>
            <p className="mt-2 text-base leading-7 text-gray-700">
              {item.body}
            </p>
          </div>
        ))}
      </div>
      {answers
        .filter((item) => item.detail)
        .map((item, i) => (
          <p className="mt-4 text-base text-gray-700" key={i}>
            확인 기록 · {item.label}: {item.detail}
          </p>
        ))}
      {result && result.limitations.length > 0 && (
        <div className="mt-6 border-t border-[#BCD8D1] pt-4">
          <h3 className="text-lg font-semibold">분석에서 남은 한계</h3>
          <ul className="mt-2 list-disc space-y-2 pl-5 text-base leading-7 text-gray-700">
            {result.limitations.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
