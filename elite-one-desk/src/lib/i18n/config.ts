export const LOCALES = ["en", "ar"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";

export const isLocale = (value: string): value is Locale =>
  (LOCALES as readonly string[]).includes(value);

export const dirOf = (locale: Locale) => (locale === "ar" ? "rtl" : "ltr");

export const LOCALE_LABELS: Record<Locale, { native: string; english: string }> = {
  en: { native: "English", english: "English" },
  ar: { native: "العربية", english: "Arabic" },
};

/**
 * English lives at the site root and Arabic under /ar. `path` is always the
 * canonical, unprefixed route ("/services/business-setup"), so a link written
 * once works in both editions.
 */
export function localeHref(locale: Locale, path: string): string {
  const clean = path.startsWith("/") ? path : `/${path}`;
  if (locale === DEFAULT_LOCALE) return clean === "/" ? "/" : clean.replace(/\/$/, "");
  return clean === "/" ? "/ar" : `/ar${clean.replace(/\/$/, "")}`;
}

/** Strips a language prefix back off, for the language switcher. */
export function stripLocale(pathname: string): string {
  const withoutPrefix = pathname.replace(/^\/(ar|en)(?=\/|$)/, "");
  return withoutPrefix === "" ? "/" : withoutPrefix;
}

/**
 * Arabic content is optional everywhere. An empty Arabic field falls back to
 * English rather than rendering a hole, which is what lets the Arabic edition
 * go live while translation is still in progress.
 */
export function pick(locale: Locale, en: string | null | undefined, ar: string | null | undefined): string {
  if (locale === "ar") return (ar ?? "").trim() || (en ?? "").trim();
  return (en ?? "").trim();
}

/**
 * Plural forms. English needs two; Arabic distinguishes one, two, a few (3–10)
 * and many (11+), and using the wrong one is immediately audible to a reader.
 * Falls back through the chain, so a dictionary entry that only defines `other`
 * still works.
 */
export type PluralForms = {
  one?: string;
  two?: string;
  few?: string;
  many?: string;
  other: string;
};

export function plural(locale: Locale, forms: PluralForms, n: number): string {
  const pick = (): string => {
    if (locale === "ar") {
      const mod100 = n % 100;
      if (n === 1) return forms.one ?? forms.other;
      if (n === 2) return forms.two ?? forms.other;
      if (mod100 >= 3 && mod100 <= 10) return forms.few ?? forms.other;
      return forms.many ?? forms.other;
    }
    return n === 1 ? (forms.one ?? forms.other) : forms.other;
  };
  return pick().replace("{n}", String(n));
}
