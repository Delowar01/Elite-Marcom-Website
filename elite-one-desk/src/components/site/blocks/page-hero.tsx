import { MediaImage } from "@/components/site/media-image";
import { mediaId, text } from "@/lib/cms/values";
import type { BlockProps } from "./context";

export function PageHeroBlock({ values, ctx, index }: BlockProps) {
  const { locale } = ctx;
  const eyebrow = text(values, "eyebrow", locale);
  const title = text(values, "title", locale);
  const lead = text(values, "lead", locale);
  const background = ctx.media.get(mediaId(values, "backgroundImage") ?? -1) ?? null;
  const Heading = index === 0 ? "h1" : "h2";

  return (
    <section className="relative overflow-clip pb-[clamp(2.5rem,4vw,4rem)] pt-[clamp(6.5rem,9vw,9rem)]">
      {background ? (
        <div className="pointer-events-none absolute inset-0 -z-20">
          <MediaImage
            media={background}
            locale={locale}
            alt=""
            sizes="100vw"
            priority
            className="size-full object-cover opacity-30"
          />
          <div
            className="absolute inset-0"
            style={{
              background:
                "linear-gradient(to bottom, color-mix(in oklab, var(--color-ink-900) 80%, transparent), var(--color-ink-800))",
            }}
          />
        </div>
      ) : (
        <div className="grid-texture pointer-events-none absolute inset-0 -z-10" />
      )}

      <div className="shell shell-wide">
        {eyebrow ? (
          <p className="eyebrow motion-safe:animate-[eod-fade-up_.7s_var(--ease-out-expo)_both]">{eyebrow}</p>
        ) : null}
        <Heading className="mt-5 max-w-4xl text-[length:var(--text-h1)] motion-safe:animate-[eod-fade-up_.8s_var(--ease-out-expo)_.06s_both]">
          {title}
        </Heading>
        {lead ? (
          <p className="lede mt-5 max-w-2xl motion-safe:animate-[eod-fade-up_.8s_var(--ease-out-expo)_.14s_both]">
            {lead}
          </p>
        ) : null}
      </div>
    </section>
  );
}
