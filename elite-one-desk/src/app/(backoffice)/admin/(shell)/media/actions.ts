"use server";

import { eq } from "drizzle-orm";
import { revalidatePath } from "next/cache";

import { logActivity } from "@/lib/activity";
import { fail, field, ok, runAction, type ActionState } from "@/lib/admin/actions";
import { guardAction } from "@/lib/auth/guard";
import { TAGS, revalidate } from "@/lib/cache";
import { db } from "@/lib/db";
import { media } from "@/lib/db/schema";
import { deleteMediaFiles, processUpload } from "@/lib/media/process";
import { isMediaFolder } from "@/lib/media/folders";
import { mediaUsage } from "@/lib/media/usage";

export async function uploadMedia(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("media-upload", async () => {
    const session = await guardAction("media.manage", form);
    const files = form.getAll("files").filter((f): f is File => f instanceof File && f.size > 0);
    if (!files.length) return fail("Choose at least one image to upload.");
    if (files.length > 12) return fail("Upload up to twelve images at a time.");

    const requested = field(form, "folder", 64);
    const folder = isMediaFolder(requested) ? requested : "general";
    const results = await Promise.all(
      files.map(async (file) =>
        processUpload(await file.arrayBuffer(), {
          originalName: file.name,
          folder,
          title: files.length === 1 ? field(form, "title", 190) : "",
          altEn: files.length === 1 ? field(form, "altEn", 255) : "",
          altAr: files.length === 1 ? field(form, "altAr", 255) : "",
          uploadedBy: session.user.id,
        }),
      ),
    );

    const failed = results.filter((r) => !r.ok);
    const added = results.length - failed.length;

    if (added) {
      await logActivity(session, {
        action: "media.uploaded",
        entityType: "media",
        summary: `Uploaded ${added} image${added === 1 ? "" : "s"}`,
      });
      revalidate(TAGS.media);
      revalidatePath("/admin/media");
    }

    if (failed.length) {
      const first = failed[0];
      return fail(
        `${added} uploaded, ${failed.length} rejected. ${first && !first.ok ? first.error : ""}`.trim(),
      );
    }
    return ok(`Uploaded ${added} image${added === 1 ? "" : "s"}.`);
  });
}

export async function updateMedia(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("media-update", async () => {
    const session = await guardAction("media.manage", form);
    const id = Number(form.get("id"));
    const folder = field(form, "folder", 64);

    const [row] = await db
      .update(media)
      .set({
        title: field(form, "title", 190),
        altEn: field(form, "altEn", 255),
        altAr: field(form, "altAr", 255),
        folder: isMediaFolder(folder) ? folder : "general",
        updatedAt: new Date(),
      })
      .where(eq(media.id, id))
      .returning({ filename: media.filename });
    if (!row) return fail("That image no longer exists.");

    await logActivity(session, {
      action: "media.updated",
      entityType: "media",
      entityId: id,
      summary: `Updated details for ${row.filename}`,
    });
    revalidate(TAGS.media);
    revalidatePath("/admin/media");
    return ok("Image details saved.");
  });
}

export async function deleteMedia(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("media-delete", async () => {
    const session = await guardAction("media.manage", form);
    const id = Number(form.get("id"));

    const [row] = await db.select().from(media).where(eq(media.id, id)).limit(1);
    if (!row) return fail("That image no longer exists.");

    const uses = await mediaUsage(id);
    if (uses.length) {
      return fail(
        `Still in use on ${uses.length} screen${uses.length === 1 ? "" : "s"}: ${uses
          .slice(0, 3)
          .map((u) => u.label)
          .join(", ")}${uses.length > 3 ? "…" : ""}. Remove it there first.`,
      );
    }

    await db.delete(media).where(eq(media.id, id));
    await deleteMediaFiles(row.filename, row.derivatives ?? []);

    await logActivity(session, {
      action: "media.deleted",
      entityType: "media",
      entityId: id,
      summary: `Deleted ${row.filename}`,
    });
    revalidate(TAGS.media);
    revalidatePath("/admin/media");
    return ok("Image deleted.");
  });
}
