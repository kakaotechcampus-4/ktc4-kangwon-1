'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  MapPin,
  MessageSquare,
  RotateCcw,
  X,
} from 'lucide-react';
import Header from '@/components/layout/Header';
import FlowPageTitle from '@/components/form/FlowPageTitle';
import Button from '@/components/ui/Button';
import { colors } from '@/styles/tokens';
import { INDUSTRIES } from '@/lib/api/industries';
import Image from 'next/image';
import KakaoListingMap, { KAKAO_MAP_KEY } from './KakaoListingMap';

/*
 * 임차인용 매물 탐색 프로토타입 — 백엔드 연결 없이 아래 목업 매물로만 동작한다.
 * 디자인은 기존 화면을 따른다.
 *  - 헤더·페이지 제목: 공실 분석 흐름과 같은 Header · FlowPageTitle
 *  - 카드: components/ui/Card와 같은 흰 바탕 + 얇은 테두리(#E2E8EE) + 옅은 그림자
 *  - 버튼: components/ui/Button(파랑, 둥근 모서리, 파란 그림자)
 *  - 입력·선택 칸: components/ui/Input과 같은 1.5px 테두리(#D5DEE7)
 */

type Listing = {
  id: number;
  district: string;
  neighborhood: string;
  // 실제 지도(카카오맵)에 찍을 대략의 위치 — 예시 매물이라 동네 중심 근처 좌표
  lat: number;
  lng: number;
  address: string; // 예시 도로명 주소
  floor: string;
  deposit: number; // 만원
  rent: number; // 만원
  area: number; // 전용 면적 ㎡
  // 임대인이 이 공실을 채움으로 분석했을 때 나온 추천 업종 1~3위(업종 코드)
  recommended: string[];
  // 공실 컨디션 사진(외관·내부) — 예시 이미지
  photos: { kind: 'exterior' | 'interior'; src: string }[];
  // 예시 지도 위 위치(%)
  x: number;
  y: number;
};

// 공실 컨디션 예시 사진 — public/prototypes/tenant-search/ — 실제 매물 사진이 아닌 예시
const photoSrc = (id: number, kind: 'exterior' | 'interior') =>
  `/prototypes/tenant-search/listing-${String(id).padStart(2, '0')}-${kind}.jpg`;

