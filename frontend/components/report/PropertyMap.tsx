'use client';

import Script from 'next/script';
import { useEffect, useRef, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { colors } from '@/styles/tokens';
import { ANALYSIS_RADIUS_M } from '@/lib/api/resultStore';

/**
 * 분석 대상 상가의 위치 지도. 상가 내부 사진 대신 주소 위치와 분석 반경을 보여준다.
 *
 * NEXT_PUBLIC_KAKAO_MAP_APP_KEY가 있으면 카카오맵 SDK로 지도를 그리고 분석 반경을
 * 원으로 덮는다. 리포트의 모든 숫자가 이 원 안을 본 결과라는 것을 글이 아니라 그림으로
 * 보여 주는 자리다. 중심은 분석이 실제로 쓴 좌표(서버 응답의 site)를 그대로 받고,
 * 좌표가 없을 때만 주소를 좌표로 바꾼다 — 분석 기준점과 지도 중심이 어긋나면 안 된다.
 * 키가 없거나 주소를 찾지 못하면 간단한 지도 그림과 "카카오맵에서 보기" 링크로 대신한다.
 */
type LatLng = object;
type Bounds = object;
type Overlay = { setMap: (map: MapInstance | null) => void };
type Circle = Overlay & { getBounds: () => Bounds };
type MapInstance = {
  relayout: () => void;
  setBounds: (
    bounds: Bounds,
    paddingTop?: number,
    paddingRight?: number,
    paddingBottom?: number,
    paddingLeft?: number
  ) => void;
};
type MapsSDK = {
  Map: new (
    element: HTMLElement,
    options: Record<string, unknown>
  ) => MapInstance;
  LatLng: new (latitude: number, longitude: number) => LatLng;
  Circle: new (options: Record<string, unknown>) => Circle;
  CustomOverlay: new (options: Record<string, unknown>) => Overlay;
  load: (callback: () => void) => void;
  services: {
    Status: { OK: string };
    Geocoder: new () => {
      addressSearch: (
        address: string,
        callback: (result: { x: string; y: string }[], status: string) => void
      ) => void;
    };
  };
};

function kakaoMaps(): MapsSDK | undefined {
  return (window as Window & { kakao?: { maps: MapsSDK } }).kakao?.maps;
}

export default function PropertyMap({
  address,
  latitude,
  longitude,
  radiusM = ANALYSIS_RADIUS_M,
}: {
  address: string;
  latitude?: number | null;
  longitude?: number | null;
  radiusM?: number;
}) {
  const keyId = process.env.NEXT_PUBLIC_KAKAO_MAP_APP_KEY;
  const container = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const kakaoLink = `https://map.kakao.com/?q=${encodeURIComponent(address)}`;

  useEffect(() => {
    if (!ready || !container.current) return;
    const sdk = kakaoMaps();
    if (!sdk) return;
    const element = container.current;
    const overlays: Overlay[] = [];
    let observer: ResizeObserver | undefined;
    let cancelled = false;

    const draw = (centerLatitude: number, centerLongitude: number) => {
      const center = new sdk.LatLng(centerLatitude, centerLongitude);
      const map = new sdk.Map(element, { center, level: 5 });
      const circle = new sdk.Circle({
        center,
        radius: radiusM,
        fillColor: colors.brand.primary,
        fillOpacity: 0.08,
        strokeColor: colors.brand.primary,
        strokeWeight: 2,
        strokeOpacity: 0.65,
        strokeStyle: 'solid',
      });
      // 원은 생성자 options의 map을 보지 않는다. setMap으로 직접 올린다.
      circle.setMap(map);
      // 지도를 만들 때 칸의 크기가 아직 0이면 도형 레이어가 화면 밖 크기로 잡힌다.
      // 타일과 마커는 다시 그려지지만 원은 그대로 안 보인다. 칸 크기가 정해질 때마다
      // 지도에 다시 재어 보게 하고, 반경 원이 다 들어오도록 범위를 맞춘다.
      // 가장자리가 잘리면 분석 범위를 오해한다.
      // 칸 크기가 바뀌면(인쇄·창 크기·늦게 도착한 CSS) 지도에 다시 재어 보게 한다.
      observer?.disconnect();
      observer = new ResizeObserver(() => {
        map.relayout();
        map.setBounds(circle.getBounds(), 8, 8, 8, 8);
      });
      observer.observe(element);
      overlays.push(
        circle,
        new sdk.CustomOverlay({
          map,
          position: center,
          yAnchor: 1,
          content: `<div style="display:flex;flex-direction:column;align-items:center;gap:6px"><div style="background:${colors.brand.dark};color:#fff;border-radius:999px;padding:8px 14px;font-size:14px;font-weight:700;white-space:nowrap">분석 대상 상가</div><div style="width:18px;height:18px;border-radius:50%;background:#F2B84B;border:4px solid #fff;box-shadow:0 4px 10px rgba(16,35,58,.3)"></div></div>`,
        })
      );
    };

    // 칸 크기가 0인 채로 지도를 만들면 반경에 맞춘 확대 수준을 계산하지 못한다.
    // 크기가 정해진 뒤에 그린다.
    const drawWhenSized = (centerLatitude: number, centerLongitude: number) => {
      if (cancelled) return;
      if (element.clientWidth > 0 && element.clientHeight > 0) {
        draw(centerLatitude, centerLongitude);
        return;
      }
      observer = new ResizeObserver(() => {
        if (cancelled || !element.clientWidth || !element.clientHeight) return;
        draw(centerLatitude, centerLongitude);
      });
      observer.observe(element);
    };

    if (typeof latitude === 'number' && typeof longitude === 'number') {
      drawWhenSized(latitude, longitude);
    } else {
      new sdk.services.Geocoder().addressSearch(address, (result, status) => {
        if (cancelled) return;
        if (status !== sdk.services.Status.OK || !result[0]) {
          setFailed(true);
          return;
        }
        drawWhenSized(Number(result[0].y), Number(result[0].x));
      });
    }
    return () => {
      cancelled = true;
      observer?.disconnect();
      overlays.forEach((overlay) => overlay.setMap(null));
      element.replaceChildren();
    };
  }, [ready, address, latitude, longitude, radiusM]);

  const fallback = !keyId || failed;

  return (
    <figure className="property-preview-photo property-map">
      {fallback ? (
        <MapIllustration />
      ) : (
        <>
          <Script
            id="kakao-property-map-sdk"
            src={`https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(keyId)}&libraries=services&autoload=false`}
            onReady={() => {
              const sdk = kakaoMaps();
              if (!sdk) {
                setFailed(true);
                return;
              }
              sdk.load(() => setReady(true));
            }}
            onError={() => setFailed(true)}
          />
          <div
            ref={container}
            className="property-map-canvas absolute inset-0"
            aria-label={`${address} 주변 지도. 원으로 표시한 범위는 분석 반경 ${radiusM}m입니다.`}
          />
          {/* 반경은 오른쪽 "분석 범위"에 이미 적혀 있어 지도에는 겹쳐 쓰지 않는다. */}
          {!ready && (
            <p
              role="status"
              className="pointer-events-none absolute top-4 left-4 z-10 rounded-md bg-white/95 px-3 py-2 text-sm font-semibold"
            >
              지도를 불러오고 있어요.
            </p>
          )}
        </>
      )}
      <figcaption className="property-map-caption">
        {/* 주소는 바로 위 제목에 있으니 지도에는 외부 링크만 둔다. */}
        <a href={kakaoLink} target="_blank" rel="noreferrer">
          카카오맵에서 보기 <ExternalLink size={14} aria-hidden="true" />
        </a>
      </figcaption>
    </figure>
  );
}

/** 지도 키가 없을 때 보여주는 간단한 동네 지도 그림(실제 위치가 아님) */
export function MapIllustration() {
  return (
    <svg
      viewBox="0 0 400 380"
      preserveAspectRatio="xMidYMid slice"
      className="absolute inset-0 h-full w-full"
      role="img"
      aria-label="분석 대상 상가 위치를 나타내는 지도 그림"
    >
      <rect width="400" height="380" fill="#EEF2F7" />
      <g fill="#FFFFFF">
        <rect x="-10" y="150" width="420" height="34" />
        <rect x="170" y="-10" width="30" height="400" />
        <rect x="-10" y="290" width="420" height="16" />
        <rect x="320" y="-10" width="16" height="400" />
        <rect x="60" y="-10" width="14" height="160" />
      </g>
      <g fill="#DCE3EE">
        <rect x="16" y="20" width="36" height="52" rx="4" />
        <rect x="16" y="84" width="36" height="52" rx="4" />
        <rect x="84" y="20" width="74" height="54" rx="4" />
        <rect x="84" y="86" width="74" height="50" rx="4" />
        <rect x="212" y="20" width="96" height="60" rx="4" />
        <rect x="212" y="92" width="96" height="44" rx="4" />
        <rect x="348" y="20" width="44" height="116" rx="4" />
        <rect x="16" y="198" width="140" height="80" rx="4" />
        <rect x="212" y="198" width="96" height="80" rx="4" />
        <rect x="348" y="198" width="44" height="80" rx="4" />
        <rect x="16" y="318" width="140" height="54" rx="4" />
        <rect x="212" y="318" width="180" height="54" rx="4" />
      </g>
      <rect x="212" y="198" width="96" height="80" rx="4" fill="#C9D6F4" />
      <circle cx="260" cy="238" r="46" fill="#2453D6" opacity="0.1" />
      <path
        d="M260 252c-12-15-20-24-20-35a20 20 0 0 1 40 0c0 11-8 20-20 35z"
        fill="#2453D6"
      />
      <circle cx="260" cy="217" r="7" fill="#FFFFFF" />
    </svg>
  );
}
