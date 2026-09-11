"use client";

import { useState } from "react";

import { AdminForm, ConfirmSubmit, Field, InlineAction, SubmitButton } from "@/components/admin/form";
import { MediaPicker, type MediaOption } from "@/components/admin/media-picker";
import { Icon } from "@/components/ui/icon";
import { youtubePoster } from "@/lib/youtube";
import { deleteVideo, moveVideo, saveVideo, toggleVideo } from "./actions";

export type VideoRow = {
  id: number;
  youtubeId: string;
  sourceUrl: string;
  titleEn: string;
  titleAr: string;
  descriptionEn: string;
  descriptionAr: string;
  category: string;
  thumbnailId: number | null;
  thumbnailFilename: string | null;
  durationLabel: string;
  isFeatured: boolean;
  isPublished: boolean;
  sortOrder: number;
};

export function VideosClient({
  csrf,
  rows,
  media,
}: {
  csrf: string;
  rows: VideoRow[];
  media: MediaOption[];
}) {
  const [editing, setEditing] = useState<number | "new" | null>(rows.length ? null : "new");

  return (
    <div className="space-y-5">
      <div className="admin-card p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2>{editing === "new" ? "Add a video" : "Videos"}</h2>
            <p className="mt-0.5 text-[0.78rem] text-muted">
              Paste a YouTube address; the id and the still are worked out for you. Nothing is
              requested from YouTube until a visitor presses play.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setEditing(editing === "new" ? null : "new")}
            className="admin-btn admin-btn-sm"
          >
            {editing === "new" ? "Cancel" : "Add video"}
          </button>
        </div>

        {editing === "new" ? <VideoForm csrf={csrf} row={null} media={media} /> : null}
      </div>

      {rows.length === 0 ? (
        <p className="admin-card px-4 py-12 text-center text-[0.85rem] text-muted">
          No videos yet. The showcase section stays hidden until there is at least one.
        </p>
      ) : (
        <ul className="space-y-3">
          {rows.map((row, index) => (
            <li key={row.id} className="admin-card p-4">
              <div className="flex flex-wrap items-start gap-4">
                <img
                  src={row.thumbnailFilename ? `/media/${row.thumbnailFilename}` : youtubePoster(row.youtubeId)}
                  alt=""
                  width={160}
                  height={90}
                  loading="lazy"
                  decoding="async"
                  className="w-40 shrink-0 rounded-[var(--radius-sm)] border border-[var(--admin-line)] object-cover"
                />

                <div className="min-w-52 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-strong">{row.titleEn}</span>
                    {row.isFeatured ? (
                      <span className="admin-badge" style={{ color: "var(--color-peach)" }}>
                        Featured
                      </span>
                    ) : null}
                    <span
                      className="admin-badge"
                      style={{ color: row.isPublished ? "#63c98c" : "#9aa2b5" }}
                    >
                      {row.isPublished ? "Published" : "Hidden"}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-[0.8rem] text-muted">{row.descriptionEn}</p>
                  <p className="mt-1 text-[0.72rem] text-muted" dir="ltr">
                    {row.youtubeId} · {row.category}
                    {row.durationLabel ? ` · ${row.durationLabel}` : ""}
                    {row.thumbnailFilename ? " · custom still" : " · YouTube still"}
                  </p>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  <InlineAction action={moveVideo} hidden={{ _csrf: csrf, id: row.id, direction: "up" }}>
                    <button type="submit" disabled={index === 0} aria-label="Move up" className="admin-btn admin-btn-sm">
                      <Icon name="chevronDown" size={11} className="rotate-180" />
                    </button>
                  </InlineAction>
                  <InlineAction action={moveVideo} hidden={{ _csrf: csrf, id: row.id, direction: "down" }}>
                    <button
                      type="submit"
                      disabled={index === rows.length - 1}
                      aria-label="Move down"
                      className="admin-btn admin-btn-sm"
                    >
                      <Icon name="chevronDown" size={11} />
                    </button>
                  </InlineAction>
                  <InlineAction action={toggleVideo} hidden={{ _csrf: csrf, id: row.id, what: "published" }}>
                    <button
                      type="submit"
                      className="admin-btn admin-btn-sm"
                      title={row.isPublished ? "Unpublish" : "Publish"}
                    >
                      <Icon name={row.isPublished ? "eyeOff" : "eye"} size={12} />
                    </button>
                  </InlineAction>
                  <InlineAction action={toggleVideo} hidden={{ _csrf: csrf, id: row.id, what: "featured" }}>
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
                  <InlineAction action={deleteVideo} hidden={{ _csrf: csrf, id: row.id }}>
                    <ConfirmSubmit className="admin-btn-sm" message={`Remove “${row.titleEn}” from the showcase?`}>
                      <Icon name="trash" size={12} />
                      <span className="sr-only">Remove</span>
                    </ConfirmSubmit>
                  </InlineAction>
                </div>
              </div>

              {editing === row.id ? (
                <div className="mt-4 border-t border-[var(--admin-line)] pt-4">
                  <VideoForm csrf={csrf} row={row} media={media} />
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function VideoForm({
  csrf,
  row,
  media,
}: {
  csrf: string;
  row: VideoRow | null;
  media: MediaOption[];
}) {
  const [thumbnailId, setThumbnailId] = useState<number | null>(row?.thumbnailId ?? null);
  const key = row?.id ?? "new";

  return (
    <AdminForm action={saveVideo} successMessage={row ? "Video saved." : "Video added."}>
      <input type="hidden" name="_csrf" value={csrf} />
      {row ? <input type="hidden" name="id" value={row.id} /> : null}
      <input type="hidden" name="thumbnailId" value={thumbnailId ?? ""} />

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="YouTube address"
          name={`sourceUrl-${key}`}
          hint="A watch link, a share link, an embed link, a Shorts link, or the 11-character id."
          className="sm:col-span-2"
        >
          <input
            id={`sourceUrl-${key}`}
            name="sourceUrl"
            defaultValue={row?.sourceUrl ?? ""}
            required
            dir="ltr"
            placeholder="https://www.youtube.com/watch?v=…"
            className="admin-input"
          />
        </Field>

        <Field label="Title (English)" name={`titleEn-${key}`}>
          <input id={`titleEn-${key}`} name="titleEn" defaultValue={row?.titleEn ?? ""} required className="admin-input" />
        </Field>
        <Field label="Title (العربية)" name={`titleAr-${key}`}>
          <input id={`titleAr-${key}`} name="titleAr" defaultValue={row?.titleAr ?? ""} dir="rtl" className="admin-input" />
        </Field>

        <Field label="Description (English)" name={`descriptionEn-${key}`}>
          <textarea
            id={`descriptionEn-${key}`}
            name="descriptionEn"
            rows={2}
            defaultValue={row?.descriptionEn ?? ""}
            className="admin-textarea"
          />
        </Field>
        <Field label="Description (العربية)" name={`descriptionAr-${key}`}>
          <textarea
            id={`descriptionAr-${key}`}
            name="descriptionAr"
            rows={2}
            defaultValue={row?.descriptionAr ?? ""}
            dir="rtl"
            className="admin-textarea"
          />
        </Field>

        <Field label="Category" name={`category-${key}`} hint="Used to filter which videos a section shows.">
          <input
            id={`category-${key}`}
            name="category"
            defaultValue={row?.category ?? "general"}
            className="admin-input"
          />
        </Field>
        <Field label="Duration label" name={`durationLabel-${key}`} hint="Shown on the card, e.g. 2:14. Optional.">
          <input
            id={`durationLabel-${key}`}
            name="durationLabel"
            defaultValue={row?.durationLabel ?? ""}
            dir="ltr"
            className="admin-input"
          />
        </Field>

        <div className="sm:col-span-2">
          <span className="admin-label">Custom still</span>
          <MediaPicker
            value={thumbnailId}
            onChange={setThumbnailId}
            options={media}
            label="Video thumbnail"
          />
          <p className="mt-1.5 text-[0.73rem] text-muted">
            Optional. Without one, YouTube&rsquo;s own still is used — which is fine, and one request
            lighter than a custom upload.
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-5">
        <label className="flex cursor-pointer items-center gap-2 text-[0.82rem]">
          <input
            type="checkbox"
            name="isPublished"
            defaultChecked={row?.isPublished ?? true}
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
          Featured — shown larger, first in the grid
        </label>
      </div>

      <div className="mt-5">
        <SubmitButton>{row ? "Save video" : "Add video"}</SubmitButton>
      </div>
    </AdminForm>
  );
}
