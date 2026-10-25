import type { LucideIcon } from 'lucide-react';
import { Building2, DoorOpen, Handshake, School, Sparkles } from 'lucide-react';
import Eyebrow from '@/components/landing/Eyebrow';
import { colors } from '@/styles/tokens';

/**
 * "이런 분들께 필요해요" — 실제 후기가 아니라 채움을 쓰는 상황 예시다.
 * 서비스가 MVP 단계라 사용자 후기 대신 상황과 리포트의 쓰임을 보여준다.
 * 카드는 옆으로 천천히 흐른다(globals.css .usecase-track).
 */
type UseCase = {
  Icon: LucideIcon;
  situation: string;
  detail: string;
  tag: string;
};

const useCases: UseCase[] = [
  {
    Icon: Building2,
    situation: '공실 6개월째인 2층 상가 건물주',
    detail:
      '2층이라 어떤 업종이 들어올 수 있을지 막막할 때, 층수와 면적 조건에 맞는 업종부터 추려 봅니다.',
    tag: '추천 · 비추천 업종',
  },
  {
    Icon: DoorOpen,
    situation: '임차인이 막 나간 1층 상가',
    detail:
      '같은 업종을 다시 들일지 고민될 때, 주변 동종 점포 수와 개업·폐업 흐름을 먼저 확인합니다.',
    tag: '경쟁업체 · 개폐업 추이',
  },
  {
    Icon: Sparkles,
    situation: '신축 상가를 처음 임대하는 건물주',
    detail:
      '동네 상권 정보가 없을 때, 시간대·연령대별 유동인구로 어떤 손님이 오가는지 살펴봅니다.',
    tag: '유동인구',
  },
  {
    Icon: School,
    situation: '학교 근처 상가를 가진 임대인',
    detail:
      '들이면 안 되는 업종이 있을까 걱정될 때, 입점 규제 대상 업종을 리포트에서 미리 표시해 줍니다.',
    tag: '입점 규제 확인',
  },
  {
    Icon: Handshake,
    situation: '중개사와 임차 조건을 상의하는 건물주',
    detail:
      '왜 이 업종이 맞는지 설명이 필요할 때, 추천 이유와 자료 출처를 리포트 그대로 보여줄 수 있습니다.',
    tag: '근거가 있는 리포트',
  },
];

function UseCaseCard({ item }: { item: UseCase }) {
  const { Icon } = item;
  return (
    <article className="flex w-[min(78vw,460px)] shrink-0 flex-col gap-5 rounded-[22px] bg-white p-8 shadow-[0_10px_30px_rgba(16,35,58,0.06)]">
      <div className="flex items-center gap-4">
        <span
          className="flex size-14 shrink-0 items-center justify-center rounded-full"
          style={{ backgroundColor: colors.brand.wash }}
        >
          <Icon
            size={26}
            strokeWidth={1.8}
            aria-hidden="true"
            color={colors.brand.primary}
          />
        </span>
        <div className="min-w-0">
          <p className="text-13 font-bold text-[#6B7886]">상황 예시</p>
          <h3
            className="mt-0.5 text-lg font-extrabold tracking-[-0.02em]"
            style={{ color: colors.brand.dark }}
          >
            {item.situation}
          </h3>
        </div>
      </div>
      <p className="text-base leading-[1.75] text-[#3F4A55]">{item.detail}</p>
      <span
        className="mt-auto self-start rounded-full px-3 py-1 text-13 font-bold"
        style={{
          backgroundColor: colors.brand.wash,
          color: colors.brand.primary,
        }}
      >
        {item.tag}
      </span>
    </article>
  );
}

export default function UseCases() {
  return (
    <section className="w-full overflow-hidden bg-[#DCEBF7] py-26">
      <div className="mx-auto max-w-[1120px] px-4 sm:px-8">
        <Eyebrow>WHO IT&apos;S FOR</Eyebrow>
        <h2
          className="mt-3.5 text-4xl font-extrabold tracking-[-0.02em]"
          style={{ color: colors.brand.dark }}
        >
          이런 분들께 필요해요
        </h2>
        <p className="mt-4 max-w-[560px] text-base leading-[1.7] text-[#4B5866]">
          공실 앞에서 자주 마주치는 고민들이에요. 채움 리포트가 어디서 답을 찾아
          주는지 상황별로 살펴보세요.
        </p>
      </div>

      <div className="usecase-viewport mt-14">
        <ul className="usecase-track flex w-max gap-6 px-4 sm:px-8">
          {useCases.map((item) => (
            <li key={item.situation} className="flex">
              <UseCaseCard item={item} />
            </li>
          ))}
          {/* 끊김 없이 흐르도록 같은 카드를 한 번 더 붙인다(보조기기에는 숨김). */}
          {useCases.map((item) => (
            <li
              key={`${item.situation}-copy`}
              className="usecase-copy flex"
              aria-hidden="true"
            >
              <UseCaseCard item={item} />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