const LISTINGS: Listing[] = [
  {
    id: 1,
    district: '마포구',
    neighborhood: '연남동',
    lat: 37.5627,
    lng: 126.9236,
    address: '동교로41길 18',
    floor: '1층',
    deposit: 3000,
    rent: 230,
    area: 49.6,
    recommended: ['I212', 'G218', 'I210'],
    photos: [
      { kind: 'exterior', src: photoSrc(1, 'exterior') },
      { kind: 'interior', src: photoSrc(1, 'interior') },
    ],
    x: 27,
    y: 41,
  },
  {
    id: 2,
    district: '마포구',
    neighborhood: '망원동',
    lat: 37.5556,
    lng: 126.901,
    address: '포은로 72',
    floor: '1층',
    deposit: 2500,
    rent: 210,
    area: 58.2,
    recommended: ['I201', 'I212', 'G205'],
    photos: [
      { kind: 'exterior', src: photoSrc(2, 'exterior') },
      { kind: 'interior', src: photoSrc(2, 'interior') },
    ],
    x: 21,
    y: 48,
  },
  {
    id: 3,
    district: '성동구',
    neighborhood: '성수동2가',
    lat: 37.5446,
    lng: 127.056,
    address: '연무장길 33',
    floor: '1층',
    deposit: 5000,
    rent: 390,
    area: 66.1,
    recommended: ['G209', 'I212', 'G215B'],
    photos: [
      { kind: 'exterior', src: photoSrc(3, 'exterior') },
      { kind: 'interior', src: photoSrc(3, 'interior') },
    ],
    x: 66,
    y: 50,
  },
  {
    id: 4,
    district: '성동구',
    neighborhood: '왕십리동',
    lat: 37.5614,
    lng: 127.0381,
    address: '왕십리로 245',
    floor: '2층',
    deposit: 3000,
    rent: 250,
    area: 92.5,
    recommended: ['P105', 'R103', 'S207'],
    photos: [
      { kind: 'exterior', src: photoSrc(4, 'exterior') },
      { kind: 'interior', src: photoSrc(4, 'interior') },
    ],
    x: 60,
    y: 42,
  },
  {
    id: 5,
    district: '강남구',
    neighborhood: '역삼동',
    lat: 37.5006,
    lng: 127.0364,
    address: '테헤란로8길 21',
    floor: '2층',
    deposit: 2000,
    rent: 180,
    area: 42.8,
    recommended: ['S207', 'S208', 'P105'],
    photos: [
      { kind: 'exterior', src: photoSrc(5, 'exterior') },
      { kind: 'interior', src: photoSrc(5, 'interior') },
    ],
    x: 66,
    y: 72,
  },
  {
    id: 6,
    district: '강남구',
    neighborhood: '논현동',
    lat: 37.511,
    lng: 127.0284,
    address: '학동로17길 9',
    floor: '지하 1층',
    deposit: 4000,
    rent: 320,
    area: 105.8,
    recommended: ['I211', 'I201', 'R104'],
    photos: [
      { kind: 'exterior', src: photoSrc(6, 'exterior') },
      { kind: 'interior', src: photoSrc(6, 'interior') },
    ],
    x: 60,
    y: 66,
  },
  {
    id: 7,
    district: '송파구',
    neighborhood: '문정동',
    lat: 37.4859,
    lng: 127.1225,
    address: '법원로 128',
    floor: '1층',
    deposit: 1500,
    rent: 150,
    area: 31.2,
    recommended: ['I212', 'I210', 'G205'],
    photos: [
      { kind: 'exterior', src: photoSrc(7, 'exterior') },
      { kind: 'interior', src: photoSrc(7, 'interior') },
    ],
    x: 82,
    y: 78,
  },
  {
    id: 8,
    district: '종로구',
    neighborhood: '익선동',
    lat: 37.5743,
    lng: 126.9887,
    address: '수표로28길 17',
    floor: '1층',
    deposit: 2000,
    rent: 200,
    area: 28.4,
    recommended: ['I201', 'I212', 'I211'],
    photos: [
      { kind: 'exterior', src: photoSrc(8, 'exterior') },
      { kind: 'interior', src: photoSrc(8, 'interior') },
    ],
    x: 47,
    y: 31,
  },
  {
    id: 9,
    district: '용산구',
    neighborhood: '한남동',
    lat: 37.5345,
    lng: 127.001,
    address: '이태원로 241',
    floor: '1층',
    deposit: 7000,
    rent: 450,
    area: 75.0,
    recommended: ['G209', 'G215B', 'I204'],
    photos: [
      { kind: 'exterior', src: photoSrc(9, 'exterior') },
      { kind: 'interior', src: photoSrc(9, 'interior') },
    ],
    x: 52,
    y: 54,
  },
  {
    id: 10,
    district: '영등포구',
    neighborhood: '문래동',
    lat: 37.518,
    lng: 126.8946,
    address: '도림로128길 12',
    floor: '1층',
    deposit: 2000,
    rent: 170,
    area: 52.9,
    recommended: ['I212', 'I211', 'M113'],
    photos: [
      { kind: 'exterior', src: photoSrc(10, 'exterior') },
      { kind: 'interior', src: photoSrc(10, 'interior') },
    ],
    x: 26,
    y: 66,
  },
  {
    id: 11,
    district: '서초구',
    neighborhood: '서초동',
    lat: 37.4918,
    lng: 127.0076,
    address: '서초대로50길 33',
    floor: '3층',
    deposit: 3000,
    rent: 280,
    area: 120.3,
    recommended: ['P105', 'Q102', 'R103'],
    photos: [
      { kind: 'exterior', src: photoSrc(11, 'exterior') },
      { kind: 'interior', src: photoSrc(11, 'interior') },
    ],
    x: 52,
    y: 75,
  },
  {
    id: 12,
    district: '광진구',
    neighborhood: '화양동',
    lat: 37.5465,
    lng: 127.0712,
    address: '아차산로33길 14',
    floor: '1층',
    deposit: 1000,
    rent: 120,
    area: 26.4,
    recommended: ['S207', 'I212', 'I210'],
    photos: [
      { kind: 'exterior', src: photoSrc(12, 'exterior') },
      { kind: 'interior', src: photoSrc(12, 'interior') },
    ],
    x: 76,
    y: 47,
  },
];

// 희망 업종 — 서비스 51개 업종(lib/api/industries). 자주 찾는 업종만 먼저 보여주고
// 나머지는 '+ 전체 업종'에서 대분류별로 고른다.
const industryName = (code: string) => INDUSTRIES[code]?.name ?? code;
const POPULAR_INDUSTRIES = [
  'I212',
  'I201',
  'I210',
  'I211',
  'S207',
  'P105',
  'G209',
  'G205',
];
const INDUSTRY_GROUPS = Object.entries(INDUSTRIES).reduce<
  { major: string; codes: string[] }[]
>((groups, [code, { major }]) => {
  const group = groups.find((g) => g.major === major);
  if (group) group.codes.push(code);
  else groups.push({ major, codes: [code] });
  return groups;
}, []);

const DISTRICTS = [
  '서울 전체',
  ...Array.from(new Set(LISTINGS.map((l) => l.district))).sort((a, b) =>
    a.localeCompare(b, 'ko')
  ),
];

// 예시 지도에 적을 구 이름 위치(%)
const DISTRICT_LABELS = [
  { name: '은평구', x: 30, y: 20 },
  { name: '종로구', x: 47, y: 24 },
  { name: '노원구', x: 74, y: 14 },
  { name: '마포구', x: 22, y: 36 },
  { name: '중구', x: 52, y: 38 },
  { name: '성동구', x: 64, y: 36 },
  { name: '광진구', x: 80, y: 41 },
  { name: '용산구', x: 45, y: 49 },
  { name: '영등포구', x: 20, y: 72 },
  { name: '서초구', x: 46, y: 82 },
  { name: '강남구', x: 70, y: 82 },
  { name: '송파구', x: 87, y: 70 },
];

const SURFACE =
  'rounded-[20px] border bg-white shadow-[0_18px_40px_rgba(16,35,58,0.06)]';

const won = (manwon: number) => `${manwon.toLocaleString('ko-KR')}만원`;
const pyeong = (sqm: number) => Math.round(sqm / 3.3058);

