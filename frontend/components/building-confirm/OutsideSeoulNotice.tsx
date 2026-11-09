import { ButtonLink } from '@/components/ui/Button';
import { colors } from '@/styles/tokens';
import AddressBanner from './AddressBanner';
import ConfirmLayout from './ConfirmLayout';
import SideCard from './SideCard';

const SEOUL_ONLY_REASONS = [
  '상권·유동인구 자료가 서울시 열린데이터광장 자료예요.',
  '서울 밖은 같은 기준의 자료가 없어 결과를 믿기 어려워요.',
  '다른 지역은 아직 준비 중이에요.',
];

type OutsideSeoulNoticeProps = {
  address: string;
  floorLabel: string;
};

export default function OutsideSeoulNotice({
  address,
  floorLabel,
}: OutsideSeoulNoticeProps) {
  return (
    <ConfirmLayout
      aside={
        <SideCard title="왜 서울만 분석하나요?" items={SEOUL_ONLY_REASONS} />
      }
      actions={
        <>
          <ButtonLink
            href="/"
            variant="outline"
            className="min-h-[52px] w-full break-keep sm:min-h-[60px] sm:w-auto sm:min-w-[176px]"
            style={{
              fontSize: 'var(--text-base)',
              color: colors.text.secondary,
            }}
          >
            홈으로
          </ButtonLink>
          <ButtonLink
            href="/vacancy-input"
            className="min-h-[52px] w-full break-keep sm:min-h-[60px] sm:w-auto"
            style={{ fontSize: 'var(--text-base)' }}
          >
            주소 다시 입력하기
          </ButtonLink>
        </>
      }
    >
      <AddressBanner
        title={address}
        floorLabel={floorLabel}
        tag="서울 밖 주소"
      />
      <div className="flex flex-col gap-2 px-4 pt-5 pb-4 sm:gap-3 sm:px-10 sm:pt-9 sm:pb-3">
        <h2
          className="text-lg font-bold break-keep sm:text-22"
          style={{ color: colors.text.primary }}
        >
          지금은 서울 상가만 분석할 수 있어요
        </h2>
        <p
          className="text-sm leading-relaxed break-keep sm:text-15"
          style={{ color: colors.text.secondary }}
        >
          상권·인구 자료가 서울시 공공데이터라서 서울 밖 주소는 정확하게 분석할
          수 없어요. 서울에 있는 상가 주소로 다시 입력해 주세요.
        </p>
      </div>
    </ConfirmLayout>
  );
}
