"use client";

import { useState } from "react";

import { AdminForm, ConfirmSubmit, Field, InlineAction, SubmitButton } from "@/components/admin/form";
import { MediaPicker, type MediaOption } from "@/components/admin/media-picker";
import { clearSeo, saveSeo } from "./actions";

export type SeoEntity = {
  type: "page" | "category" | "service" | "package";
  key: string;
  label: string;
  path: string;
  fallbackTitle: string;
  fallbackDescription: string;
  override: {
    titleEn: string;
    titleAr: string;
    descriptionEn: string;
    descriptionAr: string;
    canonicalUrl: string;
    ogTitle: string;
    ogDescription: string;
    ogImageId: number | null;
    noindex: boolean;
  } | null;
};

const GROUPS: Array<{ type: SeoEntity["type"]; title: string }> = [
  { type: "page", title: "Pages" },
  { type: "category", title: "Service categories" },
  { type: "service", title: "Services" },
  { type: "package", title: "Travel packages" },
];

export function SeoClient({
  csrf,
  entities,
  media,
}: {
  csrf: string;
  entities: SeoEntity[];
  media: MediaOption[];
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const filtered = query.trim()
    ? entities.filter((e) => `${e.label} ${e.path}`.toLowerCase().includes(query.toLowerCase()))
    : entities;

  return (
    <div className="space-y-5">
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Filter by name or address"
        aria-label="Filter"
        className="admin-input max-w-md"
      />

      {GROUPS.map((group) => {
        const rows = filtered.filter((entity) => entity.type === group.type);
        if (!rows.length) return null;
        return (
          <section key={group.type} className="admin-card overflow-hidden">
            <div className="flex items-center justify-between border-b border-[var(--admin-line)] px-4 py-3">
              <h2>{group.title}</h2>
              <span className="text-[0.74rem] text-muted">
                {rows.filter((r) => r.override).length} of {rows.length} overridden
              </span>
            </div>
            <ul className="divide-y divide-[var(--admin-line)]">
              {rows.map((entity) => {
                const id = `${entity.type}:${entity.key}`;
                const open = editing === id;
                return (
                  <li key={id} className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-strong">{entity.label}</span>
                      <span className="text-[0.74rem] text-muted" dir="ltr">
                        {entity.path}
                      </span>
                      {entity.override ? (
                        <span className="admin-badge" style={{ color: "var(--color-peach)" }}>
                          Override
                        </span>
                      ) : null}
                      {entity.override?.noindex ? (
                        <span className="admin-badge" style={{ color: "#ff8a80" }}>
                          noindex
                        </span>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => setEditing(open ? null : id)}
                        className="admin-btn admin-btn-sm ms-auto"
                      >
                        {open ? "Close" : "Edit"}
                      </button>
                    </div>

                    {!open ? (
                      <p className="mt-1 line-clamp-1 text-[0.76rem] text-muted">
                        {entity.override?.titleEn || entity.fallbackTitle}
                      </p>
                    ) : (
                      <div className="mt-3 border-t border-[var(--admin-line)] pt-3">
                        <SeoForm csrf={csrf} entity={entity} media={media} />
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function SeoForm({
  csrf,
  entity,
  media,
}: {
  csrf: string;
  entity: SeoEntity;
  media: MediaOption[];
}) {
  const [ogImageId, setOgImageId] = useState<number | null>(entity.override?.ogImageId ?? null);
  const key = `${entity.type}-${entity.key}`.replace(/[^a-z0-9-]/gi, "-");
  const o = entity.override;

  return (
    <div className="space-y-3">
      <AdminForm action={saveSeo} successMessage="SEO saved.">
        <input type="hidden" name="_csrf" value={csrf} />
        <input type="hidden" name="entityType" value={entity.type} />
        <input type="hidden" name="entityKey" value={entity.key} />
        <input type="hidden" name="ogImageId" value={ogImageId ?? ""} />

        <div className="grid gap-3 sm:grid-cols-2">
          <Field
            label="Title (English)"
            name={`titleEn-${key}`}
            hint={`Without an override: “${entity.fallbackTitle}”`}
          >
            <input id={`titleEn-${key}`} name="titleEn" defaultValue={o?.titleEn ?? ""} className="admin-input" />
          </Field>
          <Field label="Title (العربية)" name={`titleAr-${key}`}>
            <input
              id={`titleAr-${key}`}
              name="titleAr"
              defaultValue={o?.titleAr ?? ""}
              dir="rtl"
              className="admin-input"
            />
          </Field>

          <Field
            label="Meta description (English)"
            name={`descriptionEn-${key}`}
            hint="Around 150–160 characters reads well in a result."
          >
            <textarea
              id={`descriptionEn-${key}`}
              name="descriptionEn"
              rows={2}
              defaultValue={o?.descriptionEn ?? ""}
              className="admin-textarea"
            />
          </Field>
          <Field label="Meta description (العربية)" name={`descriptionAr-${key}`}>
            <textarea
              id={`descriptionAr-${key}`}
              name="descriptionAr"
              rows={2}
              defaultValue={o?.descriptionAr ?? ""}
              dir="rtl"
              className="admin-textarea"
            />
          </Field>

          <Field label="Share title" name={`ogTitle-${key}`} hint="Used when the page is shared. Falls back to the title.">
            <input id={`ogTitle-${key}`} name="ogTitle" defaultValue={o?.ogTitle ?? ""} className="admin-input" />
          </Field>
          <Field label="Share description" name={`ogDescription-${key}`}>
            <input
              id={`ogDescription-${key}`}
              name="ogDescription"
              defaultValue={o?.ogDescription ?? ""}
              className="admin-input"
            />
          </Field>

          <Field
            label="Canonical address"
            name={`canonicalUrl-${key}`}
            hint="Only set this if the same content also lives at another address."
          >
            <input
              id={`canonicalUrl-${key}`}
              name="canonicalUrl"
              defaultValue={o?.canonicalUrl ?? ""}
              dir="ltr"
              className="admin-input"
            />
          </Field>

          <div>
            <span className="admin-label">Share image</span>
            <MediaPicker value={ogImageId} onChange={setOgImageId} options={media} label="Share image" />
          </div>
        </div>

        <label className="mt-3 flex cursor-pointer items-start gap-2.5">
          <input
            type="checkbox"
            name="noindex"
            defaultChecked={o?.noindex ?? false}
            className="mt-0.5 size-4 accent-[var(--color-orange)]"
          />
          <span>
            <span className="block text-[0.85rem] text-strong">Keep out of search engines</span>
            <span className="block text-[0.73rem] text-muted">
              The page still works and is still linked — search engines are simply asked not to list it.
            </span>
          </span>
        </label>

        <div className="mt-4">
          <SubmitButton className="admin-btn-sm">Save</SubmitButton>
        </div>
      </AdminForm>

      {o ? (
        <InlineAction
          action={clearSeo}
          hidden={{ _csrf: csrf, entityType: entity.type, entityKey: entity.key }}
        >
          <ConfirmSubmit
            className="admin-btn-sm"
            message="Remove the override and let this page use its own title and intro again?"
          >
            Remove override
          </ConfirmSubmit>
        </InlineAction>
      ) : null}
    </div>
  );
}
