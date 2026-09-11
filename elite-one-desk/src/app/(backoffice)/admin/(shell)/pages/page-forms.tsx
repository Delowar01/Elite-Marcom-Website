"use client";

import { AdminForm, ConfirmSubmit, Field, SubmitButton } from "@/components/admin/form";
import { Icon } from "@/components/ui/icon";
import { createPage, deletePage, publishAllDrafts, updatePage } from "./actions";

export function NewPageForm({ csrf }: { csrf: string }) {
  return (
    <AdminForm action={createPage} className="admin-card p-5" successMessage="Page created.">
      <input type="hidden" name="_csrf" value={csrf} />
      <h2 className="mb-4">New page</h2>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Title (English)" name="titleEn">
          <input id="titleEn" name="titleEn" required className="admin-input" />
        </Field>
        <Field label="Title (العربية)" name="titleAr">
          <input id="titleAr" name="titleAr" dir="rtl" className="admin-input" />
        </Field>
        <Field
          label="Address"
          name="slug"
          hint="The page will live at /your-address. Lower case, hyphens between words."
          className="sm:col-span-2"
        >
          <input id="slug" name="slug" required placeholder="premium-residency-guide" dir="ltr" className="admin-input" />
        </Field>
      </div>
      <div className="mt-5">
        <SubmitButton>Create page</SubmitButton>
      </div>
    </AdminForm>
  );
}

export function PageSettingsForm({
  csrf,
  page,
}: {
  csrf: string;
  page: { id: number; slug: string; kind: string; titleEn: string; titleAr: string; isPublished: boolean };
}) {
  return (
    <AdminForm action={updatePage} className="admin-card p-5">
      <input type="hidden" name="_csrf" value={csrf} />
      <input type="hidden" name="id" value={page.id} />
      <h2 className="mb-4">Page settings</h2>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Title (English)" name="titleEn">
          <input id="titleEn" name="titleEn" defaultValue={page.titleEn} required className="admin-input" />
        </Field>
        <Field label="Title (العربية)" name="titleAr">
          <input id="titleAr" name="titleAr" defaultValue={page.titleAr} dir="rtl" className="admin-input" />
        </Field>
      </div>

      <label className="mt-4 flex cursor-pointer items-start gap-2.5">
        <input
          type="checkbox"
          name="isPublished"
          defaultChecked={page.isPublished}
          className="mt-0.5 size-4 accent-[var(--color-orange)]"
        />
        <span>
          <span className="block text-[0.85rem] text-strong">Published</span>
          <span className="block text-[0.73rem] text-muted">
            Unpublished pages answer with a 404 and stay out of the sitemap.
          </span>
        </span>
      </label>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <SubmitButton />
        {page.kind === "custom" ? null : (
          <span className="text-[0.74rem] text-muted">
            Built-in page — the address is fixed and it cannot be deleted.
          </span>
        )}
      </div>
    </AdminForm>
  );
}

export function DeletePageForm({ csrf, id, title }: { csrf: string; id: number; title: string }) {
  return (
    <AdminForm action={deletePage} guardUnsaved={false} className="admin-card p-5">
      <input type="hidden" name="_csrf" value={csrf} />
      <input type="hidden" name="id" value={id} />
      <h2 className="mb-2">Delete this page</h2>
      <p className="mb-4 text-[0.82rem] text-muted">
        Removes the page and every section on it. This cannot be undone.
      </p>
      <ConfirmSubmit message={`Delete “${title}” and all of its sections? This cannot be undone.`}>
        Delete page
      </ConfirmSubmit>
    </AdminForm>
  );
}

export function PublishAllButton({ csrf, pageId, count }: { csrf: string; pageId: number; count: number }) {
  if (!count) return null;
  return (
    <AdminForm action={publishAllDrafts} guardUnsaved={false} className="inline">
      <input type="hidden" name="_csrf" value={csrf} />
      <input type="hidden" name="pageId" value={pageId} />
      <ConfirmSubmit
        variant="primary"
        message={`Publish ${count} draft section${count === 1 ? "" : "s"} to the live site?`}
      >
        <Icon name="check" size={14} />
        Publish {count} draft{count === 1 ? "" : "s"}
      </ConfirmSubmit>
    </AdminForm>
  );
}
