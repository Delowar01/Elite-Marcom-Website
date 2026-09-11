import Link from "next/link";
import type { ReactNode } from "react";

import { Icon } from "@/components/ui/icon";

export type Crumb = { label: string; href?: string };

export function AdminPageHeader({
  title,
  description,
  crumbs = [],
  actions,
}: {
  title: string;
  description?: string;
  crumbs?: Crumb[];
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6">
      {crumbs.length ? (
        <nav aria-label="Breadcrumb" className="mb-2">
          <ol className="flex flex-wrap items-center gap-1.5 text-[0.75rem] text-muted">
            {crumbs.map((crumb, index) => (
              <li key={`${crumb.label}-${index}`} className="flex items-center gap-1.5">
                {index > 0 ? <Icon name="chevronRight" size={11} className="opacity-50" /> : null}
                {crumb.href ? (
                  <Link href={crumb.href} className="transition-colors hover:text-strong">
                    {crumb.label}
                  </Link>
                ) : (
                  <span>{crumb.label}</span>
                )}
              </li>
            ))}
          </ol>
        </nav>
      ) : null}

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1>{title}</h1>
          {description ? <p className="mt-1 max-w-2xl text-[0.83rem] text-muted">{description}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="admin-card flex flex-col items-center gap-3 px-6 py-14 text-center">
      <span
        className="flex size-11 items-center justify-center rounded-full border border-[var(--admin-line)]"
        style={{ color: "var(--color-peach)" }}
      >
        <Icon name="sparkle" size={19} />
      </span>
      <h2>{title}</h2>
      <p className="max-w-md text-[0.83rem] text-muted">{body}</p>
      {action}
    </div>
  );
}
