'use client';

import Script from 'next/script';
import { useEffect, useRef, useState, type ReactNode } from 'react';

/*
 * 실제 카카오맵 위에 매물 가격 핀을 띄운다(리포트의 PropertyMap과 같은 SDK·키 사용).
 * NEXT_PUBLIC_KAKAO_MAP_APP_KEY가 없거나 SDK를 불러오지 못하면 onUnavailable을 불러
 * 페이지가 예시 지도로 바꿔 보여주게 한다.
 * 카카오 개발자 콘솔의 [플랫폼 > Web]에 http://localhost:3000 이 등록돼 있어야 지도가 뜬다.
 */

export type ListingPin = {
  id: number;
  lat: number;
  lng: number;
  label: string; // 핀에 적을 글자(예: 230만)
  name: string; // 화면 낭독기용 이름
};

type LatLng = object;
type KakaoMap = {
  setBounds: (bounds: object, ...padding: number[]) => void;
  panTo: (latlng: LatLng) => void;
  relayout: () => void;
};
type Overlay = {
  setMap: (map: KakaoMap | null) => void;
  setZIndex: (z: number) => void;
};
type MapsSDK = {
  Map: new (element: HTMLElement, options: Record<string, unknown>) => KakaoMap;
  LatLng: new (latitude: number, longitude: number) => LatLng;
  LatLngBounds: new () => { extend: (latlng: LatLng) => void };
  CustomOverlay: new (options: Record<string, unknown>) => Overlay;
  load: (callback: () => void) => void;
};

function kakaoMaps(): MapsSDK | undefined {
  return (window as Window & { kakao?: { maps: MapsSDK } }).kakao?.maps;
}

export const KAKAO_MAP_KEY = process.env.NEXT_PUBLIC_KAKAO_MAP_APP_KEY;

export default function KakaoListingMap({
  pins,
  selectedId,
  onSelect,
  onUnavailable,
  children,
}: {
  pins: ListingPin[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onUnavailable: () => void;
  children?: ReactNode;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<KakaoMap | null>(null);
  const [ready, setReady] = useState(false);
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  // SDK가 5초 안에 준비되지 않으면(키 오류·도메인 미등록 등) 예시 지도로 바꾼다.
  useEffect(() => {
    if (ready) return;
    const timer = window.setTimeout(onUnavailable, 5000);
    return () => window.clearTimeout(timer);
  }, [ready, onUnavailable]);

  // 지도 만들기(한 번)
  useEffect(() => {
    if (!ready || !container.current || mapRef.current) return;
    const sdk = kakaoMaps();
    if (!sdk) return;
    mapRef.current = new sdk.Map(container.current, {
      center: new sdk.LatLng(37.5446, 127.0),
      level: 8,
    });
  }, [ready]);

  // 핀 그리기 — 목록·선택이 바뀔 때마다 다시 그린다.
  const pinKey = pins.map((p) => p.id).join(',');
  useEffect(() => {
    const sdk = kakaoMaps();
    const map = mapRef.current;
    if (!ready || !sdk || !map) return;
    const overlays = pins.map((pin) => {
      const active = pin.id === selectedId;
      const el = document.createElement('button');
      el.type = 'button';
      el.setAttribute('aria-label', `${pin.name} 매물 선택`);
      el.setAttribute('aria-pressed', String(active));
      el.style.cssText =
        'display:flex;flex-direction:column;align-items:center;border:0;background:none;padding:0;cursor:pointer;font-family:inherit;';
      const bg = active ? '#2453D6' : '#10233A';
      el.innerHTML = `<span style="background:${bg};color:#fff;border-radius:999px;padding:4px 10px;font-size:12px;font-weight:700;white-space:nowrap;box-shadow:0 6px 14px rgba(16,35,58,.18)${
        active ? ',0 0 0 4px rgba(36,83,214,.2)' : ''
      };${active ? 'transform:scale(1.1);' : ''}">${pin.label}</span><span style="width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:6px solid ${bg}"></span>`;
      el.addEventListener('click', () => onSelectRef.current(pin.id));
      const overlay = new sdk.CustomOverlay({
        position: new sdk.LatLng(pin.lat, pin.lng),
        content: el,
        yAnchor: 1,
        clickable: true,
      });
      overlay.setZIndex(active ? 3 : 1);
      overlay.setMap(map);
      return overlay;
    });
    return () => overlays.forEach((o) => o.setMap(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, pinKey, selectedId]);

  // 걸러진 매물이 모두 보이게 범위를 맞춘다.
  useEffect(() => {
    const sdk = kakaoMaps();
    const map = mapRef.current;
    if (!ready || !sdk || !map || pins.length === 0) return;
    map.relayout();
    const bounds = new sdk.LatLngBounds();
    pins.forEach((p) => bounds.extend(new sdk.LatLng(p.lat, p.lng)));
    map.setBounds(bounds, 70, 40, 90, 40);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, pinKey]);

  // 선택한 매물로 지도를 옮긴다.
  useEffect(() => {
    const sdk = kakaoMaps();
    const map = mapRef.current;
    const pin = pins.find((p) => p.id === selectedId);
    if (!ready || !sdk || !map || !pin) return;
    map.panTo(new sdk.LatLng(pin.lat, pin.lng));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, selectedId]);

  return (
    <div className="relative h-[380px] overflow-hidden bg-[#EEF3F8] sm:h-[460px] lg:h-full lg:min-h-[560px]">
      {KAKAO_MAP_KEY && (
        <Script
          id="kakao-tenant-map-sdk"
          src={`https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(KAKAO_MAP_KEY)}&autoload=false`}
          strategy="afterInteractive"
          onReady={() => kakaoMaps()?.load(() => setReady(true))}
          onError={onUnavailable}
        />
      )}
      <div ref={container} className="absolute inset-0" />
      {children}
    </div>
  );
}
