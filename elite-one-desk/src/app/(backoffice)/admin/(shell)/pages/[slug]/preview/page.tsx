import Link from "next/link";
import { notFound } from "next/navigation";
import { eq } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { pages } from "@/lib/db/schema";
import { PreviewFrame } from "./preview-frame";

export const dynamic = "force-dynamic";
export const metadata = { title: "Preview" };

export default async function PreviewPage({ params }: { params: Promise<{ slug: string }> }) {
  await requirePermission("content.view");
  const { slug } = await params;

  const [page] = await db.select().from(pages).where(eq(pages.slug, slug)).limit(1);
  if (!page) notFound();

  return (
    <>
      <AdminPageHeader
        title={`Preview — ${page.titleEn}`}
        description="Drafts and hidden sections included. Nothing here is visible to the public until you publish it."
        crumbs={[
          { label: "Pages & sections", href: "/admin/pages" },
          { label: page.titleEn, href: `/admin/pages/${page.slug}` },
          { label: "Preview" },
        ]}
        actions={
          <Link href={`/admin/pages/${page.slug}`} className="admin-btn">
            Back to the page
          </Link>
        }
      />
      <PreviewFrame src={page.slug === "home" ? "/" : `/${page.slug}`} title={page.titleEn} />
    </>
  );
}
