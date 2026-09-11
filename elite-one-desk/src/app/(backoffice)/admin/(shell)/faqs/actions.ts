"use server";

import { eq, sql } from "drizzle-orm";
import { revalidatePath } from "next/cache";

import { logActivity } from "@/lib/activity";
import {
  checkbox, fail, field, numberField, ok, optionalId, runAction, type ActionState,
} from "@/lib/admin/actions";
import { guardAction } from "@/lib/auth/guard";
import { TAGS, revalidate } from "@/lib/cache";
import { sanitizeRichText } from "@/lib/cms/sanitize";
import { db } from "@/lib/db";
import { faqs } from "@/lib/db/schema";

const SCOPES = ["global", "category", "service"] as const;
type Scope = (typeof SCOPES)[number];
const isScope = (value: string): value is Scope => (SCOPES as readonly string[]).includes(value);

const refresh = () => {
  revalidate(TAGS.faqs);
  revalidatePath("/admin/faqs");
};

export async function saveFaq(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("faq-save", async () => {
    const session = await guardAction("faqs.manage", form);
    const id = Number(form.get("id")) || 0;
    const questionEn = field(form, "questionEn", 255);
    const rawScope = field(form, "scope", 16);
    const scope: Scope = isScope(rawScope) ? rawScope : "global";

    if (!questionEn) return fail("Write the question.", { questionEn: "Required." });

    const categoryId = optionalId(form, "categoryId");
    const serviceId = optionalId(form, "serviceId");
    if (scope === "category" && !categoryId) {
      return fail("Choose the category this question belongs to.", { categoryId: "Required." });
    }
    if (scope === "service" && !serviceId) {
      return fail("Choose the service this question belongs to.", { serviceId: "Required." });
    }

    const values = {
      scope,
      // Only the link the scope actually uses is stored; the other is cleared,
      // so a question moved from one scope to another cannot keep a stale link.
      categoryId: scope === "category" ? categoryId : null,
      serviceId: scope === "service" ? serviceId : null,
      questionEn,
      questionAr: field(form, "questionAr", 255),
      answerEn: sanitizeRichText(field(form, "answerEn", 8000)),
      answerAr: sanitizeRichText(field(form, "answerAr", 8000)),
      isPublished: checkbox(form, "isPublished"),
      sortOrder: numberField(form, "sortOrder", 0),
    };

    if (id) {
      await db.update(faqs).set({ ...values, updatedAt: new Date() }).where(eq(faqs.id, id));
    } else {
      const [last] = await db.select({ n: sql<number>`coalesce(max(${faqs.sortOrder}), -1)::int` }).from(faqs);
      await db.insert(faqs).values({ ...values, sortOrder: (last?.n ?? -1) + 1 });
    }

    await logActivity(session, {
      action: id ? "faq.updated" : "faq.created",
      entityType: "faq",
      entityId: id || 0,
      summary: `${id ? "Updated" : "Added"} the question “${questionEn.slice(0, 80)}”`,
    });
    refresh();
    return ok(id ? "Question saved." : "Question added.");
  });
}

export async function deleteFaq(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("faq-delete", async () => {
    const session = await guardAction("faqs.manage", form);
    const id = Number(form.get("id"));
    const [row] = await db.select().from(faqs).where(eq(faqs.id, id)).limit(1);
    if (!row) return fail("That question no longer exists.");
    await db.delete(faqs).where(eq(faqs.id, id));
    await logActivity(session, {
      action: "faq.deleted",
      entityType: "faq",
      entityId: id,
      summary: `Deleted the question “${row.questionEn.slice(0, 80)}”`,
    });
    refresh();
    return ok("Question deleted.");
  });
}
