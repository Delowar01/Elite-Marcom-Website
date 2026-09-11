import Link from "next/link";
import { desc, eq, sql } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import {
  media,
  pageSections,
  serviceCategories,
  services,
  testimonials,
  travelPackages,
  videos,
} from "@/lib/db/schema";
import { MEDIA_FOLDERS, isMediaFolder } from "@/lib/media/folders";
import { LibraryGrid, UploadPanel, type LibraryItem } from "./media-client";

export const metadata = { title: "Media library" };
export const dynamic = "force-dynamic";

export default async function MediaPage({
  searchParams,
}: {
  searchParams: Promise<{ folder?: string }>;
}) {
  const session = await requirePermission("media.manage", "/admin/media");
  const { folder } = await searchParams;
  const active = folder && isMediaFolder(folder) ? folder : "";

  const rows = await db
    .select()
    .from(media)
    .where(active ? eq(media.folder, active) : undefined)
    .orderBy(desc(media.createdAt));

  // One pass to count placements for every image, rather than a query per card.
  const [usageRows] = await Promise.all([
    db.execute<{ image_id: number; n: number }>(sql`
      select image_id, count(*)::int as n from (
        select (e.value #>> '{}')::int as image_id
          from ${pageSections},
               lateral jsonb_each(${pageSections.published}) e
         where jsonb_typeof(e.value) = 'number'
        union all
        select (e.value #>> '{}')::int
          from ${pageSections},
               lateral jsonb_each(coalesce(${pageSections.draft}, '{}'::jsonb)) e
         where jsonb_typeof(e.value) = 'number'
        union all select ${serviceCategories.imageId} from ${serviceCategories} where ${serviceCategories.imageId} is not null
        union all select ${services.imageId} from ${services} where ${services.imageId} is not null
        union all select ${travelPackages.imageId} from ${travelPackages} where ${travelPackages.imageId} is not null
        union all select ${videos.thumbnailId} from ${videos} where ${videos.thumbnailId} is not null
        union all select ${testimonials.imageId} from ${testimonials} where ${testimonials.imageId} is not null
      ) placements
      where image_id is not null
      group by image_id
    `),
  ]);

  const usage = new Map<number, number>();
  for (const row of usageRows as unknown as Array<{ image_id: number; n: number }>) {
    usage.set(Number(row.image_id), Number(row.n));
  }

  const items: LibraryItem[] = rows.map((row) => ({
    id: row.id,
    filename: row.filename,
    title: row.title,
    altEn: row.altEn,
    altAr: row.altAr,
    folder: row.folder,
    width: row.width,
    height: row.height,
    byteSize: row.byteSize,
    mimeType: row.mimeType,
    createdAt: row.createdAt.toISOString(),
    uses: usage.get(row.id) ?? 0,
  }));

  return (
    <>
      <AdminPageHeader
        title="Media library"
        description="Every picture on the site lives here. Uploads are re-encoded on the server, so what is stored is a file this application produced — not the one that was sent."
      />

      <nav aria-label="Folders" className="mb-4 flex flex-wrap gap-1.5">
        <Link
          href="/admin/media"
          className="admin-btn admin-btn-sm"
          style={!active ? { borderColor: "var(--color-orange)" } : undefined}
        >
          All
        </Link>
        {MEDIA_FOLDERS.map((name) => (
          <Link
            key={name}
            href={`/admin/media?folder=${name}`}
            className="admin-btn admin-btn-sm"
            style={active === name ? { borderColor: "var(--color-orange)" } : undefined}
          >
            {name}
          </Link>
        ))}
      </nav>

      <div className="mb-5">
        <UploadPanel csrf={session.csrfToken} />
      </div>

      <LibraryGrid csrf={session.csrfToken} items={items} />
    </>
  );
}
