"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { Icon } from "@/components/ui/icon";
import { Logo } from "@/components/ui/logo";
import type { Locale } from "@/lib/i18n/config";
import { DEFAULT_LOCALE, localeHref, stripLocale } from "@/lib/i18n/config";

export type NavLink = { label: string; href: string; children: NavLink[]; highlight?: boolean };

type Labels = {
  menu: string;
  close: string;
  openMenu: string;
  language: string;
  switchTo: string;
  primaryCta: string;
  search: string;
  searchPlaceholder: string;
};

type Props = {
  locale: Locale;
  links: NavLink[];
  labels: Labels;
  ctaHref: string;
  searchEnabled: boolean;
  arabicEnabled: boolean;
};

/**
 * The header is one component for both breakpoints because the state it holds —
 * which dropdown is open, whether the sheet is showing, whether the page has
 * scrolled — has to stay in step across a resize.
 */
export function SiteNav({ locale, links, labels, ctaHref, searchEnabled, arabicEnabled }: Props) {
  const pathname = usePathname();
  const current = stripLocale(pathname ?? "/");
  const [scrolled, setScrolled] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const reduceMotion = useReducedMotion();
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Route changes close everything; otherwise the sheet survives navigation.
  useEffect(() => {
    setSheetOpen(false);
    setOpenDropdown(null);
    setSearchOpen(false);
  }, [pathname]);

  // The sheet and the search dialog both trap the page behind them.
  useEffect(() => {
    const locked = sheetOpen || searchOpen;
    document.documentElement.style.overflow = locked ? "hidden" : "";
    return () => {
      document.documentElement.style.overflow = "";
    };
  }, [sheetOpen, searchOpen]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setSheetOpen(false);
      setSearchOpen(false);
      setOpenDropdown(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const isActive = useCallback(
    (href: string) => href !== "/" && (current === href || current.startsWith(`${href}/`)),
    [current],
  );

  const otherLocale: Locale = locale === "ar" ? DEFAULT_LOCALE : "ar";
  const languageHref = localeHref(otherLocale, current);

  const hoverOpen = (key: string) => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setOpenDropdown(key);
  };
  const hoverClose = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => setOpenDropdown(null), 140);
  };

  return (
    <>
      <header
        data-scrolled={scrolled}
        className="fixed inset-x-0 top-0 z-50 transition-[background-color,border-color,backdrop-filter] duration-300 border-b border-transparent data-[scrolled=true]:border-line data-[scrolled=true]:bg-[color-mix(in_oklab,var(--color-ink-900)_86%,transparent)] data-[scrolled=true]:backdrop-blur-xl"
      >
        <div className="shell shell-wide flex items-center gap-4 py-3.5 data-[scrolled=true]:py-2.5 lg:gap-8">
          <Link
            href={localeHref(locale, "/")}
            className="shrink-0 transition-opacity hover:opacity-85"
            aria-label="Elite One Desk"
          >
            <Logo height={scrolled ? 34 : 40} priority className="transition-all duration-300" />
          </Link>

          <nav aria-label="Main" className="hidden flex-1 items-center justify-center lg:flex">
            <ul className="flex items-center gap-0.5">
              {links.map((link) => {
                const active = isActive(link.href);
                const hasChildren = link.children.length > 0;
                return (
                  <li
                    key={link.href}
                    className="relative"
                    onMouseEnter={() => hasChildren && hoverOpen(link.href)}
                    onMouseLeave={hoverClose}
                  >
                    <Link
                      href={localeHref(locale, link.href)}
                      aria-current={active ? "page" : undefined}
                      aria-expanded={hasChildren ? openDropdown === link.href : undefined}
                      onFocus={() => hasChildren && hoverOpen(link.href)}
                      className="group relative flex items-center gap-1.5 rounded-full px-3.5 py-2 text-[0.875rem] font-medium text-body transition-colors hover:text-strong aria-[current=page]:text-strong"
                    >
                      {link.label}
                      {hasChildren ? (
                        <Icon
                          name="chevronDown"
                          size={13}
                          className="opacity-60 transition-transform duration-200 group-aria-expanded:rotate-180"
                        />
                      ) : null}
                      <span
                        aria-hidden
                        data-active={active}
                        className="pointer-events-none absolute inset-x-3.5 -bottom-0.5 h-px origin-[inline-start] scale-x-0 bg-orange transition-transform duration-300 data-[active=true]:scale-x-100 group-hover:scale-x-100"
                        style={{ backgroundColor: "var(--color-orange)" }}
                      />
                    </Link>

                    <AnimatePresence>
                      {hasChildren && openDropdown === link.href ? (
                        <motion.div
                          initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={reduceMotion ? undefined : { opacity: 0, y: 6 }}
                          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                          onMouseEnter={() => hoverOpen(link.href)}
                          onMouseLeave={hoverClose}
                          className="absolute inset-inline-start-0 top-full z-10 pt-3"
                          style={{ insetInlineStart: 0 }}
                        >
                          <ul className="panel min-w-62 overflow-hidden p-2 shadow-[var(--shadow-lift)]">
                            {link.children.map((child) => (
                              <li key={child.href}>
                                <Link
                                  href={localeHref(locale, child.href)}
                                  className="flex items-center justify-between gap-6 rounded-[var(--radius-sm)] px-3 py-2.5 text-[0.85rem] text-body transition-colors hover:bg-[color-mix(in_oklab,var(--color-warm)_7%,transparent)] hover:text-strong"
                                >
                                  {child.label}
                                  <Icon name="chevronRight" size={13} className="flip-rtl opacity-45" />
                                </Link>
                              </li>
                            ))}
                          </ul>
                        </motion.div>
                      ) : null}
                    </AnimatePresence>
                  </li>
                );
              })}
            </ul>
          </nav>

          <div className="ms-auto flex items-center gap-1.5 lg:ms-0">
            {searchEnabled ? (
              <button
                type="button"
                onClick={() => setSearchOpen(true)}
                aria-label={labels.search}
                className="flex size-9.5 items-center justify-center rounded-full border border-line text-body transition-colors hover:border-[color-mix(in_oklab,var(--color-peach)_55%,transparent)] hover:text-strong"
              >
                <Icon name="search" size={17} />
              </button>
            ) : null}

            {arabicEnabled ? (
              <Link
                href={languageHref}
                lang={otherLocale}
                hrefLang={otherLocale}
                aria-label={`${labels.language}: ${labels.switchTo}`}
                className="hidden h-9.5 items-center rounded-full border border-line px-3.5 text-[0.8rem] font-medium text-body transition-colors hover:border-[color-mix(in_oklab,var(--color-peach)_55%,transparent)] hover:text-strong sm:flex"
              >
                {labels.switchTo}
              </Link>
            ) : null}

            <Link href={localeHref(locale, ctaHref)} className="btn btn-primary btn-sm hidden md:inline-flex">
              {labels.primaryCta}
            </Link>

            <button
              type="button"
              onClick={() => setSheetOpen(true)}
              aria-label={labels.openMenu}
              aria-expanded={sheetOpen}
              className="flex size-9.5 items-center justify-center rounded-full border border-line text-strong lg:hidden"
            >
              <Icon name="menu" size={18} />
            </button>
          </div>
        </div>
      </header>

      <MobileSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        links={links}
        locale={locale}
        labels={labels}
        ctaHref={ctaHref}
        languageHref={languageHref}
        otherLocale={otherLocale}
        arabicEnabled={arabicEnabled}
        isActive={isActive}
      />

      {searchEnabled ? (
        <SearchDialog
          open={searchOpen}
          onClose={() => setSearchOpen(false)}
          locale={locale}
          labels={labels}
        />
      ) : null}
    </>
  );
}

