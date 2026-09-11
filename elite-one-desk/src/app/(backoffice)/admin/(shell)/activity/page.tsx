import Link from "next/link";
import { and, desc, eq, ilike, or, sql, type SQL } from "drizzle-orm";

import { AdminPageHeader, EmptyState } from "@/components/admin/page-header";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { activityLogs } from "@/lib/db/schema";

export const metadata = { title: "Activity log" };
export const dynamic = "force-dynamic";

const PER_PAGE = 50;

const ENTITY_LABEL: Record<string, string> = {
  user: "Account",
  role: "Role",
  page: "Page",
  section: "Section",
  category: "Category",
  subcategory: "Group",
  service: "Service",
  package: "Package",
  video: "Video",
  testimonial: "Testimonial",
  faq: "FAQ",
  media: "Media",
  navigation: "Navigation",
  settings: "Settings",
  social: "Social link",
  seo: "SEO",
  enquiry: "Enquiry",
};

/** Actions that change who can do what, or that leave the building. */
const SENSITIVE = new Set([
  "login",
  "user.created",
  "user.deleted",
  "user.role_changed",
  "user.password_reset",
  "role.permissions_changed",
  "enquiry.exported",
]);

export default async function ActivityPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; entity?: string; page?: string }>;
}) {
  await requirePermission("activity.view", "/admin/activity");
  const params = await searchParams;
  const query = (params.q ?? "").trim().slice(0, 120);
  const entity = (params.entity ?? "").trim().slice(0, 32);
  const page = Math.max(1, Number(params.page) || 1);

  const filters: SQL[] = [];
  if (query) {
    const like = `%${query}%`;
    const match = or(
      ilike(activityLogs.actorName, like),
      ilike(activityLogs.action, like),
      ilike(activityLogs.summary, like),
    );
    if (match) filters.push(match);
  }
  if (entity) filters.push(eq(activityLogs.entityType, entity));
  const where = filters.length ? and(...filters) : undefined;

  const [rows, counted] = await Promise.all([
    db
      .select()
      .from(activityLogs)
      .where(where)
      .orderBy(desc(activityLogs.createdAt))
      .limit(PER_PAGE)
      .offset((page - 1) * PER_PAGE),
    db.select({ n: sql<number>`count(*)::int` }).from(activityLogs).where(where),
  ]);

  const total = counted[0]?.n ?? 0;
  const pages = Math.max(1, Math.ceil(total / PER_PAGE));
  const href = (next: number) => {
    const search = new URLSearchParams();
    if (query) search.set("q", query);
    if (entity) search.set("entity", entity);
    if (next > 1) search.set("page", String(next));
    const qs = search.toString();
    return qs ? `/admin/activity?${qs}` : "/admin/activity";
  };

  return (
    <>
      <AdminPageHeader
        title="Activity log"
        description="Who changed what, and when. Entries are kept even after the account that made them is deleted — the name is captured at the time."
      />

      <form method="get" className="admin-card mb-4 flex flex-wrap items-end gap-3 p-3.5">
        <div className="min-w-52 flex-1">
          <label className="admin-label" htmlFor="q">
            Search
          </label>
          <input id="q" name="q" defaultValue={query} placeholder="Person, action or summary" className="admin-input" />
        </div>
        <div>
          <label className="admin-label" htmlFor="entity">
            Type
          </label>
          <select id="entity" name="entity" defaultValue={entity} className="admin-select">
            <option value="">All</option>
            {Object.entries(ENTITY_LABEL).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className="admin-btn admin-btn-primary">
          Apply
        </button>
        {query || entity ? (
          <Link href="/admin/activity" className="admin-btn">
            Clear
          </Link>
        ) : null}
      </form>

      {rows.length === 0 ? (
        <EmptyState title="Nothing recorded" body="Actions appear here as soon as someone makes a change." />
      ) : (
        <>
          <div className="admin-card overflow-x-auto">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Who</th>
                  <th>Action</th>
                  <th>What</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td className="whitespace-nowrap text-muted">
                      {row.createdAt.toLocaleString("en-GB", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="text-strong">{row.actorName}</td>
                    <td>
                      <span
                        className="admin-badge"
                        style={{ color: SENSITIVE.has(row.action) ? "#ffd166" : "var(--text-muted)" }}
                      >
                        {row.action.replace(/[._]/g, " ")}
                      </span>
                    </td>
                    <td className="text-muted">
                      {row.summary ||
                        `${ENTITY_LABEL[row.entityType] ?? row.entityType} ${row.entityId}`.trim()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-[0.78rem] text-muted">
            <p>
              {total} entr{total === 1 ? "y" : "ies"} · page {page} of {pages}
            </p>
            {pages > 1 ? (
              <div className="flex gap-2">
                {page > 1 ? (
                  <Link href={href(page - 1)} className="admin-btn admin-btn-sm">
                    Previous
                  </Link>
                ) : null}
                {page < pages ? (
                  <Link href={href(page + 1)} className="admin-btn admin-btn-sm">
                    Next
                  </Link>
                ) : null}
              </div>
            ) : null}
          </div>
        </>
      )}
    </>
  );
}
