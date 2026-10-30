'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Building2, Check, Clock3, MapPin, X } from 'lucide-react';

export type MatchingRecommendation = {
  name: string;
};

// 실제 중개사 데이터가 아니다 — 화면에 '예시' 안내를 함께 띄운다.
const mockBrokers = [
  {
    id: 'broker-1',
    name: '한결공인중개사',
    specialty: '상가·사무실 전문 · 관악구 봉천동',
    distance: '0.2km',
    walkTime: '도보 3분',
  },
  {
    id: 'broker-2',
    name: '더채움공인중개사',
    specialty: '상가 임대 전문 · 관악구 봉천동',
    distance: '0.4km',
    walkTime: '도보 6분',
  },
  {
    id: 'broker-3',
    name: '온누리공인중개사',
    specialty: '주택·상가 · 관악구 행운동',
    distance: '0.9km',
    walkTime: '도보 13분',
  },
];

export default function TenantMatchingProposal({
  recommendations,
  propertyInfo,
}: {
  recommendations: MatchingRecommendation[];
  propertyInfo: { address: string; floor: string; area: string };
}) {
  const [isInView, setIsInView] = useState(false);
  const [isConfirmationOpen, setIsConfirmationOpen] = useState(false);
  const [flowStep, setFlowStep] = useState<
    'confirmation' | 'searching' | 'brokers' | 'complete'
  >('confirmation');
  const [selectedBrokerIds, setSelectedBrokerIds] = useState<string[]>([]);
  const proposalRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmButtonRef = useRef<HTMLButtonElement>(null);
  const stageHeadingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    const element = proposalRef.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsInView(true);
          observer.disconnect();
        }
      },
      { threshold: 0.25 }
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!isConfirmationOpen) return;

    const previouslyFocused = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    confirmButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsConfirmationOpen(false);
        return;
      }

      if (event.key !== 'Tab') return;
      const buttons = dialogRef.current?.querySelectorAll<HTMLButtonElement>(
        'button:not([disabled])'
      );
      if (!buttons?.length) return;

      const firstButton = buttons[0];
      const lastButton = buttons[buttons.length - 1];
      if (event.shiftKey && document.activeElement === firstButton) {
        event.preventDefault();
        lastButton.focus();
      } else if (!event.shiftKey && document.activeElement === lastButton) {
        event.preventDefault();
        firstButton.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyDown);
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
    };
  }, [isConfirmationOpen]);

  useEffect(() => {
    if (isConfirmationOpen && flowStep === 'searching') {
      const timeout = window.setTimeout(() => setFlowStep('brokers'), 1100);
      return () => window.clearTimeout(timeout);
    }
    if (isConfirmationOpen && flowStep === 'confirmation') {
      confirmButtonRef.current?.focus();
    }
    if (
      isConfirmationOpen &&
      (flowStep === 'brokers' || flowStep === 'complete')
    ) {
      stageHeadingRef.current?.focus();
    }
  }, [flowStep, isConfirmationOpen]);

  const closeConfirmation = () => {
    setIsConfirmationOpen(false);
    setFlowStep('confirmation');
    setSelectedBrokerIds([]);
  };

  const toggleBroker = (brokerId: string) => {
    setSelectedBrokerIds((selected) => {
      if (selected.includes(brokerId)) {
        return selected.filter((id) => id !== brokerId);
      }
      if (selected.length >= 3) return selected;
      return [...selected, brokerId];
    });
  };

  return (
    <div
      ref={proposalRef}
      className={`tenant-match${isInView ? ' is-in-view' : ''}`}
    >
      <div className="tenant-match-story">
        <div className="tenant-match-header">
          <div className="tenant-match-message">
            <p className="tenant-match-kicker">분석 결과를 활용할 다음 단계</p>
            <h3>
              추천 업종을 확인했어요.
              <br />
              이제 <span className="tenant-match-emphasis">임차인</span>을
              찾아볼까요?
            </h3>
            <p className="tenant-match-description">
              리포트의 추천 업종을 기준으로, 내 공간에 맞는 임차인 매칭을 시작해
              보세요.
            </p>
          </div>
          <button
            className="tenant-match-button"
            type="button"
            aria-haspopup="dialog"
            aria-expanded={isConfirmationOpen}
            onClick={() => {
              setFlowStep('confirmation');
              setSelectedBrokerIds([]);
              setIsConfirmationOpen(true);
            }}
          >
            임차인 매칭 시작하기 <ArrowRight size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="tenant-match-recommendations">
          <p className="tenant-match-list-title">이 공간의 추천 업종</p>
          {recommendations.length > 0 ? (
            <ol>
              {recommendations.map((item, index) => (
                <li key={`${item.name}-${index}`}>
                  <span className="tenant-match-rank">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span className="tenant-match-industry">{item.name}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="tenant-match-empty">
              매칭을 시작하면 업종과 공간 조건을 먼저 확인할 수 있어요.
            </p>
          )}
        </div>
      </div>

      {isConfirmationOpen && (
        <div
          className="tenant-confirmation-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeConfirmation();
          }}
        >
          <div
            ref={dialogRef}
            className="tenant-confirmation-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tenant-confirmation-title"
            aria-describedby="tenant-confirmation-description"
          >
            <button
              className="tenant-confirmation-close"
              type="button"
              aria-label="창 닫기"
              onClick={closeConfirmation}
            >
              <X size={20} aria-hidden="true" />
            </button>

            {flowStep === 'searching' ? (
              <div
                className="tenant-broker-search"
                role="status"
                aria-live="polite"
              >
                <div className="tenant-broker-search-visual" aria-hidden="true">
                  <span className="tenant-broker-search-orbit tenant-broker-search-orbit-outer" />
                  <span className="tenant-broker-search-orbit tenant-broker-search-orbit-inner" />
                  <span className="tenant-broker-search-building">
                    <Building2 size={28} />
                  </span>
                  <i className="tenant-broker-search-point tenant-broker-search-point-one" />
                  <i className="tenant-broker-search-point tenant-broker-search-point-two" />
                  <i className="tenant-broker-search-point tenant-broker-search-point-three" />
                </div>
                <h3 id="tenant-confirmation-title">
                  가장 가까운 중개사를
                  <br />
                  찾고 있어요
                </h3>
                <p id="tenant-confirmation-description">
                  건물 위치에서 가까운 순서로 찾는 중이에요.
                </p>
                <div
                  className="tenant-broker-search-progress"
                  role="progressbar"
                  aria-label="주변 중개사 검색 진행률"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuetext="중개사를 찾는 중"
                >
                  <span />
                </div>
                <p className="tenant-broker-search-count">
                  반경 1km 안에서 주변 중개사를 찾고 있어요
                </p>
                <div className="tenant-broker-search-property">
                  <MapPin size={18} aria-hidden="true" />
                  <span>
                    {propertyInfo.address} · {propertyInfo.floor} ·{' '}
                    {propertyInfo.area}
                  </span>
                </div>
                <button
                  className="tenant-confirmation-secondary tenant-broker-search-cancel"
                  type="button"
                  onClick={closeConfirmation}
                >
                  취소
                </button>
              </div>
            ) : flowStep === 'brokers' ? (
              <div className="tenant-broker-results">
                <p className="tenant-broker-results-kicker">주변 중개사</p>
                <h3
                  id="tenant-confirmation-title"
                  ref={stageHeadingRef}
                  tabIndex={-1}
                >
                  가까운 중개사를 찾았어요
                </h3>
                <p
                  id="tenant-confirmation-description"
                  className="tenant-confirmation-description"
                >
                  매물 정보를 보낼 중개사를 선택해 주세요. 최대 3곳까지 선택할
                  수 있어요.
                </p>
                <p className="tenant-broker-example-note">
                  ※ 화면 확인용 예시 중개사예요. 실제 중개사 연결은 준비
                  중이에요.
                </p>
                <div className="tenant-broker-results-property">
                  <MapPin size={17} aria-hidden="true" />
                  <span>
                    {propertyInfo.address} · {propertyInfo.floor} ·{' '}
                    {propertyInfo.area}
                  </span>
                </div>
                <div
                  className="tenant-broker-list"
                  role="group"
                  aria-label="등록할 중개사 선택"
                >
                  {mockBrokers.map((broker) => {
                    const isSelected = selectedBrokerIds.includes(broker.id);
                    return (
                      <button
                        key={broker.id}
                        type="button"
                        className={`tenant-broker-option${isSelected ? ' is-selected' : ''}`}
                        aria-pressed={isSelected}
                        onClick={() => toggleBroker(broker.id)}
                      >
                        <span
                          className="tenant-broker-option-check"
                          aria-hidden="true"
                        >
                          {isSelected ? <Check size={15} /> : null}
                        </span>
                        <span className="tenant-broker-option-copy">
                          <strong>{broker.name}</strong>
                          <small>{broker.specialty}</small>
                        </span>
                        <span className="tenant-broker-option-distance">
                          <strong>{broker.distance}</strong>
                          <small>
                            <Clock3 size={12} aria-hidden="true" />
                            {broker.walkTime}
                          </small>
                        </span>
                      </button>
                    );
                  })}
                </div>
                <p className="tenant-broker-selection-count" aria-live="polite">
                  {selectedBrokerIds.length}곳 선택됨
                </p>
                <div className="tenant-confirmation-actions">
                  <button
                    className="tenant-confirmation-primary"
                    type="button"
                    disabled={selectedBrokerIds.length === 0}
                    onClick={() => setFlowStep('complete')}
                  >
                    선택한 중개사
                    {selectedBrokerIds.length > 0
                      ? ` ${selectedBrokerIds.length}곳`
                      : ''}
                    에 등록하기
                  </button>
                  <button
                    className="tenant-confirmation-secondary"
                    type="button"
                    onClick={() => setFlowStep('confirmation')}
                  >
                    이전
                  </button>
                </div>
              </div>
            ) : flowStep === 'complete' ? (
              <div className="tenant-broker-complete">
                <span
                  className="tenant-broker-complete-icon"
                  aria-hidden="true"
                >
                  <Check size={30} />
                </span>
                <p className="tenant-broker-results-kicker">매물 등록</p>
                <h3
                  id="tenant-confirmation-title"
                  ref={stageHeadingRef}
                  tabIndex={-1}
                >
                  중개사에게 매물 등록을 요청했어요
                </h3>
                <p
                  id="tenant-confirmation-description"
                  className="tenant-confirmation-description"
                >
                  선택한 중개사 {selectedBrokerIds.length}곳에 공간 정보를
                  전달했어요.
                </p>
                <div
                  className="tenant-broker-map"
                  role="img"
                  aria-label="매물과 등록한 중개사의 위치를 나타낸 지도"
                >
                  <span className="tenant-broker-map-road tenant-broker-map-road-one" />
                  <span className="tenant-broker-map-road tenant-broker-map-road-two" />
                  <span className="tenant-broker-map-block tenant-broker-map-block-one" />
                  <span className="tenant-broker-map-block tenant-broker-map-block-two" />
                  <span className="tenant-broker-map-property-pin">
                    <MapPin size={24} fill="currentColor" />
                  </span>
                  {selectedBrokerIds.map((brokerId, index) => (
                    <span
                      key={brokerId}
                      className={`tenant-broker-map-broker-pin pin-${index + 1}`}
                    >
                      {index + 1}
                    </span>
                  ))}
                  <span className="tenant-broker-map-radius" />
                </div>
                <div className="tenant-broker-complete-summary">
                  <div>
                    <span>주소</span>
                    <strong>{propertyInfo.address}</strong>
                  </div>
                  <div>
                    <span>층 · 면적</span>
                    <strong>
                      {propertyInfo.floor} · {propertyInfo.area}
                    </strong>
                  </div>
                  <div>
                    <span>등록 요청한 중개사</span>
                    <strong className="tenant-broker-complete-names">
                      {mockBrokers
                        .filter((broker) =>
                          selectedBrokerIds.includes(broker.id)
                        )
                        .map((broker) => broker.name)
                        .join(' · ')}
                    </strong>
                  </div>
                </div>
                <button
                  className="tenant-confirmation-primary tenant-broker-complete-button"
                  type="button"
                  onClick={closeConfirmation}
                >
                  확인
                </button>
              </div>
            ) : (
              <>
                <span className="tenant-confirmation-icon">
                  <Building2 size={24} aria-hidden="true" />
                </span>
                <h3 id="tenant-confirmation-title">
                  이 공간을 매물로 등록하시겠어요?
                </h3>
                <p
                  id="tenant-confirmation-description"
                  className="tenant-confirmation-description"
                >
                  가까운 중개사에게 공간 정보와 분석 결과를 보내 임차인을
                  찾아볼게요.
                </p>

                <div className="tenant-confirmation-information">
                  <p>함께 보내는 정보</p>
                  <ul>
                    <li>
                      <span>공간 정보</span>
                      <strong>
                        {propertyInfo.address} · {propertyInfo.floor} ·{' '}
                        {propertyInfo.area}
                      </strong>
                    </li>
                    <li>
                      <span>분석 내용</span>
                      <strong>업종별 판단 근거 요약</strong>
                    </li>
                  </ul>
                </div>

                <div className="tenant-confirmation-actions">
                  <button
                    ref={confirmButtonRef}
                    className="tenant-confirmation-primary"
                    type="button"
                    onClick={() => setFlowStep('searching')}
                  >
                    주변 중개사 찾기
                  </button>
                  <button
                    className="tenant-confirmation-secondary"
                    type="button"
                    onClick={closeConfirmation}
                  >
                    나중에 할게요
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
