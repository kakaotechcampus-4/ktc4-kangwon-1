import Link from 'next/link';
import Button from '@/components/ui/Button';
import Card from '@/components/ui/Card';
import { colors } from '@/styles/tokens';

export type NoticeLink = { href: string; label: string };

export default function StateNotice({
  title,
  description,
  links,
  onRetry,
  busy = false,
}: {
  title: string;
  description: string;
  links: NoticeLink[];
  onRetry?: () => void;
  busy?: boolean;
}) {
  return (
    <Card className="items-start gap-4" role={busy ? 'status' : undefined}>
      <p
        className="text-xl font-extrabold tracking-[-0.02em]"
        style={{ color: colors.brand.dark }}
      >
        {title}
      </p>
      {description ? (
        <p className="text-15 text-[#4B5866]">{description}</p>
      ) : null}
      {onRetry || links.length > 0 ? (
        <div className="flex flex-wrap gap-3">
          {onRetry ? (
            <Button type="button" variant="primary" onClick={onRetry}>
              다시 불러오기
            </Button>
          ) : null}
          {links.map((link, index) => (
            <Link key={link.href} href={link.href}>
              <Button
                type="button"
                variant={index === 0 && !onRetry ? 'primary' : 'outline'}
              >
                {link.label}
              </Button>
            </Link>
          ))}
        </div>
      ) : null}
    </Card>
  );
}
