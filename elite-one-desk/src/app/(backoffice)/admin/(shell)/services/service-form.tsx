"use client";

import { useMemo, useState } from "react";

import { AdminForm, ConfirmSubmit, Field, SubmitButton } from "@/components/admin/form";
import { ItemListEditor, StepListEditor } from "@/components/admin/list-editor";
import { MediaPicker, type MediaOption } from "@/components/admin/media-picker";
import type { LocalisedItem, LocalisedStep } from "@/lib/db/schema";
import { PRESET_KEYS } from "@/lib/forms/presets";
import { createService, deleteService, updateService } from "./actions";

export type ServiceValues = {
  id?: number;
  slug: string;
  categoryId: number;
  subcategoryId: number | null;
  titleEn: string;
  titleAr: string;
  introEn: string;
  introAr: string;
  bodyEn: string;
  bodyAr: string;
  benefits: LocalisedItem[];
  audience: LocalisedItem[];
  requirements: LocalisedItem[];
  processSteps: LocalisedStep[];
  timelineEn: string;
  timelineAr: string;
  notesEn: string;
  notesAr: string;
  formPreset: string;
  imageId: number | null;
  isFeatured: boolean;
  isPublished: boolean;
  sortOrder: number;
};

const PRESET_LABEL: Record<string, string> = {
  general: "General — name, contact and message only",
  travel: "Travel — destination, dates, party size, budget",
  visa: "Visa — destination country, nationality, purpose, travel date",
  business: "Business setup — nationality, activity, company status, licence",
  iqama: "Iqama — service required, number of employees",
};

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

