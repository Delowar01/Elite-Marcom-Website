import { getDictionary } from "@/lib/i18n/dictionary";
import type { Locale } from "@/lib/i18n/config";
import { pick } from "@/lib/i18n/config";
import { getMenu } from "@/lib/queries/site";
import { getSettings } from "@/lib/settings";
import { SiteNav, type NavLink } from "./site-nav";

/**
 * Server half of the header: it resolves the menu and settings, flattens the
 * bilingual rows down to the strings this language needs, and hands the result
 * to the interactive shell. The client bundle never receives the other
 * language's copy.
 */
export async function SiteHeader({ locale }: { locale: Locale }) {
  const [menu, settings] = await Promise.all([getMenu("header"), getSettings()]);
  const dict = getDictionary(locale);

  const links: NavLink[] = menu.map((item) => ({
    label: pick(locale, item.labelEn, item.labelAr),
    href: item.href,
    highlight: item.isHighlighted,
    children: item.children.map((child) => ({
      label: pick(locale, child.labelEn, child.labelAr),
      href: child.href,
      children: [],
    })),
  }));

  return (
    <SiteNav
      locale={locale}
      links={links}
      ctaHref="/contact"
      searchEnabled={settings.features.searchEnabled}
      arabicEnabled={settings.features.arabicEnabled}
      labels={{
        menu: dict.nav.menu,
        close: dict.nav.close,
        openMenu: dict.nav.openMenu,
        language: dict.nav.language,
        switchTo: dict.nav.switchTo,
        primaryCta: dict.nav.primaryCta,
        search: dict.nav.search,
        searchPlaceholder: dict.nav.searchPlaceholder,
      }}
    />
  );
}
