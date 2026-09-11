import { asc, desc, eq } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { media, videos } from "@/lib/db/schema";
import { VideosClient, type VideoRow } from "./videos-client";

export const metadata = { title: "Videos" };
export const dynamic = "force-dynamic";

export default async function VideosPage() {
  const session = await requirePermission("videos.manage", "/admin/videos");

  const [rows, library] = await Promise.all([
    db
      .select({ video: videos, thumbnailFilename: media.filename })
      .from(videos)
      .leftJoin(media, eq(media.id, videos.thumbnailId))
      .orderBy(desc(videos.isFeatured), asc(videos.sortOrder), asc(videos.id)),
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

  const items: VideoRow[] = rows.map(({ video, thumbnailFilename }) => ({
    ...video,
    thumbnailFilename,
  }));

  return (
    <>
      <AdminPageHeader
        title="Videos"
        description="The showcase on the homepage. Posters are shown first and the player is only fetched when someone presses play, so the section costs almost nothing until it is used."
      />
      <VideosClient csrf={session.csrfToken} rows={items} media={library} />
    </>
  );
}
