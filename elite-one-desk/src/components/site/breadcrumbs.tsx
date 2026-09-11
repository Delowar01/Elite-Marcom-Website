import Link from "next/link";

import { Icon } from "@/components/ui/icon";
import type { Locale } from "@/lib/i18n/config";
import { localeHref } from "@/lib/i18n/config";

export type Crumb = { name: string; path: string };

export function Breadcrumbs({
  trail,
  locale,
  label,
}: {
  trail: Crumb[];
  locale: Locale;
  label: string;
}) {
  if (trail.length < 2) return null;
  return (
    <nav aria-label={label} className="shell shell-wide">
      <ol className="flex flex-wrap items-center gap-1.5 text-[0.78rem] text-muted">
        {trail.map((crumb, index) => {
          const last = index === trail.length - 1;
          return (
            <li key={crumb.path} className="flex items-center gap-1.5">
              {index > 0 ? (
                <Icon name="chevronRight" size={12} className="flip-rtl opacity-45" aria-hidden />
              ) : null}
              {last ? (
                <span aria-current="page" className="text-body">
                  {crumb.name}
                </span>
              ) : (
                <Link href={localeHref(locale, crumb.path)} className="transition-colors hover:text-strong">
                  {crumb.name}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
