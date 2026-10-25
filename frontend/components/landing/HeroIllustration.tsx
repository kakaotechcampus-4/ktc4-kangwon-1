/**
 * 랜딩 히어로 배경의 아이소메트릭 건물 블록 그림.
 * L자 받침 위에 뒤쪽 높은 건물, 오른쪽 상가 건물, 왼쪽 앞의 빈 상가가 있다.
 * 빈 상가 1층은 앰버 테두리와 위치 핀으로 강조한다.
 * 정적인 장식 그림이라 좌표는 아이소메트릭 투영으로 계산해 그대로 넣었다.
 */
export default function HeroIllustration({
  className = '',
}: {
  className?: string;
}) {
  return (
    <svg
      viewBox="120 20 1290 1000"
      preserveAspectRatio="xMaxYMax meet"
      className={className}
      role="img"
      aria-label="흰 건물 세 채가 놓인 블록과, 앰버 테두리와 위치 핀으로 표시된 1층 빈 상가 그림"
    >
      <defs>
        <linearGradient id="hb-wl" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#F1F4F9" />
        </linearGradient>
        <linearGradient id="hb-wr" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#E9EDF5" />
          <stop offset="1" stopColor="#DCE2EE" />
        </linearGradient>
        <linearGradient id="hb-glass" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#B9C5E3" />
          <stop offset="1" stopColor="#9EADD3" />
        </linearGradient>
        <linearGradient id="hb-warm" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FBE7B4" />
          <stop offset="1" stopColor="#F3D284" />
        </linearGradient>
        <linearGradient id="hb-shop" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#F4F2EE" />
          <stop offset="1" stopColor="#DCE1EC" />
        </linearGradient>
        <linearGradient id="hb-slab" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#B9C4DF" />
          <stop offset="1" stopColor="#A3B0D2" />
        </linearGradient>
        <radialGradient id="hb-bg" cx="0.5" cy="0.4" r="0.6">
          <stop offset="0" stopColor="#FFFFFF" stopOpacity="0.95" />
          <stop offset="1" stopColor="#FFFFFF" stopOpacity="0" />
        </radialGradient>
        <filter id="hb-blur" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="16" />
        </filter>
        <filter id="hb-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="5" />
        </filter>
      </defs>
      <ellipse cx="720" cy="470" rx="720" ry="470" fill="url(#hb-bg)" />
      <ellipse
        cx="740"
        cy="985"
        rx="520"
        ry="46"
        fill="#1B2B4A"
        opacity="0.18"
        filter="url(#hb-blur)"
      />
      <polygon
        points="183.1,816.0 425.6,956.0 425.6,920.0 183.1,780.0"
        fill="url(#hb-slab)"
      />
      <polygon
        points="702.7,796.0 425.6,956.0 425.6,920.0 702.7,760.0"
        fill="#9CA9CC"
      />
      <polygon
        points="702.7,796.0 1014.4,976.0 1014.4,940.0 702.7,760.0"
        fill="url(#hb-slab)"
      />
      <polygon
        points="1274.2,826.0 1014.4,976.0 1014.4,940.0 1274.2,790.0"
        fill="#9CA9CC"
      />
      <polygon
        points="720.0,470.0 1274.2,790.0 1014.4,940.0 702.7,760.0 425.6,920.0 183.1,780.0"
        fill="#EEF1F8"
      />
      <polyline
        points="183.1,780.0 425.6,920.0 702.7,760.0 1014.4,940.0 1274.2,790.0"
        fill="none"
        stroke="#FFFFFF"
        strokeWidth="2"
      />
      <line
        x1="772.0"
        y1="500.0"
        x2="235.0"
        y2="810.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="823.9"
        y1="530.0"
        x2="287.0"
        y2="840.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="875.9"
        y1="560.0"
        x2="339.0"
        y2="870.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="927.8"
        y1="590.0"
        x2="390.9"
        y2="900.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="979.8"
        y1="620.0"
        x2="720.0"
        y2="770.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="1031.8"
        y1="650.0"
        x2="772.0"
        y2="800.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="1083.7"
        y1="680.0"
        x2="823.9"
        y2="830.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="1135.7"
        y1="710.0"
        x2="875.9"
        y2="860.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="1187.6"
        y1="740.0"
        x2="927.8"
        y2="890.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="1239.6"
        y1="770.0"
        x2="979.8"
        y2="920.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="668.0"
        y1="500.0"
        x2="1222.3"
        y2="820.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="616.1"
        y1="530.0"
        x2="1170.3"
        y2="850.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="564.1"
        y1="560.0"
        x2="1118.4"
        y2="880.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="512.2"
        y1="590.0"
        x2="1066.4"
        y2="910.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="460.2"
        y1="620.0"
        x2="702.7"
        y2="760.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="408.2"
        y1="650.0"
        x2="650.7"
        y2="790.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="356.3"
        y1="680.0"
        x2="598.8"
        y2="820.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="304.3"
        y1="710.0"
        x2="546.8"
        y2="850.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="252.4"
        y1="740.0"
        x2="494.8"
        y2="880.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <line
        x1="200.4"
        y1="770.0"
        x2="442.9"
        y2="910.0"
        stroke="#D9DFEC"
        strokeWidth="1"
      />
      <g opacity="0.12" filter="url(#hb-blur)">
        <polygon
          points="720.0,510.0 945.2,640.0 754.6,750.0 529.5,620.0"
          fill="#3A4A70"
        />
        <polygon
          points="486.2,635.0 720.0,770.0 460.2,920.0 226.4,785.0"
          fill="#3A4A70"
        />
        <polygon
          points="953.8,635.0 1248.3,805.0 1023.1,935.0 728.7,765.0"
          fill="#3A4A70"
        />
      </g>
      <polygon
        points="538.1,615.0 720.0,720.0 720.0,290.0 538.1,185.0"
        fill="url(#hb-wl)"
      />
      <polygon
        points="901.9,615.0 720.0,720.0 720.0,290.0 901.9,185.0"
        fill="url(#hb-wr)"
      />
      <line
        x1="720.0"
        y1="720.0"
        x2="720.0"
        y2="290.0"
        stroke="#FFFFFF"
        strokeWidth="1.5"
      />
      <polygon
        points="538.1,615.0 720.0,720.0 720.0,706.0 538.1,601.0"
        fill="#E2E7F1"
      />
      <polygon
        points="901.9,615.0 720.0,720.0 720.0,706.0 901.9,601.0"
        fill="#CBD3E4"
      />
      <polygon
        points="561.5,571.5 596.2,591.5 596.2,541.5 561.5,521.5"
        fill="#DCE2EE"
      />
      <polygon
        points="564.1,570.0 593.6,587.0 593.6,543.0 564.1,526.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="617.8,604.0 652.5,624.0 652.5,574.0 617.8,554.0"
        fill="#DCE2EE"
      />
      <polygon
        points="620.4,602.5 649.9,619.5 649.9,575.5 620.4,558.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="669.8,634.0 704.4,654.0 704.4,604.0 669.8,584.0"
        fill="#DCE2EE"
      />
      <polygon
        points="672.4,632.5 701.8,649.5 701.8,605.5 672.4,588.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="878.5,571.5 843.8,591.5 843.8,541.5 878.5,521.5"
        fill="#CDD5E5"
      />
      <polygon
        points="875.9,570.0 846.4,587.0 846.4,543.0 875.9,526.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="822.2,604.0 787.5,624.0 787.5,574.0 822.2,554.0"
        fill="#CDD5E5"
      />
      <polygon
        points="819.6,602.5 790.1,619.5 790.1,575.5 819.6,558.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="770.2,634.0 735.6,654.0 735.6,604.0 770.2,584.0"
        fill="#CDD5E5"
      />
      <polygon
        points="767.6,632.5 738.2,649.5 738.2,605.5 767.6,588.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="561.5,499.5 596.2,519.5 596.2,469.5 561.5,449.5"
        fill="#DCE2EE"
      />
      <polygon
        points="564.1,498.0 593.6,515.0 593.6,471.0 564.1,454.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="617.8,532.0 652.5,552.0 652.5,502.0 617.8,482.0"
        fill="#DCE2EE"
      />
      <polygon
        points="620.4,530.5 649.9,547.5 649.9,503.5 620.4,486.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="669.8,562.0 704.4,582.0 704.4,532.0 669.8,512.0"
        fill="#DCE2EE"
      />
      <polygon
        points="672.4,560.5 701.8,577.5 701.8,533.5 672.4,516.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="878.5,499.5 843.8,519.5 843.8,469.5 878.5,449.5"
        fill="#CDD5E5"
      />
      <polygon
        points="875.9,498.0 846.4,515.0 846.4,471.0 875.9,454.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="822.2,532.0 787.5,552.0 787.5,502.0 822.2,482.0"
        fill="#CDD5E5"
      />
      <polygon
        points="819.6,530.5 790.1,547.5 790.1,503.5 819.6,486.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="770.2,562.0 735.6,582.0 735.6,532.0 770.2,512.0"
        fill="#CDD5E5"
      />
      <polygon
        points="767.6,560.5 738.2,577.5 738.2,533.5 767.6,516.5"
        fill="url(#hb-warm)"
      />
      <polygon
        points="561.5,427.5 596.2,447.5 596.2,397.5 561.5,377.5"
        fill="#DCE2EE"
      />
      <polygon
        points="564.1,426.0 593.6,443.0 593.6,399.0 564.1,382.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="617.8,460.0 652.5,480.0 652.5,430.0 617.8,410.0"
        fill="#DCE2EE"
      />
      <polygon
        points="620.4,458.5 649.9,475.5 649.9,431.5 620.4,414.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="669.8,490.0 704.4,510.0 704.4,460.0 669.8,440.0"
        fill="#DCE2EE"
      />
      <polygon
        points="672.4,488.5 701.8,505.5 701.8,461.5 672.4,444.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="878.5,427.5 843.8,447.5 843.8,397.5 878.5,377.5"
        fill="#CDD5E5"
      />
      <polygon
        points="875.9,426.0 846.4,443.0 846.4,399.0 875.9,382.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="822.2,460.0 787.5,480.0 787.5,430.0 822.2,410.0"
        fill="#CDD5E5"
      />
      <polygon
        points="819.6,458.5 790.1,475.5 790.1,431.5 819.6,414.5"
        fill="url(#hb-warm)"
      />
      <polygon
        points="770.2,490.0 735.6,510.0 735.6,460.0 770.2,440.0"
        fill="#CDD5E5"
      />
      <polygon
        points="767.6,488.5 738.2,505.5 738.2,461.5 767.6,444.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="561.5,355.5 596.2,375.5 596.2,325.5 561.5,305.5"
        fill="#DCE2EE"
      />
      <polygon
        points="564.1,354.0 593.6,371.0 593.6,327.0 564.1,310.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="617.8,388.0 652.5,408.0 652.5,358.0 617.8,338.0"
        fill="#DCE2EE"
      />
      <polygon
        points="620.4,386.5 649.9,403.5 649.9,359.5 620.4,342.5"
        fill="url(#hb-warm)"
      />
      <polygon
        points="669.8,418.0 704.4,438.0 704.4,388.0 669.8,368.0"
        fill="#DCE2EE"
      />
      <polygon
        points="672.4,416.5 701.8,433.5 701.8,389.5 672.4,372.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="878.5,355.5 843.8,375.5 843.8,325.5 878.5,305.5"
        fill="#CDD5E5"
      />
      <polygon
        points="875.9,354.0 846.4,371.0 846.4,327.0 875.9,310.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="822.2,388.0 787.5,408.0 787.5,358.0 822.2,338.0"
        fill="#CDD5E5"
      />
      <polygon
        points="819.6,386.5 790.1,403.5 790.1,359.5 819.6,342.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="770.2,418.0 735.6,438.0 735.6,388.0 770.2,368.0"
        fill="#CDD5E5"
      />
      <polygon
        points="767.6,416.5 738.2,433.5 738.2,389.5 767.6,372.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="561.5,283.5 596.2,303.5 596.2,253.5 561.5,233.5"
        fill="#DCE2EE"
      />
      <polygon
        points="564.1,282.0 593.6,299.0 593.6,255.0 564.1,238.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="617.8,316.0 652.5,336.0 652.5,286.0 617.8,266.0"
        fill="#DCE2EE"
      />
      <polygon
        points="620.4,314.5 649.9,331.5 649.9,287.5 620.4,270.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="669.8,346.0 704.4,366.0 704.4,316.0 669.8,296.0"
        fill="#DCE2EE"
      />
      <polygon
        points="672.4,344.5 701.8,361.5 701.8,317.5 672.4,300.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="878.5,283.5 843.8,303.5 843.8,253.5 878.5,233.5"
        fill="#CDD5E5"
      />
      <polygon
        points="875.9,282.0 846.4,299.0 846.4,255.0 875.9,238.0"
        fill="url(#hb-warm)"
      />
      <polygon
        points="822.2,316.0 787.5,336.0 787.5,286.0 822.2,266.0"
        fill="#CDD5E5"
      />
      <polygon
        points="819.6,314.5 790.1,331.5 790.1,287.5 819.6,270.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="770.2,346.0 735.6,366.0 735.6,316.0 770.2,296.0"
        fill="#CDD5E5"
      />
      <polygon
        points="767.6,344.5 738.2,361.5 738.2,317.5 767.6,300.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="538.1,185.0 720.0,290.0 720.0,276.0 538.1,171.0"
        fill="#C2CCE6"
      />
      <polygon
        points="901.9,185.0 720.0,290.0 720.0,276.0 901.9,171.0"
        fill="#AEBADB"
      />
      <polygon
        points="720.0,66.0 901.9,171.0 720.0,276.0 538.1,171.0"
        fill="#D2DAF0"
      />
      <polygon
        points="720.0,82.0 874.1,171.0 720.0,260.0 565.9,171.0"
        fill="#C3CDEA"
      />
      <polygon
        points="720.0,82.0 874.1,171.0 869.0,174.0 720.0,88.0 571.0,174.0 565.9,171.0"
        fill="#AFBBDC"
      />
      <polyline
        points="538.1,171.0 720.0,276.0 901.9,171.0"
        fill="none"
        stroke="#FFFFFF"
        strokeOpacity="0.8"
        strokeWidth="1.5"
      />
      <polygon
        points="754.6,760.0 1014.4,910.0 1014.4,610.0 754.6,460.0"
        fill="url(#hb-wl)"
      />
      <polygon
        points="1222.3,790.0 1014.4,910.0 1014.4,610.0 1222.3,490.0"
        fill="url(#hb-wr)"
      />
      <line
        x1="1014.4"
        y1="910.0"
        x2="1014.4"
        y2="610.0"
        stroke="#FFFFFF"
        strokeWidth="1.5"
      />
      <polygon
        points="754.6,668.0 1014.4,818.0 1014.4,806.0 754.6,656.0"
        fill="#E3E8F2"
      />
      <polygon
        points="1222.3,698.0 1014.4,818.0 1014.4,806.0 1222.3,686.0"
        fill="#CED6E6"
      />
      <polygon
        points="769.4,763.5 869.8,821.5 869.8,743.5 769.4,685.5"
        fill="#DCE2EE"
      />
      <polygon
        points="772.0,762.0 867.2,817.0 867.2,745.0 772.0,690.0"
        fill="url(#hb-shop)"
      />
      <line
        x1="819.6"
        y1="789.5"
        x2="819.6"
        y2="717.5"
        stroke="#E4E9F2"
        strokeWidth="2.5"
      />
      <polygon
        points="890.6,833.5 999.7,896.5 999.7,818.5 890.6,755.5"
        fill="#DCE2EE"
      />
      <polygon
        points="893.2,832.0 997.1,892.0 997.1,820.0 893.2,760.0"
        fill="url(#hb-shop)"
      />
      <line
        x1="945.2"
        y1="862.0"
        x2="945.2"
        y2="790.0"
        stroke="#E4E9F2"
        strokeWidth="2.5"
      />
      <polygon
        points="1207.6,793.5 1124.4,841.5 1124.4,763.5 1207.6,715.5"
        fill="#CDD5E5"
      />
      <polygon
        points="1205.0,792.0 1127.0,837.0 1127.0,765.0 1205.0,720.0"
        fill="url(#hb-shop)"
      />
      <line
        x1="1166.0"
        y1="814.5"
        x2="1166.0"
        y2="742.5"
        stroke="#D6DDEA"
        strokeWidth="2.5"
      />
      <polygon
        points="1108.0,851.0 1029.2,896.5 1029.2,818.5 1108.0,773.0"
        fill="#CDD5E5"
      />
      <polygon
        points="1105.4,849.5 1031.8,892.0 1031.8,820.0 1105.4,777.5"
        fill="url(#hb-shop)"
      />
      <line
        x1="1068.6"
        y1="870.8"
        x2="1068.6"
        y2="798.8"
        stroke="#D6DDEA"
        strokeWidth="2.5"
      />
      <polygon
        points="771.1,648.5 810.9,671.5 810.9,627.5 771.1,604.5"
        fill="#DCE2EE"
      />
      <polygon
        points="773.7,647.0 808.3,667.0 808.3,629.0 773.7,609.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="830.0,682.5 869.8,705.5 869.8,661.5 830.0,638.5"
        fill="#DCE2EE"
      />
      <polygon
        points="832.6,681.0 867.2,701.0 867.2,663.0 832.6,643.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="888.9,716.5 928.7,739.5 928.7,695.5 888.9,672.5"
        fill="#DCE2EE"
      />
      <polygon
        points="891.5,715.0 926.1,735.0 926.1,697.0 891.5,677.0"
        fill="url(#hb-warm)"
      />
      <polygon
        points="947.8,750.5 987.6,773.5 987.6,729.5 947.8,706.5"
        fill="#DCE2EE"
      />
      <polygon
        points="950.4,749.0 985.0,769.0 985.0,731.0 950.4,711.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="1198.9,682.5 1160.8,704.5 1160.8,660.5 1198.9,638.5"
        fill="#CDD5E5"
      />
      <polygon
        points="1196.3,681.0 1163.4,700.0 1163.4,662.0 1196.3,643.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="1142.6,715.0 1104.5,737.0 1104.5,693.0 1142.6,671.0"
        fill="#CDD5E5"
      />
      <polygon
        points="1140.0,713.5 1107.1,732.5 1107.1,694.5 1140.0,675.5"
        fill="url(#hb-warm)"
      />
      <polygon
        points="1086.3,747.5 1048.2,769.5 1048.2,725.5 1086.3,703.5"
        fill="#CDD5E5"
      />
      <polygon
        points="1083.7,746.0 1050.8,765.0 1050.8,727.0 1083.7,708.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="771.1,590.5 810.9,613.5 810.9,569.5 771.1,546.5"
        fill="#DCE2EE"
      />
      <polygon
        points="773.7,589.0 808.3,609.0 808.3,571.0 773.7,551.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="830.0,624.5 869.8,647.5 869.8,603.5 830.0,580.5"
        fill="#DCE2EE"
      />
      <polygon
        points="832.6,623.0 867.2,643.0 867.2,605.0 832.6,585.0"
        fill="url(#hb-warm)"
      />
      <polygon
        points="888.9,658.5 928.7,681.5 928.7,637.5 888.9,614.5"
        fill="#DCE2EE"
      />
      <polygon
        points="891.5,657.0 926.1,677.0 926.1,639.0 891.5,619.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="947.8,692.5 987.6,715.5 987.6,671.5 947.8,648.5"
        fill="#DCE2EE"
      />
      <polygon
        points="950.4,691.0 985.0,711.0 985.0,673.0 950.4,653.0"
        fill="url(#hb-warm)"
      />
      <polygon
        points="1198.9,624.5 1160.8,646.5 1160.8,602.5 1198.9,580.5"
        fill="#CDD5E5"
      />
      <polygon
        points="1196.3,623.0 1163.4,642.0 1163.4,604.0 1196.3,585.0"
        fill="url(#hb-warm)"
      />
      <polygon
        points="1142.6,657.0 1104.5,679.0 1104.5,635.0 1142.6,613.0"
        fill="#CDD5E5"
      />
      <polygon
        points="1140.0,655.5 1107.1,674.5 1107.1,636.5 1140.0,617.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="1086.3,689.5 1048.2,711.5 1048.2,667.5 1086.3,645.5"
        fill="#CDD5E5"
      />
      <polygon
        points="1083.7,688.0 1050.8,707.0 1050.8,669.0 1083.7,650.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="771.1,532.5 810.9,555.5 810.9,511.5 771.1,488.5"
        fill="#DCE2EE"
      />
      <polygon
        points="773.7,531.0 808.3,551.0 808.3,513.0 773.7,493.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="830.0,566.5 869.8,589.5 869.8,545.5 830.0,522.5"
        fill="#DCE2EE"
      />
      <polygon
        points="832.6,565.0 867.2,585.0 867.2,547.0 832.6,527.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="888.9,600.5 928.7,623.5 928.7,579.5 888.9,556.5"
        fill="#DCE2EE"
      />
      <polygon
        points="891.5,599.0 926.1,619.0 926.1,581.0 891.5,561.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="947.8,634.5 987.6,657.5 987.6,613.5 947.8,590.5"
        fill="#DCE2EE"
      />
      <polygon
        points="950.4,633.0 985.0,653.0 985.0,615.0 950.4,595.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="1198.9,566.5 1160.8,588.5 1160.8,544.5 1198.9,522.5"
        fill="#CDD5E5"
      />
      <polygon
        points="1196.3,565.0 1163.4,584.0 1163.4,546.0 1196.3,527.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="1142.6,599.0 1104.5,621.0 1104.5,577.0 1142.6,555.0"
        fill="#CDD5E5"
      />
      <polygon
        points="1140.0,597.5 1107.1,616.5 1107.1,578.5 1140.0,559.5"
        fill="url(#hb-glass)"
      />
      <polygon
        points="1086.3,631.5 1048.2,653.5 1048.2,609.5 1086.3,587.5"
        fill="#CDD5E5"
      />
      <polygon
        points="1083.7,630.0 1050.8,649.0 1050.8,611.0 1083.7,592.0"
        fill="url(#hb-warm)"
      />
      <polygon
        points="754.6,460.0 1014.4,610.0 1014.4,596.0 754.6,446.0"
        fill="#C2CCE6"
      />
      <polygon
        points="1222.3,490.0 1014.4,610.0 1014.4,596.0 1222.3,476.0"
        fill="#AEBADB"
      />
      <polygon
        points="962.5,326.0 1222.3,476.0 1014.4,596.0 754.6,446.0"
        fill="#D2DAF0"
      />
      <polygon
        points="962.5,342.0 1194.6,476.0 1014.4,580.0 782.4,446.0"
        fill="#C3CDEA"
      />
      <polygon
        points="962.5,342.0 1194.6,476.0 1189.4,479.0 962.5,348.0 787.5,449.0 782.4,446.0"
        fill="#AFBBDC"
      />
      <polyline
        points="754.6,446.0 1014.4,596.0 1222.3,476.0"
        fill="none"
        stroke="#FFFFFF"
        strokeOpacity="0.8"
        strokeWidth="1.5"
      />
      <polygon
        points="235.0,780.0 434.2,895.0 434.2,699.0 235.0,584.0"
        fill="url(#hb-wl)"
      />
      <polygon
        points="676.7,755.0 434.2,895.0 434.2,699.0 676.7,559.0"
        fill="url(#hb-wr)"
      />
      <line
        x1="434.2"
        y1="895.0"
        x2="434.2"
        y2="699.0"
        stroke="#FFFFFF"
        strokeWidth="1.5"
      />
      <polygon
        points="242.8,781.5 426.4,887.5 426.4,799.5 242.8,693.5"
        fill="#DCE2EE"
      />
      <polygon
        points="245.4,780.0 423.8,883.0 423.8,801.0 245.4,698.0"
        fill="url(#hb-shop)"
      />
      <line
        x1="290.0"
        y1="805.8"
        x2="290.0"
        y2="723.8"
        stroke="#E4E9F2"
        strokeWidth="2.5"
      />
      <line
        x1="334.6"
        y1="831.5"
        x2="334.6"
        y2="749.5"
        stroke="#E4E9F2"
        strokeWidth="2.5"
      />
      <line
        x1="379.2"
        y1="857.2"
        x2="379.2"
        y2="775.2"
        stroke="#E4E9F2"
        strokeWidth="2.5"
      />
      <polygon
        points="575.4,810.5 442.0,887.5 442.0,799.5 575.4,722.5"
        fill="#CDD5E5"
      />
      <polygon
        points="572.8,809.0 444.6,883.0 444.6,801.0 572.8,727.0"
        fill="url(#hb-shop)"
      />
      <line
        x1="530.1"
        y1="833.7"
        x2="530.1"
        y2="751.7"
        stroke="#D6DDEA"
        strokeWidth="2.5"
      />
      <line
        x1="487.3"
        y1="858.3"
        x2="487.3"
        y2="776.3"
        stroke="#D6DDEA"
        strokeWidth="2.5"
      />
      <path
        d="M245.4 780.0 L434.2 889.0 L572.8 809.0 L572.8 727.0 L434.2 807.0 L245.4 698.0 Z M434.2 889.0 L434.2 807.0"
        fill="none"
        stroke="#F2B84B"
        strokeWidth="9"
        opacity="0.55"
        filter="url(#hb-glow)"
      />
      <path
        d="M245.4 780.0 L434.2 889.0 L572.8 809.0 L572.8 727.0 L434.2 807.0 L245.4 698.0 Z M434.2 889.0 L434.2 807.0"
        fill="none"
        stroke="#F5C24E"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <polygon
        points="221.2,690.0 434.2,813.0 434.2,797.0 221.2,674.0"
        fill="#D5DCEC"
      />
      <polygon
        points="590.1,723.0 434.2,813.0 434.2,797.0 590.1,707.0"
        fill="#BFC9E0"
      />
      <polygon
        points="377.1,584.0 590.1,707.0 434.2,797.0 221.2,674.0"
        fill="#EEF1F8"
      />
      <polygon
        points="249.8,667.5 341.6,720.5 341.6,662.5 249.8,609.5"
        fill="#DCE2EE"
      />
      <polygon
        points="252.4,666.0 339.0,716.0 339.0,664.0 252.4,614.0"
        fill="url(#hb-glass)"
      />
      <line
        x1="281.2"
        y1="682.7"
        x2="281.2"
        y2="630.7"
        stroke="#E4E9F2"
        strokeWidth="2.5"
      />
      <line
        x1="310.1"
        y1="699.3"
        x2="310.1"
        y2="647.3"
        stroke="#E4E9F2"
        strokeWidth="2.5"
      />
      <polygon
        points="362.3,732.5 419.5,765.5 419.5,707.5 362.3,674.5"
        fill="#DCE2EE"
      />
      <polygon
        points="364.9,731.0 416.9,761.0 416.9,709.0 364.9,679.0"
        fill="url(#hb-glass)"
      />
      <polygon
        points="662.0,642.5 578.8,690.5 578.8,632.5 662.0,584.5"
        fill="#CDD5E5"
      />
      <polygon
        points="659.4,641.0 581.4,686.0 581.4,634.0 659.4,589.0"
        fill="url(#hb-glass)"
      />
      <line
        x1="620.4"
        y1="663.5"
        x2="620.4"
        y2="611.5"
        stroke="#D6DDEA"
        strokeWidth="2.5"
      />
      <polygon
        points="558.1,702.5 457.6,760.5 457.6,702.5 558.1,644.5"
        fill="#CDD5E5"
      />
      <polygon
        points="555.5,701.0 460.2,756.0 460.2,704.0 555.5,649.0"
        fill="url(#hb-glass)"
      />
      <line
        x1="507.8"
        y1="728.5"
        x2="507.8"
        y2="676.5"
        stroke="#D6DDEA"
        strokeWidth="2.5"
      />
      <polygon
        points="235.0,584.0 434.2,699.0 434.2,685.0 235.0,570.0"
        fill="#C2CCE6"
      />
      <polygon
        points="676.7,559.0 434.2,699.0 434.2,685.0 676.7,545.0"
        fill="#AEBADB"
      />
      <polygon
        points="477.5,430.0 676.7,545.0 434.2,685.0 235.0,570.0"
        fill="#D2DAF0"
      />
      <polygon
        points="477.5,446.0 649.0,545.0 434.2,669.0 262.8,570.0"
        fill="#C3CDEA"
      />
      <polygon
        points="477.5,446.0 649.0,545.0 643.8,548.0 477.5,452.0 267.9,573.0 262.8,570.0"
        fill="#AFBBDC"
      />
      <polyline
        points="235.0,570.0 434.2,685.0 676.7,545.0"
        fill="none"
        stroke="#FFFFFF"
        strokeOpacity="0.8"
        strokeWidth="1.5"
      />
      <g transform="translate(425.6 766.0)">
        <ellipse cx="0" cy="6" rx="12" ry="5" fill="#1B2B4A" opacity="0.18" />
        <path
          d="M0 4 C-9 -8 -16 -16 -16 -26 A16 16 0 0 1 16 -26 C16 -16 9 -8 0 4 Z"
          fill="#F2B84B"
        />
        <circle cx="0" cy="-26" r="6" fill="#FFFFFF" />
      </g>
    </svg>
  );
}
