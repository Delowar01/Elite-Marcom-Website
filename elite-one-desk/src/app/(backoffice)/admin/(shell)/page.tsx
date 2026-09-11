import Link from "next/link";
import { and, desc, eq, gte, isNotNull, sql } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { Icon } from "@/components/ui/icon";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import {
  activityLogs,
  enquiries,
  media,
  pageSections,
  services,
  testimonials,
  videos,
} from "@/lib/db/schema";

export const metadata = { title: "Dashboard" };
export const dynamic = "force-dynamic";

const STATUS_TONE: Record<string, string> = {
  new: "#ffa476",
  contacted: "#7fb2ff",
  in_progress: "#ffd166",
  waiting_customer: "#c9a6ff",
  completed: "#63c98c",
  closed: "#9aa2b5",
  spam: "#ff8a80",
};

const STATUS_LABEL: Record<string, string> = {
  new: "New",
  contacted: "Contacted",
  in_progress: "In progress",
  waiting_customer: "Waiting for customer",
  completed: "Completed",
  closed: "Closed",
  spam: "Spam",
};

function Stat({
  label,
  value,
  hint,
  href,
  accent,
}: {
  label: string;
  value: number | string;
  hint?: string;
  href?: string;
  accent?: boolean;
}) {
  const body = (
    <>
      <p className="text-[0.74rem] font-semibold uppercase tracking-[0.08em] text-muted">{label}</p>
      <p
        className="mt-2 font-display text-[1.9rem] font-bold leading-none tabular-nums"
        style={{ color: accent ? "var(--color-peach)" : "var(--text-strong)" }}
      >
        {value}
      </p>
      {hint ? <p className="mt-1.5 text-[0.74rem] text-muted">{hint}</p> : null}
    </>
  );
  return href ? (
    <Link href={href} className="admin-card block p-4 transition-colors hover:border-[var(--admin-line-strong)]">
      {body}
    </Link>
  ) : (
    <div className="admin-card p-4">{body}</div>
  );
}

