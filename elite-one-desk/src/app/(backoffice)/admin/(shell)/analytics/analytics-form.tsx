"use client";

import { AdminForm, Field, SubmitButton } from "@/components/admin/form";
import { saveAnalytics } from "../settings/actions";

export function AnalyticsForm({
  csrf,
  analytics,
}: {
  csrf: string;
  analytics: { ga4Id: string; gtmId: string; metaPixelId: string };
}) {
  return (
    <AdminForm action={saveAnalytics} className="admin-card max-w-2xl p-5">
      <input type="hidden" name="_csrf" value={csrf} />

      <div className="space-y-5">
        <Field
          label="Google Analytics 4 — measurement id"
          name="ga4Id"
          hint="Starts with G-. IP anonymisation is switched on for you. Leave empty to load nothing."
        >
          <input
            id="ga4Id"
            name="ga4Id"
            defaultValue={analytics.ga4Id}
            dir="ltr"
            placeholder="G-XXXXXXXXXX"
            className="admin-input"
          />
        </Field>

        <Field
          label="Google Tag Manager — container id"
          name="gtmId"
          hint="Starts with GTM-. Use this instead of GA4 if your tags are managed in Tag Manager; setting both loads both."
        >
          <input
            id="gtmId"
            name="gtmId"
            defaultValue={analytics.gtmId}
            dir="ltr"
            placeholder="GTM-XXXXXXX"
            className="admin-input"
          />
        </Field>

        <Field
          label="Meta Pixel id"
          name="metaPixelId"
          hint="Digits only. Only add this if the business is actually running Meta advertising."
        >
          <input
            id="metaPixelId"
            name="metaPixelId"
            defaultValue={analytics.metaPixelId}
            dir="ltr"
            inputMode="numeric"
            className="admin-input"
          />
        </Field>
      </div>

      <div className="mt-6 border-t border-[var(--admin-line)] pt-5">
        <SubmitButton />
      </div>

      <p className="mt-5 text-[0.75rem] text-muted">
        Whatever you enable here is disclosed in the privacy policy page — keep the two in step.
      </p>
    </AdminForm>
  );
}
