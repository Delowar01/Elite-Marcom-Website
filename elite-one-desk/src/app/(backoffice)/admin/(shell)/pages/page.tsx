import Link from "next/link";
import { asc, eq, sql } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { Icon } from "@/components/ui/icon";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { pageSections, pages } from "@/lib/db/schema";
import { NewPageForm } from "./page-forms";

export const metadata = { title: "Pages & sections" };
export const dynamic = "force-dynamic";

export default async function PagesIndex() {
  const session = await requirePermission("content.view", "/admin/pages");
  const canManage = session.permissions.has("content.manage");

  const rows = await db
    .select({
      id: pages.id,
      slug: pages.slug,
      kind: pages.kind,
      titleEn: pages.titleEn,
      isPublished: pages.isPublished,
      updatedAt: pages.updatedAt,
      sections: sql<number>`count(${pageSections.id})::int`,
      drafts: sql<number>`count(${pageSections.draft})::int`,
      hidden: sql<number>`count(*) filter (where ${pageSections.isPublished} = false)::int`,
    })
    .from(pages)
    .leftJoin(pageSections, eq(pageSections.pageId, pages.id))
    .groupBy(pages.id)
    .orderBy(asc(pages.kind), asc(pages.sortOrder), asc(pages.id));

  return (
    <>
      <AdminPageHeader
        title="Pages & sections"
        description="Every page is a stack of sections you choose from a fixed set. The design system stays intact — you control the content, the order and what is visible."
      />

      <div className="admin-card mb-5 overflow-x-auto">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Page</th>
              <th>Address</th>
              <th>Sections</th>
              <th>State</th>
              <th>Last change</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <Link
                    href={`/admin/pages/${row.slug}`}
                    className="font-semibold text-strong hover:text-[var(--color-peach)]"
                  >
                    {row.titleEn}
                  </Link>
                  {row.kind === "builtin" ? (
                    <span className="ms-2 text-[0.7rem] text-muted">built-in</span>
                  ) : null}
                </td>
                <td className="text-muted" dir="ltr">
                  {row.slug === "home" ? "/" : `/${row.slug}`}
                </td>
                <td className="text-muted">
                  {row.sections}
                  {row.hidden ? <span className="ms-2 text-[0.72rem]">{row.hidden} hidden</span> : null}
                </td>
                <td>
                  <span
                    className="admin-badge"
                    style={{ color: row.isPublished ? "#63c98c" : "#9aa2b5" }}
                  >
                    {row.isPublished ? "Published" : "Unpublished"}
                  </span>
                  {row.drafts ? (
                    <span className="admin-badge ms-1.5" style={{ color: "#ffd166" }}>
                      {row.drafts} draft{row.drafts === 1 ? "" : "s"}
                    </span>
                  ) : null}
                </td>
                <td className="whitespace-nowrap text-muted">
                  {row.updatedAt.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                </td>
                <td className="text-end">
                  <Link href={`/admin/pages/${row.slug}`} className="admin-btn admin-btn-sm">
                    Edit
                    <Icon name="chevronRight" size={12} />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {canManage ? <NewPageForm csrf={session.csrfToken} /> : null}
    </>
  );
}
