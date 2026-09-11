import { Counter } from "@/components/site/counter";
import { Reveal } from "@/components/site/reveal";
import { getBlock } from "@/lib/cms/blocks";
import { items, text } from "@/lib/cms/values";
import type { BlockProps } from "./context";

/**
 * Renders nothing until an owner has entered real figures — §47 is explicit
 * that unsupported statistics stay off, so an empty list is not an empty
 * section, it is no section.
 */
export function StatsBlock({ values, ctx }: BlockProps) {
  const { locale, settings } = ctx;
  if (!settings.features.showStats) return null;

  const def = getBlock("stats")!;
  const fields = def.fields.find((f) => f.name === "items")!.itemFields ?? [];
  const figures = items(values, "items", locale, fields).filter((f) => f.value?.trim());
  if (!figures.length) return null;

  return (
    <section className="section-tight">
      <div className="shell shell-wide">
        <ul className="grid gap-8 border-y border-line py-10 sm:grid-cols-2 lg:grid-cols-4">
          {figures.map((figure, index) => (
            <Reveal as="li" key={figure.label || index} delay={index * 70}>
              <Counter
                value={figure.value}
                className="block font-display text-[clamp(1.9rem,1.3rem+1.8vw,2.9rem)] font-bold leading-none text-strong"
              />
              <span className="mt-2.5 block text-small text-muted">{figure.label}</span>
            </Reveal>
          ))}
        </ul>
        {text(values, "title", locale) ? (
          <p className="mt-4 text-[0.78rem] text-muted">{text(values, "title", locale)}</p>
        ) : null}
      </div>
    </section>
  );
}
