'use client';
import { useState, type ReactNode } from 'react';
import { School, TriangleAlert, ExternalLink } from 'lucide-react';
export type SchoolProtectionZone = 'absolute' | 'relative' | 'unknown';
// 실제 보호구역 조회 결과 연결 전에는 위치의 해당 여부를 단정하지 않는다.
export default function SchoolRegulation({
  zone = 'unknown',
  children,
}: {
  zone?: SchoolProtectionZone;
  children?: ReactNode;
}) {
  const [preview, setPreview] = useState<SchoolProtectionZone | null>(null);
  const displayed = preview ?? zone;
  return (
    <div className="school-regulation">
      <div className="regulation-status" data-inside={displayed !== 'unknown'}>
        <span className="school-symbol">
          <School size={35} strokeWidth={1.6} aria-hidden="true" />
        </span>
        <div>
          <p>학교 주변 교육환경보호구역</p>
          <h3>
            {displayed === 'absolute'
              ? '절대보호구역 · 해당 금지 업종 불가'
              : displayed === 'relative'
                ? '상대보호구역 · 입점 가능 여부 확인 필요'
                : '보호구역 해당 여부 확인 필요'}
          </h3>
        </div>
        <span className={`regulation-badge zone-${displayed}`}>
          {displayed === 'absolute' ? '불가' : '확인 필요'}
        </span>
      </div>
      {preview && (
        <p className="regulation-demo-note">
          시안 예시입니다. 이 상가의 실제 보호구역 판정이 아닙니다.
        </p>
      )}
      {children ?? (
        <>
          <p className="regulation-explanation">
            {displayed === 'absolute'
              ? 'PC방·숙박업·노래연습장 등 법에서 금지하는 업종은 입점이 제한됩니다.'
              : displayed === 'relative'
                ? 'PC방·숙박업·노래연습장 등은 금지 대상 여부와 교육지원청 심의·허용 여부를 먼저 확인하세요.'
                : '학교 위치와 고시된 보호구역 자료가 아직 연결되지 않았습니다. 규제 확인이 완료되기 전에는 입점 가능으로 판단하지 않습니다.'}
          </p>
          <div className="school-zone-rules">
            <article>
              <div>
                <strong>절대보호구역</strong>
                <span className="regulation-badge zone-absolute">불가</span>
              </div>
              <p className="zone-distance">50m</p>
              <p>학교 출입문에서 직선거리 50m까지</p>
              <p>
                <strong>해당 금지 업종은 입점 불가</strong>
              </p>
            </article>
            <article>
              <div>
                <strong>상대보호구역</strong>
                <span className="regulation-badge zone-relative">
                  확인 필요
                </span>
              </div>
              <p className="zone-distance">200m</p>
              <p>
                학교 경계 등에서 직선거리 200m까지 중 절대보호구역을 제외한 지역
              </p>
              <p>
                <strong>대상 업종의 심의·허용 여부 확인</strong>
              </p>
            </article>
          </div>
          <p className="regulation-limit">
            <TriangleAlert size={20} aria-hidden="true" />
            학교 종류·업종의 법적 분류·고시 구역에 따라 적용이 달라집니다.
            상대보호구역의 모든 업종이 심의로 허용되는 것은 아닙니다.
          </p>
          <a
            className="regulation-source"
            href="https://www.law.go.kr/법령/교육환경보호에관한법률"
            target="_blank"
            rel="noopener noreferrer"
          >
            교육환경 보호에 관한 법률 제8조·제9조{' '}
            <ExternalLink size={16} aria-hidden="true" />
          </a>
        </>
      )}
      {!children && (
        <details className="regulation-preview">
          <summary>보호구역 표시 시안 확인</summary>
          <p>실제 분석 결과에는 영향을 주지 않습니다.</p>
          <div>
            {(
              [
                ['unknown', '조회 전'],
                ['absolute', '절대보호구역 예시'],
                ['relative', '상대보호구역 예시'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={displayed === value}
                onClick={() => setPreview(value === 'unknown' ? null : value)}
              >
                {label}
              </button>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
