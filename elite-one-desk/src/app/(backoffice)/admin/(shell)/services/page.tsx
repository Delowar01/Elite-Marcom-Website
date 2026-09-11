import Link from "next/link";
import { and, asc, eq, ilike, or, sql, type SQL } from "drizzle-orm";

import { AdminPageHeader, EmptyState } from "@/components/admin/page-header";
import { Icon } from "@/components/ui/icon";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { serviceCategories, serviceSubcategories, services } from "@/lib/db/schema";
import { ServiceRows } from "./service-rows";

export const metadata = { title: "Services" };
export const dynamic = "force-dynamic";

export default async function ServicesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; category?: string; state?: string }>;
}) {
  const session = await requirePermission("services.manage", "/admin/services");
  const params = await searchParams;
  const query = (params.q ?? "").trim().slice(0, 120);
  const categoryId = Number(params.category) || 0;
  const state = params.state === "hidden" ? "hidden" : params.state === "live" ? "live" : "";

  const filters: SQL[] = [];
  if (query) {
    const like = `%${query}%`;
    const match = or(ilike(services.titleEn, like), ilike(services.slug, like), ilike(services.introEn, like));
    if (match) filters.push(match);
  }
  if (categoryId) filters.push(eq(services.categoryId, categoryId));
  if (state) filters.push(eq(services.isPublished, state === "live"));

  const [rows, categories] = await Promise.all([
    db
      .select({
        id: services.id,
        slug: services.slug,
        titleEn: services.titleEn,
        isPublished: services.isPublished,
        isFeatured: services.isFeatured,
        categoryTitle: serviceCategories.titleEn,
        categorySlug: serviceCategories.slug,
        groupTitle: serviceSubcategories.titleEn,
      })
      .from(services)
      .innerJoin(serviceCategories, eq(serviceCategories.id, services.categoryId))
      .leftJoin(serviceSubcategories, eq(serviceSubcategories.id, services.subcategoryId))
      .where(filters.length ? and(...filters) : undefined)
      .orderBy(asc(serviceCategories.sortOrder), asc(services.sortOrder), asc(services.id)),
    db
      .select({ id: serviceCategories.id, titleEn: serviceCategories.titleEn, n: sql<number>`0::int` })
      .from(serviceCategories)
      .orderBy(asc(serviceCategories.sortOrder)),
  ]);

  return (
    <>
      <AdminPageHeader
        title="Services"
        description="Every service has its own page built from the same template. Leave a field empty and its section simply does not appear."
        actions={
          <Link href="/admin/services/new" className="admin-btn admin-btn-primary">
            <Icon name="sparkle" size={14} />
            New service
          </Link>
        }
      />

      <form method="get" className="admin-card mb-4 flex flex-wrap items-end gap-3 p-3.5">
        <div className="min-w-52 flex-1">
          <label className="admin-label" htmlFor="q">
            Search
          </label>
          <input id="q" name="q" defaultValue={query} placeholder="Title, address or intro" className="admin-input" />
        </div>
        <div>
          <label className="admin-label" htmlFor="category">
            Category
          </label>
          <select id="category" name="category" defaultValue={categoryId || ""} className="admin-select">
            <option value="">All</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.titleEn}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="admin-label" htmlFor="state">
            State
          </label>
          <select id="state" name="state" defaultValue={state} className="admin-select">
            <option value="">All</option>
            <option value="live">Published</option>
            <option value="hidden">Unpublished</option>
          </select>
        </div>
        <button type="submit" className="admin-btn admin-btn-primary">
          Apply
        </button>
        {query || categoryId || state ? (
          <Link href="/admin/services" className="admin-btn">
            Clear
          </Link>
        ) : null}
      </form>

      {rows.length === 0 ? (
        <EmptyState
          title="Nothing matched"
          body="Try a different search, or clear the filters."
          action={
            <Link href="/admin/services" className="admin-btn">
              Clear filters
            </Link>
          }
        />
      ) : (
        <>
          <ServiceRows csrf={session.csrfToken} rows={rows} />
          <p className="mt-3 text-[0.78rem] text-muted">
            {rows.length} service{rows.length === 1 ? "" : "s"}
          </p>
        </>
      )}
    </>
  );
}