export default async function DashboardPage() {
  const session = await requirePermission("dashboard.view", "/admin");
  const canSeeEnquiries = session.permissions.has("enquiries.view");
  const since30 = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
  // postgres-js only binds primitives inside a raw `sql` template, so the cutoff
  // is passed as an ISO string with an explicit cast rather than as a Date.
  const since30Sql = sql`${since30.toISOString()}::timestamptz`;

  const [
    enquiryTotals,
    byStatus,
    topServices,
    recentEnquiries,
    contentCounts,
    recentActivity,
  ] = await Promise.all([
    db
      .select({
        total: sql<number>`count(*)::int`,
        unread: sql<number>`count(*) filter (where ${enquiries.isRead} = false)::int`,
        open: sql<number>`count(*) filter (where ${enquiries.status} in ('new','contacted','in_progress','waiting_customer'))::int`,
        last30: sql<number>`count(*) filter (where ${enquiries.createdAt} >= ${since30Sql})::int`,
      })
      .from(enquiries),
    db
      .select({ status: enquiries.status, n: sql<number>`count(*)::int` })
      .from(enquiries)
      .groupBy(enquiries.status),
    db
      .select({ label: enquiries.serviceLabel, n: sql<number>`count(*)::int` })
      .from(enquiries)
      .where(and(isNotNull(enquiries.serviceId), gte(enquiries.createdAt, since30)))
      .groupBy(enquiries.serviceLabel)
      .orderBy(desc(sql`count(*)`))
      .limit(6),
    canSeeEnquiries
      ? db
          .select({
            id: enquiries.id,
            reference: enquiries.reference,
            name: enquiries.name,
            serviceLabel: enquiries.serviceLabel,
            categoryLabel: enquiries.categoryLabel,
            status: enquiries.status,
            isRead: enquiries.isRead,
            createdAt: enquiries.createdAt,
          })
          .from(enquiries)
          .orderBy(desc(enquiries.createdAt))
          .limit(8)
      : Promise.resolve([]),
    Promise.all([
      db.select({ n: sql<number>`count(*)::int` }).from(services).where(eq(services.isPublished, true)),
      db.select({ n: sql<number>`count(*)::int` }).from(videos).where(eq(videos.isPublished, true)),
      db.select({ n: sql<number>`count(*)::int` }).from(media),
      db
        .select({ n: sql<number>`count(*)::int` })
        .from(pageSections)
        .where(isNotNull(pageSections.draft)),
      db
        .select({ n: sql<number>`count(*)::int` })
        .from(testimonials)
        .where(eq(testimonials.isPublished, false)),
    ]),
    db
      .select({
        id: activityLogs.id,
        actorName: activityLogs.actorName,
        action: activityLogs.action,
        entityType: activityLogs.entityType,
        summary: activityLogs.summary,
        createdAt: activityLogs.createdAt,
      })
      .from(activityLogs)
      .orderBy(desc(activityLogs.createdAt))
      .limit(10),
  ]);

  const totals = enquiryTotals[0] ?? { total: 0, unread: 0, open: 0, last30: 0 };
  const [publishedServices, publishedVideos, mediaCount, draftSections, unpublishedTestimonials] =
    contentCounts;

  return (
    <>
      <AdminPageHeader
        title={`Good to see you, ${session.user.name.split(" ")[0]}`}
        description="Everything waiting on you, and what changed recently."
        actions={
          canSeeEnquiries ? (
            <Link href="/admin/enquiries" className="admin-btn admin-btn-primary">
              Open enquiries
              <Icon name="arrowRight" size={14} />
            </Link>
          ) : null
        }
      />

      <section aria-label="At a glance" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Unread enquiries"
          value={totals.unread}
          hint={totals.unread ? "Waiting to be opened" : "Nothing unread"}
          href={canSeeEnquiries ? "/admin/enquiries?status=new" : undefined}
          accent={totals.unread > 0}
        />
        <Stat
          label="Open enquiries"
          value={totals.open}
          hint="Not yet completed or closed"
          href={canSeeEnquiries ? "/admin/enquiries" : undefined}
        />
        <Stat label="Last 30 days" value={totals.last30} hint="New enquiries received" />
        <Stat
          label="Unpublished edits"
          value={(draftSections[0]?.n ?? 0) + (unpublishedTestimonials[0]?.n ?? 0)}
          hint={`${draftSections[0]?.n ?? 0} section drafts · ${unpublishedTestimonials[0]?.n ?? 0} testimonials`}
          href="/admin/pages"
        />
      </section>

      <div className="mt-5 grid gap-5 xl:grid-cols-[1.35fr_1fr]">
        <section className="admin-card overflow-hidden" aria-label="Recent enquiries">
          <div className="flex items-center justify-between border-b border-[var(--admin-line)] px-4 py-3">
            <h2>Recent enquiries</h2>
            {canSeeEnquiries ? (
              <Link href="/admin/enquiries" className="text-[0.76rem] text-muted hover:text-strong">
                View all
              </Link>
            ) : null}
          </div>

          {recentEnquiries.length === 0 ? (
            <p className="px-4 py-10 text-center text-[0.82rem] text-muted">
              No enquiries yet. They appear here the moment a form is sent.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Name</th>
                    <th>Service</th>
                    <th>Status</th>
                    <th>Received</th>
                  </tr>
                </thead>
                <tbody>
                  {recentEnquiries.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <Link
                          href={`/admin/enquiries/${row.id}`}
                          className="font-semibold text-strong hover:text-[var(--color-peach)]"
                        >
                          {row.reference}
                        </Link>
                        {!row.isRead ? (
                          <span
                            className="ms-2 inline-block size-1.5 rounded-full align-middle"
                            style={{ background: "var(--color-orange)" }}
                            aria-label="Unread"
                          />
                        ) : null}
                      </td>
                      <td className="text-strong">{row.name}</td>
                      <td className="text-muted">
                        {row.serviceLabel || row.categoryLabel || "General enquiry"}
                      </td>
                      <td>
                        <span className="admin-badge" style={{ color: STATUS_TONE[row.status] }}>
                          {STATUS_LABEL[row.status]}
                        </span>
                      </td>
                      <td className="text-muted">
                        {row.createdAt.toLocaleDateString("en-GB", {
                          day: "numeric",
                          month: "short",
                        })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <div className="space-y-5">
          <section className="admin-card p-4" aria-label="Most requested services">
            <h2 className="mb-3">Most requested — last 30 days</h2>
            {topServices.length === 0 ? (
              <p className="py-4 text-[0.8rem] text-muted">
                Nothing yet. This ranks the services people actually ask about.
              </p>
            ) : (
              <ul className="space-y-2.5">
                {topServices.map((row) => {
                  const max = topServices[0]?.n || 1;
                  return (
                    <li key={row.label}>
                      <div className="mb-1 flex items-baseline justify-between gap-3">
                        <span className="truncate text-[0.8rem] text-strong">{row.label}</span>
                        <span className="text-[0.76rem] tabular-nums text-muted">{row.n}</span>
                      </div>
                      <div className="h-1 overflow-hidden rounded-full bg-[color-mix(in_oklab,var(--color-warm)_8%,transparent)]">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${Math.max(6, (row.n / max) * 100)}%`,
                            background: "var(--color-orange)",
                          }}
                        />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="admin-card p-4" aria-label="Content">
            <h2 className="mb-3">Content</h2>
            <dl className="grid grid-cols-2 gap-3 text-[0.82rem]">
              {[
                { label: "Published services", value: publishedServices[0]?.n ?? 0, href: "/admin/services" },
                { label: "Published videos", value: publishedVideos[0]?.n ?? 0, href: "/admin/videos" },
                { label: "Media files", value: mediaCount[0]?.n ?? 0, href: "/admin/media" },
                { label: "Section drafts", value: draftSections[0]?.n ?? 0, href: "/admin/pages" },
              ].map((item) => (
                <div key={item.label}>
                  <dt className="text-[0.72rem] text-muted">{item.label}</dt>
                  <dd className="mt-0.5">
                    <Link href={item.href} className="font-semibold text-strong hover:text-[var(--color-peach)]">
                      {item.value}
                    </Link>
                  </dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="admin-card p-4" aria-label="Enquiries by status">
            <h2 className="mb-3">By status</h2>
            <ul className="flex flex-wrap gap-1.5">
              {Object.entries(STATUS_LABEL).map(([key, label]) => {
                const n = byStatus.find((s) => s.status === key)?.n ?? 0;
                return (
                  <li key={key}>
                    <span
                      className="admin-badge"
                      style={{ color: n ? STATUS_TONE[key] : "var(--text-muted)" }}
                    >
                      {label}
                      <span className="tabular-nums opacity-80">{n}</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        </div>
      </div>

      <section className="admin-card mt-5 overflow-hidden" aria-label="Recent activity">
        <div className="flex items-center justify-between border-b border-[var(--admin-line)] px-4 py-3">
          <h2>Recent activity</h2>
          {session.permissions.has("activity.view") ? (
            <Link href="/admin/activity" className="text-[0.76rem] text-muted hover:text-strong">
              Full log
            </Link>
          ) : null}
        </div>
        {recentActivity.length === 0 ? (
          <p className="px-4 py-8 text-center text-[0.82rem] text-muted">Nothing recorded yet.</p>
        ) : (
          <ul className="divide-y divide-[var(--admin-line)]">
            {recentActivity.map((row) => (
              <li key={row.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-1 px-4 py-2.5 text-[0.82rem]">
                <span className="font-semibold text-strong">{row.actorName}</span>
                <span className="text-muted">{row.summary || row.action.replace(/[._]/g, " ")}</span>
                <span className="ms-auto text-[0.74rem] text-muted">
                  {row.createdAt.toLocaleString("en-GB", {
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
