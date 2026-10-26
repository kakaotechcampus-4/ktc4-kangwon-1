'use client';

import Script from 'next/script';
import { useEffect, useRef, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { colors } from '@/styles/tokens';

/**
 * 분석 대상 상가의 위치 지도. 상가 내부 사진 대신 주소 위치를 보여준다.
 *
 * NEXT_PUBLIC_KAKAO_MAP_APP_KEY가 있으면 카카오맵 SDK(services 포함)로 주소를
 * 좌표로 바꿔 지도를 그리고, 키가 없거나 주소를 찾지 못하면 간단한 지도 그림과
 * "카카오맵에서 보기" 링크로 대신한다.
 */
type LatLng = object;
type Overlay = { setMap: (map: null) => void };
type MapsSDK = {
  Map: new (element: HTMLElement, options: Record<string, unknown>) => object;
  LatLng: new (latitude: number, longitude: number) => LatLng;
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

export default function PropertyMap({ address }: { address: string }) {
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
    let overlay: Overlay | undefined;
    let cancelled = false;
    new sdk.services.Geocoder().addressSearch(address, (result, status) => {
      if (cancelled) return;
      if (status !== sdk.services.Status.OK || !result[0]) {
        setFailed(true);
        return;
      }
      const center = new sdk.LatLng(Number(result[0].y), Number(result[0].x));
      const map = new sdk.Map(element, { center, level: 3 });
      overlay = new sdk.CustomOverlay({
        map,
        position: center,
        yAnchor: 1,
        content: `<div style="display:flex;flex-direction:column;align-items:center;gap:6px"><div style="background:${colors.brand.dark};color:#fff;border-radius:999px;padding:8px 14px;font-size:14px;font-weight:700;white-space:nowrap">분석 대상 상가</div><div style="width:18px;height:18px;border-radius:50%;background:#F2B84B;border:4px solid #fff;box-shadow:0 4px 10px rgba(16,35,58,.3)"></div></div>`,
      });
    });
    return () => {
      cancelled = true;
      overlay?.setMap(null);
      element.replaceChildren();
    };
  }, [ready, address]);

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
            className="absolute inset-0"
            aria-label={`${address} 주변 지도`}
          />
          {!ready && (
            <p
              role="status"
              className="absolute top-4 left-4 rounded-md bg-white px-3 py-2 text-sm"
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