/* -------------------------------------------------------------------------- */

function MobileSheet({
  open,
  onClose,
  links,
  locale,
  labels,
  ctaHref,
  languageHref,
  otherLocale,
  arabicEnabled,
  isActive,
}: {
  open: boolean;
  onClose: () => void;
  links: NavLink[];
  locale: Locale;
  labels: Labels;
  ctaHref: string;
  languageHref: string;
  otherLocale: Locale;
  arabicEnabled: boolean;
  isActive: (href: string) => boolean;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const reduceMotion = useReducedMotion();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) panelRef.current?.focus();
  }, [open]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          key="sheet"
          className="fixed inset-0 z-60 lg:hidden"
          initial={reduceMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduceMotion ? undefined : { opacity: 0 }}
          transition={{ duration: 0.22 }}
        >
          <button
            type="button"
            aria-label={labels.close}
            onClick={onClose}
            className="absolute inset-0 bg-[color-mix(in_oklab,var(--color-ink-900)_88%,transparent)] backdrop-blur-sm"
          />
          <motion.div
            ref={panelRef}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-label={labels.menu}
            initial={reduceMotion ? false : { y: "-4%", opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={reduceMotion ? undefined : { y: "-3%", opacity: 0 }}
            transition={{ duration: 0.34, ease: [0.16, 1, 0.3, 1] }}
            className="absolute inset-x-0 top-0 max-h-dvh overflow-y-auto bg-[var(--color-ink-800)] pb-10 outline-none"
          >
            <div className="shell flex items-center justify-between py-3.5">
              <Logo height={36} />
              <button
                type="button"
                onClick={onClose}
                aria-label={labels.close}
                className="flex size-10 items-center justify-center rounded-full border border-line text-strong"
              >
                <Icon name="close" size={18} />
              </button>
            </div>

            <nav aria-label={labels.menu} className="shell mt-3">
              <ul className="divide-y" style={{ borderColor: "var(--border-color)" }}>
                {links.map((link, index) => {
                  const hasChildren = link.children.length > 0;
                  const isOpen = expanded === link.href;
                  return (
                    <motion.li
                      key={link.href}
                      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.05 + index * 0.035, duration: 0.36, ease: [0.16, 1, 0.3, 1] }}
                      className="border-b border-line"
                    >
                      <div className="flex items-center">
                        <Link
                          href={localeHref(locale, link.href)}
                          aria-current={isActive(link.href) ? "page" : undefined}
                          className="flex-1 py-4 font-display text-[1.05rem] font-semibold text-strong"
                        >
                          {link.label}
                        </Link>
                        {hasChildren ? (
                          <button
                            type="button"
                            onClick={() => setExpanded(isOpen ? null : link.href)}
                            aria-expanded={isOpen}
                            aria-label={link.label}
                            className="flex size-10 items-center justify-center rounded-full text-body"
                          >
                            <Icon
                              name="chevronDown"
                              size={16}
                              style={{ transform: isOpen ? "rotate(180deg)" : undefined, transition: "transform .2s" }}
                            />
                          </button>
                        ) : null}
                      </div>
                      <AnimatePresence initial={false}>
                        {hasChildren && isOpen ? (
                          <motion.ul
                            initial={reduceMotion ? false : { height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={reduceMotion ? undefined : { height: 0, opacity: 0 }}
                            transition={{ duration: 0.26, ease: [0.16, 1, 0.3, 1] }}
                            className="overflow-hidden ps-3"
                          >
                            {link.children.map((child) => (
                              <li key={child.href}>
                                <Link
                                  href={localeHref(locale, child.href)}
                                  className="block py-2.5 text-[0.9rem] text-body"
                                >
                                  {child.label}
                                </Link>
                              </li>
                            ))}
                            <li className="h-2" />
                          </motion.ul>
                        ) : null}
                      </AnimatePresence>
                    </motion.li>
                  );
                })}
              </ul>

              <div className="mt-7 flex flex-col gap-3">
                <Link href={localeHref(locale, ctaHref)} className="btn btn-primary w-full">
                  {labels.primaryCta}
                </Link>
                {arabicEnabled ? (
                  <Link href={languageHref} lang={otherLocale} hrefLang={otherLocale} className="btn btn-ghost w-full">
                    {labels.switchTo}
                  </Link>
                ) : null}
              </div>
            </nav>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}

/* -------------------------------------------------------------------------- */

function SearchDialog({
  open,
  onClose,
  locale,
  labels,
}: {
  open: boolean;
  onClose: () => void;
  locale: Locale;
  labels: Labels;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const reduceMotion = useReducedMotion();
  const id = useId();

  useEffect(() => {
    if (open) {
      const timer = setTimeout(() => inputRef.current?.focus(), 60);
      return () => clearTimeout(timer);
    }
  }, [open]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-60 flex items-start justify-center px-5 pt-[18vh]"
          initial={reduceMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduceMotion ? undefined : { opacity: 0 }}
          transition={{ duration: 0.18 }}
        >
          <button
            type="button"
            aria-label={labels.close}
            onClick={onClose}
            className="absolute inset-0 bg-[color-mix(in_oklab,var(--color-ink-900)_82%,transparent)] backdrop-blur-md"
          />
          <motion.form
            role="dialog"
            aria-modal="true"
            aria-labelledby={id}
            action={locale === "ar" ? "/ar/search" : "/search"}
            method="get"
            initial={reduceMotion ? false : { opacity: 0, y: -12, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduceMotion ? undefined : { opacity: 0, y: -8 }}
            transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
            className="panel relative z-10 w-full max-w-2xl p-2.5 shadow-[var(--shadow-lift)]"
          >
            <label id={id} htmlFor={`${id}-input`} className="sr-only">
              {labels.search}
            </label>
            <div className="flex items-center gap-2">
              <Icon name="search" size={19} className="ms-3 shrink-0 text-muted" />
              <input
                ref={inputRef}
                id={`${id}-input`}
                name="q"
                type="search"
                autoComplete="off"
                placeholder={labels.searchPlaceholder}
                className="min-w-0 flex-1 bg-transparent py-3 text-[1rem] text-strong outline-none placeholder:text-muted"
              />
              <button type="submit" className="btn btn-primary btn-sm">
                {labels.search}
              </button>
            </div>
          </motion.form>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
