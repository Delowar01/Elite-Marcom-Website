import Link from "next/link";
import { notFound } from "next/navigation";
import { asc, eq } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { Icon } from "@/components/ui/icon";
import { requirePermission } from "@/lib/auth/guard";
import { blocksForPage, getBlock } from "@/lib/cms/blocks";
import { text } from "@/lib/cms/values";
import { db } from "@/lib/db";
import { pageSections, pages } from "@/lib/db/schema";
import { DeletePageForm, PageSettingsForm, PublishAllButton } from "../page-forms";
import { SectionList, type SectionRow } from "./section-list";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const [row] = await db.select({ titleEn: pages.titleEn }).from(pages).where(eq(pages.slug, slug)).limit(1);
  return { title: row?.titleEn ?? "Page" };
}

export default async function PageEditor({ params }: { params: Promise<{ slug: string }> }) {
  const session = await requirePermission("content.view");
  const { slug } = await params;
  const canManage = session.permissions.has("content.manage");

  const [page] = await db.select().from(pages).where(eq(pages.slug, slug)).limit(1);
  if (!page) notFound();

  const rows = await db
    .select()
    .from(pageSections)
    .where(eq(pageSections.pageId, page.id))
    .orderBy(asc(pageSections.position), asc(pageSections.id));

  const sections: SectionRow[] = rows.map((row) => {
    const block = getBlock(row.blockType);
    const values = (row.draft ?? row.published) as Record<string, unknown>;
    // A one-line summary so the list is scannable without opening each section.
    const summary =
      text(values, "title", "en") ||
      text(values, "headline", "en") ||
      text(values, "eyebrow", "en") ||
      "";
    return {
      id: row.id,
      blockType: row.blockType,
      blockName: block?.name ?? row.blockType,
      blockDescription: block?.description ?? "",
      summary,
      isPublished: row.isPublished,
      hasDraft: Boolean(row.draft),
      position: row.position,
    };
  });

  const draftCount = sections.filter((s) => s.hasDraft).length;
  const livePath = page.slug === "home" ? "/" : `/${page.slug}`;

  return (
    <>
      <AdminPageHeader
        title={page.titleEn}
        description={`The sections below are the page, in order. ${page.isPublished ? "" : "This page is currently unpublished."}`}
        crumbs={[{ label: "Pages & sections", href: "/admin/pages" }, { label: page.titleEn }]}
        actions={
          <>
            {canManage ? (
              <PublishAllButton csrf={session.csrfToken} pageId={page.id} count={draftCount} />
            ) : null}
            <Link href={`/admin/pages/${page.slug}/preview`} className="admin-btn">
              <Icon name="search" size={13} />
              Preview
            </Link>
            <Link href={livePath} target="_blank" rel="noopener" className="admin-btn">
              <Icon name="arrowUpRight" size={13} />
              View live
            </Link>
          </>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr] xl:items-start">
        <SectionList
          csrf={session.csrfToken}
          pageId={page.id}
          sections={sections}
          blocks={blocksForPage(page.slug)}
          canManage={canManage}
        />

        {canManage ? (
          <div className="space-y-5">
            <PageSettingsForm csrf={session.csrfToken} page={page} />
            {page.kind === "custom" ? (
              <DeletePageForm csrf={session.csrfToken} id={page.id} title={page.titleEn} />
            ) : null}
          </div>
        ) : null}
      </div>
    </>
  );
}
