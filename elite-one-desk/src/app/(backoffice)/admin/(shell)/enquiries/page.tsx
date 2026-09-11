import Link from "next/link";
import { and, asc, desc, eq, ilike, or, sql, type SQL } from "drizzle-orm";

import { AdminPageHeader, EmptyState } from "@/components/admin/page-header";
import { Icon } from "@/components/ui/icon";
import {
  ENQUIRY_STATUSES,
  STATUS_LABEL,
  STATUS_TONE,
  isEnquiryStatus,
} from "@/lib/admin/enquiry";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { enquiries, serviceCategories } from "@/lib/db/schema";

export const metadata = { title: "Enquiries" };
export const dynamic = "force-dynamic";

const PER_PAGE = 25;

type Search = {
  q?: string;
  status?: string;
  category?: string;
  sort?: string;
  page?: string;
};

export default async function EnquiriesPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const session = await requirePermission("enquiries.view", "/admin/enquiries");
  const params = await searchParams;

  const query = (params.q ?? "").trim().slice(0, 120);
  const status = params.status && isEnquiryStatus(params.status) ? params.status : "";
  const categoryId = Number(params.category) || 0;
  const sort = params.sort === "oldest" ? "oldest" : "newest";
  const page = Math.max(1, Number(params.page) || 1);

  const filters: SQL[] = [];
  if (query) {
    const like = `%${query}%`;
    const match = or(
      ilike(enquiries.reference, like),
      ilike(enquiries.name, like),
      ilike(enquiries.email, like),
      ilike(enquiries.phone, like),
      ilike(enquiries.serviceLabel, like),
      ilike(enquiries.message, like),
    );
    if (match) filters.push(match);
  }
  if (status) filters.push(eq(enquiries.status, status));
  if (categoryId) filters.push(eq(enquiries.categoryId, categoryId));
  const where = filters.length ? and(...filters) : undefined;

  const [rows, counted, categories] = await Promise.all([
    db
      .select({
        id: enquiries.id,
        reference: enquiries.reference,
        name: enquiries.name,
        email: enquiries.email,
        phone: enquiries.phone,
        serviceLabel: enquiries.serviceLabel,
        categoryLabel: enquiries.categoryLabel,
        status: enquiries.status,
        isRead: enquiries.isRead,
        locale: enquiries.locale,
        createdAt: enquiries.createdAt,
      })
      .from(enquiries)
      .where(where)
      .orderBy(sort === "oldest" ? asc(enquiries.createdAt) : desc(enquiries.createdAt))
      .limit(PER_PAGE)
      .offset((page - 1) * PER_PAGE),
    db.select({ n: sql<number>`count(*)::int` }).from(enquiries).where(where),
    db
      .select({ id: serviceCategories.id, title: serviceCategories.titleEn })
      .from(serviceCategories)
      .orderBy(asc(serviceCategories.sortOrder)),
  ]);

  const total = counted[0]?.n ?? 0;
  const pages = Math.max(1, Math.ceil(total / PER_PAGE));

  const buildHref = (next: Partial<Search>) => {
    const search = new URLSearchParams();
    const merged = { q: query, status, category: categoryId ? String(categoryId) : "", sort, ...next };
    for (const [key, value] of Object.entries(merged)) {
      if (value && value !== "newest") search.set(key, String(value));
    }
    const qs = search.toString();
    return qs ? `/admin/enquiries?${qs}` : "/admin/enquiries";
  };

  const exportSearch = new URLSearchParams();
  if (query) exportSearch.set("q", query);
  if (status) exportSearch.set("status", status);
  if (categoryId) exportSearch.set("category", String(categoryId));

  return (
    <>
      <AdminPageHeader
        title="Enquiries"
        description="Every form on the website lands here. Lightweight by design — statuses, notes and an export, not a CRM."
        actions={
          session.permissions.has("enquiries.export") ? (
            <a
              href={`/api/admin/enquiries/export?${exportSearch.toString()}`}
              className="admin-btn"
              download
            >
              <Icon name="fileText" size={14} />
              Export CSV
            </a>
          ) : null
        }
      />

      <form method="get" className="admin-card mb-4 flex flex-wrap items-end gap-3 p-3.5">
        <div className="min-w-52 flex-1">
          <label className="admin-label" htmlFor="q">
            Search
          </label>
          <input
            id="q"
            name="q"
            defaultValue={query}
            placeholder="Reference, name, email, phone or message"
            className="admin-input"
          />
        </div>
        <div>
          <label className="admin-label" htmlFor="status">
            Status
          </label>
          <select id="status" name="status" defaultValue={status} className="admin-select">
            <option value="">All</option>
            {ENQUIRY_STATUSES.map((key) => (
              <option key={key} value={key}>
                {STATUS_LABEL[key]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="admin-label" htmlFor="category">
            Category
          </label>
          <select
            id="category"
            name="category"
            defaultValue={categoryId ? String(categoryId) : ""}
            className="admin-select"
          >
            <option value="">All</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="admin-label" htmlFor="sort">
            Sort
          </label>
          <select id="sort" name="sort" defaultValue={sort} className="admin-select">
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
          </select>
        </div>
        <button type="submit" className="admin-btn admin-btn-primary">
          Apply
        </button>
        {query || status || categoryId ? (
          <Link href="/admin/enquiries" className="admin-btn">
            Clear
          </Link>
        ) : null}
      </form>

      {rows.length === 0 ? (
        <EmptyState
          title={total === 0 && !query && !status ? "No enquiries yet" : "Nothing matched"}
          body={
            total === 0 && !query && !status
              ? "As soon as someone sends a form on the website, it appears here with a reference you can quote back to them."
              : "Try a different search, or clear the filters."
          }
          action={
            query || status || categoryId ? (
              <Link href="/admin/enquiries" className="admin-btn">
                Clear filters
              </Link>
            ) : null
          }
        />
      ) : (
        <>
          <div className="admin-card overflow-x-auto">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Name</th>
                  <th>Contact</th>
                  <th>Service</th>
                  <th>Status</th>
                  <th>Received</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td className="whitespace-nowrap">
                      {!row.isRead ? (
                        <span
                          className="me-2 inline-block size-1.5 rounded-full align-middle"
                          style={{ background: "var(--color-orange)" }}
                          aria-label="Unread"
                        />
                      ) : null}
                      <Link
                        href={`/admin/enquiries/${row.id}`}
                        className="font-semibold text-strong hover:text-[var(--color-peach)]"
                      >
                        {row.reference}
                      </Link>
                    </td>
                    <td className="text-strong">
                      {row.name}
                      {row.locale === "ar" ? (
                        <span className="ms-2 text-[0.7rem] text-muted">AR</span>
                      ) : null}
                    </td>
                    <td className="text-muted">
                      <span className="block text-[0.78rem]" dir="ltr">
                        {row.phone || "—"}
                      </span>
                      <span className="block text-[0.75rem] opacity-80">{row.email || ""}</span>
                    </td>
                    <td className="max-w-52 truncate text-muted">
                      {row.serviceLabel || row.categoryLabel || "General enquiry"}
                    </td>
                    <td>
                      <span className="admin-badge" style={{ color: STATUS_TONE[row.status] }}>
                        {STATUS_LABEL[row.status]}
                      </span>
                    </td>
                    <td className="whitespace-nowrap text-muted">
                      {row.createdAt.toLocaleString("en-GB", {
                        day: "numeric",
                        month: "short",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="text-end">
                      <Link href={`/admin/enquiries/${row.id}`} className="admin-btn admin-btn-sm">
                        Open
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-[0.78rem] text-muted">
            <p>
              {total} enquir{total === 1 ? "y" : "ies"} · page {page} of {pages}
            </p>
            {pages > 1 ? (
              <div className="flex gap-2">
                {page > 1 ? (
                  <Link href={buildHref({ page: String(page - 1) })} className="admin-btn admin-btn-sm">
                    Previous
                  </Link>
                ) : null}
                {page < pages ? (
                  <Link href={buildHref({ page: String(page + 1) })} className="admin-btn admin-btn-sm">
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
