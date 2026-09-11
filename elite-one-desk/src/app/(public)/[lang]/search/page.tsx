import Link from "next/link";
import { notFound } from "next/navigation";

import { Icon } from "@/components/ui/icon";
import { isLocale, localeHref } from "@/lib/i18n/config";
import { getDictionary } from "@/lib/i18n/dictionary";
import { search } from "@/lib/search";
import { buildMetadata } from "@/lib/seo";

type Props = {
  params: Promise<{ lang: string }>;
  searchParams: Promise<{ q?: string }>;
};

export async function generateMetadata({ params }: Props) {
  const { lang } = await params;
  if (!isLocale(lang)) return {};
  return buildMetadata({
    locale: lang,
    path: "/search",
    title: lang === "ar" ? "البحث" : "Search",
    // A results page has nothing durable to index.
    noindex: true,
  });
}

export default async function SearchPage({ params, searchParams }: Props) {
  const { lang } = await params;
  if (!isLocale(lang)) notFound();

  const { q } = await searchParams;
  const query = (q ?? "").slice(0, 120);
  const dict = getDictionary(lang);
  const results = query.trim() ? await search(query, lang) : [];

  return (
    <div className="shell shell-wide pb-[var(--spacing-section)] pt-[clamp(6.5rem,9vw,9rem)]">
      <h1 className="text-[length:var(--text-h1)]">{dict.nav.search}</h1>

      <form action={localeHref(lang, "/search")} method="get" className="mt-7 max-w-2xl">
        <label htmlFor="search-q" className="sr-only">
          {dict.nav.search}
        </label>
        <div className="panel flex items-center gap-2 p-2">
          <Icon name="search" size={18} className="ms-2.5 shrink-0 text-muted" />
          <input
            id="search-q"
            name="q"
            type="search"
            defaultValue={query}
            placeholder={dict.nav.searchPlaceholder}
            className="min-w-0 flex-1 bg-transparent py-2.5 text-strong outline-none placeholder:text-muted"
          />
          <button type="submit" className="btn btn-primary btn-sm">
            {dict.nav.search}
          </button>
        </div>
      </form>

      {query.trim() ? (
        results.length ? (
          <>
            <p className="mt-7 text-small text-muted">
              {lang === "ar"
                ? `${results.length} نتيجة لـ «${query}»`
                : `${results.length} result${results.length === 1 ? "" : "s"} for “${query}”`}
            </p>
            <ul className="mt-5 divide-y border-t" style={{ borderColor: "var(--border-color)" }}>
              {results.map((hit) => (
                <li key={`${hit.kind}-${hit.href}-${hit.title}`} className="border-b border-line">
                  <Link href={localeHref(lang, hit.href)} className="group block py-5">
                    <span className="text-[0.72rem] uppercase tracking-[0.12em] text-muted rtl:tracking-normal">
                      {hit.context}
                    </span>
                    <span className="mt-1.5 flex items-center gap-2 font-display text-[1rem] font-semibold text-strong">
                      {hit.title}
                      <Icon
                        name="arrowRight"
                        size={14}
                        className="flip-rtl opacity-0 transition-opacity group-hover:opacity-70"
                      />
                    </span>
                    {hit.excerpt ? (
                      <span className="mt-1.5 block max-w-3xl text-small text-muted">{hit.excerpt}</span>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <div className="mt-10 max-w-xl">
            <p className="text-[1.05rem] text-strong">{dict.common.noResults}</p>
            <p className="mt-2 text-small text-muted">{dict.common.noResultsHint}</p>
          </div>
        )
      ) : null}
    </div>
  );
}
