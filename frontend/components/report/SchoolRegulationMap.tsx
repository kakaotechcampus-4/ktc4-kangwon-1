'use client';

import { useEffect, useRef, useState } from 'react';
import { Monitor, BedDouble, MicVocal } from 'lucide-react';
import KakaoSchoolMap from './KakaoSchoolMap';

/** Illustrative map only; no school coordinates or gazetted boundaries are available yet. */
export default function SchoolRegulationMap({
  embedded = false,
}: { embedded?: boolean } = {}) {
  const [zone, setZone] = useState<'absolute' | 'relative'>('absolute');
  const absolute = zone === 'absolute';
  const industryList = useRef<HTMLDivElement>(null);
  const [industriesVisible, setIndustriesVisible] = useState(false);
  useEffect(() => {
    if (!industryList.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIndustriesVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.6 }
    );
    observer.observe(industryList.current);
    return () => observer.disconnect();
  }, []);
  return (
    <section
      id="school-regulation"
      aria-label="학교 주변 규제 확인"
      className={embedded ? 'mt-6' : 'mx-8 mt-14 mb-12'}
    >
      {!embedded && (
        <div className="mb-6 flex items-center justify-between gap-4">
          <div>
            <h2
              id="school-regulation-title"
              className="text-2xl font-bold text-gray-900"
            >
              학교 주변 규제 확인
            </h2>
            <p className="mt-2 text-base text-gray-600">
              학교와 가까운 상가는 업종에 따라 입점이 제한될 수 있어요.
            </p>
          </div>
          <span className="shrink-0 rounded-md bg-gray-100 px-3 py-2 text-sm font-semibold text-gray-600">
            이 상가의 규제 판정 · 미확인
          </span>
        </div>
      )}
      <div
        className={
          embedded
            ? 'grid grid-cols-[1.1fr_1fr] items-start gap-8'
            : 'grid grid-cols-[1.1fr_1fr] overflow-hidden rounded-2xl border border-gray-200 bg-white'
        }
      >
        <div className={embedded ? 'overflow-hidden rounded-2xl' : ''}>
          <KakaoSchoolMap absolute={absolute} />
        </div>
        <div className={embedded ? 'min-w-0 p-0' : 'px-8 py-7'}>
          <div className="mb-4 flex gap-2" aria-label="보호구역 선택">
            {(['absolute', 'relative'] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={zone === value}
                onClick={() => setZone(value)}
                className={`rounded-lg border px-4 py-2 text-base font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 ${zone === value ? 'border-[#004F54] bg-[#E8F6F2] text-[#004F54]' : 'border-gray-200 text-gray-600'}`}
              >
                {value === 'absolute' ? '50m 안' : '200m 안'}
              </button>
            ))}
          </div>
          <span
            className={`inline-block rounded-md px-3 py-1 text-base font-bold ${absolute ? 'border-red-200 bg-red-50 text-[#C63742]' : 'border-amber-200 bg-amber-50 text-amber-800'}`}
          >
            {absolute ? '절대보호구역' : '확인 필요 · 상대보호구역'}
          </span>
          <h3 className="mt-3 text-2xl leading-snug font-bold text-gray-900">
            {absolute
              ? '50m 보호구역의 적용 여부를 확인하세요'
              : '200m 보호구역의 적용 여부를 확인하세요'}
          </h3>
          <p className="mt-2 text-base leading-6 text-gray-600">
            아래 업종의 실제 제한 여부는 대상 학교·업종 분류와 관할 교육지원청
            확인이 필요합니다.
          </p>
          <div ref={industryList} className="mt-4 grid grid-cols-3 gap-3">
            {[
              ['PC방', Monitor],
              ['숙박업', BedDouble],
              ['노래연습장', MicVocal],
            ].map(([label, Icon], index) => {
              const Symbol = Icon as typeof Monitor;
              return (
                <span
                  key={`${zone}-${label}`}
                  style={{ animationDelay: `${350 + index * 280}ms` }}
                  className={`${industriesVisible ? 'regulation-industry-enter' : 'regulation-industry-pending'} flex flex-col items-center justify-center gap-2 rounded-xl border px-3 py-3 text-xl font-bold ${absolute ? 'border-red-200 bg-red-50 text-[#C63742]' : 'border-amber-200 bg-amber-50 text-amber-800'}`}
                >
                  <Symbol size={32} aria-hidden="true" />
                  {label as string}
                </span>
              );
            })}
          </div>
          <p className="mt-3 text-base leading-6 text-gray-600">
            {absolute
              ? '절대보호구역은 학교 출입문에서 50m까지입니다. 위 업종은 적용 대상 학교·시설인지 먼저 확인해야 합니다.'
              : '상대보호구역은 학교 경계에서 200m까지 중 절대보호구역을 제외한 지역입니다. 대상 업종과 교육지원청 심의·허용 여부를 확인해야 합니다.'}
          </p>
        </div>
      </div>
      <style jsx>{`
        .regulation-industry-pending {
          opacity: 0;
        }
        .regulation-industry-enter {
          animation: regulation-industry-reveal 650ms ease-out both;
        }
        @keyframes regulation-industry-reveal {
          from {
            opacity: 0;
            transform: translateY(14px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .regulation-industry-pending {
            opacity: 1;
          }
          .regulation-industry-enter {
            animation: none;
          }
        }
      `}</style>
    </section>
  );
}
