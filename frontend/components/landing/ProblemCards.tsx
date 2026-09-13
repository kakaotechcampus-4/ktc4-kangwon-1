import { Outfit, DM_Mono } from 'next/font/google';
import { LayoutGrid, Share2, Target, type LucideIcon } from 'lucide-react';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import { colors } from '@/styles/tokens';

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['700'],
});

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['400'],
});

type Problem = {
  id: string;
  number: string;
  tag: string;
  icon: LucideIcon;
  title: string;
  description: string;
};

const problems: Problem[] = [
  {
    id: 'category-fit',
    number: '01',
    tag: '업종 판단',
    icon: Target,
    title: '업종 판단의 어려움',
    description: '업종별 공간 요건이 다양해 비전문가 혼자 판단하기 어렵습니다.',
  },
  {
    id: 'space-mismatch',
    number: '02',
    tag: '공간 구조',
    icon: LayoutGrid,
    title: '상권과 공간의 불일치',
    description: '전면폭, 층고, 급·배수 위치가 특정 업종의 성패를 좌우합니다.',
  },
  {
    id: 'data-fragmentation',
    number: '03',
    tag: '데이터 통합',
    icon: Share2,
    title: '흩어진 정보, 통합된 판단 부재',
    description: '분산된 정보를 통합적으로 분석하는 체계적 도구가 없었습니다.',
  },
];

export default function ProblemCards() {
  return (
    <div className="flex w-full flex-col items-start px-5 py-12 sm:px-8 lg:px-[100px] lg:py-16">
      <h2
        className={`${outfit.className} text-[30px] leading-[1.2] font-bold sm:text-[36px] lg:text-[44px] lg:leading-[50px]`}
        style={{ color: colors.neutral.black }}
      >
        건물주는 이런 문제를 마주합니다.
      </h2>
      <p className="pt-2 text-base leading-[1.7] text-gray-500 sm:text-lg sm:leading-[30px]">
        상권만으로는 내 공실에 맞는 업종을 판단하기 어렵습니다.
      </p>

      <div className="mx-auto grid w-full max-w-[1137px] grid-cols-1 gap-6 pt-10 md:grid-cols-2 lg:grid-cols-3 lg:gap-[60px]">
        {problems.map(({ id, number, tag, icon: Icon, title, description }) => (
          <Card key={id} className="w-full">
            <div className="flex w-full items-center justify-between">
              <p className={`${dmMono.className} text-[13px] text-gray-300`}>
                {number}
              </p>
              <Badge>{tag}</Badge>
            </div>

            <div className="pt-5 opacity-75">
              <Icon
                size={28}
                strokeWidth={1.5}
                style={{ color: colors.brand.primary }}
              />
            </div>

            <p
              className={`${outfit.className} w-full pt-4 text-[21px] leading-[1.3] font-bold sm:text-[23px] sm:leading-[30px]`}
              style={{ color: colors.neutral.black }}
            >
              {title}
            </p>

            <p className="w-full pt-2.5 text-[15px] leading-[22.95px] text-gray-500">
              {description}
            </p>
          </Card>
        ))}
      </div>
    </div>
  );
}
