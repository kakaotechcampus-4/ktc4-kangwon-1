import Header from '@/components/layout/Header';
import Card from '@/components/ui/Card';
import { colors } from '@/styles/tokens';

export type LegalSection = {
  title: string;
  paragraphs?: string[];
  items?: string[];
  table?: { head: string[]; rows: string[][] };
};

export type LegalDoc = {
  eyebrow: string;
  title: string;
  effectiveDate: string;
  intro: string;
  sections: LegalSection[];
};

const BODY = 'text-base leading-relaxed text-[#4B5866] break-keep';

const WORD_JOINER = '\u2060';
const NO_BREAK_SPACE = '\u00a0';
const CLOSING_BEFORE_HANGUL = /([)\]】])(?=[가-힣])/g;
const MIDDLE_DOT = /·/g;
const PLACEHOLDER = /【[^】]*】/g;

function keepTogether(text: string) {
  return text
    .replace(CLOSING_BEFORE_HANGUL, `$1${WORD_JOINER}`)
    .replace(MIDDLE_DOT, `${WORD_JOINER}·${WORD_JOINER}`)
    .replace(PLACEHOLDER, (placeholder) =>
      placeholder.replace(/ /g, NO_BREAK_SPACE)
    );
}

export default function LegalDocument({ doc }: { doc: LegalDoc }) {
  return (
    <div
      className="flex min-h-screen flex-col"
      style={{ backgroundColor: colors.neutral.background }}
    >
      <Header />
      <main className="mx-auto flex w-full max-w-[880px] flex-col gap-8 px-4 pt-14 pb-24 sm:px-8">
        <div className="flex flex-col gap-3">
          <p
            className="text-15 font-bold tracking-[0.08em]"
            style={{ color: colors.brand.primary }}
          >
            {doc.eyebrow}
          </p>
          <h1
            className="font-extrabold tracking-[-0.04em] break-keep"
            style={{
              color: colors.brand.dark,
              fontSize: 'clamp(26px, 3vw, 42px)',
            }}
          >
            {doc.title}
          </h1>
          <div className="flex flex-col gap-1">
            <p className={BODY}>{keepTogether(doc.intro)}</p>
            <p className="text-15 text-[#4B5866] break-keep">
              시행일 {doc.effectiveDate}
            </p>
          </div>
        </div>

        {doc.sections.map((section) => (
          <Card key={section.title} className="gap-4">
            <h2
              className="text-xl font-extrabold tracking-[-0.02em] break-keep"
              style={{ color: colors.brand.dark }}
            >
              {section.title}
            </h2>
            {section.paragraphs?.map((text) => (
              <p key={text} className={BODY}>
                {keepTogether(text)}
              </p>
            ))}
            {section.table ? (
              <LegalTable title={section.title} table={section.table} />
            ) : null}
            {section.items ? (
              <ul className={`flex list-disc flex-col gap-2 pl-5 ${BODY}`}>
                {section.items.map((item) => (
                  <li key={item}>{keepTogether(item)}</li>
                ))}
              </ul>
            ) : null}
          </Card>
        ))}
      </main>
    </div>
  );
}

function LegalTable({
  title,
  table,
}: {
  title: string;
  table: NonNullable<LegalSection['table']>;
}) {
  const line = { borderColor: colors.neutral.border };
  const heading = { color: colors.brand.dark };
  return (
    <div
      role="region"
      aria-label={title}
      tabIndex={0}
      className="overflow-x-auto rounded-2xl border"
      style={line}
    >
      <table className="w-full min-w-[600px] border-collapse text-left text-15 leading-relaxed text-[#4B5866] break-keep">
        <thead style={{ backgroundColor: colors.brand.wash }}>
          <tr>
            {table.head.map((cell) => (
              <th
                key={cell}
                scope="col"
                className="px-4 py-3 font-bold whitespace-nowrap"
                style={heading}
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map(([rowHeading, ...cells]) => (
            <tr key={rowHeading} className="border-t" style={line}>
              <th
                scope="row"
                className="px-4 py-3 align-top font-bold whitespace-nowrap"
                style={heading}
              >
                {keepTogether(rowHeading)}
              </th>
              {cells.map((cell, index) => (
                <td key={index} className="px-4 py-3 align-top">
                  {keepTogether(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
