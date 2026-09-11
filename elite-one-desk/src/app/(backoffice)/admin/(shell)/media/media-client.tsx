"use client";

import { useState } from "react";

import { AdminForm, ConfirmSubmit, Field, InlineAction, SubmitButton } from "@/components/admin/form";
import { Icon } from "@/components/ui/icon";
import { MEDIA_FOLDERS } from "@/lib/media/folders";
import { deleteMedia, updateMedia, uploadMedia } from "./actions";

export type LibraryItem = {
  id: number;
  filename: string;
  title: string;
  altEn: string;
  altAr: string;
  folder: string;
  width: number;
  height: number;
  byteSize: number;
  mimeType: string;
  createdAt: string;
  uses: number;
};

const kb = (bytes: number) =>
  bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;

export function UploadPanel({ csrf }: { csrf: string }) {
  return (
    <AdminForm action={uploadMedia} className="admin-card p-5" successMessage="Uploaded.">
      <input type="hidden" name="_csrf" value={csrf} />
      <h2 className="mb-1">Upload images</h2>
      <p className="mb-4 text-[0.8rem] text-muted">
        JPG, PNG, WebP, AVIF, GIF or SVG, up to 10&nbsp;MB each. Everything is re-encoded to WebP and
        three smaller widths are written alongside, so pages load the size they need.
      </p>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Files" name="files" className="sm:col-span-2">
          <input
            id="files"
            name="files"
            type="file"
            multiple
            accept="image/png,image/jpeg,image/webp,image/avif,image/gif,image/svg+xml"
            required
            className="admin-input file:me-3 file:rounded-[6px] file:border-0 file:bg-[color-mix(in_oklab,var(--color-warm)_10%,transparent)] file:px-2.5 file:py-1 file:text-[0.78rem] file:text-strong"
          />
        </Field>
        <Field label="Folder" name="folder">
          <select id="folder" name="folder" className="admin-select" defaultValue="general">
            {MEDIA_FOLDERS.map((folder) => (
              <option key={folder} value={folder}>
                {folder}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Title"
          name="title"
          hint="Used when a single file is uploaded. Optional."
        >
          <input id="title" name="title" className="admin-input" />
        </Field>
        <Field
          label="Alt text (English)"
          name="altEn"
          hint="What the picture shows, for screen readers and when an image fails to load."
          className="sm:col-span-2"
        >
          <input id="altEn" name="altEn" className="admin-input" />
        </Field>
      </div>

      <div className="mt-5">
        <SubmitButton pendingLabel="Uploading…">Upload</SubmitButton>
      </div>
    </AdminForm>
  );
}

export function LibraryGrid({ csrf, items }: { csrf: string; items: LibraryItem[] }) {
  const [editing, setEditing] = useState<number | null>(null);

  if (!items.length) {
    return (
      <p className="admin-card px-4 py-12 text-center text-[0.85rem] text-muted">
        The library is empty. Upload the first image above.
      </p>
    );
  }

  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {items.map((item) => (
        <li key={item.id} className="admin-card overflow-hidden">
          <div className="aspect-[4/3] bg-[#05041a]">
            <img
              src={`/media/${item.filename}`}
              alt={item.altEn || ""}
              loading="lazy"
              decoding="async"
              className="size-full object-contain"
            />
          </div>

          <div className="p-3">
            <p className="truncate text-[0.82rem] font-semibold text-strong" title={item.filename}>
              {item.title || item.filename}
            </p>
            <p className="mt-0.5 text-[0.72rem] text-muted">
              {item.width}×{item.height} · {kb(item.byteSize)} · {item.folder}
            </p>
            {item.uses ? (
              <p className="mt-1 text-[0.72rem]" style={{ color: "#ffd166" }}>
                Used in {item.uses} place{item.uses === 1 ? "" : "s"}
              </p>
            ) : (
              <p className="mt-1 text-[0.72rem] text-muted">Not placed anywhere yet</p>
            )}

            <div className="mt-2.5 flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => setEditing(editing === item.id ? null : item.id)}
                className="admin-btn admin-btn-sm"
              >
                {editing === item.id ? "Close" : "Details"}
              </button>
              <a
                href={`/media/${item.filename}`}
                target="_blank"
                rel="noopener"
                className="admin-btn admin-btn-sm"
              >
                <Icon name="arrowUpRight" size={12} />
                Open
              </a>
              <InlineAction action={deleteMedia} hidden={{ _csrf: csrf, id: item.id }}>
                <ConfirmSubmit
                  className="admin-btn-sm"
                  message={`Delete ${item.filename}? The file and its resized copies are removed.`}
                >
                  <Icon name="trash" size={12} />
                  <span className="sr-only">Delete</span>
                </ConfirmSubmit>
              </InlineAction>
            </div>

            {editing === item.id ? (
              <div className="mt-3 border-t border-[var(--admin-line)] pt-3">
                <AdminForm action={updateMedia} successMessage="Saved.">
                  <input type="hidden" name="_csrf" value={csrf} />
                  <input type="hidden" name="id" value={item.id} />
                  <div className="space-y-2.5">
                    <Field label="Title" name={`title-${item.id}`}>
                      <input
                        id={`title-${item.id}`}
                        name="title"
                        defaultValue={item.title}
                        className="admin-input"
                      />
                    </Field>
                    <Field label="Alt text (English)" name={`altEn-${item.id}`}>
                      <input
                        id={`altEn-${item.id}`}
                        name="altEn"
                        defaultValue={item.altEn}
                        className="admin-input"
                      />
                    </Field>
                    <Field label="Alt text (العربية)" name={`altAr-${item.id}`}>
                      <input
                        id={`altAr-${item.id}`}
                        name="altAr"
                        defaultValue={item.altAr}
                        dir="rtl"
                        className="admin-input"
                      />
                    </Field>
                    <Field label="Folder" name={`folder-${item.id}`}>
                      <select
                        id={`folder-${item.id}`}
                        name="folder"
                        defaultValue={item.folder}
                        className="admin-select"
                      >
                        {MEDIA_FOLDERS.map((folder) => (
                          <option key={folder} value={folder}>
                            {folder}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <SubmitButton className="admin-btn-sm">Save</SubmitButton>
                  </div>
                </AdminForm>
              </div>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
