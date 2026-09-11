"use client";

import { useState } from "react";

import { AdminForm, ConfirmSubmit, Field, InlineAction, SubmitButton } from "@/components/admin/form";
import { MediaPicker, type MediaOption } from "@/components/admin/media-picker";
import { ICON_NAMES, Icon } from "@/components/ui/icon";
import {
  createCategory,
  deleteCategory,
  deleteSubcategory,
  saveSubcategory,
  updateCategory,
} from "./actions";

export type CategoryValues = {
  id?: number;
  slug: string;
  titleEn: string;
  titleAr: string;
  taglineEn: string;
  taglineAr: string;
  summaryEn: string;
  summaryAr: string;
  bodyEn: string;
  bodyAr: string;
  ctaLabelEn: string;
  ctaLabelAr: string;
  icon: string;
  imageId: number | null;
  sortOrder: number;
  isPublished: boolean;
};

const bilingual = (
  label: string,
  name: string,
  values: Record<string, string>,
  kind: "input" | "textarea" = "input",
  rows = 3,
) => (
  <div>
    <span className="admin-label">{label}</span>
    <div className="grid gap-2.5 lg:grid-cols-2">
      {(["En", "Ar"] as const).map((suffix) => {
        const fieldName = `${name}${suffix}`;
        const rtl = suffix === "Ar";
        return (
          <div key={suffix}>
            <label
              className="mb-1 block text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-muted"
              htmlFor={fieldName}
            >
              {rtl ? "العربية" : "English"}
            </label>
            {kind === "input" ? (
              <input
                id={fieldName}
                name={fieldName}
                defaultValue={values[fieldName] ?? ""}
                dir={rtl ? "rtl" : "ltr"}
                className="admin-input"
              />
            ) : (
              <textarea
                id={fieldName}
                name={fieldName}
                rows={rows}
                defaultValue={values[fieldName] ?? ""}
                dir={rtl ? "rtl" : "ltr"}
                className="admin-textarea"
              />
            )}
          </div>
        );
      })}
    </div>
  </div>
);

