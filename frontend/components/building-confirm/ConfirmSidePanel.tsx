import Card from '@/components/ui/Card';
import { colors } from '@/styles/tokens';

const REASONS = [
  '내 상가는 임대인이 가장 잘 알아요.',
  '건축물대장 기재가 실제와 다를 수 있어요.',
  '건축물대장에 없는 칸(주차 등)은 직접 채워 주세요.',
];

type Judgement = {
  tag: string;
  tone: 'danger' | 'warning' | 'muted';
  text: string;
};

const JUDGEMENTS: Judgement[] = [
  {
    tag: '불가능',
    tone: 'danger',
    text: '제1종 근린생활시설 건물에서는 술을 파는 일반음식점이 안 돼요.',
  },
  {
    tag: '불가능',
    tone: 'danger',
    text: '강의실이 30㎡ 이상이어야 해서 전용 30㎡ 미만이면 학원 등록이 안 돼요.',
  },
  {
    tag: '추천 안 함',
    tone: 'warning',
    text: '주차가 없으면 병원·대형 음식점은 불리해요.',
  },
  {
    tag: '확인 필요',
    tone: 'muted',
    text: '모르는 칸이 있으면 억지로 판단하지 않고 따로 표시해요.',
  },
];

const TONE_STYLES: Record<Judgement['tone'], { bg: string; color: string }> = {
  danger: {
    bg: `${colors.status.notRecommend}1A`,
    color: colors.status.notRecommend,
  },
  warning: { bg: `${colors.accent.orange}1A`, color: colors.accent.orange },
  muted: { bg: colors.neutral.background, color: colors.text.secondary },
};

// 여백은 화면 폭에 따라 --card-pad로 바꾼다(Card 기본 p-7보다 style이 우선한다).
const CARD_STYLE = {
  padding: 'var(--card-pad)',
  borderRadius: '24px',
  borderWidth: '0px',
};

const CARD_CLASS = 'w-full gap-5 [--card-pad:20px] sm:[--card-pad:32px]';

/** 확인 화면 오른쪽 정적 안내 패널 2개. */
export default function ConfirmSidePanel() {
  return (
    // 태블릿 폭에서는 카드 아래에 두 패널을 나란히, 넓은 화면에서는 오른쪽에 세로로 쌓는다.
    <div className="grid w-full items-start gap-6 md:grid-cols-2 lg:grid-cols-1">
      <Card className={CARD_CLASS} style={CARD_STYLE}>
        <p className="text-xl font-bold" style={{ color: colors.text.primary }}>
          왜 먼저 확인하나요?
        </p>
        <ul
          className="flex list-disc flex-col gap-3 pl-5 text-base"
          style={{ color: colors.text.secondary }}
        >
          {REASONS.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
        <p
          className="text-13 leading-relaxed"
          style={{ color: colors.text.tertiary }}
        >
          고친 값은 법적 판단의 근거가 아니라서 리포트에 “확인 필요”로 남겨요.
        </p>
      </Card>

      <Card className={CARD_CLASS} style={CARD_STYLE}>
        <p className="text-xl font-bold" style={{ color: colors.text.primary }}>
          이 정보로 이런 걸 판단해요
        </p>
        <ul className="flex flex-col gap-4">
          {JUDGEMENTS.map(({ tag, tone, text }) => (
            <li key={text} className="flex items-start gap-3">
              <span
                className="shrink-0 rounded-md px-2 py-1 text-13 font-semibold whitespace-nowrap"
                style={{
                  backgroundColor: TONE_STYLES[tone].bg,
                  color: TONE_STYLES[tone].color,
                }}
              >
                {tag}
              </span>
              <p
                className="text-15 leading-relaxed"
                style={{ color: colors.text.secondary }}
              >
                {text}
              </p>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