function FilterLabel({ children }: { children: string }) {
  return (
    <p className="mb-2 text-13 font-semibold text-[#4B5866]">{children}</p>
  );
}

// 입력한 면적을 평으로 바꿔 안내한다(1평 ≈ 3.3㎡).
function areaHint(lo: number, hi: number) {
  if (lo === 0 && hi === Infinity) return '비워 두면 면적 제한 없이 찾아요';
  if (lo === 0) return `약 ${pyeong(hi)}평 이하`;
  if (hi === Infinity) return `약 ${pyeong(lo)}평 이상`;
  return `약 ${pyeong(lo)}~${pyeong(hi)}평`;
}

function AreaInput({
  id,
  label,
  placeholder,
  value,
  onChange,
}: {
  id: string;
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label
      htmlFor={id}
      className="flex h-11 w-[124px] items-center rounded-xl border-[1.5px] border-[#D5DEE7] bg-white pr-3 focus-within:border-[#2453D6]"
    >
      <span className="sr-only">{label}</span>
      <input
        id={id}
        type="number"
        inputMode="decimal"
        min={0}
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="h-full w-full min-w-0 rounded-xl bg-transparent pl-3.5 text-sm font-semibold text-[#10233A] outline-none placeholder:font-medium placeholder:text-[#9CA3AF] [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
      />
      <span className="shrink-0 text-13 font-medium text-[#8A97A5]">㎡</span>
    </label>
  );
}

function Chip({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`h-9 rounded-full border px-3.5 text-13 font-semibold whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2453D6] ${
        active
          ? 'border-[#2453D6] bg-[#EAF0FC] text-[#2453D6]'
          : 'border-[#E2E8EE] bg-white text-[#4B5866] hover:border-[#B9C7D8] hover:text-[#10233A]'
      }`}
    >
      {children}
    </button>
  );
}

