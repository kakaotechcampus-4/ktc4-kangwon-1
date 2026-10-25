import { Star } from 'lucide-react';
import PersonaAvatar from '@/components/landing/PersonaAvatar';
import {
  mockTestimonials,
  type Testimonial,
} from '@/lib/mockData/testimonials';
import { colors } from '@/styles/tokens';

/**
 * 랜딩 "사장님들의 이야기" — 후기 카드가 옆으로 천천히 흐른다
 * (globals.css .usecase-track). 지금은 목업 후기라 제목 아래에 예시 안내를 둔다.
 */
function TestimonialCard({ item }: { item: Testimonial }) {
  return (
    <article className="flex w-[min(80vw,480px)] shrink-0 flex-col gap-6 rounded-[22px] bg-white p-8 shadow-[0_10px_30px_rgba(16,35,58,0.06)]">
      <div className="flex items-center gap-4">
        <PersonaAvatar size={64} />
        <div className="min-w-0">
          <p className="text-15 font-bold" style={{ color: colors.brand.dark }}>
            {item.author}
          </p>
          <p
            className="mt-1.5 flex gap-1"
            role="img"
            aria-label={`별점 5점 만점에 ${item.rating}점`}
          >
            {Array.from({ length: 5 }, (_, index) => (
              <Star
                key={index}
                size={20}
                aria-hidden="true"
                fill={index < item.rating ? colors.brand.primary : '#D5DEE7'}
                strokeWidth={0}
              />
            ))}
          </p>
        </div>
      </div>
      <p className="text-base leading-[1.75] text-[#2B3440]">{item.body}</p>
    </article>
  );
}

export default function Testimonials() {
  if (mockTestimonials.length === 0) return null;

  return (
    <section className="w-full overflow-hidden bg-[#DCEBF7] py-26">
      <div className="mx-auto max-w-[1120px] px-4 sm:px-8">
        <p
          className="text-sm font-bold tracking-[0.08em]"
          style={{ color: colors.brand.primary }}
        >
          고객 사례
        </p>
        <h2
          className="mt-3.5 text-4xl font-extrabold tracking-[-0.02em]"
          style={{ color: colors.brand.dark }}
        >
          사장님들의 이야기
        </h2>
        <p className="mt-3 text-13 text-[#6B7886]">
          * 서비스 출시 전 화면 구성을 위한 예시 후기입니다.
        </p>
      </div>

      <div className="usecase-viewport mt-14">
        <ul className="usecase-track flex w-max gap-6 px-4 sm:px-8">
          {mockTestimonials.map((item) => (
            <li key={item.id} className="flex">
              <TestimonialCard item={item} />
            </li>
          ))}
          {/* 끊김 없이 흐르도록 같은 카드를 한 번 더 붙인다(보조기기에는 숨김). */}
          {mockTestimonials.map((item) => (
            <li
              key={`${item.id}-copy`}
              className="usecase-copy flex"
              aria-hidden="true"
            >
              <TestimonialCard item={item} />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
