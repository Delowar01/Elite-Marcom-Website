"use client";

import { useState } from "react";

import { Icon } from "@/components/ui/icon";

export type LocalisedItem = { en: string; ar: string };
export type LocalisedStep = { en: string; ar: string; detailEn: string; detailAr: string };

/**
 * Repeatable bilingual lists on the service form — benefits, audience,
 * requirements. State lives here and is serialised into one hidden input, which
 * the action re-validates; the row order is the order on the page.
 */
export function ItemListEditor({
  name,
  label,
  hint,
  initial,
  max = 16,
}: {
  name: string;
  label: string;
  hint?: string;
  initial: LocalisedItem[];
  max?: number;
}) {
  const [rows, setRows] = useState<LocalisedItem[]>(initial.length ? initial : []);

  const update = (index: number, key: keyof LocalisedItem, value: string) =>
    setRows(rows.map((row, i) => (i === index ? { ...row, [key]: value } : row)));

  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= rows.length) return;
    const copy = [...rows];
    [copy[index], copy[target]] = [copy[target]!, copy[index]!];
    setRows(copy);
  };

  return (
    <div>
      <input type="hidden" name={name} value={JSON.stringify(rows.filter((r) => r.en.trim() || r.ar.trim()))} />
      <div className="mb-1.5 flex items-center justify-between gap-3">
        <span className="admin-label mb-0">{label}</span>
        <span className="text-[0.72rem] text-muted">
          {rows.length} / {max}
        </span>
      </div>
      {hint ? <p className="mb-2 text-[0.73rem] text-muted">{hint}</p> : null}

      <ul className="space-y-2">
        {rows.map((row, index) => (
          <li key={index} className="flex items-start gap-2">
            <div className="grid flex-1 gap-2 sm:grid-cols-2">
              <input
                value={row.en}
                onChange={(event) => update(index, "en", event.target.value)}
                placeholder="English"
                aria-label={`${label} ${index + 1}, English`}
                className="admin-input"
              />
              <input
                value={row.ar}
                onChange={(event) => update(index, "ar", event.target.value)}
                placeholder="العربية"
                dir="rtl"
                aria-label={`${label} ${index + 1}, Arabic`}
                className="admin-input"
              />
            </div>
            <div className="flex shrink-0 gap-1">
              <button
                type="button"
                onClick={() => move(index, -1)}
                disabled={index === 0}
                aria-label="Move up"
                className="admin-btn admin-btn-sm"
              >
                <Icon name="chevronDown" size={11} className="rotate-180" />
              </button>
              <button
                type="button"
                onClick={() => move(index, 1)}
                disabled={index === rows.length - 1}
                aria-label="Move down"
                className="admin-btn admin-btn-sm"
              >
                <Icon name="chevronDown" size={11} />
              </button>
              <button
                type="button"
                onClick={() => setRows(rows.filter((_, i) => i !== index))}
                aria-label="Remove"
                className="admin-btn admin-btn-sm admin-btn-danger"
              >
                <Icon name="close" size={11} />
              </button>
            </div>
          </li>
        ))}
      </ul>

      <button
        type="button"
        onClick={() => setRows([...rows, { en: "", ar: "" }])}
        disabled={rows.length >= max}
        className="admin-btn admin-btn-sm mt-2"
      >
        Add row
      </button>
    </div>
  );
}

export function StepListEditor({
  name,
  label,
  hint,
  initial,
  max = 10,
}: {
  name: string;
  label: string;
  hint?: string;
  initial: LocalisedStep[];
  max?: number;
}) {
  const [rows, setRows] = useState<LocalisedStep[]>(initial);

  const update = (index: number, key: keyof LocalisedStep, value: string) =>
    setRows(rows.map((row, i) => (i === index ? { ...row, [key]: value } : row)));

  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= rows.length) return;
    const copy = [...rows];
    [copy[index], copy[target]] = [copy[target]!, copy[index]!];
    setRows(copy);
  };

  return (
    <div>
      <input type="hidden" name={name} value={JSON.stringify(rows.filter((r) => r.en.trim() || r.ar.trim()))} />
      <div className="mb-1.5 flex items-center justify-between gap-3">
        <span className="admin-label mb-0">{label}</span>
        <span className="text-[0.72rem] text-muted">
          {rows.length} / {max}
        </span>
      </div>
      {hint ? <p className="mb-2 text-[0.73rem] text-muted">{hint}</p> : null}

      <ol className="space-y-2.5">
        {rows.map((row, index) => (
          <li key={index} className="rounded-[var(--radius-sm)] border border-[var(--admin-line)] p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[0.72rem] font-semibold text-muted">
                Step {String(index + 1).padStart(2, "0")}
              </span>
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={() => move(index, -1)}
                  disabled={index === 0}
                  aria-label="Move up"
                  className="admin-btn admin-btn-sm"
                >
                  <Icon name="chevronDown" size={11} className="rotate-180" />
                </button>
                <button
                  type="button"
                  onClick={() => move(index, 1)}
                  disabled={index === rows.length - 1}
                  aria-label="Move down"
                  className="admin-btn admin-btn-sm"
                >
                  <Icon name="chevronDown" size={11} />
                </button>
                <button
                  type="button"
                  onClick={() => setRows(rows.filter((_, i) => i !== index))}
                  aria-label="Remove"
                  className="admin-btn admin-btn-sm admin-btn-danger"
                >
                  <Icon name="close" size={11} />
                </button>
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <input
                value={row.en}
                onChange={(event) => update(index, "en", event.target.value)}
                placeholder="Step title (English)"
                className="admin-input"
              />
              <input
                value={row.ar}
                onChange={(event) => update(index, "ar", event.target.value)}
                placeholder="عنوان الخطوة"
                dir="rtl"
                className="admin-input"
              />
              <textarea
                value={row.detailEn}
                onChange={(event) => update(index, "detailEn", event.target.value)}
                rows={2}
                placeholder="What happens at this step (English)"
                className="admin-textarea"
              />
              <textarea
                value={row.detailAr}
                onChange={(event) => update(index, "detailAr", event.target.value)}
                rows={2}
                placeholder="تفاصيل الخطوة"
                dir="rtl"
                className="admin-textarea"
              />
            </div>
          </li>
        ))}
      </ol>

      <button
        type="button"
        onClick={() => setRows([...rows, { en: "", ar: "", detailEn: "", detailAr: "" }])}
        disabled={rows.length >= max}
        className="admin-btn admin-btn-sm mt-2"
      >
        Add step
      </button>
    </div>
  );
}
