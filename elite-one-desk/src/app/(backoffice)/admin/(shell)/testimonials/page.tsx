import { asc, desc } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { media, testimonials } from "@/lib/db/schema";
import { TestimonialsClient, type TestimonialRow } from "./testimonials-client";

export const metadata = { title: "Testimonials" };
export const dynamic = "force-dynamic";

export default async function TestimonialsPage() {
  const session = await requirePermission("testimonials.manage", "/admin/testimonials");

  const [rows, library] = await Promise.all([
    db
      .select()
      .from(testimonials)
      .orderBy(desc(testimonials.isFeatured), asc(testimonials.sortOrder), asc(testimonials.id)),
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

  return (
    <>
      <AdminPageHeader
        title="Testimonials"
        description="Quotes from clients, shown on the homepage. Publish only what you have permission to quote."
      />
      <TestimonialsClient
        csrf={session.csrfToken}
        rows={rows as TestimonialRow[]}
        media={library}
      />
    </>
  );
}
