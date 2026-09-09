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
    <div className="flex w-full flex-col items-start px-[100px] py-16">
      <h2
        className={`${outfit.className} text-[44px] leading-[50px] font-bold`}
        style={{ color: colors.neutral.black }}
      >
        건물주는 이런 문제를 마주합니다.
      </h2>
      <p className="pt-2 text-lg leading-[30px] text-gray-500">
        상권만으로는 내 공실에 맞는 업종을 판단하기 어렵습니다.
      </p>

      <div className="mx-auto flex w-[1137px] gap-[60px] pt-10">
        {problems.map(({ id, number, tag, icon: Icon, title, description }) => (
          <Card key={id} className="w-[339px] shrink-0">
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
              className={`${outfit.className} w-[280px] pt-4 text-[23px] leading-[30px] font-bold`}
              style={{ color: colors.neutral.black }}
            >
              {title}
            </p>

            <p className="w-[280px] pt-2.5 text-[15px] leading-[22.95px] text-gray-500">
              {description}
            </p>
          </Card>
        ))}
      </div>
    </div>
  );
}
