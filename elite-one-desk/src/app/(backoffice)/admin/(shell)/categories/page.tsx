import Link from "next/link";
import { asc, eq, sql } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { Icon } from "@/components/ui/icon";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { serviceCategories, services } from "@/lib/db/schema";
import { CategoryRows } from "./category-rows";

export const metadata = { title: "Service categories" };
export const dynamic = "force-dynamic";

export default async function CategoriesPage() {
  const session = await requirePermission("services.manage", "/admin/categories");

  const rows = await db
    .select({
      id: serviceCategories.id,
      slug: serviceCategories.slug,
      titleEn: serviceCategories.titleEn,
      taglineEn: serviceCategories.taglineEn,
      icon: serviceCategories.icon,
      isPublished: serviceCategories.isPublished,
      sortOrder: serviceCategories.sortOrder,
      serviceCount: sql<number>`count(${services.id})::int`,
    })
    .from(serviceCategories)
    .leftJoin(services, eq(services.categoryId, serviceCategories.id))
    .groupBy(serviceCategories.id)
    .orderBy(asc(serviceCategories.sortOrder), asc(serviceCategories.id));

  return (
    <>
      <AdminPageHeader
        title="Service categories"
        description="The six columns of the business. Their order here is the order on the homepage and in the services index."
        actions={
          <Link href="/admin/categories/new" className="admin-btn admin-btn-primary">
            <Icon name="sparkle" size={14} />
            New category
          </Link>
        }
      />
      <CategoryRows csrf={session.csrfToken} rows={rows} />
    </>
  );
}
