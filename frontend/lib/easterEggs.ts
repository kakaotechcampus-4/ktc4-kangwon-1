export type EasterEgg = {
  id: string;
  paragraphs: string[];
  links: { label: string; href: string }[];
};

type EasterEggRule = EasterEgg & { patterns: RegExp[] };

const DASHES = /[‐‑‒–—―−]/g;

function houseNumber(source: string): RegExp {
  return new RegExp(String.raw`${source}(?![\d-])(?!\s*번길)`);
}

function addressPattern(...sources: string[]): RegExp[] {
  return sources.map(houseNumber);
}

const HWAGAE_JANGTEO = {
  label: '화개장터 듣기',
  href: 'https://www.youtube.com/watch?v=BXrjZOc6gW0',
};

const rules: EasterEggRule[] = [
  {
    id: 'pangyo',
    patterns: addressPattern(
      String.raw`판교역로\s*166`,
      String.raw`백현동\s*532`
    ),
    paragraphs: [
      '여기에 의심의 여지 없이 무언가 터가 좋습니다...',
      '풍수지리학적으로 노란색 IT 기업이 들어오면 승승장구 할 것입니다...',
      '춘천의 K대 학생들이랑 잘 어울리는군요....',
    ],
    links: [],
  },
  {
    id: 'samseong',
    patterns: addressPattern(String.raw`삼성동\s*144-28`),
    paragraphs: [
      '의심의 여지 없이 무언가 터가 좋습니다...',
      '풍수지리학적으로 보라색 IT 기업이 들어오면 승승장구 할 것입니다...',
      '춘천의 K대 학생들이랑 잘 어울리는군요....',
    ],
    links: [],
  },
  {
    id: 'kangwon',
    patterns: addressPattern(String.raw`강원대학길\s*1`),
    paragraphs: [
      '무언가 큰 인물들이 나올 거 같습니다...',
      '이 출신 인물들은 꼭 노란색 혹은 보라색 IT 기업에서 스카우트 해야합니다',
    ],
    links: [],
  },
  {
    id: 'pusan',
    patterns: addressPattern(String.raw`부산대학로\s*63번길\s*2`),
    paragraphs: [],
    links: [
      {
        label: '부산 바캉스 MV 보기',
        href: 'https://www.youtube.com/watch?v=PehlE8g0ReA',
      },
    ],
  },
  {
    id: 'kyungpook',
    patterns: addressPattern(String.raw`대구(?:광역시)?\s*북구\s*대학로\s*80`),
    paragraphs: [],
    links: [HWAGAE_JANGTEO],
  },
  {
    id: 'chonnam',
    patterns: addressPattern(String.raw`용봉로\s*77`),
    paragraphs: [],
    links: [HWAGAE_JANGTEO],
  },
  {
    id: 'chungnam',
    patterns: addressPattern(
      String.raw`대전(?:광역시)?\s*유성구\s*대학로\s*99`
    ),
    paragraphs: [],
    links: [{ label: '성심당 가 보기', href: 'https://www.sungsimdang.co.kr' }],
  },
];

function normalize(address: string): string {
  return address
    .normalize('NFKC')
    .replace(DASHES, '-')
    .replace(/\s+/g, ' ')
    .trim();
}

export function findEasterEgg(address: string): EasterEgg | null {
  const normalized = normalize(address);
  const rule = rules.find(({ patterns }) =>
    patterns.some((pattern) => pattern.test(normalized))
  );
  if (!rule) {
    return null;
  }
  const { id, paragraphs, links } = rule;
  return { id, paragraphs, links };
}
