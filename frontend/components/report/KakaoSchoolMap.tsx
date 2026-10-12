'use client';

import Script from 'next/script';
import { useEffect, useRef, useState } from 'react';
import { mockProperty } from '@/lib/mockData/property';
import SchoolMapPreview from './SchoolMapPreview';

type Overlay = {
  setMap: (map: null) => void;
  setRadius?: (radius: number) => void;
};
type MapInstance = object;
type MapsSDK = {
  Map: new (
    element: HTMLElement,
    options: Record<string, unknown>
  ) => MapInstance;
  LatLng: new (latitude: number, longitude: number) => unknown;
  Circle: new (options: Record<string, unknown>) => Overlay;
  CustomOverlay: new (options: Record<string, unknown>) => Overlay;
  load: (callback: () => void) => void;
};

export default function KakaoSchoolMap({ absolute }: { absolute: boolean }) {
  const keyId = process.env.NEXT_PUBLIC_KAKAO_MAP_APP_KEY;
  const container = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!ready || !container.current) return;
    const sdk = (window as Window & { kakao?: { maps: MapsSDK } }).kakao?.maps;
    if (!sdk) return;
    const element = container.current;
    const center = new sdk.LatLng(
      mockProperty.latitude,
      mockProperty.longitude
    );
    // School coordinates are deliberately fictional; the store stays at the common mock property.
    const school = new sdk.LatLng(
      mockProperty.latitude + (absolute ? 0.00024 : 0.00105),
      mockProperty.longitude - (absolute ? 0.00022 : 0.00095)
    );
    const map = new sdk.Map(element, {
      center: school,
      level: absolute ? 1 : 3,
    });
    const overlays: Overlay[] = [
      ...(!absolute
        ? [
            new sdk.Circle({
              map,
              center: school,
              radius: 200,
              fillColor: '#F3B34A',
              fillOpacity: 0.12,
              strokeColor: '#D6B785',
              strokeWeight: 2,
              strokeStyle: 'solid',
            }),
          ]
        : []),
      new sdk.Circle({
        map,
        center: school,
        radius: 50,
        fillColor: '#C63742',
        fillOpacity: 0.17,
        strokeColor: '#DFA0A5',
        strokeStyle: 'solid',
        strokeWeight: 2,
      }),
      new sdk.CustomOverlay({
        map,
        position: school,
        yAnchor: 1,
        content:
          '<div style="background:white;border:2px solid #C63742;border-radius:10px;padding:10px;color:#C63742;font-size:18px;font-weight:700;white-space:nowrap">🏫 학교</div>',
      }),
      new sdk.CustomOverlay({
        map,
        position: center,
        yAnchor: 1,
        content:
          '<div style="background:#C63742;border-radius:10px;padding:10px;color:white;font-size:16px;font-weight:700;white-space:nowrap">성희 프라자 4층</div>',
      }),
    ];
    // 지도 경계는 실제 반경에 고정합니다.
    const emphasis = (absolute ? [50] : [50, 200]).map((radius) => ({
      radius,
      overlay: new sdk.Circle({
        map,
        center: school,
        radius,
        fillOpacity: 0,
        strokeColor: radius === 50 ? '#A51F2B' : '#965B08',
        strokeWeight: 3,
        strokeOpacity: 0.9,
        strokeStyle: 'solid',
      }),
    }));
    return () => {
      emphasis.forEach(({ overlay }) => overlay.setMap(null));
      overlays.forEach((overlay) => overlay.setMap(null));
      element.replaceChildren();
    };
  }, [ready, absolute]);

  if (!keyId || failed)
    return (
      <div className="relative">
        <SchoolMapPreview absolute={absolute} />
      </div>
    );

  return (
    <div className="relative min-h-[400px] border-r border-gray-200 bg-gray-100">
      <Script
        id="kakao-school-map-sdk"
        src={`https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(keyId)}&autoload=false`}
        onReady={() => {
          const sdk = (window as Window & { kakao?: { maps: MapsSDK } }).kakao
            ?.maps;
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
        aria-label="성희 프라자 주변 카카오맵."
      />
      {absolute && (
        <span className="pointer-events-none absolute top-28 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-full bg-white/95 px-4 py-2 text-base font-bold text-[#C63742]">
          절대보호구역 50m
        </span>
      )}
      {!ready && (
        <p
          role="status"
          className="absolute top-4 left-4 rounded-md bg-white p-3"
        >
          카카오맵를 불러오고 있어요.
        </p>
      )}
      <div className="absolute bottom-10 left-4 rounded-md bg-white/95 px-3 py-1.5 text-[12px]">
        <span className="font-semibold text-[#C63742]">50m · 불가</span>
        {!absolute && (
          <span className="ml-4 font-semibold text-amber-800">
            200m · 확인 필요
          </span>
        )}
      </div>
    </div>
  );
}
