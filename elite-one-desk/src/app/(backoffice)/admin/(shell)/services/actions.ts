"use server";

import { and, eq } from "drizzle-orm";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";

import { logActivity } from "@/lib/activity";
import {
  checkbox,
  fail,
  field,
  numberField,
  ok,
  optionalId,
  runAction,
  type ActionState,
} from "@/lib/admin/actions";
import { guardAction } from "@/lib/auth/guard";
import { TAGS, revalidate } from "@/lib/cache";
import { sanitizeRichText } from "@/lib/cms/sanitize";
import { db } from "@/lib/db";
import { services } from "@/lib/db/schema";
import type { LocalisedItem, LocalisedStep } from "@/lib/db/schema";
import { isPresetKey } from "@/lib/forms/presets";

const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

const refresh = () => {
  revalidate(TAGS.catalog);
  revalidatePath("/admin/services");
};

/** Parses one of the hidden JSON lists the list editors submit. */
function itemList(form: FormData, name: string, max = 16): LocalisedItem[] {
  try {
    const raw = JSON.parse(String(form.get(name) ?? "[]")) as unknown;
    if (!Array.isArray(raw)) return [];
    return raw
      .map((row) => {
        const record = (typeof row === "object" && row ? row : {}) as Record<string, unknown>;
        return {
          en: String(record.en ?? "").slice(0, 400).trim(),
          ar: String(record.ar ?? "").slice(0, 400).trim(),
        };
      })
      .filter((row) => row.en || row.ar)
      .slice(0, max);
  } catch {
    return [];
  }
}

function stepList(form: FormData, name: string, max = 10): LocalisedStep[] {
  try {
    const raw = JSON.parse(String(form.get(name) ?? "[]")) as unknown;
    if (!Array.isArray(raw)) return [];
    return raw
      .map((row) => {
        const record = (typeof row === "object" && row ? row : {}) as Record<string, unknown>;
        return {
          en: String(record.en ?? "").slice(0, 200).trim(),
          ar: String(record.ar ?? "").slice(0, 200).trim(),
          detailEn: String(record.detailEn ?? "").slice(0, 800).trim(),
          detailAr: String(record.detailAr ?? "").slice(0, 800).trim(),
        };
      })
      .filter((row) => row.en || row.ar)
      .slice(0, max);
  } catch {
    return [];
  }
}

function readService(form: FormData) {
  const preset = field(form, "formPreset", 32);
  return {
    categoryId: Number(form.get("categoryId")),
    subcategoryId: optionalId(form, "subcategoryId"),
    titleEn: field(form, "titleEn", 190),
    titleAr: field(form, "titleAr", 190),
    introEn: field(form, "introEn", 2000),
    introAr: field(form, "introAr", 2000),
    bodyEn: sanitizeRichText(field(form, "bodyEn", 20000)),
    bodyAr: sanitizeRichText(field(form, "bodyAr", 20000)),
    benefits: itemList(form, "benefits"),
    audience: itemList(form, "audience"),
    requirements: itemList(form, "requirements"),
    processSteps: stepList(form, "processSteps"),
    timelineEn: field(form, "timelineEn", 190),
    timelineAr: field(form, "timelineAr", 190),
    notesEn: sanitizeRichText(field(form, "notesEn", 8000)),
    notesAr: sanitizeRichText(field(form, "notesAr", 8000)),
    formPreset: isPresetKey(preset) ? preset : "general",
    imageId: optionalId(form, "imageId"),
    isFeatured: checkbox(form, "isFeatured"),
    isPublished: checkbox(form, "isPublished"),
    sortOrder: numberField(form, "sortOrder", 0),
  };
}

export async function createService(_prev: ActionState, form: FormData): Promise<ActionState> {
  let newId = 0;
  const result = await runAction("service-create", async () => {
    const session = await guardAction("services.manage", form);
    const slug = field(form, "slug", 120).toLowerCase();
    const values = readService(form);

    if (!values.titleEn) return fail("Give the service a title.", { titleEn: "Required." });
    if (!values.categoryId) return fail("Choose a category.", { categoryId: "Required." });
    if (!SLUG.test(slug)) {
      return fail("The address must be lower-case words joined by hyphens.", { slug: "Invalid." });
    }

    const [taken] = await db
      .select({ id: services.id })
      .from(services)
      .where(and(eq(services.categoryId, values.categoryId), eq(services.slug, slug)))
      .limit(1);
    if (taken) return fail("A service in that category already uses this address.", { slug: "Already taken." });

    const [row] = await db
      .insert(services)
      .values({ ...values, slug })
      .returning({ id: services.id });
    newId = row!.id;

    await logActivity(session, {
      action: "service.created",
      entityType: "service",
      entityId: newId,
      summary: `Created the service “${values.titleEn}”`,
    });
    refresh();
    return ok("Service created.", newId);
  });

  if (!result.ok) return result;
  redirect(`/admin/services/${newId}`);
}

export async function updateService(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("service-update", async () => {
    const session = await guardAction("services.manage", form);
    const id = Number(form.get("id"));
    const values = readService(form);
    if (!values.titleEn) return fail("Give the service a title.", { titleEn: "Required." });
    if (!values.categoryId) return fail("Choose a category.", { categoryId: "Required." });

    const [row] = await db
      .update(services)
      .set({ ...values, updatedAt: new Date() })
      .where(eq(services.id, id))
      .returning({ slug: services.slug });
    if (!row) return fail("That service no longer exists.");

    await logActivity(session, {
      action: "service.updated",
      entityType: "service",
      entityId: id,
      summary: `Updated the service “${values.titleEn}”`,
    });
    refresh();
    revalidatePath(`/admin/services/${id}`);
    return ok("Service saved.");
  });
}

export async function toggleServicePublished(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("service-toggle", async () => {
    const session = await guardAction("services.manage", form);
    const id = Number(form.get("id"));
    const [row] = await db.select().from(services).where(eq(services.id, id)).limit(1);
    if (!row) return fail("That service no longer exists.");

    await db
      .update(services)
      .set({ isPublished: !row.isPublished, updatedAt: new Date() })
      .where(eq(services.id, id));

    await logActivity(session, {
      action: row.isPublished ? "service.unpublished" : "service.published",
      entityType: "service",
      entityId: id,
      summary: `${row.isPublished ? "Unpublished" : "Published"} “${row.titleEn}”`,
    });
    refresh();
    return ok(row.isPublished ? "Service hidden from the site." : "Service is live.");
  });
}

export async function deleteService(_prev: ActionState, form: FormData): Promise<ActionState> {
  const result = await runAction("service-delete", async () => {
    const session = await guardAction("services.manage", form);
    const id = Number(form.get("id"));
    const [row] = await db.select().from(services).where(eq(services.id, id)).limit(1);
    if (!row) return fail("That service no longer exists.");

    await db.delete(services).where(eq(services.id, id));
    await logActivity(session, {
      action: "service.deleted",
      entityType: "service",
      entityId: id,
      summary: `Deleted the service “${row.titleEn}”`,
    });
    refresh();
    return ok("Service deleted.");
  });
  if (!result.ok) return result;
  redirect("/admin/services");
}
