import { FaqAccordion, type FaqEntry } from "@/components/site/faq-accordion";
import { JsonLd } from "@/components/site/json-ld";
import { SectionHeading } from "@/components/site/section-heading";
import { faqJsonLd } from "@/lib/seo";
import { num, str, text } from "@/lib/cms/values";
import { pick } from "@/lib/i18n/config";
import type { BlockProps } from "./context";

export async function FaqBlock({ values, ctx }: BlockProps) {
  const { locale, dict } = ctx;
  const scope = str(values, "scope", "global");
  const limit = num(values, "limit", 8);

  const rows = ctx.faqs
    .filter((faq) => (scope === "all" ? true : faq.scope === "global"))
    .slice(0, limit > 0 ? limit : undefined);
  if (!rows.length) return null;

  const entries: FaqEntry[] = rows.map((row) => ({
    id: row.id,
    question: pick(locale, row.questionEn, row.questionAr),
    answer: pick(locale, row.answerEn, row.answerAr),
  }));

  const schema = faqJsonLd(entries);

  return (
    <section className="section">
      <div className="shell shell-wide grid gap-10 lg:grid-cols-[0.75fr_1.25fr] lg:gap-16">
        <div className="lg:sticky lg:top-28 lg:self-start">
          <SectionHeading
            eyebrow={text(values, "eyebrow", locale) || dict.sections.faqEyebrow}
            title={text(values, "title", locale)}
          />
        </div>
        <div>
          <FaqAccordion entries={entries} />
        </div>
      </div>
      {schema ? <JsonLd data={schema} /> : null}
    </section>
  );
}
