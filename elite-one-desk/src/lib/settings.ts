import "server-only";

import { cache } from "react";
import { eq, inArray } from "drizzle-orm";

import { db } from "@/lib/db";
import { siteSettings } from "@/lib/db/schema";
import { SETTINGS_DEFAULTS, type SettingsKey, type SiteSettings } from "./settings-defaults";

export { SETTINGS_DEFAULTS };
export type { SettingsKey, SiteSettings };

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

/** Stored values win, but a key the panel has never saved still has a shape. */
function merge(stored: Array<{ key: string; value: Record<string, unknown> }>): SiteSettings {
  const result = clone(SETTINGS_DEFAULTS) as unknown as SiteSettings;
  for (const row of stored) {
    const key = row.key as SettingsKey;
    if (!(key in result)) continue;
    Object.assign(result[key] as Record<string, unknown>, row.value ?? {});
  }
  return result;
}

/** One query per request, shared by the layout, the pages and the metadata. */
export const getSettings = cache(async (): Promise<SiteSettings> => {
  const rows = await db
    .select({ key: siteSettings.key, value: siteSettings.value })
    .from(siteSettings)
    .where(inArray(siteSettings.key, Object.keys(SETTINGS_DEFAULTS)));
  return merge(rows);
});

export async function getSettingsGroup<K extends SettingsKey>(key: K): Promise<SiteSettings[K]> {
  const [row] = await db
    .select({ value: siteSettings.value })
    .from(siteSettings)
    .where(eq(siteSettings.key, key))
    .limit(1);
  const base = clone(SETTINGS_DEFAULTS[key]) as SiteSettings[K];
  return Object.assign(base as Record<string, unknown>, row?.value ?? {}) as SiteSettings[K];
}

export async function saveSettingsGroup(
  key: SettingsKey,
  value: Record<string, unknown>,
  userId?: number,
): Promise<void> {
  await db
    .insert(siteSettings)
    .values({ key, value, updatedBy: userId ?? null })
    .onConflictDoUpdate({
      target: siteSettings.key,
      set: { value, updatedAt: new Date(), updatedBy: userId ?? null },
    });
}

/**
 * Builds a wa.me link with the message pre-filled. Returns null when WhatsApp
 * is off or no number is configured, so a caller never renders a dead button.
 */
export function whatsappLink(
  settings: SiteSettings,
  locale: "en" | "ar",
  context?: string,
): string | null {
  const { enabled, number, defaultMessageEn, defaultMessageAr } = settings.whatsapp;
  const digits = String(number).replace(/\D/g, "");
  if (!enabled || !digits) return null;
  const base = locale === "ar" ? defaultMessageAr : defaultMessageEn;
  const message = context
    ? locale === "ar"
      ? `مرحبًا إيليت ون ديسك، أود الاستفسار بخصوص: ${context}.`
      : `Hello Elite One Desk, I would like assistance with ${context}.`
    : base;
  return `https://wa.me/${digits}?text=${encodeURIComponent(message)}`;
}