export function ServiceForm({
  csrf,
  service,
  categories,
  subcategories,
  media,
}: {
  csrf: string;
  service: ServiceValues;
  categories: Array<{ id: number; titleEn: string }>;
  subcategories: Array<{ id: number; categoryId: number; titleEn: string }>;
  media: MediaOption[];
}) {
  const isNew = !service.id;
  const [categoryId, setCategoryId] = useState(service.categoryId || categories[0]?.id || 0);
  const [imageId, setImageId] = useState<number | null>(service.imageId);
  const values = service as unknown as Record<string, string>;

  const groups = useMemo(
    () => subcategories.filter((s) => s.categoryId === categoryId),
    [categoryId, subcategories],
  );

  return (
    <AdminForm
      action={isNew ? createService : updateService}
      className="admin-card p-5"
      successMessage={isNew ? "Service created." : "Service saved."}
    >
      <input type="hidden" name="_csrf" value={csrf} />
      {service.id ? <input type="hidden" name="id" value={service.id} /> : null}
      <input type="hidden" name="imageId" value={imageId ?? ""} />

      <div className="space-y-6">
        <section className="space-y-5">
          <h2>Basics</h2>
          <Pair label="Title" name="title" values={values} />
          <Pair
            label="Short introduction"
            name="intro"
            values={values}
            kind="textarea"
            rows={3}
            hint="One or two sentences. Used on the service page, in listings and as the meta description."
          />

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Category" name="categoryId">
              <select
                id="categoryId"
                name="categoryId"
                value={categoryId}
                onChange={(event) => setCategoryId(Number(event.target.value))}
                className="admin-select"
              >
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.titleEn}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Group" name="subcategoryId" hint="Optional heading within the category.">
              <select
                id="subcategoryId"
                name="subcategoryId"
                defaultValue={service.subcategoryId ? String(service.subcategoryId) : ""}
                key={categoryId}
                className="admin-select"
              >
                <option value="">No group</option>
                {groups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.titleEn}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Address" name="slug" hint="Changing this breaks existing links.">
              <input
                id="slug"
                name="slug"
                defaultValue={service.slug}
                required
                dir="ltr"
                className="admin-input"
              />
            </Field>
            <Field label="Order" name="sortOrder">
              <input
                id="sortOrder"
                name="sortOrder"
                type="number"
                min={0}
                defaultValue={service.sortOrder}
                className="admin-input"
              />
            </Field>
          </div>

          <Field
            label="Request form"
            name="formPreset"
            hint="Which extra questions the request form asks on this service's page."
          >
            <select
              id="formPreset"
              name="formPreset"
              defaultValue={service.formPreset}
              className="admin-select"
            >
              {PRESET_KEYS.map((key) => (
                <option key={key} value={key}>
                  {PRESET_LABEL[key]}
                </option>
              ))}
            </select>
          </Field>

          <div>
            <span className="admin-label">Image</span>
            <MediaPicker value={imageId} onChange={setImageId} options={media} label="Service image" />
          </div>
        </section>

        <section className="space-y-5 border-t border-[var(--admin-line)] pt-6">
          <h2>Page content</h2>
          <Pair
            label="Detailed content"
            name="body"
            values={values}
            kind="textarea"
            rows={10}
            hint="Bold, italic, links, lists and h3/h4 headings are kept. Everything else becomes plain text."
          />

          <ItemListEditor
            name="benefits"
            label="Key benefits"
            initial={service.benefits}
            hint="Shown as a checked list. Keep each one to a single line."
          />
          <ItemListEditor
            name="audience"
            label="Who this service is for"
            initial={service.audience}
          />
          <ItemListEditor
            name="requirements"
            label="Documents and requirements"
            initial={service.requirements}
            hint="Never publish a requirement you are not sure of — these change, and the page is what a client will hold you to."
          />
          <StepListEditor
            name="processSteps"
            label="How the process runs"
            initial={service.processSteps}
          />

          <Pair
            label="Indicative timeline"
            name="timeline"
            values={values}
            hint="Free text, and optional. Leave it empty rather than publishing a duration you cannot stand behind."
          />
          <Pair
            label="Important notes"
            name="notes"
            values={values}
            kind="textarea"
            rows={4}
          />
        </section>

        <section className="space-y-3 border-t border-[var(--admin-line)] pt-6">
          <h2>Visibility</h2>
          <label className="flex cursor-pointer items-start gap-2.5">
            <input
              type="checkbox"
              name="isPublished"
              defaultChecked={service.isPublished}
              className="mt-0.5 size-4 accent-[var(--color-orange)]"
            />
            <span>
              <span className="block text-[0.85rem] text-strong">Published</span>
              <span className="block text-[0.73rem] text-muted">
                Unpublished services disappear from the site, the search and the request form.
              </span>
            </span>
          </label>
          <label className="flex cursor-pointer items-start gap-2.5">
            <input
              type="checkbox"
              name="isFeatured"
              defaultChecked={service.isFeatured}
              className="mt-0.5 size-4 accent-[var(--color-orange)]"
            />
            <span>
              <span className="block text-[0.85rem] text-strong">Featured</span>
              <span className="block text-[0.73rem] text-muted">
                Ranks higher in search results within the site.
              </span>
            </span>
          </label>
        </section>
      </div>

      <div className="mt-6 border-t border-[var(--admin-line)] pt-5">
        <SubmitButton>{isNew ? "Create service" : "Save changes"}</SubmitButton>
      </div>
    </AdminForm>
  );
}

export function DeleteService({ csrf, id, title }: { csrf: string; id: number; title: string }) {
  return (
    <AdminForm action={deleteService} guardUnsaved={false} className="admin-card p-5">
      <input type="hidden" name="_csrf" value={csrf} />
      <input type="hidden" name="id" value={id} />
      <h2 className="mb-2">Delete this service</h2>
      <p className="mb-4 text-[0.82rem] text-muted">
        Unpublishing is usually what you want — it keeps the record and the link can be restored.
        Deleting removes it permanently.
      </p>
      <ConfirmSubmit message={`Delete “${title}”? This cannot be undone.`}>Delete service</ConfirmSubmit>
    </AdminForm>
  );
}
