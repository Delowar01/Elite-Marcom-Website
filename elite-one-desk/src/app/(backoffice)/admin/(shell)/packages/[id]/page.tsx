import Link from "next/link";
import { notFound } from "next/navigation";
import { asc, eq } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { media, travelPackages } from "@/lib/db/schema";
import { DeletePackage, PackageForm, type PackageValues } from "../package-form";

export const dynamic = "force-dynamic";

const BLANK: PackageValues = {
  slug: "",
  region: "egypt",
  titleEn: "",
  titleAr: "",
  destinationEn: "",
  destinationAr: "",
  durationEn: "",
  durationAr: "",
  summaryEn: "",
  summaryAr: "",
  bodyEn: "",
  bodyAr: "",
  highlights: [],
  imageId: null,
  isFeatured: false,
  isPublished: true,
  sortOrder: 0,
};

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (id === "new") return { title: "New package" };
  const [row] = await db
    .select({ titleEn: travelPackages.titleEn })
    .from(travelPackages)
    .where(eq(travelPackages.id, Number(id) || 0))
    .limit(1);
  return { title: row?.titleEn ?? "Package" };
}

export default async function PackageEditor({ params }: { params: Promise<{ id: string }> }) {
  const session = await requirePermission("packages.manage");
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
          title="New package"
          crumbs={[{ label: "Travel packages", href: "/admin/packages" }, { label: "New" }]}
          actions={
            <Link href="/admin/packages" className="admin-btn">
              Cancel
            </Link>
          }
        />
        <div className="max-w-4xl">
          <PackageForm csrf={session.csrfToken} pkg={BLANK} media={library} />
        </div>
      </>
    );
  }

  const [row] = await db.select().from(travelPackages).where(eq(travelPackages.id, id)).limit(1);
  if (!row) notFound();

  return (
    <>
      <AdminPageHeader
        title={row.titleEn}
        crumbs={[{ label: "Travel packages", href: "/admin/packages" }, { label: row.titleEn }]}
        actions={
          <Link href={`/packages/${row.slug}`} target="_blank" rel="noopener" className="admin-btn">
            View live
          </Link>
        }
      />
      <div className="grid gap-5 xl:grid-cols-[1.6fr_1fr] xl:items-start">
        <PackageForm csrf={session.csrfToken} pkg={row as unknown as PackageValues} media={library} />
        <DeletePackage csrf={session.csrfToken} id={id} title={row.titleEn} />
      </div>
    </>
  );
}
