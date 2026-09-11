"use client";

import { useState } from "react";

import { AdminForm, ConfirmSubmit, Field, SubmitButton } from "@/components/admin/form";
import { ItemListEditor } from "@/components/admin/list-editor";
import { MediaPicker, type MediaOption } from "@/components/admin/media-picker";
import type { LocalisedItem } from "@/lib/db/schema";
import { createPackage, deletePackage, updatePackage } from "./actions";

export type PackageValues = {
  id?: number;
  slug: string;
  region: string;
  titleEn: string;
  titleAr: string;
  destinationEn: string;
  destinationAr: string;
  durationEn: string;
  durationAr: string;
  summaryEn: string;
  summaryAr: string;
  bodyEn: string;
  bodyAr: string;
  highlights: LocalisedItem[];
  imageId: number | null;
  isFeatured: boolean;
  isPublished: boolean;
  sortOrder: number;
};

const REGIONS = [
  { value: "egypt", label: "Egypt" },
  { value: "international", label: "International" },
  { value: "holiday", label: "Holiday" },
  { value: "corporate", label: "Corporate" },
];

function Pair({
  label,
  name,
  values,
  kind = "input",
  rows = 3,
  hint,
}: {
  label: string;
  name: string;
  values: Record<string, string>;
  kind?: "input" | "textarea";
  rows?: number;
  hint?: string;
}) {
  return (
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
      {hint ? <p className="mt-1.5 text-[0.73rem] text-muted">{hint}</p> : null}
    </div>
  );
}

export function PackageForm({
  csrf,
  pkg,
  media,
}: {
  csrf: string;
  pkg: PackageValues;
  media: MediaOption[];
}) {
  const isNew = !pkg.id;
  const [imageId, setImageId] = useState<number | null>(pkg.imageId);
  const values = pkg as unknown as Record<string, string>;

  return (
    <AdminForm
      action={isNew ? createPackage : updatePackage}
      className="admin-card p-5"
      successMessage={isNew ? "Package created." : "Package saved."}
    >
      <input type="hidden" name="_csrf" value={csrf} />
      {pkg.id ? <input type="hidden" name="id" value={pkg.id} /> : null}
      <input type="hidden" name="imageId" value={imageId ?? ""} />

      <div className="space-y-5">
        <Pair label="Title" name="title" values={values} />
        <Pair label="Destination" name="destination" values={values} />
        <Pair
          label="Duration"
          name="duration"
          values={values}
          hint="Free text — “5 nights”, “flexible”. No price is published anywhere on the site."
        />
        <Pair label="Summary" name="summary" values={values} kind="textarea" rows={3} />
        <Pair label="Detail" name="body" values={values} kind="textarea" rows={8} />

        <ItemListEditor
          name="highlights"
          label="What the programme includes"
          initial={pkg.highlights}
        />

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Region" name="region">
            <select id="region" name="region" defaultValue={pkg.region} className="admin-select">
              {REGIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Address" name="slug">
            <input id="slug" name="slug" defaultValue={pkg.slug} required dir="ltr" className="admin-input" />
          </Field>
          <Field label="Order" name="sortOrder">
            <input
              id="sortOrder"
              name="sortOrder"
              type="number"
              min={0}
              defaultValue={pkg.sortOrder}
              className="admin-input"
            />
          </Field>
        </div>

        <div>
          <span className="admin-label">Image</span>
          <MediaPicker value={imageId} onChange={setImageId} options={media} label="Package image" />
        </div>

        <div className="flex flex-wrap gap-5">
          <label className="flex cursor-pointer items-center gap-2 text-[0.82rem]">
            <input
              type="checkbox"
              name="isPublished"
              defaultChecked={pkg.isPublished}
              className="size-4 accent-[var(--color-orange)]"
            />
            Published
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-[0.82rem]">
            <input
              type="checkbox"
              name="isFeatured"
              defaultChecked={pkg.isFeatured}
              className="size-4 accent-[var(--color-orange)]"
            />
            Featured — listed first
          </label>
        </div>
      </div>

      <div className="mt-6 border-t border-[var(--admin-line)] pt-5">
        <SubmitButton>{isNew ? "Create package" : "Save changes"}</SubmitButton>
      </div>
    </AdminForm>
  );
}

export function DeletePackage({ csrf, id, title }: { csrf: string; id: number; title: string }) {
  return (
    <AdminForm action={deletePackage} guardUnsaved={false} className="admin-card p-5">
      <input type="hidden" name="_csrf" value={csrf} />
      <input type="hidden" name="id" value={id} />
      <h2 className="mb-2">Delete this package</h2>
      <p className="mb-4 text-[0.82rem] text-muted">
        Unpublishing keeps the record and the address. Deleting is permanent.
      </p>
      <ConfirmSubmit message={`Delete “${title}”? This cannot be undone.`}>Delete package</ConfirmSubmit>
    </AdminForm>
  );
}
