import "server-only";

import { toPlainText } from "@/lib/cms/sanitize";
import type { Locale } from "@/lib/i18n/config";
import { pick } from "@/lib/i18n/config";
import { getCatalog, getFaqs, getPackages } from "@/lib/queries/catalog";

export type SearchHit = {
  kind: "service" | "category" | "package" | "faq";
  title: string;
  excerpt: string;
  href: string;
  context: string;
  score: number;
};

/**
 * Search runs over the cached catalogue in memory rather than against Postgres.
 * The whole searchable corpus is a few hundred short records that are already
 * loaded for other pages, so a query costs no round trip — and it works the
 * same for Arabic, where a Postgres English text-search configuration would
 * quietly stem nothing.
 */
const normalise = (value: string) =>
  value
    .toLowerCase()
    .normalize("NFKD")
    // Strip Arabic diacritics and unify alef forms, so "الإقامة" matches "اقامة".
    .replace(/[ً-ْٰ]/g, "")
    .replace(/[آأإ]/g, "ا")
    .replace(/ة/g, "ه")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();

function score(terms: string[], weighted: Array<{ text: string; weight: number }>): number {
  let total = 0;
  for (const { text, weight } of weighted) {
    const haystack = normalise(text);
    if (!haystack) continue;
    for (const term of terms) {
      if (!haystack.includes(term)) continue;
      // A word-boundary hit is worth more than a substring buried in a sentence.
      const exact = new RegExp(`(^|\\s)${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`).test(haystack);
      total += weight * (exact ? 2 : 1);
    }
  }
  return total;
}

export async function search(query: string, locale: Locale): Promise<SearchHit[]> {
  const terms = normalise(query).split(" ").filter((t) => t.length > 1);
  if (!terms.length) return [];

  const [catalog, packages, faqs] = await Promise.all([getCatalog(), getPackages(), getFaqs()]);
  const categoryById = new Map(catalog.categories.map((c) => [c.id, c]));
  const hits: SearchHit[] = [];

  for (const category of catalog.categories) {
    const title = pick(locale, category.titleEn, category.titleAr);
    const summary = pick(locale, category.summaryEn, category.summaryAr);
    const value = score(terms, [
      { text: title, weight: 10 },
      { text: pick(locale, category.taglineEn, category.taglineAr), weight: 4 },
      { text: summary, weight: 2 },
    ]);
    if (value > 0) {
      hits.push({
        kind: "category",
        title,
        excerpt: toPlainText(summary, 180),
        href: `/services/${category.slug}`,
        context: locale === "ar" ? "فئة" : "Category",
        score: value + 3,
      });
    }
  }

  for (const service of catalog.services) {
    const category = categoryById.get(service.categoryId);
    if (!category) continue;
    const title = pick(locale, service.titleEn, service.titleAr);
    const intro = pick(locale, service.introEn, service.introAr);
    const value = score(terms, [
      { text: title, weight: 10 },
      { text: intro, weight: 3 },
      { text: toPlainText(pick(locale, service.bodyEn, service.bodyAr)), weight: 1 },
    ]);
    if (value > 0) {
      hits.push({
        kind: "service",
        title,
        excerpt: toPlainText(intro, 180),
        href: `/services/${category.slug}/${service.slug}`,
        context: pick(locale, category.titleEn, category.titleAr),
        score: value + (service.isFeatured ? 2 : 0),
      });
    }
  }

  for (const row of packages) {
    const title = pick(locale, row.titleEn, row.titleAr);
    const summary = pick(locale, row.summaryEn, row.summaryAr);
    const value = score(terms, [
      { text: title, weight: 9 },
      { text: pick(locale, row.destinationEn, row.destinationAr), weight: 6 },
      { text: summary, weight: 2 },
    ]);
    if (value > 0) {
      hits.push({
        kind: "package",
        title,
        excerpt: toPlainText(summary, 180),
        href: `/packages/${row.slug}`,
        context: locale === "ar" ? "برنامج" : "Package",
        score: value,
      });
    }
  }

  for (const faq of faqs) {
    const question = pick(locale, faq.questionEn, faq.questionAr);
    const answer = pick(locale, faq.answerEn, faq.answerAr);
    const value = score(terms, [
      { text: question, weight: 7 },
      { text: toPlainText(answer), weight: 2 },
    ]);
    if (value > 0) {
      const service = faq.serviceId ? catalog.services.find((s) => s.id === faq.serviceId) : null;
      const category = service ? categoryById.get(service.categoryId) : null;
      hits.push({
        kind: "faq",
        title: question,
        excerpt: toPlainText(answer, 200),
        href:
          service && category
            ? `/services/${category.slug}/${service.slug}`
            : "/contact",
        context: locale === "ar" ? "سؤال شائع" : "FAQ",
        score: value,
      });
    }
  }

  return hits.sort((a, b) => b.score - a.score || a.title.localeCompare(b.title)).slice(0, 40);
}
