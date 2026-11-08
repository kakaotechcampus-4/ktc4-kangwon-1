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

const WORD_GAP = /(\s+)(?![^【]*】)/;
const KEEP_ON_ONE_LINE = /[)\]】·@]/;
const EMAIL = /([\w.+-]+@[\w-]+(?:\.[\w-]+)+)/;

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
            <p className={BODY}>
              <Phrase text={doc.intro} />
            </p>
            <p className="text-15 text-[#4B5866] break-keep">
              시행일 {doc.effectiveDate}
            </p>
          </div>
        </div>

        {doc.sections.map((section, index) => {
          const headingId = `legal-section-${index + 1}`;
          return (
            <Card key={section.title} className="gap-4">
              <h2
                id={headingId}
                className="text-xl font-extrabold tracking-[-0.02em] break-keep"
                style={{ color: colors.brand.dark }}
              >
                {section.title}
              </h2>
              {section.paragraphs?.map((text) => (
                <p key={text} className={BODY}>
                  <Phrase text={text} />
                </p>
              ))}
              {section.table ? (
                <LegalTable labelledBy={headingId} table={section.table} />
              ) : null}
              {section.items ? (
                <ul className={`flex list-disc flex-col gap-2 pl-5 ${BODY}`}>
                  {section.items.map((item) => (
                    <li key={item}>
                      <Phrase text={item} />
                    </li>
                  ))}
                </ul>
              ) : null}
            </Card>
          );
        })}
      </main>
    </div>
  );
}

function LegalTable({
  labelledBy,
  table,
}: {
  labelledBy: string;
  table: NonNullable<LegalSection['table']>;
}) {
  const line = { borderColor: colors.neutral.border };
  const heading = { color: colors.brand.dark };
  const wide = table.head.length > 2;
  const minWidth = wide ? 'min-w-[600px]' : '';
  const headingWrap = wide ? 'whitespace-nowrap' : 'sm:whitespace-nowrap';
  return (
    <div
      role="region"
      aria-labelledby={labelledBy}
      tabIndex={0}
      className="overflow-x-auto rounded-2xl border"
      style={line}
    >
      <table
        aria-labelledby={labelledBy}
        className={`w-full border-collapse text-left text-15 leading-relaxed text-[#4B5866] break-keep ${minWidth}`}
      >
        <thead style={{ backgroundColor: colors.brand.wash }}>
          <tr>
            {table.head.map((cell) => (
              <th
                key={cell}
                scope="col"
                className={`px-4 py-3 font-bold ${headingWrap}`}
                style={heading}
              >
                <Phrase text={cell} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map(([rowHeading, ...cells]) => (
            <tr key={rowHeading} className="border-t" style={line}>
              <th
                scope="row"
                className={`px-4 py-3 align-top font-bold ${headingWrap}`}
                style={heading}
              >
                <Phrase text={rowHeading} />
              </th>
              {cells.map((cell, index) => (
                <td key={index} className="px-4 py-3 align-top">
                  <Phrase text={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Phrase({ text }: { text: string }) {
  return text.split(WORD_GAP).map((word, index) =>
    KEEP_ON_ONE_LINE.test(word) ? (
      <span key={index} className="whitespace-nowrap">
        {linkEmail(word)}
      </span>
    ) : (
      word
    )
  );
}

function linkEmail(word: string) {
  return word.split(EMAIL).map((part, index) =>
    index % 2 === 1 ? (
      <a
        key={index}
        href={`mailto:${part}`}
        className="underline underline-offset-2"
        style={{ color: colors.brand.primary }}
      >
        {part}
      </a>
    ) : (
      part
    )
  );
}
