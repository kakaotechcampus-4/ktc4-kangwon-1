'use client';

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
    <div className="problem-container flex w-full flex-col items-start py-16">
      <h2
        className={`problem-headline ${outfit.className} font-bold`}
        style={{ color: colors.neutral.black }}
      >
        건물주는 이런 문제를 마주합니다.
      </h2>
      <p className="pt-2 text-lg leading-[30px] text-gray-500">
        상권만으로는 내 공실에 맞는 업종을 판단하기 어렵습니다.
      </p>

      <div className="problem-row mx-auto flex w-full pt-10">
        {problems.map(({ id, number, tag, icon: Icon, title, description }) => (
          <Card key={id} className="problem-card shrink-0">
            <div className="flex w-full items-center justify-between">
              <p
                className={`problem-number ${dmMono.className} text-gray-300`}
              >
                {number}
              </p>
              <Badge className="problem-badge">{tag}</Badge>
            </div>

            <div className="pt-5 opacity-75">
              <Icon
                size={28}
                strokeWidth={1.5}
                style={{ color: colors.brand.primary }}
              />
            </div>

            <p
              className={`problem-title ${outfit.className} w-full pt-4 font-bold`}
              style={{ color: colors.neutral.black }}
            >
              {title}
            </p>

            <p className="problem-desc w-full pt-2.5 text-gray-500">
              {description}
            </p>
          </Card>
        ))}
      </div>

      {/*
        375px~1337px 사이를 별도 구간 나누기 없이 하나의 1차식(clamp)으로
        처리한다. 두 기준점에서 "카드3 + gap*2 + 좌우여백*2 = 뷰포트 폭"이
        정확히 성립하도록 역산했기 때문에(375px: 101*3+16*2+20*2=375,
        1337px: 339*3+60*2+100*2=1337), 그 사이 어떤 폭에서도 이 등식이
        선형적으로 유지되어 카드 행이 화면보다 넘치거나 과도하게 남는
        여백이 생기지 않는다. clamp()가 375px 미만/1337px 초과 구간은
        각각 최소/최대값으로 고정해주므로 별도 @media 분기가 필요 없다.
      */}
      <style jsx global>{`
        /*
          섹션 헤드라인(h2, 44px)도 같은 375px~1337px clamp 패턴을 따른다.
          이 사이트의 다른 두 섹션 헤드라인(ValueSteps, ReportPreview)과
          정확히 동일한 min/slope/max를 공유해, 스크롤하며 세 헤드라인을
          지나갈 때 축소되는 느낌이 일관되도록 한다. line-height는 별도
          clamp 대신 font-size 값(--headline-fs)에 고정 비율(50/44)을 곱해
          계산해, 두 값이 항상 정확히 같은 비율로 함께 줄어든다.
        */
        .problem-headline {
          --headline-fs: clamp(
            26px,
            calc(26px + (100vw - 375px) * 0.018711),
            44px
          );
          font-size: var(--headline-fs);
          line-height: calc(var(--headline-fs) * 1.13636);
        }
        .problem-container {
          padding-inline: clamp(
            20px,
            calc(20px + (100vw - 375px) * 0.0832),
            100px
          );
        }
        .problem-row {
          max-width: 1137px;
          gap: clamp(16px, calc(16px + (100vw - 375px) * 0.04574), 60px);
        }
        .problem-card {
          width: clamp(101px, calc(101px + (100vw - 375px) * 0.2474), 339px);
        }
        .problem-title {
          font-size: clamp(
            14px,
            calc(14px + (100vw - 375px) * 0.00936),
            23px
          );
          line-height: clamp(
            20px,
            calc(20px + (100vw - 375px) * 0.0104),
            30px
          );
        }
        .problem-desc {
          font-size: clamp(
            11px,
            calc(11px + (100vw - 375px) * 0.00416),
            15px
          );
          line-height: clamp(
            16px,
            calc(16px + (100vw - 375px) * 0.00722),
            22.95px
          );
        }
        .problem-number {
          font-size: clamp(9px, calc(9px + (100vw - 375px) * 0.00416), 13px);
        }
        .problem-badge {
          font-size: clamp(7px, calc(7px + (100vw - 375px) * 0.00312), 10px);
        }
      `}</style>
    </div>
  );
}