function ExampleBadge({ children = '예시' }: { children?: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-[#FFF4DE] px-2 py-0.5 text-11 font-bold text-[#9A5B00]">
      {children}
    </span>
  );
}

// 지도 위에 겹쳐 보여주는 것들 — 예시 지도·카카오맵 둘 다 쓴다.
function MapOverlays({
  listings,
  selected,
  badge,
}: {
  listings: Listing[];
  selected: Listing | null;
  badge: string;
}) {
  return (
    <>
      <div className="absolute top-3 left-3 flex items-center gap-1.5 rounded-full bg-white/95 px-3 py-1.5 text-xs font-semibold text-[#4B5866] shadow-[0_4px_12px_rgba(16,35,58,0.08)]">
        <MapPin size={13} className="text-[#2453D6]" aria-hidden="true" />
        서울 · 매물 {listings.length}곳
      </div>
      <div className="absolute top-3 right-3">
        <ExampleBadge>{badge}</ExampleBadge>
      </div>

      {selected && (
        <div className="absolute inset-x-3 bottom-3 flex items-center justify-between gap-3 rounded-2xl border border-[#E2E8EE] bg-white/95 px-4 py-3 shadow-[0_10px_24px_rgba(16,35,58,0.1)]">
          <div className="min-w-0">
            <p className="truncate text-13 font-bold text-[#2453D6]">
              {selected.district} · {selected.neighborhood}
            </p>
            <p className="truncate text-sm font-bold text-[#10233A]">
              {selected.address} · {selected.floor}
            </p>
          </div>
          <p className="shrink-0 text-right text-13 text-[#4B5866]">
            <span className="block">보증금 {won(selected.deposit)}</span>
            <span className="block font-bold text-[#10233A]">
              월세 {won(selected.rent)}
            </span>
          </p>
        </div>
      )}
    </>
  );
}

function SeoulExampleMap({
  listings,
  selectedId,
  onSelect,
}: {
  listings: Listing[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const selected = listings.find((l) => l.id === selectedId) ?? null;
  return (
    <div className="relative h-[380px] overflow-hidden bg-[#EEF3F8] sm:h-[460px] lg:h-full lg:min-h-[560px]">
      {/* 바탕 그림 — 실제 지도가 아니라 서울을 단순하게 그린 예시 */}
      <svg
        aria-hidden="true"
        className="absolute inset-0 size-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        <path
          d="M-2 18 C 20 10, 40 8, 60 10 S 95 6, 102 12 L 102 -2 L -2 -2 Z"
          fill="#E6EDF4"
        />
        {/* 한강 */}
        <path
          d="M -2 60 C 14 56, 26 58, 36 62 S 52 66, 62 61 S 82 54, 102 51"
          fill="none"
          stroke="#D6E4F5"
          strokeWidth="22"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
        {/* 큰길 — 화면 크기가 바뀌어도 선 굵기가 같도록 non-scaling-stroke */}
        {[
          'M -2 40 C 25 37, 55 36, 102 33',
          'M -2 82 C 30 79, 60 77, 102 72',
          'M 38 -2 C 41 30, 43 60, 47 102',
          'M 72 -2 C 69 35, 66 70, 63 102',
          'M 14 -2 C 18 30, 24 70, 30 102',
        ].map((d) => (
          <path
            key={d}
            d={d}
            fill="none"
            stroke="#FFFFFF"
            strokeWidth="5"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
      <span
        className="absolute top-[57%] left-[6%] -rotate-3 text-11 font-semibold tracking-[0.2em] text-[#8FA9CF]"
        aria-hidden="true"
      >
        한강
      </span>
      {DISTRICT_LABELS.map((d) => (
        <span
          key={d.name}
          aria-hidden="true"
          className="absolute -translate-x-1/2 -translate-y-1/2 text-11 font-medium text-[#8A97A5]"
          style={{ left: `${d.x}%`, top: `${d.y}%` }}
        >
          {d.name}
        </span>
      ))}

      {listings.map((listing) => {
        const active = listing.id === selectedId;
        return (
          <button
            key={listing.id}
            type="button"
            aria-pressed={active}
            aria-label={`${listing.district} ${listing.neighborhood} ${listing.floor} 매물 선택, 월세 ${won(listing.rent)}`}
            onClick={() => onSelect(listing.id)}
            className={`absolute -translate-x-1/2 -translate-y-full transition-transform duration-150 focus-visible:outline-none ${
              active ? 'z-20 scale-110' : 'z-10 hover:z-20 hover:scale-105'
            }`}
            style={{ left: `${listing.x}%`, top: `${listing.y}%` }}
          >
            <span
              className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold whitespace-nowrap text-white shadow-[0_6px_14px_rgba(16,35,58,0.18)] ${
                active
                  ? 'bg-[#2453D6] ring-4 ring-[#2453D6]/20'
                  : 'bg-[#10233A]'
              }`}
            >
              {listing.rent}만
            </span>
            <span
              className={`mx-auto block size-0 border-x-[5px] border-t-[6px] border-x-transparent ${
                active ? 'border-t-[#2453D6]' : 'border-t-[#10233A]'
              }`}
            />
          </button>
        );
      })}

      <MapOverlays listings={listings} selected={selected} badge="예시 지도" />
    </div>
  );
}

function ListingItem({
  listing,
  active,
  onSelect,
  onInquire,
  itemRef,
}: {
  listing: Listing;
  active: boolean;
  onSelect: () => void;
  onInquire: () => void;
  itemRef: (el: HTMLElement | null) => void;
}) {
  const [photoIndex, setPhotoIndex] = useState(0);
  const photo = listing.photos[photoIndex];
  return (
    <article
      ref={itemRef}
      onClick={onSelect}
      className={`cursor-pointer rounded-[20px] border bg-white p-5 transition-[border-color,box-shadow] duration-150 ${
        active
          ? 'border-[#2453D6] shadow-[0_0_0_3px_rgba(36,83,214,0.12),0_18px_40px_rgba(16,35,58,0.06)]'
          : 'border-[#E2E8EE] hover:border-[#B9C7D8]'
      }`}
    >
      <div className="flex flex-col gap-4 sm:flex-row">
        {/* 공실 컨디션 사진(예시 사진) — 양옆 화살표로 넘겨 본다 */}
        <div
          className="group relative h-[168px] w-full shrink-0 overflow-hidden rounded-2xl bg-[#EEF2F7] sm:h-[132px] sm:w-[176px]"
          aria-roledescription="사진 넘겨 보기"
        >
          <Image
            src={photo.src}
            alt={`${listing.neighborhood} ${listing.floor} 공실 ${
              photo.kind === 'exterior' ? '외관' : '내부'
            } 예시 사진`}
            fill
            sizes="(min-width: 640px) 176px, 100vw"
            className="object-cover"
          />
          <span className="absolute top-2 left-2 rounded-full bg-[#10233A]/70 px-2 py-0.5 text-11 font-semibold text-white">
            {photoIndex + 1}/{listing.photos.length}
          </span>
          <span className="absolute right-2 bottom-2 rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold text-[#6B7A8A]">
            예시 사진
          </span>
          {photoIndex > 0 && (
            <button
              type="button"
              aria-label="이전 사진"
              onClick={(event) => {
                event.stopPropagation();
                setPhotoIndex((index) => index - 1);
              }}
              className="absolute top-1/2 left-1.5 grid size-7 -translate-y-1/2 place-items-center rounded-full bg-white/65 text-[#10233A] shadow-[0_2px_8px_rgba(16,35,58,0.12)] backdrop-blur-sm transition-colors hover:bg-white/80 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#2453D6]"
            >
              <ChevronLeft size={16} aria-hidden="true" />
            </button>
          )}
          {photoIndex < listing.photos.length - 1 && (
            <button
              type="button"
              aria-label="다음 사진"
              onClick={(event) => {
                event.stopPropagation();
                setPhotoIndex((index) => index + 1);
              }}
              className="absolute top-1/2 right-1.5 grid size-7 -translate-y-1/2 place-items-center rounded-full bg-white/65 text-[#10233A] shadow-[0_2px_8px_rgba(16,35,58,0.12)] backdrop-blur-sm transition-colors hover:bg-white/80 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#2453D6]"
            >
              <ChevronRight size={16} aria-hidden="true" />
            </button>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <button
              type="button"
              aria-pressed={active}
              onClick={(event) => {
                event.stopPropagation();
                onSelect();
              }}
              className="min-w-0 text-left focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#2453D6]"
            >
              <span className="block text-13 font-bold text-[#2453D6]">
                {listing.district} · {listing.neighborhood}
              </span>
              <span className="mt-1 block text-lg leading-snug font-extrabold tracking-[-0.02em] text-[#10233A]">
                {listing.address}
              </span>
            </button>
            <span className="mt-0.5 shrink-0 text-xs font-medium text-[#8A97A5]">
              예시 매물
            </span>
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2.5">
            {[
              ['보증금', won(listing.deposit)],
              ['월세', won(listing.rent)],
              ['전용 면적', `${listing.area}㎡`],
              ['층', listing.floor],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="text-xs font-medium text-[#6B7A8A]">{label}</dt>
                <dd className="mt-0.5 text-15 font-bold whitespace-nowrap text-[#10233A] tabular-nums">
                  {value}
                  {label === '전용 면적' && (
                    <span className="ml-1 text-xs font-medium text-[#8A97A5]">
                      약 {pyeong(listing.area)}평
                    </span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-3 border-t border-[#EEF2F6] pt-4 sm:flex-row sm:items-center">
        {/* 임대인이 이 공실을 채움으로 분석했을 때 나온 추천 업종(순위 순) */}
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
          <span className="mr-0.5 text-xs font-bold text-[#2453D6]">
            채움 추천
          </span>
          {listing.recommended.map((code) => (
            <span
              key={code}
              className="rounded-full bg-[#EAF0FC] px-2.5 py-1 text-xs font-semibold text-[#2453D6]"
            >
              {industryName(code)}
            </span>
          ))}
        </div>
        <Button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onSelect();
            onInquire();
          }}
          className="gap-1.5 self-end !px-4 !py-2.5 sm:self-auto focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2453D6]"
        >
          매물 문의하기 <ArrowRight size={15} aria-hidden="true" />
        </Button>
      </div>
    </article>
  );
}

function InquiryDialog({
  listing,
  onClose,
}: {
  listing: Listing;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  // review: 매물 확인 → message: 공인중개사에게 메시지 작성 → sent: 보냄(예시)
  const [step, setStep] = useState<'review' | 'message' | 'sent'>('review');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [message, setMessage] = useState(
    `안녕하세요. ${listing.neighborhood} ${listing.address} ${listing.floor} 매물(전용 ${listing.area}㎡, 보증금 ${won(listing.deposit)} / 월세 ${won(listing.rent)})을 보고 연락드려요. 방문해서 공간을 보고 싶은데 가능한 일정을 알려주세요.`
  );
  const phoneOk = /^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(phone.trim());
  const canSend = phoneOk && message.trim().length > 0;
  // 매물을 맡은 공인중개사(예시)
  const broker = {
    office: `${listing.neighborhood} 공인중개사사무소`,
    agent: '대표 공인중개사',
    phone: '02-***-1234',
  };

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-[#10233A]/40 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="inquiry-title"
        className="w-full max-w-[440px] rounded-3xl border border-[#E2E8EE] bg-white p-6 shadow-[0_24px_60px_rgba(16,35,58,0.18)] sm:p-7"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-bold tracking-[0.08em] text-[#2453D6]">
              {step === 'review' ? 'INQUIRY' : 'MESSAGE'}
            </p>
            <h2
              id="inquiry-title"
              className="mt-1.5 text-xl font-extrabold tracking-[-0.03em] text-[#10233A]"
            >
              {step === 'review'
                ? '이 매물에 문의할까요?'
                : step === 'message'
                  ? '공인중개사에게 메시지 보내기'
                  : '메시지를 보냈어요'}
            </h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            aria-label="닫기"
            onClick={onClose}
            className="grid size-9 shrink-0 place-items-center rounded-full text-[#6B7A8A] transition-colors hover:bg-[#F1F5F9] focus-visible:outline-2 focus-visible:outline-[#2453D6]"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        {step === 'review' && (
          <>
            <div className="mt-5 grid grid-cols-2 gap-2">
              {listing.photos.map((photo, index) => (
                <figure
                  key={index}
                  className="relative h-[110px] overflow-hidden rounded-xl bg-[#EEF2F7]"
                >
                  <Image
                    src={photo.src}
                    alt={`공실 ${photo.kind === 'exterior' ? '외관' : '내부'} 예시 사진`}
                    fill
                    sizes="200px"
                    className="object-cover"
                  />
                  <figcaption className="absolute top-1.5 left-1.5 rounded-full bg-[#10233A]/70 px-2 py-0.5 text-[10px] font-semibold text-white">
                    {photo.kind === 'exterior' ? '외관' : '내부'} · 예시 사진
                  </figcaption>
                </figure>
              ))}
            </div>

            <div className="mt-3 rounded-2xl bg-[#F5F8FB] p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="text-13 font-bold text-[#2453D6]">
                  {listing.district} · {listing.neighborhood}
                </p>
                <ExampleBadge>예시 매물</ExampleBadge>
              </div>
              <p className="mt-1 text-base font-extrabold text-[#10233A]">
                {listing.address} · {listing.floor}
              </p>
              <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                {[
                  [
                    '채움 추천',
                    listing.recommended.map(industryName).join(', '),
                  ],
                  ['보증금', won(listing.deposit)],
                  ['월세', won(listing.rent)],
                  [
                    '전용 면적',
                    `${listing.area}㎡ (약 ${pyeong(listing.area)}평)`,
                  ],
                ].map(([label, value]) => (
                  <div key={label} className="contents">
                    <dt className="text-[#6B7A8A]">{label}</dt>
                    <dd className="font-semibold text-[#10233A]">{value}</dd>
                  </div>
                ))}
              </dl>
            </div>

            <p className="mt-4 text-13 leading-relaxed text-[#6B7A8A]">
              이 매물을 맡은 공인중개사에게 메시지로 문의할 수 있어요.
            </p>

            <div className="mt-6 flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                className="flex-1 !py-3"
              >
                닫기
              </Button>
              <Button
                type="button"
                onClick={() => setStep('message')}
                className="flex-[1.4] gap-1.5 !py-3"
              >
                <MessageSquare size={16} aria-hidden="true" />
                메시지 보내기
              </Button>
            </div>
          </>
        )}

        {step === 'message' && (
          <form
            className="mt-5"
            onSubmit={(event) => {
              event.preventDefault();
              if (canSend) setStep('sent');
            }}
          >
            {/* 받는 사람 — 이 매물을 맡은 공인중개사(예시) */}
            <div className="flex items-center gap-3 rounded-2xl bg-[#F5F8FB] p-4">
              <span
                className="grid size-10 shrink-0 place-items-center rounded-full bg-[#EAF0FC] text-sm font-extrabold text-[#2453D6]"
                aria-hidden="true"
              >
                중개
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-bold text-[#10233A]">
                  {broker.office}
                </p>
                <p className="mt-0.5 truncate text-xs text-[#6B7A8A]">
                  {broker.agent} · {broker.phone} · {listing.address}{' '}
                  {listing.floor} 담당
                </p>
              </div>
              <ExampleBadge>예시</ExampleBadge>
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-13 font-semibold text-[#4B5866]">
                  이름{' '}
                  <span className="font-medium text-[#8A97A5]">(선택)</span>
                </span>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="홍길동"
                  className="h-11 w-full rounded-xl border-[1.5px] border-[#D5DEE7] bg-white px-3.5 text-sm text-[#10233A] outline-none placeholder:text-[#9CA3AF] focus:border-[#2453D6]"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-13 font-semibold text-[#4B5866]">
                  연락처
                </span>
                <input
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                  inputMode="tel"
                  placeholder="010-0000-0000"
                  aria-invalid={phone !== '' && !phoneOk}
                  className={`h-11 w-full rounded-xl border-[1.5px] bg-white px-3.5 text-sm text-[#10233A] outline-none placeholder:text-[#9CA3AF] focus:border-[#2453D6] ${
                    phone !== '' && !phoneOk
                      ? 'border-[#D6383B]'
                      : 'border-[#D5DEE7]'
                  }`}
                />
                {phone !== '' && !phoneOk && (
                  <span className="mt-1 block text-xs text-[#D6383B]">
                    연락처를 010-0000-0000 형식으로 적어 주세요.
                  </span>
                )}
              </label>
            </div>

            <label className="mt-3 block">
              <span className="mb-1.5 block text-13 font-semibold text-[#4B5866]">
                메시지
              </span>
              <textarea
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                rows={5}
                className="w-full resize-none rounded-xl border-[1.5px] border-[#D5DEE7] bg-white px-3.5 py-3 text-sm leading-relaxed text-[#10233A] outline-none focus:border-[#2453D6]"
              />
            </label>

            <div className="mt-5 flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setStep('review')}
                className="flex-1 gap-1 !py-3"
              >
                <ArrowLeft size={16} aria-hidden="true" />
                이전
              </Button>
              <Button
                type="submit"
                disabled={!canSend}
                className="flex-[1.4] gap-1.5 !py-3 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <MessageSquare size={16} aria-hidden="true" />
                보내기
              </Button>
            </div>
          </form>
        )}

        {step === 'sent' && (
          <div className="mt-5">
            <div className="flex flex-col items-center rounded-2xl bg-[#F5F8FB] px-5 py-6 text-center">
              <CheckCircle2
                size={36}
                className="text-[#2453D6]"
                aria-hidden="true"
              />
              <p className="mt-3 text-base font-bold text-[#10233A]">
                {broker.office}에 메시지를 보냈어요
              </p>
              <p className="mt-1.5 text-13 leading-relaxed break-keep text-[#6B7A8A]">
                {name.trim() ? `${name.trim()}님, ` : ''}중개사가 {phone.trim()}
                (으)로 연락드릴 거예요.
                <br />
                프로토타입이라 실제로 전송되지는 않아요.
              </p>
            </div>
            <Button
              type="button"
              onClick={onClose}
              className="mt-5 w-full !py-3"
            >
              확인
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}

export default function TenantSearchPrototypePage() {
  const [district, setDistrict] = useState('서울 전체');
  const [areaMin, setAreaMin] = useState('');
  const [areaMax, setAreaMax] = useState('');
  const [wanted, setWanted] = useState<string[]>([]);
  const [showAllIndustries, setShowAllIndustries] = useState(false);
  const [industryQuery, setIndustryQuery] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [inquiry, setInquiry] = useState<Listing | null>(null);
  const itemRefs = useRef(new Map<number, HTMLElement>());
  const closeInquiry = useCallback(() => setInquiry(null), []);
  // 카카오맵을 못 불러오면(키 없음·도메인 미등록) 예시 지도로 바꾼다.
  const [kakaoFailed, setKakaoFailed] = useState(false);
  const markKakaoFailed = useCallback(() => setKakaoFailed(true), []);

  // 최소·최대 중 빈 칸은 제한 없음. 거꾸로 넣으면 작은 값을 최소로 본다.
  const [lo, hi] = useMemo(() => {
    const a = areaMin === '' ? 0 : Number(areaMin);
    const b = areaMax === '' ? Infinity : Number(areaMax);
    return a <= b ? [a, b] : [b, a];
  }, [areaMin, areaMax]);

  // 희망 업종을 고르면, 그 업종이 채움 추천 1~3위에 든 매물만 보여주고
  // 순위가 높은 매물부터 정렬한다.
  const visible = useMemo(() => {
    const bestRank = (l: Listing) =>
      Math.min(
        ...wanted.map((code) => {
          const rank = l.recommended.indexOf(code);
          return rank === -1 ? Infinity : rank;
        })
      );
    const rows = LISTINGS.filter(
      (l) =>
        (district === '서울 전체' || l.district === district) &&
        l.area >= lo &&
        l.area <= hi &&
        (wanted.length === 0 || bestRank(l) !== Infinity)
    );
    return wanted.length === 0
      ? rows
      : [...rows].sort((a, b) => bestRank(a) - bestRank(b));
  }, [district, lo, hi, wanted]);

  // 선택한 매물이 필터에서 빠지면 선택을 비운다.
  const activeId = visible.some((l) => l.id === selectedId) ? selectedId : null;
  const filtered =
    district !== '서울 전체' ||
    areaMin !== '' ||
    areaMax !== '' ||
    wanted.length > 0;

  function toggleIndustry(code: string) {
    setWanted((current) =>
      current.includes(code)
        ? current.filter((c) => c !== code)
        : [...current, code]
    );
  }

  // 자주 찾는 업종 + 전체 목록에서 고른 업종(앞줄에 함께 보여준다)
  const quickCodes = [
    ...POPULAR_INDUSTRIES,
    ...wanted.filter((code) => !POPULAR_INDUSTRIES.includes(code)),
  ];
  const query = industryQuery.trim();

  function selectFromMap(id: number) {
    setSelectedId(id);
    itemRefs.current
      .get(id)
      ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function resetFilters() {
    setDistrict('서울 전체');
    setAreaMin('');
    setAreaMax('');
    setWanted([]);
  }

  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />

      <main className="mx-auto flex w-full max-w-[1280px] flex-col gap-7 px-4 pt-10 pb-20 sm:px-8 sm:pt-12">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <FlowPageTitle
            eyebrow="FIND A SPACE"
            title="내 가게가 될 공간을 찾아보세요"
            description="지역과 면적, 희망 업종으로 서울의 상가 매물을 비교해 보세요."
          />
          <ExampleBadge>예시 매물 · 예시 지도로 만든 화면이에요</ExampleBadge>
        </div>

        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
          {/* 왼쪽: 필터 + 매물 목록 */}
          <div className="flex min-w-0 flex-col gap-5">
            <section
              aria-label="매물 검색 조건"
              className={`${SURFACE} border-[#E2E8EE] p-5 sm:p-6`}
            >
              <div className="flex flex-col gap-4">
                <div>
                  <FilterLabel>서울 지역</FilterLabel>
                  <label className="sr-only" htmlFor="district">
                    서울 지역
                  </label>
                  <select
                    id="district"
                    value={district}
                    onChange={(event) => setDistrict(event.target.value)}
                    className="h-11 w-full max-w-[260px] cursor-pointer rounded-xl border-[1.5px] border-[#D5DEE7] bg-white px-3.5 text-sm font-semibold text-[#10233A] outline-none focus:border-[#2453D6]"
                  >
                    {DISTRICTS.map((d) => (
                      <option key={d}>{d}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <FilterLabel>전용 면적</FilterLabel>
                  <div className="flex flex-wrap items-center gap-2">
                    <AreaInput
                      id="area-min"
                      label="최소 전용 면적"
                      placeholder="최소"
                      value={areaMin}
                      onChange={setAreaMin}
                    />
                    <span className="text-sm text-[#8A97A5]" aria-hidden="true">
                      ~
                    </span>
                    <AreaInput
                      id="area-max"
                      label="최대 전용 면적"
                      placeholder="최대"
                      value={areaMax}
                      onChange={setAreaMax}
                    />
                    <span className="text-xs text-[#8A97A5]">
                      {areaHint(lo, hi)}
                    </span>
                  </div>
                </div>
              </div>

              <div className="mt-5 border-t border-[#EEF2F6] pt-4">
                <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-13 font-semibold text-[#4B5866]">
                    희망 업종
                    {wanted.length > 0 && (
                      <span className="ml-1.5 text-[#2453D6]">
                        {wanted.length}개 선택
                      </span>
                    )}
                  </p>
                </div>
                <div
                  className="flex flex-wrap gap-1.5"
                  role="group"
                  aria-label="희망 업종"
                >
                  {quickCodes.map((code) => (
                    <Chip
                      key={code}
                      active={wanted.includes(code)}
                      onClick={() => toggleIndustry(code)}
                    >
                      {industryName(code)}
                    </Chip>
                  ))}
                  <button
                    type="button"
                    aria-expanded={showAllIndustries}
                    onClick={() => setShowAllIndustries((v) => !v)}
                    className="h-9 rounded-full border border-dashed border-[#B9C7D8] px-3.5 text-13 font-semibold text-[#2453D6] transition-colors hover:border-[#2453D6] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2453D6]"
                  >
                    {showAllIndustries
                      ? '전체 업종 접기'
                      : `+ 전체 업종 ${Object.keys(INDUSTRIES).length}개`}
                  </button>
                </div>

                {showAllIndustries && (
                  <div className="mt-3 rounded-2xl bg-[#F5F8FB] p-4">
                    <label className="flex h-10 items-center rounded-xl border-[1.5px] border-[#D5DEE7] bg-white px-3 focus-within:border-[#2453D6]">
                      <span className="sr-only">업종 이름 검색</span>
                      <input
                        value={industryQuery}
                        onChange={(event) =>
                          setIndustryQuery(event.target.value)
                        }
                        placeholder="업종 이름으로 찾기 (예: 미용, 소매)"
                        className="h-full w-full bg-transparent text-sm text-[#10233A] outline-none placeholder:text-[#9CA3AF]"
                      />
                    </label>
                    <div className="mt-3 flex max-h-[300px] flex-col gap-3.5 overflow-y-auto pr-1">
                      {INDUSTRY_GROUPS.map((group) => {
                        const codes = group.codes.filter((code) =>
                          industryName(code).includes(query)
                        );
                        if (codes.length === 0) return null;
                        return (
                          <div
                            key={group.major}
                            role="group"
                            aria-label={group.major}
                          >
                            <p className="mb-1.5 text-xs font-semibold text-[#6B7A8A]">
                              {group.major}
                            </p>
                            <div className="flex flex-wrap gap-1.5">
                              {codes.map((code) => (
                                <Chip
                                  key={code}
                                  active={wanted.includes(code)}
                                  onClick={() => toggleIndustry(code)}
                                >
                                  {industryName(code)}
                                </Chip>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </section>

            <section aria-label="매물 목록" className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-3 px-1">
                <h2
                  className="text-lg font-extrabold tracking-[-0.02em] text-[#10233A]"
                  aria-live="polite"
                >
                  조건에 맞는 공간{' '}
                  <span className="text-[#2453D6]">{visible.length}</span>곳
                </h2>
                {filtered && (
                  <button
                    type="button"
                    onClick={resetFilters}
                    className="inline-flex items-center gap-1 text-13 font-semibold text-[#4B5866] hover:text-[#2453D6]"
                  >
                    <RotateCcw size={13} aria-hidden="true" /> 조건 초기화
                  </button>
                )}
              </div>

              {visible.map((listing) => (
                <ListingItem
                  key={listing.id}
                  listing={listing}
                  active={listing.id === activeId}
                  onSelect={() => setSelectedId(listing.id)}
                  onInquire={() => setInquiry(listing)}
                  itemRef={(el) => {
                    if (el) itemRefs.current.set(listing.id, el);
                    else itemRefs.current.delete(listing.id);
                  }}
                />
              ))}

              {visible.length === 0 && (
                <div
                  className={`${SURFACE} border-[#E2E8EE] px-6 py-12 text-center`}
                >
                  <p className="font-bold text-[#10233A]">
                    조건에 맞는 매물이 없어요
                  </p>
                  <p className="mt-1.5 text-sm text-[#6B7A8A]">
                    지역이나 면적, 상가 특징 조건을 넓혀 보세요.
                  </p>
                </div>
              )}
            </section>
          </div>

          {/* 오른쪽: 지도 (모바일에서는 목록 아래) */}
          <aside
            aria-label="매물 위치 지도"
            className={`${SURFACE} overflow-hidden border-[#E2E8EE] lg:sticky lg:top-6 lg:flex lg:h-[calc(100vh-48px)] lg:max-h-[760px] lg:flex-col`}
          >
            <div className="flex items-center justify-between gap-3 border-b border-[#EEF2F6] px-5 py-3.5">
              <h2 className="text-15 font-bold text-[#10233A]">
                지도에서 보기
              </h2>
              <p className="text-xs text-[#6B7A8A]">
                핀을 누르면 왼쪽 매물이 표시돼요
              </p>
            </div>
            <div className="lg:flex-1">
              {KAKAO_MAP_KEY && !kakaoFailed ? (
                <KakaoListingMap
                  pins={visible.map((l) => ({
                    id: l.id,
                    lat: l.lat,
                    lng: l.lng,
                    label: `${l.rent}만`,
                    name: `${l.district} ${l.neighborhood} ${l.address}`,
                  }))}
                  selectedId={activeId}
                  onSelect={selectFromMap}
                  onUnavailable={markKakaoFailed}
                >
                  <MapOverlays
                    listings={visible}
                    selected={visible.find((l) => l.id === activeId) ?? null}
                    badge="예시 매물 위치"
                  />
                </KakaoListingMap>
              ) : (
                <SeoulExampleMap
                  listings={visible}
                  selectedId={activeId}
                  onSelect={selectFromMap}
                />
              )}
            </div>
          </aside>
        </div>

        <p className="text-xs leading-relaxed text-[#8A97A5]">
          이 화면은 임차인용 매물 탐색 흐름을 보여주는 프로토타입이에요. 매물
          정보와 지도 위치는 모두 예시이며 실제 매물이 아니에요.
        </p>
      </main>

      {inquiry && <InquiryDialog listing={inquiry} onClose={closeInquiry} />}
    </div>
  );
}
