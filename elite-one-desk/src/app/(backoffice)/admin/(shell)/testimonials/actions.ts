"use server";

import { eq, sql } from "drizzle-orm";
import { revalidatePath } from "next/cache";

import { logActivity } from "@/lib/activity";
import {
  checkbox, fail, field, numberField, ok, optionalId, runAction, type ActionState,
} from "@/lib/admin/actions";
import { guardAction } from "@/lib/auth/guard";
import { TAGS, revalidate } from "@/lib/cache";
import { db } from "@/lib/db";
import { testimonials } from "@/lib/db/schema";

const refresh = () => {
  revalidate(TAGS.testimonials);
  revalidatePath("/admin/testimonials");
};

export async function saveTestimonial(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("testimonial-save", async () => {
    const session = await guardAction("testimonials.manage", form);
    const id = Number(form.get("id")) || 0;
    const name = field(form, "name", 120);
    const quoteEn = field(form, "quoteEn", 2000);

    if (!name) return fail("Who is this from?", { name: "Required." });
    if (!quoteEn && !field(form, "quoteAr", 2000)) {
      return fail("A testimonial needs the words.", { quoteEn: "Required." });
    }

    const ratingRaw = numberField(form, "rating", 0);
    const values = {
      name,
      company: field(form, "company", 120),
      country: field(form, "country", 80),
      quoteEn,
      quoteAr: field(form, "quoteAr", 2000),
      imageId: optionalId(form, "imageId"),
      // Zero means "they did not give one" and renders no stars at all.
      rating: ratingRaw >= 1 && ratingRaw <= 5 ? ratingRaw : null,
      isFeatured: checkbox(form, "isFeatured"),
      isPublished: checkbox(form, "isPublished"),
      sortOrder: numberField(form, "sortOrder", 0),
    };

    if (id) {
      await db.update(testimonials).set({ ...values, updatedAt: new Date() }).where(eq(testimonials.id, id));
    } else {
      const [last] = await db
        .select({ n: sql<number>`coalesce(max(${testimonials.sortOrder}), -1)::int` })
        .from(testimonials);
      await db.insert(testimonials).values({ ...values, sortOrder: (last?.n ?? -1) + 1 });
    }

    await logActivity(session, {
      action: id ? "testimonial.updated" : "testimonial.created",
      entityType: "testimonial",
      entityId: id || 0,
      summary: `${id ? "Updated" : "Added"} a testimonial from ${name}`,
    });
    refresh();
    return ok(id ? "Testimonial saved." : "Testimonial added.");
  });
}

export async function deleteTestimonial(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("testimonial-delete", async () => {
    const session = await guardAction("testimonials.manage", form);
    const id = Number(form.get("id"));
    const [row] = await db.select().from(testimonials).where(eq(testimonials.id, id)).limit(1);
    if (!row) return fail("That testimonial no longer exists.");
    await db.delete(testimonials).where(eq(testimonials.id, id));
    await logActivity(session, {
      action: "testimonial.deleted",
      entityType: "testimonial",
      entityId: id,
      summary: `Deleted the testimonial from ${row.name}`,
    });
    refresh();
    return ok("Testimonial deleted.");
  });
}

export async function toggleTestimonial(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("testimonial-toggle", async () => {
    const session = await guardAction("testimonials.manage", form);
    const id = Number(form.get("id"));
    const what = field(form, "what", 16);
    const [row] = await db.select().from(testimonials).where(eq(testimonials.id, id)).limit(1);
    if (!row) return fail("That testimonial no longer exists.");
    await db
      .update(testimonials)
      .set(
        what === "featured"
          ? { isFeatured: !row.isFeatured, updatedAt: new Date() }
          : { isPublished: !row.isPublished, updatedAt: new Date() },
      )
      .where(eq(testimonials.id, id));
    await logActivity(session, {
      action: "testimonial.updated",
      entityType: "testimonial",
      entityId: id,
      summary: `Toggled ${what} on the testimonial from ${row.name}`,
    });
    refresh();
    return ok();
  });
}
