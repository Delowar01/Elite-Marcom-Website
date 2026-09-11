"use client";

import { useState } from "react";

import { Icon } from "@/components/ui/icon";
import type { BlockDef, FieldDef, ItemFieldDef } from "@/lib/cms/blocks";
import { MediaPicker, type MediaOption } from "./media-picker";

type Values = Record<string, unknown>;
type Localised = { en: string; ar: string };

const asLocalised = (value: unknown): Localised => {
  const source = (typeof value === "object" && value !== null ? value : {}) as Record<string, unknown>;
  return { en: String(source.en ?? ""), ar: String(source.ar ?? "") };
};

const RICH_HINT = "Bold, italic, links, lists, and h3/h4 headings are kept. Everything else becomes plain text.";

/**
 * One editor for every section type.
 *
 * The fields come from the block registry rather than from hand-written forms,
 * so adding a block type is a registry entry and nothing else — the editor, the
 * validator and the renderer all read the same definition. State is held here
 * and serialised into one hidden input, which is what the server re-validates
 * field by field.
 */
export function BlockEditor({
  block,
  initial,
  media,
  name = "values",
}: {
  block: BlockDef;
  initial: Values;
  media: MediaOption[];
  name?: string;
}) {
  const [values, setValues] = useState<Values>(initial);

  const set = (key: string, value: unknown) => setValues((prev) => ({ ...prev, [key]: value }));

  return (
    <>
      <input type="hidden" name={name} value={JSON.stringify(values)} />
      <div className="space-y-5">
        {block.fields.map((field) => (
          <FieldRow
            key={field.name}
            field={field}
            value={values[field.name]}
            media={media}
            onChange={(next) => set(field.name, next)}
          />
        ))}
      </div>
    </>
  );
}

