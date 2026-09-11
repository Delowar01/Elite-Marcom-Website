import { asc } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { navigationItems } from "@/lib/db/schema";
import { NavigationClient, type NavRow } from "./navigation-client";

export const metadata = { title: "Navigation & footer" };
export const dynamic = "force-dynamic";

export default async function NavigationPage() {
  const session = await requirePermission("navigation.manage", "/admin/navigation");

  const rows = await db
    .select()
    .from(navigationItems)
    .orderBy(asc(navigationItems.menu), asc(navigationItems.sortOrder), asc(navigationItems.id));

  return (
    <>
      <AdminPageHeader
        title="Navigation & footer"
        description="Both editions read the same structure: the English label is required, and an empty Arabic label falls back to it."
      />
      <NavigationClient csrf={session.csrfToken} rows={rows as NavRow[]} />
    </>
  );
}
