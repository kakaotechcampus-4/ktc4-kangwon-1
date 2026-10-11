'use client';

import { School, Store } from 'lucide-react';

// 카카오맵 캡처를 예시 배경으로 쓰고, 반경 원은 설명용으로 그린다.
export default function SchoolMapPreview({ absolute }: { absolute: boolean }) {
  // 첨부한 거리 측정 화면의 중심과 반경에 맞춰 지도와 원을 함께 배치합니다.
  const imageScale = absolute ? 200 / 406 : 0.5;
  const radius50 = absolute ? 200 : 50;
  const radius200 = 200;
  const mapImage = absolute
    ? {
        src: '/images/kakao-school-map-50m.png',
        x: 610,
        y: 568,
        width: 1276,
        height: 1232,
      }
    : {
        src: '/images/kakao-school-map-v2.png',
        x: 1044,
        y: 548,
        width: 2012,
        height: 1198,
      };
  const shopX = absolute ? 422 : 437;
  const shopY = absolute ? 324 : 313;
  return (
    <div className="relative min-h-[400px] overflow-hidden border-r border-gray-200 bg-[#EDF0EA]">
      <svg
        viewBox="0 0 620 480"
        preserveAspectRatio="xMidYMid slice"
        className="absolute h-full w-full"
        role="img"
        aria-label={`카카오맵 위례광장로 199 주변 실제 지도 배경. 상가는 ${absolute ? '50m' : '200m'} 안에 표시됩니다.`}
      >
        <image
          href={mapImage.src}
          x={310 - mapImage.x * imageScale}
          y={240 - mapImage.y * imageScale}
          width={mapImage.width * imageScale}
          height={mapImage.height * imageScale}
          preserveAspectRatio="xMidYMid slice"
        />
        {!absolute && (
          <circle
            cx="310"
            cy="240"
            r={radius200}
            fill="#F3B34A"
            fillOpacity=".12"
            stroke="#B58B50"
            strokeWidth="2"
          />
        )}
        <circle
          cx="310"
          cy="240"
          r={radius50}
          fill="#C63742"
          fillOpacity=".17"
          stroke="#B95A64"
          strokeWidth="2"
        />
        <circle
          key={absolute ? 'absolute-radius' : 'relative-radius'}
          className="school-radius-emphasis"
          cx="310"
          cy="240"
          r={radius50}
          fill="none"
          stroke="#A51F2B"
          strokeWidth="3"
          pathLength="100"
          strokeDasharray="30 70"
          strokeLinecap="round"
          opacity=".4"
        />
        {!absolute && (
          <circle
            className="school-radius-emphasis school-radius-emphasis-outer"
            cx="310"
            cy="240"
            r={radius200}
            fill="none"
            stroke="#965B08"
            strokeWidth="3"
            pathLength="100"
            strokeDasharray="30 70"
            strokeLinecap="round"
            opacity=".4"
          />
        )}
        <g fontSize="14" fontWeight="600" fontFamily="inherit">
          {!absolute && (
            <>
              <rect
                x="224"
                y={240 - radius200 + 10}
                width="172"
                height="30"
                rx="15"
                fill="white"
              />
              <text
                x="310"
                y={240 - radius200 + 30}
                textAnchor="middle"
                fill="#925B08"
              >
                상대보호구역 200m
              </text>
            </>
          )}
          <rect
            x="230"
            y={absolute ? 118 : 240 - radius50 - 34}
            width="160"
            height="30"
            rx="15"
            fill="white"
          />
          <text
            x="310"
            y={absolute ? 138 : 240 - radius50 - 14}
            textAnchor="middle"
            fill="#C63742"
          >
            절대보호구역 50m
          </text>
        </g>
        <foreignObject x="273" y="207" width="74" height="65">
          <div className="rounded-lg border border-red-200 bg-white p-2 text-center">
            <School
              size={28}
              color="#C63742"
              className="mx-auto"
              aria-hidden="true"
            />
            <span className="text-xs font-bold text-gray-800">학교</span>
          </div>
        </foreignObject>
        <circle
          cx={shopX}
          cy={shopY}
          r="7"
          fill="#C63742"
          stroke="white"
          strokeWidth="3"
        />
        <path
          d={`M${shopX} ${shopY}L${shopX + 28} ${shopY + 43}`}
          stroke="#B95A64"
          strokeWidth="2"
        />
        <foreignObject x={shopX + 15} y={shopY + 40} width="108" height="64">
          <div className="rounded-lg bg-[#C63742] p-2 text-center text-white">
            <Store size={22} className="mx-auto" aria-hidden="true" />
            <span className="text-xs font-bold">상가</span>
          </div>
        </foreignObject>
      </svg>
      <style jsx>{`
        .school-radius-emphasis {
          transform-box: view-box;
          transform-origin: 310px 240px;
          animation: school-radius-orbit 3s linear infinite;
        }
        .school-radius-emphasis-outer {
          animation-direction: reverse;
        }
        @keyframes school-radius-orbit {
          from {
            transform: rotate(-90deg);
          }
          to {
            transform: rotate(270deg);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .school-radius-emphasis {
            animation: none;
          }
        }
      `}</style>
      <div className="absolute bottom-8 left-4 flex gap-3 rounded-md bg-white/95 px-3 py-1.5 text-[12px] font-medium text-gray-700">
        <span>
          <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-[#C63742]" />
          50m · 불가
        </span>
        {!absolute && (
          <span>
            <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-[#BB7A15]" />
            200m · 확인 필요
          </span>
        )}
      </div>
      <a
        href="https://map.kakao.com/"
        target="_blank"
        rel="noopener noreferrer"
        className="absolute right-0 bottom-0 bg-white/95 px-2 py-1 text-xs text-gray-700 underline"
      >
        카카오맵
      </a>
    </div>
  );
}
