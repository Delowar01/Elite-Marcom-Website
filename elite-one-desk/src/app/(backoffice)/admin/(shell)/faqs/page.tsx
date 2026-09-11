import { asc } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { faqs, serviceCategories, services } from "@/lib/db/schema";
import { FaqsClient, type FaqRow } from "./faqs-client";

export const metadata = { title: "FAQs" };
export const dynamic = "force-dynamic";

export default async function FaqsPage() {
  const session = await requirePermission("faqs.manage", "/admin/faqs");

  const [rows, categories, serviceRows] = await Promise.all([
    db.select().from(faqs).orderBy(asc(faqs.sortOrder), asc(faqs.id)),
    db
      .select({ id: serviceCategories.id, label: serviceCategories.titleEn })
      .from(serviceCategories)
      .orderBy(asc(serviceCategories.sortOrder)),
    db
      .select({ id: services.id, label: services.titleEn })
      .from(services)
      .orderBy(asc(services.titleEn)),
  ]);

  const categoryNames = new Map(categories.map((c) => [c.id, c.label]));
  const serviceNames = new Map(serviceRows.map((s) => [s.id, s.label]));

  const items: FaqRow[] = rows.map((row) => ({
    ...row,
    attachedTo:
      row.scope === "category"
        ? (categoryNames.get(row.categoryId ?? 0) ?? "Category")
        : row.scope === "service"
          ? (serviceNames.get(row.serviceId ?? 0) ?? "Service")
          : "Global",
  }));

  return (
    <>
      <AdminPageHeader
        title="FAQs"
        description="Questions shown on the homepage, on category pages and on individual service pages. Each answer is also published as structured data, so it can appear directly in search results."
      />
      <FaqsClient
        csrf={session.csrfToken}
        rows={items}
        categories={categories}
        services={serviceRows}
      />
    </>
  );
}
