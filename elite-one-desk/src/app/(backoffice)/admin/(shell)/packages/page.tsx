import Link from "next/link";
import { asc, desc } from "drizzle-orm";

import { AdminPageHeader, EmptyState } from "@/components/admin/page-header";
import { Icon } from "@/components/ui/icon";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { travelPackages } from "@/lib/db/schema";
import { PackageRows } from "./package-rows";

export const metadata = { title: "Travel packages" };
export const dynamic = "force-dynamic";

export default async function PackagesPage() {
  const session = await requirePermission("packages.manage", "/admin/packages");

  const rows = await db
    .select({
      id: travelPackages.id,
      slug: travelPackages.slug,
      titleEn: travelPackages.titleEn,
      region: travelPackages.region,
      destinationEn: travelPackages.destinationEn,
      durationEn: travelPackages.durationEn,
      isPublished: travelPackages.isPublished,
      isFeatured: travelPackages.isFeatured,
    })
    .from(travelPackages)
    .orderBy(desc(travelPackages.isFeatured), asc(travelPackages.sortOrder), asc(travelPackages.id));

  return (
    <>
      <AdminPageHeader
        title="Travel packages"
        description="Egypt and international programmes. Each gets its own page with a travel request form attached."
        actions={
          <Link href="/admin/packages/new" className="admin-btn admin-btn-primary">
            <Icon name="sparkle" size={14} />
            New package
          </Link>
        }
      />
      {rows.length === 0 ? (
        <EmptyState
          title="No packages yet"
          body="Add one and it appears on the packages page and anywhere a package grid section is placed."
          action={
            <Link href="/admin/packages/new" className="admin-btn admin-btn-primary">
              New package
            </Link>
          }
        />
      ) : (
        <PackageRows csrf={session.csrfToken} rows={rows} />
      )}
    </>
  );
}
