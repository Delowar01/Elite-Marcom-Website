import Link from "next/link";

import { AdminSidebar } from "@/components/admin/sidebar";
import { Icon } from "@/components/ui/icon";
import { ADMIN_NAV } from "@/lib/admin/nav";
import { requireSession } from "@/lib/auth/guard";
import { signOut } from "../login/actions";

/**
 * Everything behind the sign-in wall. The session check happens here rather
 * than per page, so a new screen cannot be added without it — and each page
 * still asserts its own permission before it reads anything.
 */
export default async function AdminShellLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();

  // The sidebar only lists what this person may actually open.
  const groups = ADMIN_NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) => session.permissions.has(item.permission)),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="min-h-dvh lg:ps-64">
      <AdminSidebar
        groups={groups}
        user={{ name: session.user.name, roleName: session.user.roleName }}
      />

      <div className="flex min-h-dvh flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-[var(--admin-line)] bg-[color-mix(in_oklab,var(--admin-bg)_88%,transparent)] px-4 py-2.5 backdrop-blur-lg lg:px-7">
          <span className="ms-12 text-[0.78rem] text-muted lg:ms-0">
            Signed in as <span className="text-strong">{session.user.email}</span>
          </span>

          <div className="ms-auto flex items-center gap-2">
            <Link
              href="/"
              target="_blank"
              rel="noopener"
              className="admin-btn admin-btn-sm"
              title="Open the live website in a new tab"
            >
              <Icon name="arrowUpRight" size={13} />
              View site
            </Link>
            <form action={signOut}>
              <button type="submit" className="admin-btn admin-btn-sm">
                Sign out
              </button>
            </form>
          </div>
        </header>

        <main className="flex-1 px-4 py-6 lg:px-7 lg:py-8">{children}</main>
      </div>
    </div>
  );
}