function FieldRow({
  field,
  value,
  media,
  onChange,
}: {
  field: FieldDef;
  value: unknown;
  media: MediaOption[];
  onChange: (next: unknown) => void;
}) {
  const id = `field-${field.name}`;

  if (field.type === "items") {
    return <ItemsField field={field} value={value} onChange={onChange} />;
  }

  if (field.type === "media") {
    return (
      <div>
        <span className="admin-label">{field.label}</span>
        <MediaPicker
          value={typeof value === "number" ? value : null}
          onChange={(next) => onChange(next)}
          options={media}
          label={field.label}
        />
        {field.help ? <p className="mt-1.5 text-[0.73rem] text-muted">{field.help}</p> : null}
      </div>
    );
  }

  if (field.type === "boolean") {
    return (
      <label className="flex cursor-pointer items-start gap-2.5">
        <input
          type="checkbox"
          checked={value === true}
          onChange={(event) => onChange(event.target.checked)}
          className="mt-0.5 size-4 accent-[var(--color-orange)]"
        />
        <span>
          <span className="block text-[0.85rem] text-strong">{field.label}</span>
          {field.help ? <span className="block text-[0.73rem] text-muted">{field.help}</span> : null}
        </span>
      </label>
    );
  }

  if (field.type === "select") {
    return (
      <div>
        <label className="admin-label" htmlFor={id}>
          {field.label}
        </label>
        <select
          id={id}
          value={String(value ?? field.options?.[0]?.value ?? "")}
          onChange={(event) => onChange(event.target.value)}
          className="admin-select"
        >
          {(field.options ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {field.help ? <p className="mt-1.5 text-[0.73rem] text-muted">{field.help}</p> : null}
      </div>
    );
  }

  if (field.type === "number") {
    return (
      <div className="max-w-40">
        <label className="admin-label" htmlFor={id}>
          {field.label}
        </label>
        <input
          id={id}
          type="number"
          min={0}
          value={Number(value ?? 0)}
          onChange={(event) => onChange(Number(event.target.value))}
          className="admin-input"
        />
        {field.help ? <p className="mt-1.5 text-[0.73rem] text-muted">{field.help}</p> : null}
      </div>
    );
  }

  if (field.type === "link") {
    return (
      <div>
        <label className="admin-label" htmlFor={id}>
          {field.label}
        </label>
        <input
          id={id}
          value={String(value ?? "")}
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.placeholder}
          className="admin-input"
          dir="ltr"
        />
        {field.help ? <p className="mt-1.5 text-[0.73rem] text-muted">{field.help}</p> : null}
      </div>
    );
  }

  // text / textarea / richtext — localised or not.
  if (!field.localised) {
    return (
      <div>
        <label className="admin-label" htmlFor={id}>
          {field.label}
        </label>
        {field.type === "text" ? (
          <input
            id={id}
            value={String(value ?? "")}
            onChange={(event) => onChange(event.target.value)}
            placeholder={field.placeholder}
            className="admin-input"
          />
        ) : (
          <textarea
            id={id}
            rows={field.rows ?? 3}
            value={String(value ?? "")}
            onChange={(event) => onChange(event.target.value)}
            className="admin-textarea"
          />
        )}
        {field.help ? <p className="mt-1.5 text-[0.73rem] text-muted">{field.help}</p> : null}
      </div>
    );
  }

  const pair = asLocalised(value);
  const hint = field.type === "richtext" ? RICH_HINT : field.help;

  return (
    <div>
      <span className="admin-label">{field.label}</span>
      <div className="grid gap-2.5 lg:grid-cols-2">
        {(["en", "ar"] as const).map((lang) => (
          <div key={lang}>
            <label
              className="mb-1 block text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-muted"
              htmlFor={`${id}-${lang}`}
            >
              {lang === "en" ? "English" : "العربية"}
            </label>
            {field.type === "text" ? (
              <input
                id={`${id}-${lang}`}
                value={pair[lang]}
                onChange={(event) => onChange({ ...pair, [lang]: event.target.value })}
                placeholder={field.placeholder}
                dir={lang === "ar" ? "rtl" : "ltr"}
                className="admin-input"
              />
            ) : (
              <textarea
                id={`${id}-${lang}`}
                rows={field.rows ?? (field.type === "richtext" ? 8 : 3)}
                value={pair[lang]}
                onChange={(event) => onChange({ ...pair, [lang]: event.target.value })}
                dir={lang === "ar" ? "rtl" : "ltr"}
                className="admin-textarea"
              />
            )}
          </div>
        ))}
      </div>
      <p className="mt-1.5 text-[0.73rem] text-muted">
        {hint ? `${hint} ` : ""}Leave Arabic empty to fall back to the English text.
      </p>
    </div>
  );
}

function ItemsField({
  field,
  value,
  onChange,
}: {
  field: FieldDef;
  value: unknown;
  onChange: (next: unknown) => void;
}) {
  const fields: ItemFieldDef[] = field.itemFields ?? [];
  const rows = Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
  const atLimit = rows.length >= (field.maxItems ?? 24);

  const update = (index: number, key: string, next: unknown) => {
    const copy = rows.map((row, i) => (i === index ? { ...row, [key]: next } : row));
    onChange(copy);
  };

  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= rows.length) return;
    const copy = [...rows];
    [copy[index], copy[target]] = [copy[target]!, copy[index]!];
    onChange(copy);
  };

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="admin-label mb-0">{field.label}</span>
        <span className="text-[0.72rem] text-muted">
          {rows.length}
          {field.maxItems ? ` / ${field.maxItems}` : ""}
        </span>
      </div>
      {field.help ? <p className="mb-2 text-[0.73rem] text-muted">{field.help}</p> : null}

      <ul className="space-y-2.5">
        {rows.map((row, index) => (
          <li
            key={index}
            className="rounded-[var(--radius-sm)] border border-[var(--admin-line)] p-3"
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[0.72rem] font-semibold text-muted">#{index + 1}</span>
              <div className="flex gap-1">
                <button
                  type="button"
                  onClick={() => move(index, -1)}
                  disabled={index === 0}
                  aria-label="Move up"
                  className="admin-btn admin-btn-sm"
                >
                  <Icon name="chevronDown" size={12} className="rotate-180" />
                </button>
                <button
                  type="button"
                  onClick={() => move(index, 1)}
                  disabled={index === rows.length - 1}
                  aria-label="Move down"
                  className="admin-btn admin-btn-sm"
                >
                  <Icon name="chevronDown" size={12} />
                </button>
                <button
                  type="button"
                  onClick={() => onChange(rows.filter((_, i) => i !== index))}
                  aria-label="Remove"
                  className="admin-btn admin-btn-sm admin-btn-danger"
                >
                  <Icon name="close" size={12} />
                </button>
              </div>
            </div>

            <div className="space-y-2.5">
              {fields.map((sub) => {
                const raw = row[sub.name];
                if (!sub.localised) {
                  return (
                    <div key={sub.name}>
                      <label
                        className="mb-1 block text-[0.68rem] font-semibold text-muted"
                        htmlFor={`${field.name}-${index}-${sub.name}`}
                      >
                        {sub.label}
                      </label>
                      <input
                        id={`${field.name}-${index}-${sub.name}`}
                        value={String(raw ?? "")}
                        onChange={(event) => update(index, sub.name, event.target.value)}
                        className="admin-input"
                        dir={sub.name === "href" ? "ltr" : undefined}
                      />
                    </div>
                  );
                }
                const pair = asLocalised(raw);
                return (
                  <div key={sub.name} className="grid gap-2 lg:grid-cols-2">
                    {(["en", "ar"] as const).map((lang) => (
                      <div key={lang}>
                        <label
                          className="mb-1 block text-[0.68rem] font-semibold text-muted"
                          htmlFor={`${field.name}-${index}-${sub.name}-${lang}`}
                        >
                          {sub.label} · {lang === "en" ? "EN" : "AR"}
                        </label>
                        {sub.type === "textarea" ? (
                          <textarea
                            id={`${field.name}-${index}-${sub.name}-${lang}`}
                            rows={2}
                            value={pair[lang]}
                            onChange={(event) =>
                              update(index, sub.name, { ...pair, [lang]: event.target.value })
                            }
                            dir={lang === "ar" ? "rtl" : "ltr"}
                            className="admin-textarea"
                          />
                        ) : (
                          <input
                            id={`${field.name}-${index}-${sub.name}-${lang}`}
                            value={pair[lang]}
                            onChange={(event) =>
                              update(index, sub.name, { ...pair, [lang]: event.target.value })
                            }
                            dir={lang === "ar" ? "rtl" : "ltr"}
                            className="admin-input"
                          />
                        )}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </li>
        ))}
      </ul>

      <button
        type="button"
        onClick={() => onChange([...rows, emptyRow(fields)])}
        disabled={atLimit}
        className="admin-btn admin-btn-sm mt-2.5"
      >
        <Icon name="sparkle" size={12} />
        Add {field.label.toLowerCase().replace(/s$/, "")}
      </button>
      {atLimit ? (
        <p className="mt-1.5 text-[0.73rem] text-muted">
          That is the maximum for this section — more would not lay out well.
        </p>
      ) : null}
    </div>
  );
}

function emptyRow(fields: ItemFieldDef[]): Record<string, unknown> {
  const row: Record<string, unknown> = {};
  for (const field of fields) row[field.name] = field.localised ? { en: "", ar: "" } : "";
  return row;
}
