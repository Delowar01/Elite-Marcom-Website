import { AdminPageHeader } from "@/components/admin/page-header";
import { requirePermission } from "@/lib/auth/guard";
import { getSettings } from "@/lib/settings";
import { AnalyticsForm } from "./analytics-form";

export const metadata = { title: "Analytics" };
export const dynamic = "force-dynamic";

export default async function AnalyticsPage() {
  const session = await requirePermission("analytics.manage", "/admin/analytics");
  const settings = await getSettings();

  return (
    <>
      <AdminPageHeader
        title="Analytics"
        description="No measurement id is built into the site. A tag is loaded only once you enter its id here, and only after the page has become interactive — so analytics never competes with the first paint."
      />
      <AnalyticsForm csrf={session.csrfToken} analytics={settings.analytics} />
    </>
  );
}