export function CategoryForm({
  csrf,
  category,
  media,
}: {
  csrf: string;
  category: CategoryValues;
  media: MediaOption[];
}) {
  const [imageId, setImageId] = useState<number | null>(category.imageId);
  const isNew = !category.id;
  const values = category as unknown as Record<string, string>;

  return (
    <AdminForm
      action={isNew ? createCategory : updateCategory}
      className="admin-card p-5"
      successMessage={isNew ? "Category created." : "Category saved."}
    >
      <input type="hidden" name="_csrf" value={csrf} />
      {category.id ? <input type="hidden" name="id" value={category.id} /> : null}
      <input type="hidden" name="imageId" value={imageId ?? ""} />

      <div className="space-y-5">
        {bilingual("Title", "title", values)}
        {bilingual("Tagline", "tagline", values)}
        {bilingual("Summary", "summary", values, "textarea", 3)}
        {bilingual("Body", "body", values, "textarea", 8)}
        {bilingual("Call-to-action label", "ctaLabel", values)}

        <div className="grid gap-4 sm:grid-cols-3">
          <Field
            label="Address"
            name="slug"
            hint={isNew ? "Becomes /services/your-address." : "Changing this breaks existing links."}
          >
            <input
              id="slug"
              name="slug"
              defaultValue={category.slug}
              required
              dir="ltr"
              className="admin-input"
            />
          </Field>
          <Field label="Icon" name="icon">
            <select id="icon" name="icon" defaultValue={category.icon} className="admin-select">
              {ICON_NAMES.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Order" name="sortOrder">
            <input
              id="sortOrder"
              name="sortOrder"
              type="number"
              min={0}
              defaultValue={category.sortOrder}
              className="admin-input"
            />
          </Field>
        </div>

        <div>
          <span className="admin-label">Image</span>
          <MediaPicker value={imageId} onChange={setImageId} options={media} label="Category image" />
        </div>

        <label className="flex cursor-pointer items-start gap-2.5">
          <input
            type="checkbox"
            name="isPublished"
            defaultChecked={category.isPublished}
            className="mt-0.5 size-4 accent-[var(--color-orange)]"
          />
          <span>
            <span className="block text-[0.85rem] text-strong">Published</span>
            <span className="block text-[0.73rem] text-muted">
              Unpublishing hides the category and every service inside it.
            </span>
          </span>
        </label>
      </div>

      <div className="mt-6 border-t border-[var(--admin-line)] pt-5">
        <SubmitButton>{isNew ? "Create category" : "Save changes"}</SubmitButton>
      </div>
    </AdminForm>
  );
}

export function DeleteCategory({ csrf, id, title, serviceCount }: { csrf: string; id: number; title: string; serviceCount: number }) {
  return (
    <AdminForm action={deleteCategory} guardUnsaved={false} className="admin-card p-5">
      <input type="hidden" name="_csrf" value={csrf} />
      <input type="hidden" name="id" value={id} />
      <h2 className="mb-2">Delete this category</h2>
      <p className="mb-4 text-[0.82rem] text-muted">
        {serviceCount
          ? `This also deletes ${serviceCount} service${serviceCount === 1 ? "" : "s"} inside it.`
          : "This category has no services."}{" "}
        Enquiries already received keep the names they were sent with.
      </p>
      <ConfirmSubmit
        message={`Delete “${title}”${serviceCount ? ` and its ${serviceCount} services` : ""}? This cannot be undone.`}
      >
        Delete category
      </ConfirmSubmit>
    </AdminForm>
  );
}

export type SubcategoryRow = {
  id: number;
  slug: string;
  titleEn: string;
  titleAr: string;
  summaryEn: string;
  summaryAr: string;
  sortOrder: number;
  isPublished: boolean;
  serviceCount: number;
};

export function SubcategoryManager({
  csrf,
  categoryId,
  rows,
}: {
  csrf: string;
  categoryId: number;
  rows: SubcategoryRow[];
}) {
  const [editing, setEditing] = useState<number | "new" | null>(null);

  return (
    <section className="admin-card p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2>Groups</h2>
          <p className="mt-0.5 text-[0.78rem] text-muted">
            Optional headings that break a long category into sections on the page.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setEditing(editing === "new" ? null : "new")}
          className="admin-btn admin-btn-sm"
        >
          {editing === "new" ? "Cancel" : "Add group"}
        </button>
      </div>

      {editing === "new" ? (
        <div className="mb-4 rounded-[var(--radius-sm)] border border-[var(--admin-line)] p-4">
          <SubcategoryForm csrf={csrf} categoryId={categoryId} row={null} />
        </div>
      ) : null}

      {rows.length === 0 ? (
        <p className="text-[0.82rem] text-muted">No groups. Services appear as one list.</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <li key={row.id} className="rounded-[var(--radius-sm)] border border-[var(--admin-line)] p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-strong">{row.titleEn}</span>
                <span className="text-[0.74rem] text-muted">
                  {row.serviceCount} service{row.serviceCount === 1 ? "" : "s"}
                </span>
                {!row.isPublished ? (
                  <span className="admin-badge" style={{ color: "#9aa2b5" }}>
                    Hidden
                  </span>
                ) : null}
                <div className="ms-auto flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => setEditing(editing === row.id ? null : row.id)}
                    className="admin-btn admin-btn-sm"
                  >
                    {editing === row.id ? "Close" : "Edit"}
                  </button>
                  <InlineAction action={deleteSubcategory} hidden={{ _csrf: csrf, id: row.id }}>
                    <ConfirmSubmit
                      className="admin-btn-sm"
                      message={`Delete the group “${row.titleEn}”? Its services stay in the category.`}
                    >
                      <Icon name="trash" size={12} />
                      <span className="sr-only">Delete group</span>
                    </ConfirmSubmit>
                  </InlineAction>
                </div>
              </div>
              {editing === row.id ? (
                <div className="mt-3 border-t border-[var(--admin-line)] pt-3">
                  <SubcategoryForm csrf={csrf} categoryId={categoryId} row={row} />
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SubcategoryForm({
  csrf,
  categoryId,
  row,
}: {
  csrf: string;
  categoryId: number;
  row: SubcategoryRow | null;
}) {
  return (
    <AdminForm action={saveSubcategory} successMessage={row ? "Group saved." : "Group created."}>
      <input type="hidden" name="_csrf" value={csrf} />
      <input type="hidden" name="categoryId" value={categoryId} />
      {row ? <input type="hidden" name="id" value={row.id} /> : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Title (English)" name={`sub-titleEn-${row?.id ?? "new"}`}>
          <input
            id={`sub-titleEn-${row?.id ?? "new"}`}
            name="titleEn"
            defaultValue={row?.titleEn ?? ""}
            required
            className="admin-input"
          />
        </Field>
        <Field label="Title (العربية)" name={`sub-titleAr-${row?.id ?? "new"}`}>
          <input
            id={`sub-titleAr-${row?.id ?? "new"}`}
            name="titleAr"
            defaultValue={row?.titleAr ?? ""}
            dir="rtl"
            className="admin-input"
          />
        </Field>
        <Field label="Address" name={`sub-slug-${row?.id ?? "new"}`}>
          <input
            id={`sub-slug-${row?.id ?? "new"}`}
            name="slug"
            defaultValue={row?.slug ?? ""}
            required
            dir="ltr"
            className="admin-input"
          />
        </Field>
        <Field label="Order" name={`sub-order-${row?.id ?? "new"}`}>
          <input
            id={`sub-order-${row?.id ?? "new"}`}
            name="sortOrder"
            type="number"
            min={0}
            defaultValue={row?.sortOrder ?? 0}
            className="admin-input"
          />
        </Field>
        <Field label="Summary (English)" name={`sub-sumEn-${row?.id ?? "new"}`} className="sm:col-span-2">
          <textarea
            id={`sub-sumEn-${row?.id ?? "new"}`}
            name="summaryEn"
            rows={2}
            defaultValue={row?.summaryEn ?? ""}
            className="admin-textarea"
          />
        </Field>
      </div>

      <label className="mt-3 flex cursor-pointer items-center gap-2.5 text-[0.82rem]">
        <input
          type="checkbox"
          name="isPublished"
          defaultChecked={row?.isPublished ?? true}
          className="size-4 accent-[var(--color-orange)]"
        />
        Published
      </label>

      <div className="mt-4">
        <SubmitButton className="admin-btn-sm">{row ? "Save group" : "Create group"}</SubmitButton>
      </div>
    </AdminForm>
  );
}
