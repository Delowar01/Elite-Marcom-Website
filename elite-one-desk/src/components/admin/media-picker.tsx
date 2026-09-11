"use client";

import { useEffect, useState } from "react";

import { Icon } from "@/components/ui/icon";

export type MediaOption = {
  id: number;
  filename: string;
  title: string;
  altEn: string;
  width: number;
  height: number;
  folder: string;
};

/**
 * Picks an image from the library. Deliberately a chooser and not an uploader:
 * everything goes through the Media library so there is one validator, one
 * place a file can be deleted from, and one place to see where a picture is
 * used.
 */
export function MediaPicker({
  value,
  onChange,
  options,
  label = "Image",
}: {
  value: number | null;
  onChange: (id: number | null) => void;
  options: MediaOption[];
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const selected = options.find((o) => o.id === value) ?? null;

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const filtered = query.trim()
    ? options.filter((o) =>
        `${o.title} ${o.altEn} ${o.filename} ${o.folder}`.toLowerCase().includes(query.toLowerCase()),
      )
    : options;

  return (
    <div>
      <div className="flex items-center gap-3">
        <div className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-[var(--radius-sm)] border border-[var(--admin-line)] bg-[color-mix(in_oklab,#05041a_45%,transparent)]">
          {selected ? (
            <img
              src={`/media/${selected.filename}`}
              alt=""
              className="size-full object-cover"
              loading="lazy"
              decoding="async"
            />
          ) : (
            <Icon name="layers" size={18} className="opacity-40" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[0.82rem] text-strong">
            {selected ? selected.title || selected.filename : "No image selected"}
          </p>
          <div className="mt-1.5 flex gap-2">
            <button type="button" onClick={() => setOpen(true)} className="admin-btn admin-btn-sm">
              {selected ? "Change" : "Choose"}
            </button>
            {selected ? (
              <button
                type="button"
                onClick={() => onChange(null)}
                className="admin-btn admin-btn-sm"
              >
                Remove
              </button>
            ) : null}
          </div>
        </div>
      </div>

      {open ? (
        <div className="fixed inset-0 z-70 flex items-center justify-center p-4">
          <button
            type="button"
            aria-label="Close"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label={`Choose ${label}`}
            className="admin-card relative z-10 flex max-h-[80vh] w-full max-w-3xl flex-col overflow-hidden"
          >
            <div className="flex items-center gap-3 border-b border-[var(--admin-line)] p-3.5">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search the library"
                className="admin-input"
                autoFocus
              />
              <button type="button" onClick={() => setOpen(false)} className="admin-btn admin-btn-sm">
                <Icon name="close" size={14} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-3.5">
              {filtered.length === 0 ? (
                <p className="py-10 text-center text-[0.83rem] text-muted">
                  Nothing in the library matches. Upload images under Media library.
                </p>
              ) : (
                <ul className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                  {filtered.map((option) => (
                    <li key={option.id}>
                      <button
                        type="button"
                        onClick={() => {
                          onChange(option.id);
                          setOpen(false);
                        }}
                        className="group w-full overflow-hidden rounded-[var(--radius-sm)] border border-[var(--admin-line)] text-start transition-colors hover:border-[var(--color-orange)]"
                      >
                        <span className="block aspect-[4/3] overflow-hidden bg-[#05041a]">
                          <img
                            src={`/media/${option.filename}`}
                            alt=""
                            loading="lazy"
                            decoding="async"
                            className="size-full object-cover"
                          />
                        </span>
                        <span className="block truncate p-2 text-[0.74rem] text-body">
                          {option.title || option.filename}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
