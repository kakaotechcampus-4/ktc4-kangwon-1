/**
 * 모든 화면 맨 아래에 붙는 공통 바닥글.
 *
 * 공공누리 자료는 출처를 늘 보여야 한다(테크스펙 v2 법적 제약 1번 '출처표시 상시노출').
 * 리포트 장마다 붙은 출처는 그 장을 펼친 사람에게만 보이므로, 서비스가 쓰는
 * 외부 자료 전체를 여기에 한 번 더 모은다. 이용조건은 각 자료 페이지에 적힌 그대로다.
 */

type DataSource = {
  provider: string;
  name: string;
  href: string;
  terms?: string;
};

const DATA_SOURCES: DataSource[] = [
  {
    provider: '서울특별시',
    name: '서울 열린데이터광장 상권분석서비스(길단위인구·상주인구·직장인구·영역·점포)',
    href: 'https://data.seoul.go.kr/dataList/OA-15568/S/1/datasetView.do',
    terms: '공공누리 제1유형(출처표시)',
  },
  {
    provider: '소상공인시장진흥공단',
    name: '상가(상권)정보',
    href: 'https://www.data.go.kr/data/15012005/openapi.do',
    terms: '공공데이터포털',
  },
  {
    provider: '공정거래위원회',
    name: '가맹정보 브랜드별 가맹점 현황',
    href: 'https://www.data.go.kr/data/15110241/openapi.do',
    terms: '공공데이터포털',
  },
  {
    provider: '국토교통부',
    name: '건축HUB 건축물대장정보',
    href: 'https://www.data.go.kr/data/15134735/openapi.do',
    terms: '공공데이터포털',
  },
  {
    provider: '국토교통부',
    name: '브이월드(V-World) 교육환경보호구역·행정경계',
    href: 'https://www.vworld.kr',
  },
  {
    provider: '카카오',
    name: '주소 검색·지도(카카오 로컬 API·카카오맵)',
    href: 'https://developers.kakao.com',
  },
];

export default function Footer() {
  return (
    <footer className="w-full border-t border-[#EEF1F4] bg-white px-4 py-10 sm:px-8">
      <div className="mx-auto flex max-w-[1120px] flex-col gap-6 text-sm text-[#5B6470]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="font-extrabold text-[#111827]">채움 · chum.ai</p>
          <p>공간의 다음 가능성을 찾습니다. © 2026 chum.ai</p>
        </div>
        <section
          aria-labelledby="footer-data-sources"
          className="text-xs leading-relaxed"
        >
          <h2
            id="footer-data-sources"
            className="mb-2 font-bold text-[#374151]"
          >
            데이터 출처
          </h2>
          <ul className="flex flex-col gap-1">
            {DATA_SOURCES.map((source) => (
              <li key={source.name}>
                {source.provider} ·{' '}
                <a
                  href={source.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline decoration-[#C9CED6] underline-offset-2 hover:text-[#111827]"
                >
                  {source.name}
                </a>
                {source.terms ? ` (${source.terms})` : null}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[#8A929C]">
            각 자료의 기준 시점은 리포트의 해당 장에 적혀 있습니다.
          </p>
        </section>
      </div>
    </footer>
  );
}
