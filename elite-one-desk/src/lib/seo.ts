import "server-only";

import type { Metadata } from "next";

import { siteUrl } from "@/lib/env";
import type { Locale } from "@/lib/i18n/config";
import { DEFAULT_LOCALE, localeHref, pick } from "@/lib/i18n/config";
import { getMediaMap } from "@/lib/queries/site";
import { getSeo } from "@/lib/queries/content";
import { getSettings } from "@/lib/settings";
import { mediaSrc } from "@/lib/media/url";
import { toPlainText } from "@/lib/cms/sanitize";

type BuildArgs = {
  locale: Locale;
  /** Canonical path without a language prefix, e.g. "/services/business-setup". */
  path: string;
  /** Looked up in seo_metadata; a row there overrides everything below. */
  entityType?: string;
  entityKey?: string;
  title?: string;
  description?: string;
  imageId?: number | null;
  noindex?: boolean;
  type?: "website" | "article";
};

const absolute = (path: string) => `${siteUrl}${path}`;

/**
 * One place builds every page's metadata, so a canonical, an OG tag and a
 * hreflang can never describe different addresses. The order is always:
 * an explicit override from the SEO screen, then the page's own values, then
 * the site defaults.
 */
export async function buildMetadata(args: BuildArgs): Promise<Metadata> {
  const settings = await getSettings();
  const override =
    args.entityType && args.entityKey ? await getSeo(args.entityType, args.entityKey) : null;

  const isArabic = args.locale === "ar";
  const template = isArabic ? settings.seo.titleTemplateAr : settings.seo.titleTemplateEn;
  const siteName = isArabic ? settings.brand.siteNameAr : settings.brand.siteNameEn;

  const rawTitle =
    pick(args.locale, override?.titleEn, override?.titleAr) ||
    args.title ||
    (isArabic ? settings.seo.defaultTitleAr : settings.seo.defaultTitleEn);

  const description =
    toPlainText(
      pick(args.locale, override?.descriptionEn, override?.descriptionAr) ||
        args.description ||
        (isArabic ? settings.seo.defaultDescriptionAr : settings.seo.defaultDescriptionEn),
      300,
    ) || undefined;

  // A page title already ending in the brand name is left alone rather than
  // repeating it.
  const title =
    rawTitle.includes(siteName) || !template
      ? rawTitle
      : template.replace("%s", rawTitle);

  const canonicalPath = override?.canonicalUrl || localeHref(args.locale, args.path);
  const canonical = canonicalPath.startsWith("http") ? canonicalPath : absolute(canonicalPath);

  const imageId = override?.ogImageId ?? args.imageId ?? settings.seo.ogImageId ?? null;
  let imageUrl = absolute("/brand/og-default.jpg");
  if (imageId) {
    const mediaMap = await getMediaMap();
    const found = mediaMap.get(imageId);
    if (found) imageUrl = absolute(mediaSrc(found, found.derivatives?.[2] ?? undefined));
  }

  const noindex = override?.noindex || args.noindex || false;

  const languages: Record<string, string> = {
    [DEFAULT_LOCALE]: absolute(localeHref(DEFAULT_LOCALE, args.path)),
    "x-default": absolute(localeHref(DEFAULT_LOCALE, args.path)),
  };
  if (settings.features.arabicEnabled) languages.ar = absolute(localeHref("ar", args.path));

  return {
    title,
    description,
    metadataBase: new URL(siteUrl),
    alternates: { canonical, languages },
    robots: noindex
      ? { index: false, follow: true }
      : { index: true, follow: true, "max-image-preview": "large" },
    openGraph: {
      type: args.type ?? "website",
      siteName,
      locale: isArabic ? "ar_SA" : "en_US",
      alternateLocale: isArabic ? "en_US" : "ar_SA",
      url: canonical,
      title: override?.ogTitle || title,
      description: override?.ogDescription || description,
      images: [{ url: imageUrl, width: 1200, height: 630, alt: siteName }],
    },
    twitter: {
      card: "summary_large_image",
      site: settings.seo.twitterHandle || undefined,
      title: override?.ogTitle || title,
      description: override?.ogDescription || description,
      images: [imageUrl],
    },
  };
}

/**
 * Organization data for the homepage. `Organization`, never `GovernmentOffice`
 * or anything that would imply an official role — §28 of the brief, and simply
 * true: Elite One Desk is an independent provider.
 */
export async function organizationJsonLd(locale: Locale) {
  const settings = await getSettings();
  const { contact, brand } = settings;
  const sameAs: string[] = [];

  const data: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: pick(locale, brand.legalNameEn, brand.legalNameAr),
    url: siteUrl,
    logo: absolute("/brand/logo-320.png"),
    image: absolute("/brand/og-default.jpg"),
    description: pick(
      locale,
      settings.seo.defaultDescriptionEn,
      settings.seo.defaultDescriptionAr,
    ),
  };

  if (contact.phone) {
    data.contactPoint = [
      {
        "@type": "ContactPoint",
        telephone: contact.phone,
        contactType: "customer service",
        availableLanguage: ["English", "Arabic"],
      },
    ];
  }
  if (contact.email) data.email = contact.email;

  const street = pick(locale, contact.addressEn, contact.addressAr);
  const city = pick(locale, contact.cityEn, contact.cityAr);
  if (street || city) {
    data.address = {
      "@type": "PostalAddress",
      streetAddress: street || undefined,
      addressLocality: city || undefined,
      addressCountry: "SA",
    };
  }
  if (sameAs.length) data.sameAs = sameAs;
  return data;
}

export function breadcrumbJsonLd(
  locale: Locale,
  trail: Array<{ name: string; path: string }>,
) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: trail.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: absolute(localeHref(locale, item.path)),
    })),
  };
}

export function faqJsonLd(entries: Array<{ question: string; answer: string }>) {
  if (!entries.length) return null;
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: entries.map((entry) => ({
      "@type": "Question",
      name: entry.question,
      acceptedAnswer: { "@type": "Answer", text: toPlainText(entry.answer, 900) },
    })),
  };
}
