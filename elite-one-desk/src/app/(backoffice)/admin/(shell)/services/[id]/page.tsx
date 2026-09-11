import Link from "next/link";
import { notFound } from "next/navigation";
import { asc, eq } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { media, serviceCategories, serviceSubcategories, services } from "@/lib/db/schema";
import { DeleteService, ServiceForm, type ServiceValues } from "../service-form";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (id === "new") return { title: "New service" };
  const [row] = await db
    .select({ titleEn: services.titleEn })
    .from(services)
    .where(eq(services.id, Number(id) || 0))
    .limit(1);
  return { title: row?.titleEn ?? "Service" };
}

export default async function ServiceEditor({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ category?: string }>;
}) {
  const session = await requirePermission("services.manage");
  const { id: rawId } = await params;
  const { category } = await searchParams;
  const isNew = rawId === "new";
  const id = isNew ? 0 : Number(rawId) || 0;

  const [categories, subcategories, library] = await Promise.all([
    db
      .select({ id: serviceCategories.id, titleEn: serviceCategories.titleEn })
      .from(serviceCategories)
      .orderBy(asc(serviceCategories.sortOrder)),
    db
      .select({
        id: serviceSubcategories.id,
        categoryId: serviceSubcategories.categoryId,
        titleEn: serviceSubcategories.titleEn,
      })
      .from(serviceSubcategories)
      .orderBy(asc(serviceSubcategories.sortOrder)),
    db
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
      .orderBy(asc(media.folder), asc(media.title)),
  ]);

  if (isNew) {
    const blank: ServiceValues = {
      slug: "",
      categoryId: Number(category) || categories[0]?.id || 0,
      subcategoryId: null,
      titleEn: "",
      titleAr: "",
      introEn: "",
      introAr: "",
      bodyEn: "",
      bodyAr: "",
      benefits: [],
      audience: [],
      requirements: [],
      processSteps: [],
      timelineEn: "",
      timelineAr: "",
      notesEn: "",
      notesAr: "",
      formPreset: "general",
      imageId: null,
      isFeatured: false,
      isPublished: true,
      sortOrder: 0,
    };
    return (
      <>
        <AdminPageHeader
          title="New service"
          crumbs={[{ label: "Services", href: "/admin/services" }, { label: "New" }]}
          actions={
            <Link href="/admin/services" className="admin-btn">
              Cancel
            </Link>
          }
        />
        <div className="max-w-4xl">
          <ServiceForm
            csrf={session.csrfToken}
            service={blank}
            categories={categories}
            subcategories={subcategories}
            media={library}
          />
        </div>
      </>
    );
  }

  const [row] = await db
    .select({ service: services, categorySlug: serviceCategories.slug })
    .from(services)
    .innerJoin(serviceCategories, eq(serviceCategories.id, services.categoryId))
    .where(eq(services.id, id))
    .limit(1);
  if (!row) notFound();

  return (
    <>
      <AdminPageHeader
        title={row.service.titleEn}
        crumbs={[{ label: "Services", href: "/admin/services" }, { label: row.service.titleEn }]}
        actions={
          <Link
            href={`/services/${row.categorySlug}/${row.service.slug}`}
            target="_blank"
            rel="noopener"
            className="admin-btn"
          >
            View live
          </Link>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[1.6fr_1fr] xl:items-start">
        <ServiceForm
          csrf={session.csrfToken}
          service={row.service as unknown as ServiceValues}
          categories={categories}
          subcategories={subcategories}
          media={library}
        />
        <DeleteService csrf={session.csrfToken} id={id} title={row.service.titleEn} />
      </div>
    </>
  );
}
