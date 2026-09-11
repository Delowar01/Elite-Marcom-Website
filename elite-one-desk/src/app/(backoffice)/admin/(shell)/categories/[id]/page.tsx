import Link from "next/link";
import { notFound } from "next/navigation";
import { asc, eq, sql } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { media, serviceCategories, serviceSubcategories, services } from "@/lib/db/schema";
import {
  CategoryForm,
  DeleteCategory,
  SubcategoryManager,
  type CategoryValues,
  type SubcategoryRow,
} from "../category-form";

export const dynamic = "force-dynamic";

const BLANK: CategoryValues = {
  slug: "",
  titleEn: "",
  titleAr: "",
  taglineEn: "",
  taglineAr: "",
  summaryEn: "",
  summaryAr: "",
  bodyEn: "",
  bodyAr: "",
  ctaLabelEn: "",
  ctaLabelAr: "",
  icon: "desk",
  imageId: null,
  sortOrder: 0,
  isPublished: true,
};

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (id === "new") return { title: "New category" };
  const [row] = await db
    .select({ titleEn: serviceCategories.titleEn })
    .from(serviceCategories)
    .where(eq(serviceCategories.id, Number(id) || 0))
    .limit(1);
  return { title: row?.titleEn ?? "Category" };
}

export default async function CategoryEditor({ params }: { params: Promise<{ id: string }> }) {
  const session = await requirePermission("services.manage");
  const { id: rawId } = await params;
  const isNew = rawId === "new";
  const id = isNew ? 0 : Number(rawId) || 0;

  const library = await db
    .select({
      id: media.id,
      filename: media.filename,
      title: media.title,
      altEn: media.altEn,
      width: media.width,
      height: media.height,
      folder: media.folder,
    })
    .from(media)
    .orderBy(asc(media.folder), asc(media.title));

  if (isNew) {
    return (
      <>
        <AdminPageHeader
          title="New category"
          crumbs={[{ label: "Service categories", href: "/admin/categories" }, { label: "New" }]}
          actions={
            <Link href="/admin/categories" className="admin-btn">
              Cancel
            </Link>
          }
        />
        <div className="max-w-4xl">
          <CategoryForm csrf={session.csrfToken} category={BLANK} media={library} />
        </div>
      </>
    );
  }

  const [row] = await db.select().from(serviceCategories).where(eq(serviceCategories.id, id)).limit(1);
  if (!row) notFound();

  const [subs, counted] = await Promise.all([
    db
      .select({
        id: serviceSubcategories.id,
        slug: serviceSubcategories.slug,
        titleEn: serviceSubcategories.titleEn,
        titleAr: serviceSubcategories.titleAr,
        summaryEn: serviceSubcategories.summaryEn,
        summaryAr: serviceSubcategories.summaryAr,
        sortOrder: serviceSubcategories.sortOrder,
        isPublished: serviceSubcategories.isPublished,
        serviceCount: sql<number>`count(${services.id})::int`,
      })
      .from(serviceSubcategories)
      .leftJoin(services, eq(services.subcategoryId, serviceSubcategories.id))
      .where(eq(serviceSubcategories.categoryId, id))
      .groupBy(serviceSubcategories.id)
      .orderBy(asc(serviceSubcategories.sortOrder)),
    db
      .select({ n: sql<number>`count(*)::int` })
      .from(services)
      .where(eq(services.categoryId, id)),
  ]);

  return (
    <>
      <AdminPageHeader
        title={row.titleEn}
        crumbs={[{ label: "Service categories", href: "/admin/categories" }, { label: row.titleEn }]}
        actions={
          <>
            <Link href={`/admin/services?category=${id}`} className="admin-btn">
              {counted[0]?.n ?? 0} services
            </Link>
            <Link href={`/services/${row.slug}`} target="_blank" rel="noopener" className="admin-btn">
              View live
            </Link>
          </>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr] xl:items-start">
        <CategoryForm csrf={session.csrfToken} category={row as CategoryValues} media={library} />
        <div className="space-y-5">
          <SubcategoryManager
            csrf={session.csrfToken}
            categoryId={id}
            rows={subs as SubcategoryRow[]}
          />
          <DeleteCategory
            csrf={session.csrfToken}
            id={id}
            title={row.titleEn}
            serviceCount={counted[0]?.n ?? 0}
          />
        </div>
      </div>
    </>
  );
}
