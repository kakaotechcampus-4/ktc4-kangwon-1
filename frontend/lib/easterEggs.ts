export type EasterEgg = {
  id: string;
  paragraphs: string[];
  links: { label: string; href: string }[];
};

type EasterEggRule = EasterEgg & { pattern: RegExp };

const NOT_FOLLOWED_BY_NUMBER = String.raw`(?![\d-])`;

function addressPattern(...sources: string[]): RegExp {
  return new RegExp(
    sources.map((source) => `${source}${NOT_FOLLOWED_BY_NUMBER}`).join('|')
  );
}

const HWAGAE_JANGTEO = {
  label: '화개장터 듣기',
  href: 'https://www.youtube.com/watch?v=BXrjZOc6gW0',
};

const rules: EasterEggRule[] = [
  {
    id: 'pangyo',
    pattern: addressPattern('판교역로166', '백현동532'),
    paragraphs: [
      '여기에 의심의 여지 없이 무언가 터가 좋습니다...',
      '풍수지리학적으로 노란색 IT 기업이 들어오면 승승장구 할 것입니다...',
      '춘천의 K대 학생들이랑 잘 어울리는군요....',
    ],
    links: [],
  },
  {
    id: 'samseong',
    pattern: addressPattern('삼성동144-28'),
    paragraphs: [
      '의심의 여지 없이 무언가 터가 좋습니다...',
      '풍수지리학적으로 보라색 IT 기업이 들어오면 승승장구 할 것입니다...',
      '춘천의 K대 학생들이랑 잘 어울리는군요....',
    ],
    links: [],
  },
  {
    id: 'kangwon',
    pattern: addressPattern('강원대학길1'),
    paragraphs: [
      '무언가 큰 인물들이 나올 거 같습니다...',
      '이 출신 인물들은 꼭 노란색 혹은 보라색 IT 기업에서 스카우트 해야합니다',
    ],
    links: [],
  },
  {
    id: 'pusan',
    pattern: addressPattern('부산대학로63번길2'),
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
    pattern: addressPattern('대구(광역시)?북구대학로80'),
    paragraphs: [],
    links: [HWAGAE_JANGTEO],
  },
  {
    id: 'chonnam',
    pattern: addressPattern('용봉로77'),
    paragraphs: [],
    links: [HWAGAE_JANGTEO],
  },
  {
    id: 'chungnam',
    pattern: addressPattern('대전(광역시)?유성구대학로99'),
    paragraphs: [],
    links: [{ label: '성심당 가 보기', href: 'https://www.sungsimdang.co.kr' }],
  },
];

export function findEasterEgg(address: string): EasterEgg | null {
  const compact = address.replace(/\s+/g, '');
  const rule = rules.find(({ pattern }) => pattern.test(compact));
  if (!rule) {
    return null;
  }
  const { id, paragraphs, links } = rule;
  return { id, paragraphs, links };
}
