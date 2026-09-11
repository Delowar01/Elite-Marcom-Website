"use client";

import { useState } from "react";

import { AdminForm, ConfirmSubmit, Field, InlineAction, SubmitButton } from "@/components/admin/form";
import { MediaPicker, type MediaOption } from "@/components/admin/media-picker";
import { Icon } from "@/components/ui/icon";
import { deleteTestimonial, saveTestimonial, toggleTestimonial } from "./actions";

export type TestimonialRow = {
  id: number;
  name: string;
  company: string;
  country: string;
  quoteEn: string;
  quoteAr: string;
  imageId: number | null;
  rating: number | null;
  isFeatured: boolean;
  isPublished: boolean;
  sortOrder: number;
};

export function TestimonialsClient({
  csrf,
  rows,
  media,
}: {
  csrf: string;
  rows: TestimonialRow[];
  media: MediaOption[];
}) {
  const [editing, setEditing] = useState<number | "new" | null>(rows.length ? null : "new");

  return (
    <div className="space-y-5">
      <div className="admin-card p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2>{editing === "new" ? "Add a testimonial" : "Testimonials"}</h2>
            <p className="mt-0.5 text-[0.78rem] text-muted">
              New testimonials arrive unpublished. Publish one only when you have the client&rsquo;s
              permission to quote them.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setEditing(editing === "new" ? null : "new")}
            className="admin-btn admin-btn-sm"
          >
            {editing === "new" ? "Cancel" : "Add testimonial"}
          </button>
        </div>
        {editing === "new" ? <TestimonialForm csrf={csrf} row={null} media={media} /> : null}
      </div>

      {rows.length === 0 ? (
        <p className="admin-card px-4 py-12 text-center text-[0.85rem] text-muted">
          No testimonials yet. The section stays hidden until one is published.
        </p>
      ) : (
        <ul className="space-y-3">
          {rows.map((row) => (
            <li key={row.id} className="admin-card p-4">
              <div className="flex flex-wrap items-start gap-4">
                <div className="min-w-52 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-strong">{row.name}</span>
                    {row.company || row.country ? (
                      <span className="text-[0.78rem] text-muted">
                        {[row.company, row.country].filter(Boolean).join(" · ")}
                      </span>
                    ) : null}
                    {row.rating ? (
                      <span className="admin-badge" style={{ color: "var(--color-peach)" }}>
                        {row.rating}/5
                      </span>
                    ) : null}
                    {row.isFeatured ? (
                      <span className="admin-badge" style={{ color: "var(--color-peach)" }}>
                        Featured
                      </span>
                    ) : null}
                    <span className="admin-badge" style={{ color: row.isPublished ? "#63c98c" : "#9aa2b5" }}>
                      {row.isPublished ? "Published" : "Unpublished"}
                    </span>
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-[0.82rem] text-body">{row.quoteEn || row.quoteAr}</p>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  <InlineAction action={toggleTestimonial} hidden={{ _csrf: csrf, id: row.id, what: "published" }}>
                    <button type="submit" className="admin-btn admin-btn-sm" title={row.isPublished ? "Unpublish" : "Publish"}>
                      <Icon name={row.isPublished ? "eyeOff" : "eye"} size={12} />
                    </button>
                  </InlineAction>
                  <InlineAction action={toggleTestimonial} hidden={{ _csrf: csrf, id: row.id, what: "featured" }}>
                    <button type="submit" className="admin-btn admin-btn-sm" title="Toggle featured">
                      <Icon name="star" size={12} />
                    </button>
                  </InlineAction>
                  <button
                    type="button"
                    onClick={() => setEditing(editing === row.id ? null : row.id)}
                    className="admin-btn admin-btn-sm"
                  >
                    {editing === row.id ? "Close" : "Edit"}
                  </button>
                  <InlineAction action={deleteTestimonial} hidden={{ _csrf: csrf, id: row.id }}>
                    <ConfirmSubmit className="admin-btn-sm" message={`Delete the testimonial from ${row.name}?`}>
                      <Icon name="trash" size={12} />
                      <span className="sr-only">Delete</span>
                    </ConfirmSubmit>
                  </InlineAction>
                </div>
              </div>

              {editing === row.id ? (
                <div className="mt-4 border-t border-[var(--admin-line)] pt-4">
                  <TestimonialForm csrf={csrf} row={row} media={media} />
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TestimonialForm({
  csrf,
  row,
  media,
}: {
  csrf: string;
  row: TestimonialRow | null;
  media: MediaOption[];
}) {
  const [imageId, setImageId] = useState<number | null>(row?.imageId ?? null);
  const key = row?.id ?? "new";

  return (
    <AdminForm action={saveTestimonial} successMessage={row ? "Testimonial saved." : "Testimonial added."}>
      <input type="hidden" name="_csrf" value={csrf} />
      {row ? <input type="hidden" name="id" value={row.id} /> : null}
      <input type="hidden" name="imageId" value={imageId ?? ""} />

      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Client name" name={`name-${key}`}>
          <input id={`name-${key}`} name="name" defaultValue={row?.name ?? ""} required className="admin-input" />
        </Field>
        <Field label="Company" name={`company-${key}`} hint="Optional.">
          <input id={`company-${key}`} name="company" defaultValue={row?.company ?? ""} className="admin-input" />
        </Field>
        <Field label="Country" name={`country-${key}`} hint="Optional.">
          <input id={`country-${key}`} name="country" defaultValue={row?.country ?? ""} className="admin-input" />
        </Field>

        <Field label="Testimonial (English)" name={`quoteEn-${key}`} className="sm:col-span-3">
          <textarea
            id={`quoteEn-${key}`}
            name="quoteEn"
            rows={3}
            defaultValue={row?.quoteEn ?? ""}
            className="admin-textarea"
          />
        </Field>
        <Field label="Testimonial (العربية)" name={`quoteAr-${key}`} className="sm:col-span-3">
          <textarea
            id={`quoteAr-${key}`}
            name="quoteAr"
            rows={3}
            defaultValue={row?.quoteAr ?? ""}
            dir="rtl"
            className="admin-textarea"
          />
        </Field>

        <Field label="Rating" name={`rating-${key}`} hint="Leave at 0 when none was given.">
          <select id={`rating-${key}`} name="rating" defaultValue={String(row?.rating ?? 0)} className="admin-select">
            <option value="0">No rating</option>
            {[5, 4, 3, 2, 1].map((n) => (
              <option key={n} value={n}>
                {n} / 5
              </option>
            ))}
          </select>
        </Field>
        <Field label="Order" name={`sortOrder-${key}`}>
          <input
            id={`sortOrder-${key}`}
            name="sortOrder"
            type="number"
            min={0}
            defaultValue={row?.sortOrder ?? 0}
            className="admin-input"
          />
        </Field>
        <div>
          <span className="admin-label">Photo</span>
          <MediaPicker value={imageId} onChange={setImageId} options={media} label="Client photo" />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-5">
        <label className="flex cursor-pointer items-center gap-2 text-[0.82rem]">
          <input
            type="checkbox"
            name="isPublished"
            defaultChecked={row?.isPublished ?? false}
            className="size-4 accent-[var(--color-orange)]"
          />
          Published
        </label>
        <label className="flex cursor-pointer items-center gap-2 text-[0.82rem]">
          <input
            type="checkbox"
            name="isFeatured"
            defaultChecked={row?.isFeatured ?? false}
            className="size-4 accent-[var(--color-orange)]"
          />
          Featured — shown first
        </label>
      </div>

      <div className="mt-5">
        <SubmitButton>{row ? "Save testimonial" : "Add testimonial"}</SubmitButton>
      </div>
    </AdminForm>
  );
}
