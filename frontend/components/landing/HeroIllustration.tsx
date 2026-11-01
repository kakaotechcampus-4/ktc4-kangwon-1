/**
 * 랜딩 히어로 배경의 아이소메트릭 건물 블록 그림.
 * 앞줄 왼쪽 칸이 지붕과 안쪽 벽만 남은 "빈 상가"이고, 나머지는 채워진 건물이다.
 * 정적인 장식 그림이라 좌표는 디자인 캔버스에서 그대로 옮겼다.
 */
export default function HeroIllustration({
  className = '',
}: {
  className?: string;
}) {
  return (
    <svg
      viewBox="40 100 1440 1000"
      preserveAspectRatio="xMidYMax meet"
      className={className}
      role="img"
      aria-label="연한 하늘색 지붕을 얹은 흰 건물 블록 사이에 빈 상가 한 칸이 있는 아이소메트릭 그림"
    >
      <defs>
        <linearGradient id="chum-wl" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#E3E9F0" />
        </linearGradient>
        <linearGradient id="chum-wr" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#D9E1EA" />
          <stop offset="1" stopColor="#B9C6D3" />
        </linearGradient>
        <linearGradient id="chum-rt" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#D3E0EF" />
          <stop offset="1" stopColor="#B3C6DE" />
        </linearGradient>
        <linearGradient id="chum-rl" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#A8BCD6" />
          <stop offset="1" stopColor="#8FA6C4" />
        </linearGradient>
        <linearGradient id="chum-rr" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#BCCDE2" />
          <stop offset="1" stopColor="#A0B5D0" />
        </linearGradient>
        <linearGradient id="chum-gl" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#E9F1F8" />
          <stop offset="1" stopColor="#8FA7BF" />
        </linearGradient>
        <linearGradient id="chum-gw" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFF1CF" />
          <stop offset="1" stopColor="#F2B84B" />
        </linearGradient>
        <linearGradient id="chum-st" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#F7F9FB" />
          <stop offset="1" stopColor="#DCE3EA" />
        </linearGradient>
        <linearGradient id="chum-sl" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#C2CFDD" />
          <stop offset="1" stopColor="#A3B4C7" />
        </linearGradient>
        <radialGradient id="chum-vf" cx="0.5" cy="0.5" r="0.6">
          <stop offset="0" stopColor="#FFE3A3" />
          <stop offset="0.55" stopColor="#F6C873" />
          <stop offset="1" stopColor="#C99A4A" />
        </radialGradient>
        <radialGradient id="chum-glow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#FFD27A" stopOpacity="0.9" />
          <stop offset="1" stopColor="#FFD27A" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="chum-bgl" cx="0.5" cy="0.35" r="0.6">
          <stop offset="0" stopColor="#FFFFFF" stopOpacity="0.9" />
          <stop offset="1" stopColor="#FFFFFF" stopOpacity="0" />
        </radialGradient>
        <filter id="chum-blur18" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="18" />
        </filter>
        <filter id="chum-blur6" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
        <filter id="chum-card" x="-20%" y="-30%" width="140%" height="180%">
          <feDropShadow
            dx="0"
            dy="10"
            stdDeviation="12"
            floodColor="#0B1A2A"
            floodOpacity="0.18"
          />
        </filter>
      </defs>
      <ellipse cx="760" cy="520" rx="700" ry="420" fill="url(#chum-bgl)" />
      <ellipse
        cx="800"
        cy="1050"
        rx="560"
        ry="60"
        fill="#0B1A2A"
        opacity="0.22"
        filter="url(#chum-blur18)"
      />
      <polygon
        points="269.7,736.0 858.6,1076.0 858.6,1030.0 269.7,690.0"
        fill="url(#chum-sl)"
      />
      <polygon
        points="1308.9,816.0 858.6,1076.0 858.6,1030.0 1308.9,770.0"
        fill="url(#chum-rl)"
      />
      <polygon
        points="269.7,694.0 858.6,1034.0 858.6,1030.0 269.7,690.0"
        fill="#FFFFFF"
        opacity="0.25"
      />
      <polygon
        points="720.0,430.0 1308.9,770.0 858.6,1030.0 269.7,690.0"
        fill="url(#chum-st)"
      />
      <polygon
        points="772.0,460.0 773.3,460.8 322.9,720.8 321.6,720.0"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="823.9,490.0 825.2,490.8 374.9,750.8 373.6,750.0"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="875.9,520.0 877.2,520.8 426.9,780.8 425.6,780.0"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="927.8,550.0 929.1,550.8 478.8,810.8 477.5,810.0"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="979.8,580.0 981.1,580.8 530.8,840.8 529.5,840.0"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="1031.8,610.0 1033.1,610.8 582.7,870.8 581.4,870.0"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="1083.7,640.0 1085.0,640.8 634.7,900.8 633.4,900.0"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="1135.7,670.0 1137.0,670.8 686.7,930.8 685.4,930.0"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="1187.6,700.0 1188.9,700.8 738.6,960.8 737.3,960.0"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="1239.6,730.0 1240.9,730.8 790.6,990.8 789.3,990.0"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="1291.6,760.0 1292.9,760.8 842.5,1020.8 841.2,1020.0"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="668.0,460.0 1256.9,800.0 1255.6,800.8 666.7,460.8"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="616.1,490.0 1205.0,830.0 1203.7,830.8 614.8,490.8"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="564.1,520.0 1153.0,860.0 1151.7,860.8 562.8,520.8"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="512.2,550.0 1101.0,890.0 1099.7,890.8 510.9,550.8"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="460.2,580.0 1049.1,920.0 1047.8,920.8 458.9,580.8"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="408.2,610.0 997.1,950.0 995.8,950.8 406.9,610.8"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="356.3,640.0 945.2,980.0 943.9,980.8 355.0,640.8"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <polygon
        points="304.3,670.0 893.2,1010.0 891.9,1010.8 303.0,670.8"
        fill="#C9D3DD"
        opacity="0.45"
      />
      <g opacity="0.22" filter="url(#chum-blur18)">
        <polygon
          points="720.0,470.0 984.6,622.8 798.7,730.1 534.1,577.3"
          fill="#1B2B3C"
        />
        <polygon
          points="936.5,595.0 1153.4,720.2 985.3,817.3 768.4,692.1"
          fill="#1B2B3C"
        />
        <polygon
          points="1109.7,695.0 1330.1,822.2 1141.0,931.4 920.6,804.2"
          fill="#1B2B3C"
        />
        <polygon
          points="728.7,715.0 897.1,812.2 717.5,915.9 549.1,818.7"
          fill="#1B2B3C"
        />
        <polygon
          points="901.9,815.0 1098.0,928.2 907.5,1038.2 711.4,925.0"
          fill="#1B2B3C"
        />
        <polygon
          points="512.2,590.0 701.4,699.2 518.2,805.0 329.0,695.8"
          fill="#1B2B3C"
        />
      </g>
      <polygon
        points="564.1,560.0 728.7,655.0 728.7,325.0 564.1,230.0"
        fill="url(#chum-wl)"
      />
      <polygon
        points="884.5,565.0 728.7,655.0 728.7,325.0 884.5,235.0"
        fill="url(#chum-wr)"
      />
      <polygon
        points="576.2,533.0 595.3,544.0 595.3,514.0 576.2,503.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="576.2,475.0 595.3,486.0 595.3,456.0 576.2,445.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="576.2,475.0 595.3,486.0 595.3,456.0 576.2,445.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="576.2,417.0 595.3,428.0 595.3,398.0 576.2,387.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="576.2,359.0 595.3,370.0 595.3,340.0 576.2,329.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="576.2,359.0 595.3,370.0 595.3,340.0 576.2,329.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="576.2,301.0 595.3,312.0 595.3,282.0 576.2,271.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="617.8,557.0 636.9,568.0 636.9,538.0 617.8,527.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="617.8,499.0 636.9,510.0 636.9,480.0 617.8,469.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="617.8,499.0 636.9,510.0 636.9,480.0 617.8,469.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="617.8,441.0 636.9,452.0 636.9,422.0 617.8,411.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="617.8,383.0 636.9,394.0 636.9,364.0 617.8,353.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="617.8,383.0 636.9,394.0 636.9,364.0 617.8,353.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="617.8,325.0 636.9,336.0 636.9,306.0 617.8,295.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="659.4,581.0 678.4,592.0 678.4,562.0 659.4,551.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="659.4,581.0 678.4,592.0 678.4,562.0 659.4,551.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="659.4,523.0 678.4,534.0 678.4,504.0 659.4,493.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="659.4,523.0 678.4,534.0 678.4,504.0 659.4,493.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="659.4,465.0 678.4,476.0 678.4,446.0 659.4,435.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="659.4,407.0 678.4,418.0 678.4,388.0 659.4,377.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="659.4,349.0 678.4,360.0 678.4,330.0 659.4,319.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="659.4,349.0 678.4,360.0 678.4,330.0 659.4,319.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="872.4,538.0 853.4,549.0 853.4,519.0 872.4,508.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="872.4,480.0 853.4,491.0 853.4,461.0 872.4,450.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="872.4,422.0 853.4,433.0 853.4,403.0 872.4,392.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="872.4,364.0 853.4,375.0 853.4,345.0 872.4,334.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="872.4,306.0 853.4,317.0 853.4,287.0 872.4,276.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="830.8,562.0 811.8,573.0 811.8,543.0 830.8,532.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="830.8,504.0 811.8,515.0 811.8,485.0 830.8,474.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="830.8,504.0 811.8,515.0 811.8,485.0 830.8,474.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="830.8,446.0 811.8,457.0 811.8,427.0 830.8,416.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="830.8,388.0 811.8,399.0 811.8,369.0 830.8,358.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="830.8,330.0 811.8,341.0 811.8,311.0 830.8,300.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="830.8,330.0 811.8,341.0 811.8,311.0 830.8,300.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="789.3,586.0 770.2,597.0 770.2,567.0 789.3,556.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="789.3,586.0 770.2,597.0 770.2,567.0 789.3,556.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="789.3,528.0 770.2,539.0 770.2,509.0 789.3,498.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="789.3,470.0 770.2,481.0 770.2,451.0 789.3,440.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="789.3,412.0 770.2,423.0 770.2,393.0 789.3,382.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="789.3,354.0 770.2,365.0 770.2,335.0 789.3,324.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="553.7,230.0 728.7,331.0 728.7,313.0 553.7,212.0"
        fill="url(#chum-rl)"
      />
      <polygon
        points="894.9,235.0 728.7,331.0 728.7,313.0 894.9,217.0"
        fill="url(#chum-rr)"
      />
      <polygon
        points="720.0,116.0 894.9,217.0 728.7,313.0 553.7,212.0"
        fill="url(#chum-rt)"
      />
      <polyline
        points="553.7,212.0 728.7,313.0 894.9,217.0"
        fill="none"
        stroke="#FFFFFF"
        strokeOpacity="0.35"
        strokeWidth="1.5"
      />
      <polygon
        points="512.2,590.0 668.0,680.0 494.8,780.0 339.0,690.0"
        fill="url(#chum-st)"
      />
      <polygon
        points="512.2,590.0 339.0,690.0 339.0,580.0 512.2,480.0"
        fill="url(#chum-wl)"
      />
      <polygon
        points="512.2,590.0 668.0,680.0 668.0,570.0 512.2,480.0"
        fill="url(#chum-wr)"
      />
      <polygon
        points="512.2,456.0 678.4,552.0 661.1,562.0 512.2,476.0 345.9,572.0 328.6,562.0"
        fill="url(#chum-rt)"
      />
      <polygon
        points="512.2,494.0 661.1,580.0 661.1,562.0 512.2,476.0"
        fill="url(#chum-rr)"
      />
      <polygon
        points="512.2,494.0 345.9,590.0 345.9,572.0 512.2,476.0"
        fill="url(#chum-rl)"
      />
      <polygon
        points="328.6,580.0 345.9,590.0 345.9,572.0 328.6,562.0"
        fill="url(#chum-rl)"
      />
      <polygon
        points="678.4,570.0 661.1,580.0 661.1,562.0 678.4,552.0"
        fill="url(#chum-rr)"
      />
      <polygon
        points="789.3,680.0 936.5,765.0 936.5,535.0 789.3,450.0"
        fill="url(#chum-wl)"
      />
      <polygon
        points="1083.7,680.0 936.5,765.0 936.5,535.0 1083.7,450.0"
        fill="url(#chum-wr)"
      />
      <polygon
        points="801.4,653.0 820.5,664.0 820.5,634.0 801.4,623.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="801.4,595.0 820.5,606.0 820.5,576.0 801.4,565.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="801.4,537.0 820.5,548.0 820.5,518.0 801.4,507.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="843.0,677.0 862.0,688.0 862.0,658.0 843.0,647.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="843.0,677.0 862.0,688.0 862.0,658.0 843.0,647.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="843.0,619.0 862.0,630.0 862.0,600.0 843.0,589.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="843.0,619.0 862.0,630.0 862.0,600.0 843.0,589.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="843.0,561.0 862.0,572.0 862.0,542.0 843.0,531.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="884.5,701.0 903.6,712.0 903.6,682.0 884.5,671.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="884.5,643.0 903.6,654.0 903.6,624.0 884.5,613.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="884.5,585.0 903.6,596.0 903.6,566.0 884.5,555.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1071.6,653.0 1052.5,664.0 1052.5,634.0 1071.6,623.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1071.6,595.0 1052.5,606.0 1052.5,576.0 1071.6,565.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1071.6,537.0 1052.5,548.0 1052.5,518.0 1071.6,507.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1030.0,677.0 1011.0,688.0 1011.0,658.0 1030.0,647.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1030.0,619.0 1011.0,630.0 1011.0,600.0 1030.0,589.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1030.0,561.0 1011.0,572.0 1011.0,542.0 1030.0,531.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="988.5,701.0 969.4,712.0 969.4,682.0 988.5,671.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="988.5,643.0 969.4,654.0 969.4,624.0 988.5,613.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="988.5,585.0 969.4,596.0 969.4,566.0 988.5,555.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="778.9,450.0 936.5,541.0 936.5,523.0 778.9,432.0"
        fill="url(#chum-rl)"
      />
      <polygon
        points="1094.1,450.0 936.5,541.0 936.5,523.0 1094.1,432.0"
        fill="url(#chum-rr)"
      />
      <polygon
        points="936.5,341.0 1094.1,432.0 936.5,523.0 778.9,432.0"
        fill="url(#chum-rt)"
      />
      <polyline
        points="778.9,432.0 936.5,523.0 1094.1,432.0"
        fill="none"
        stroke="#FFFFFF"
        strokeOpacity="0.35"
        strokeWidth="1.5"
      />
      <polygon
        points="945.2,790.0 1083.7,870.0 1083.7,600.0 945.2,520.0"
        fill="url(#chum-wl)"
      />
      <polygon
        points="1248.3,775.0 1083.7,870.0 1083.7,600.0 1248.3,505.0"
        fill="url(#chum-wr)"
      />
      <polygon
        points="957.3,763.0 976.3,774.0 976.3,744.0 957.3,733.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="957.3,705.0 976.3,716.0 976.3,686.0 957.3,675.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="957.3,647.0 976.3,658.0 976.3,628.0 957.3,617.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="957.3,589.0 976.3,600.0 976.3,570.0 957.3,559.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="957.3,589.0 976.3,600.0 976.3,570.0 957.3,559.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="998.9,787.0 1017.9,798.0 1017.9,768.0 998.9,757.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="998.9,729.0 1017.9,740.0 1017.9,710.0 998.9,699.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="998.9,671.0 1017.9,682.0 1017.9,652.0 998.9,641.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="998.9,671.0 1017.9,682.0 1017.9,652.0 998.9,641.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="998.9,613.0 1017.9,624.0 1017.9,594.0 998.9,583.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1040.4,811.0 1059.5,822.0 1059.5,792.0 1040.4,781.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="1040.4,811.0 1059.5,822.0 1059.5,792.0 1040.4,781.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="1040.4,753.0 1059.5,764.0 1059.5,734.0 1040.4,723.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1040.4,695.0 1059.5,706.0 1059.5,676.0 1040.4,665.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1040.4,637.0 1059.5,648.0 1059.5,618.0 1040.4,607.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1236.1,748.0 1217.1,759.0 1217.1,729.0 1236.1,718.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1236.1,690.0 1217.1,701.0 1217.1,671.0 1236.1,660.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1236.1,632.0 1217.1,643.0 1217.1,613.0 1236.1,602.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1236.1,574.0 1217.1,585.0 1217.1,555.0 1236.1,544.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1194.6,772.0 1175.5,783.0 1175.5,753.0 1194.6,742.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1194.6,714.0 1175.5,725.0 1175.5,695.0 1194.6,684.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1194.6,656.0 1175.5,667.0 1175.5,637.0 1194.6,626.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1194.6,598.0 1175.5,609.0 1175.5,579.0 1194.6,568.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1153.0,796.0 1133.9,807.0 1133.9,777.0 1153.0,766.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1153.0,738.0 1133.9,749.0 1133.9,719.0 1153.0,708.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1153.0,680.0 1133.9,691.0 1133.9,661.0 1153.0,650.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="1153.0,680.0 1133.9,691.0 1133.9,661.0 1153.0,650.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="1153.0,622.0 1133.9,633.0 1133.9,603.0 1153.0,592.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="934.8,520.0 1083.7,606.0 1083.7,588.0 934.8,502.0"
        fill="url(#chum-rl)"
      />
      <polygon
        points="1258.7,505.0 1083.7,606.0 1083.7,588.0 1258.7,487.0"
        fill="url(#chum-rr)"
      />
      <polygon
        points="1109.7,401.0 1258.7,487.0 1083.7,588.0 934.8,502.0"
        fill="url(#chum-rt)"
      />
      <polyline
        points="934.8,502.0 1083.7,588.0 1258.7,487.0"
        fill="none"
        stroke="#FFFFFF"
        strokeOpacity="0.35"
        strokeWidth="1.5"
      />
      <polygon
        points="555.5,815.0 702.7,900.0 702.7,830.0 555.5,745.0"
        fill="url(#chum-wl)"
      />
      <polygon
        points="875.9,800.0 702.7,900.0 702.7,830.0 875.9,730.0"
        fill="url(#chum-wr)"
      />
      <polygon
        points="567.6,816.0 690.6,887.0 690.6,841.0 567.6,770.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="564.1,766.0 694.0,841.0 680.2,857.0 550.3,782.0"
        fill="#2453D6"
      />
      <polygon
        points="545.1,745.0 702.7,836.0 702.7,818.0 545.1,727.0"
        fill="url(#chum-rl)"
      />
      <polygon
        points="886.3,730.0 702.7,836.0 702.7,818.0 886.3,712.0"
        fill="url(#chum-rr)"
      />
      <polygon
        points="728.7,621.0 886.3,712.0 702.7,818.0 545.1,727.0"
        fill="url(#chum-rt)"
      />
      <polyline
        points="545.1,727.0 702.7,818.0 886.3,712.0"
        fill="none"
        stroke="#FFFFFF"
        strokeOpacity="0.35"
        strokeWidth="1.5"
      />
      <polygon
        points="728.7,915.0 867.2,995.0 867.2,805.0 728.7,725.0"
        fill="url(#chum-wl)"
      />
      <polygon
        points="1040.4,895.0 867.2,995.0 867.2,805.0 1040.4,705.0"
        fill="url(#chum-wr)"
      />
      <polygon
        points="740.8,888.0 759.8,899.0 759.8,869.0 740.8,858.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="740.8,830.0 759.8,841.0 759.8,811.0 740.8,800.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="782.4,912.0 801.4,923.0 801.4,893.0 782.4,882.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="782.4,854.0 801.4,865.0 801.4,835.0 782.4,824.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="823.9,936.0 843.0,947.0 843.0,917.0 823.9,906.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="823.9,878.0 843.0,889.0 843.0,859.0 823.9,848.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="1028.3,868.0 1009.2,879.0 1009.2,849.0 1028.3,838.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="1028.3,868.0 1009.2,879.0 1009.2,849.0 1028.3,838.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="1028.3,810.0 1009.2,821.0 1009.2,791.0 1028.3,780.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="986.7,892.0 967.7,903.0 967.7,873.0 986.7,862.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="986.7,892.0 967.7,903.0 967.7,873.0 986.7,862.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="986.7,834.0 967.7,845.0 967.7,815.0 986.7,804.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="986.7,834.0 967.7,845.0 967.7,815.0 986.7,804.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="945.2,916.0 926.1,927.0 926.1,897.0 945.2,886.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="945.2,916.0 926.1,927.0 926.1,897.0 945.2,886.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="945.2,858.0 926.1,869.0 926.1,839.0 945.2,828.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="903.6,940.0 884.5,951.0 884.5,921.0 903.6,910.0"
        fill="url(#chum-gw)"
      />
      <polygon
        points="903.6,940.0 884.5,951.0 884.5,921.0 903.6,910.0"
        fill="#FFD27A"
        opacity="0.5"
        filter="url(#chum-blur6)"
      />
      <polygon
        points="903.6,882.0 884.5,893.0 884.5,863.0 903.6,852.0"
        fill="url(#chum-gl)"
      />
      <polygon
        points="718.3,725.0 867.2,811.0 867.2,793.0 718.3,707.0"
        fill="url(#chum-rl)"
      />
      <polygon
        points="1050.8,705.0 867.2,811.0 867.2,793.0 1050.8,687.0"
        fill="url(#chum-rr)"
      />
      <polygon
        points="901.9,601.0 1050.8,687.0 867.2,793.0 718.3,707.0"
        fill="url(#chum-rt)"
      />
      <polyline
        points="718.3,707.0 867.2,793.0 1050.8,687.0"
        fill="none"
        stroke="#FFFFFF"
        strokeOpacity="0.35"
        strokeWidth="1.5"
      />
    </svg>
  );
}
