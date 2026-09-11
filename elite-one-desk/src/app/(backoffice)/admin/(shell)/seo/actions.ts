"use server";

import { and, eq } from "drizzle-orm";
import { revalidatePath } from "next/cache";

import { logActivity } from "@/lib/activity";
import {
  checkbox, fail, field, ok, optionalId, runAction, type ActionState,
} from "@/lib/admin/actions";
import { guardAction } from "@/lib/auth/guard";
import { TAGS, revalidate } from "@/lib/cache";
import { db } from "@/lib/db";
import { seoMetadata } from "@/lib/db/schema";

const TYPES = ["page", "category", "service", "package"] as const;
type EntityType = (typeof TYPES)[number];
const isType = (value: string): value is EntityType => (TYPES as readonly string[]).includes(value);

export async function saveSeo(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("seo-save", async () => {
    const session = await guardAction("seo.manage", form);
    const entityType = field(form, "entityType", 32);
    const entityKey = field(form, "entityKey", 190);
    if (!isType(entityType) || !entityKey) return fail("That page could not be identified.");

    const canonicalUrl = field(form, "canonicalUrl", 255);
    if (canonicalUrl && !/^https:\/\//i.test(canonicalUrl) && !canonicalUrl.startsWith("/")) {
      return fail("A canonical address must be a site path or a full https address.", {
        canonicalUrl: "Start with / or https://.",
      });
    }

    const values = {
      entityType,
      entityKey,
      titleEn: field(form, "titleEn", 190),
      titleAr: field(form, "titleAr", 190),
      descriptionEn: field(form, "descriptionEn", 320),
      descriptionAr: field(form, "descriptionAr", 320),
      canonicalUrl,
      ogTitle: field(form, "ogTitle", 190),
      ogDescription: field(form, "ogDescription", 320),
      ogImageId: optionalId(form, "ogImageId"),
      noindex: checkbox(form, "noindex"),
    };

    await db
      .insert(seoMetadata)
      .values(values)
      .onConflictDoUpdate({
        target: [seoMetadata.entityType, seoMetadata.entityKey],
        set: { ...values, updatedAt: new Date() },
      });

    await logActivity(session, {
      action: "seo.updated",
      entityType: "seo",
      entityId: `${entityType}:${entityKey}`,
      summary: `Updated SEO for ${entityType} ${entityKey}`,
    });
    revalidate(TAGS.seo);
    revalidatePath("/admin/seo");
    return ok("SEO saved.");
  });
}

export async function clearSeo(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("seo-clear", async () => {
    const session = await guardAction("seo.manage", form);
    const entityType = field(form, "entityType", 32);
    const entityKey = field(form, "entityKey", 190);
    if (!isType(entityType) || !entityKey) return fail("That page could not be identified.");

    await db
      .delete(seoMetadata)
      .where(and(eq(seoMetadata.entityType, entityType), eq(seoMetadata.entityKey, entityKey)));

    await logActivity(session, {
      action: "seo.cleared",
      entityType: "seo",
      entityId: `${entityType}:${entityKey}`,
      summary: `Removed the SEO override for ${entityType} ${entityKey}`,
    });
    revalidate(TAGS.seo);
    revalidatePath("/admin/seo");
    return ok("Override removed. The page falls back to its own title and intro.");
  });
}
