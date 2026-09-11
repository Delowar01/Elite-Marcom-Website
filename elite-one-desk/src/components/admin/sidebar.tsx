"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Icon } from "@/components/ui/icon";
import { Logo } from "@/components/ui/logo";
import type { AdminNavGroup } from "@/lib/admin/nav";

export function AdminSidebar({
  groups,
  user,
}: {
  groups: AdminNavGroup[];
  user: { name: string; roleName: string };
}) {
  const pathname = usePathname() ?? "";
  const [open, setOpen] = useState(false);

  useEffect(() => setOpen(false), [pathname]);

  const isActive = (href: string, exact?: boolean) =>
    exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open the admin menu"
        className="admin-btn fixed left-4 top-3.5 z-40 lg:hidden"
      >
        <Icon name="menu" size={16} />
      </button>

      {open ? (
        <button
          type="button"
          aria-label="Close the admin menu"
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
        />
      ) : null}

      <aside
        data-open={open}
        className="fixed inset-y-0 left-0 z-50 flex w-64 -translate-x-full flex-col border-r border-[var(--admin-line)] bg-[var(--admin-panel)] transition-transform duration-300 data-[open=true]:translate-x-0 lg:translate-x-0"
      >
        <div className="flex items-center justify-between border-b border-[var(--admin-line)] px-4 py-3.5">
          <Link href="/admin" aria-label="Elite One Desk admin">
            <Logo height={30} />
          </Link>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close the admin menu"
            className="admin-btn admin-btn-sm lg:hidden"
          >
            <Icon name="close" size={14} />
          </button>
        </div>

        <nav aria-label="Admin" className="flex-1 overflow-y-auto px-2.5 py-4">
          {groups.map((group) => (
            <div key={group.title} className="mb-5 last:mb-0">
              <p className="mb-1.5 px-2 text-[0.66rem] font-semibold uppercase tracking-[0.1em] text-muted">
                {group.title}
              </p>
              <ul className="space-y-0.5">
                {group.items.map((item) => (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className="admin-nav-link"
                      aria-current={isActive(item.href, item.exact) ? "page" : undefined}
                    >
                      <Icon name={item.icon} size={16} className="shrink-0 opacity-75" />
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-[var(--admin-line)] px-4 py-3.5">
          <p className="truncate text-[0.82rem] font-semibold text-strong">{user.name}</p>
          <p className="text-[0.72rem] text-muted">{user.roleName}</p>
        </div>
      </aside>
    </>
  );
}
