import { Reveal } from "@/components/site/reveal";
import { SectionHeading } from "@/components/site/section-heading";
import { getBlock } from "@/lib/cms/blocks";
import { items, text } from "@/lib/cms/values";
import type { BlockProps } from "./context";

/**
 * How it works. A sticky heading beside a stepped column rather than a basic
 * timeline: the numbers stay in view while the steps scroll past them, which is
 * the "visually modern rather than a basic timeline" the brief asks for.
 */
export function ProcessBlock({ values, ctx }: BlockProps) {
  const { locale, dict } = ctx;
  const def = getBlock("process")!;
  const fields = def.fields.find((f) => f.name === "steps")!.itemFields ?? [];
  const steps = items(values, "steps", locale, fields);
  if (!steps.length) return null;

  return (
    <section className="section">
      <div className="shell shell-wide grid gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:gap-16">
        <div className="lg:sticky lg:top-28 lg:self-start">
          <SectionHeading
            eyebrow={text(values, "eyebrow", locale) || dict.sections.processEyebrow}
            title={text(values, "title", locale)}
          />
        </div>

        <ol className="relative">
          {/* The spine the numbers sit on. */}
          <span
            aria-hidden
            className="absolute inset-y-0 w-px"
            style={{ insetInlineStart: "1.375rem", background: "var(--border-color)" }}
          />
          {steps.map((step, index) => (
            <Reveal as="li" key={step.label} delay={index * 70} className="relative ps-14 pb-9 last:pb-0">
              <span
                className="absolute top-0 flex size-11 items-center justify-center rounded-full border font-display text-[0.78rem] font-bold tabular-nums"
                style={{
                  insetInlineStart: 0,
                  borderColor: "color-mix(in oklab, var(--color-orange) 45%, transparent)",
                  background: "var(--color-ink-800)",
                  color: "var(--color-peach)",
                }}
              >
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="pt-2.5 text-[length:var(--text-h3)]">{step.label}</h3>
              {step.text ? <p className="mt-2 max-w-xl text-body">{step.text}</p> : null}
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  );
}
