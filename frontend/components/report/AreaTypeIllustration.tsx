/**
 * 유동인구 유형(주거생활형·직장인형·여가상업형 등)에 맞춘 장식용 그림.
 * 라벨 문자열로 장면을 고르고, 알 수 없는 유형은 상점가 장면으로 둔다.
 * 정보는 옆 문장이 모두 전달하므로 스크린리더에서는 숨긴다.
 */

const NAVY = '#10233A';
const BLUE = '#2453D6';
const SKY = '#C9D7F5';
const WASH = '#EAF0FC';
const LINE = '#D5DEE7';

function Ground() {
  return (
    <>
      <ellipse cx="150" cy="186" rx="138" ry="16" fill={WASH} />
      <rect x="20" y="182" width="260" height="2" rx="1" fill={LINE} />
    </>
  );
}

function Tree({ x, y, s = 1 }: { x: number; y: number; s?: number }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <rect x="-2" y="0" width="4" height="16" rx="2" fill="#8EA2CF" />
      <circle cx="0" cy="-6" r="12" fill="#9DB7EC" />
      <circle cx="-6" cy="-1" r="8" fill="#B5C9F1" />
    </g>
  );
}

function Windows({
  x,
  y,
  cols,
  rows,
  w = 8,
  h = 7,
  gx = 6,
  gy = 7,
  lit = [] as number[],
}: {
  x: number;
  y: number;
  cols: number;
  rows: number;
  w?: number;
  h?: number;
  gx?: number;
  gy?: number;
  lit?: number[];
}) {
  const cells = [];
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const i = r * cols + c;
      cells.push(
        <rect
          key={i}
          x={x + c * (w + gx)}
          y={y + r * (h + gy)}
          width={w}
          height={h}
          rx="1.5"
          fill={lit.includes(i) ? '#F2C66B' : '#FFFFFF'}
        />
      );
    }
  }
  return <>{cells}</>;
}

/** 주거생활형 — 아파트 단지, 단독주택, 동네 가게 */
function Residential() {
  return (
    <>
      <Ground />
      {/* 뒤쪽 아파트 */}
      <rect x="150" y="38" width="62" height="146" rx="6" fill={SKY} />
      <rect x="150" y="38" width="62" height="10" rx="5" fill="#B3C5EE" />
      <Windows x={159} y={58} cols={3} rows={8} lit={[4, 13, 20]} />
      {/* 앞쪽 아파트 */}
      <rect x="208" y="70" width="58" height="114" rx="6" fill="#DCE5F8" />
      <Windows x={216} y={86} cols={3} rows={6} w={7} lit={[2, 9]} />
      {/* 단독주택 */}
      <path d="M44 128 L80 100 L116 128 Z" fill={NAVY} />
      <rect
        x="52"
        y="126"
        width="56"
        height="58"
        rx="3"
        fill="#FFFFFF"
        stroke={LINE}
      />
      <rect x="62" y="140" width="14" height="14" rx="2" fill={SKY} />
      <rect x="84" y="150" width="14" height="34" rx="2" fill={BLUE} />
      <rect x="96" y="104" width="8" height="16" fill={NAVY} />
      {/* 동네 가게 */}
      <rect
        x="114"
        y="146"
        width="40"
        height="38"
        rx="3"
        fill="#FFFFFF"
        stroke={LINE}
      />
      <path d="M110 146 h48 l-4 10 h-40 z" fill={BLUE} />
      <path
        d="M118 146 v10 M126 146 v10 M134 146 v10 M142 146 v10 M150 146 v10"
        stroke="#FFFFFF"
        strokeWidth="2"
      />
      <rect x="121" y="162" width="12" height="22" rx="1.5" fill={SKY} />
      <rect x="137" y="162" width="11" height="10" rx="1.5" fill={WASH} />
      <Tree x={28} y={168} />
      <Tree x={276} y={170} s={0.85} />
      {/* 산책하는 사람 */}
      <g transform="translate(178 160)">
        <circle cx="0" cy="0" r="4" fill={NAVY} />
        <rect x="-4" y="5" width="8" height="13" rx="4" fill={BLUE} />
        <rect x="-3" y="17" width="2.5" height="7" rx="1" fill={NAVY} />
        <rect x="0.5" y="17" width="2.5" height="7" rx="1" fill={NAVY} />
      </g>
    </>
  );
}

/** 직장인형 — 오피스 빌딩과 출퇴근길 */
function Office() {
  return (
    <>
      <Ground />
      <rect x="70" y="20" width="70" height="164" rx="6" fill={SKY} />
      <Windows
        x={80}
        y={34}
        cols={4}
        rows={10}
        w={9}
        h={8}
        gx={5}
        gy={6}
        lit={[5, 18, 27]}
      />
      <rect x="146" y="58" width="60" height="126" rx="6" fill="#DCE5F8" />
      <Windows x={155} y={72} cols={3} rows={7} w={10} gx={6} />
      <rect x="212" y="96" width="46" height="88" rx="5" fill={NAVY} />
      <Windows
        x={220}
        y={108}
        cols={2}
        rows={5}
        w={10}
        gx={10}
        lit={[0, 3, 6, 9]}
      />
      <rect x="96" y="160" width="18" height="24" rx="2" fill={BLUE} />
      <Tree x={40} y={168} />
      <Tree x={278} y={170} s={0.8} />
    </>
  );
}

/** 여가상업형·기타 — 상점가 */
function Shops() {
  const shops = [
    { x: 40, color: BLUE },
    { x: 108, color: NAVY },
    { x: 176, color: '#5C78C4' },
  ];
  return (
    <>
      <Ground />
      <rect x="30" y="70" width="230" height="114" rx="6" fill={SKY} />
      <Windows
        x={44}
        y={84}
        cols={9}
        rows={2}
        w={14}
        h={10}
        gx={10}
        gy={10}
        lit={[3, 11]}
      />
      {shops.map((shop) => (
        <g key={shop.x}>
          <rect
            x={shop.x}
            y="136"
            width="60"
            height="48"
            rx="3"
            fill="#FFFFFF"
          />
          <path d={`M${shop.x - 4} 130 h68 l-5 12 h-58 z`} fill={shop.color} />
          <rect
            x={shop.x + 8}
            y="150"
            width="20"
            height="34"
            rx="2"
            fill={WASH}
          />
          <rect
            x={shop.x + 34}
            y="150"
            width="18"
            height="14"
            rx="2"
            fill={WASH}
          />
        </g>
      ))}
      <Tree x={20} y={168} s={0.9} />
      <Tree x={280} y={168} s={0.9} />
    </>
  );
}

export default function AreaTypeIllustration({ label }: { label: string }) {
  const scene = /주거|생활/.test(label) ? (
    <Residential />
  ) : /직장|오피스|업무/.test(label) ? (
    <Office />
  ) : (
    <Shops />
  );
  return (
    <svg
      className="area-type-illustration"
      viewBox="0 0 300 200"
      aria-hidden="true"
      focusable="false"
    >
      {scene}
    </svg>
  );
}
