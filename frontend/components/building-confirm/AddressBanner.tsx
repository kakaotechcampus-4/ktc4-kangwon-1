import { pretendard } from '@/styles/fonts';
import { colors } from '@/styles/tokens';

const dmMono = pretendard;

type AddressBannerProps = {
  title: string;
  floorLabel: string;
  tag: string;
  subtitle?: string;
  note?: string;
};

export default function AddressBanner({
  title,
  floorLabel,
  tag,
  subtitle,
  note,
}: AddressBannerProps) {
  return (
    <div
      className="flex flex-col items-start gap-3 px-4 py-5 sm:gap-4 sm:px-8 sm:py-7"
      style={{ backgroundColor: colors.brand.dark }}
    >
      <h2
        className="w-full font-bold leading-[1.4] break-keep"
        style={{
          color: colors.neutral.white,
          fontSize: 'clamp(1.25rem, 2vw, 1.875rem)',
          overflowWrap: 'normal',
        }}
      >
        {title}
      </h2>
      {subtitle && (
        <p
          className="text-sm break-keep"
          style={{ color: `${colors.neutral.white}CC` }}
        >
          {subtitle}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="rounded-md px-3 py-1.5 text-13 font-semibold"
          style={{
            backgroundColor: `${colors.neutral.white}14`,
            color: `${colors.neutral.white}E6`,
          }}
        >
          {floorLabel}
        </span>
        <span
          className={`${dmMono.className} shrink-0 rounded-md px-3 py-1.5 text-13 tracking-[1px]`}
          style={{
            backgroundColor: `${colors.neutral.white}14`,
            color: '#7F9BDC',
          }}
        >
          {tag}
        </span>
      </div>
      {note && (
        <p
          className="text-sm break-keep"
          style={{ color: `${colors.neutral.white}CC` }}
        >
          {note}
        </p>
      )}
    </div>
  );
}
