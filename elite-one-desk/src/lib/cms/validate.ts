import { sanitizeHref, sanitizeRichText } from "./sanitize";
import type { BlockDef, FieldDef, ItemFieldDef } from "./blocks";

/**
 * Rebuilds a section's values from what the panel submitted.
 *
 * The output is constructed field by field from the block definition — the
 * submitted object is read, never merged — so a key the registry does not
 * declare cannot reach the database, and a `richtext` field cannot arrive as an
 * array. Rich text goes through the tag whitelist here, on the way in, so the
 * renderer never has to trust what it reads back.
 */

const MAX_TEXT = 400;
const MAX_AREA = 4000;
const MAX_RICH = 20000;

type Localised = { en: string; ar: string };

const asString = (value: unknown, max: number): string =>
  typeof value === "string" ? value.slice(0, max).trim() : "";

function localised(value: unknown, max: number, rich = false): Localised {
  const source = (typeof value === "object" && value !== null ? value : {}) as Record<string, unknown>;
  const clean = (raw: unknown) => {
    const text = asString(raw, max);
    return rich ? sanitizeRichText(text) : text;
  };
  return { en: clean(source.en), ar: clean(source.ar) };
}

function itemRow(row: unknown, fields: ItemFieldDef[]): Record<string, unknown> {
  const source = (typeof row === "object" && row !== null ? row : {}) as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  for (const field of fields) {
    const max = field.type === "textarea" ? MAX_AREA : MAX_TEXT;
    if (field.localised) {
      out[field.name] = localised(source[field.name], max);
    } else if (field.name === "href") {
      out[field.name] = sanitizeHref(asString(source[field.name], MAX_TEXT));
    } else {
      out[field.name] = asString(source[field.name], max);
    }
  }
  return out;
}

function fieldValue(field: FieldDef, raw: unknown): unknown {
  switch (field.type) {
    case "richtext":
      return field.localised
        ? localised(raw, MAX_RICH, true)
        : sanitizeRichText(asString(raw, MAX_RICH));
    case "textarea":
      return field.localised ? localised(raw, MAX_AREA) : asString(raw, MAX_AREA);
    case "link":
      return sanitizeHref(asString(raw, MAX_TEXT));
    case "media": {
      const id = typeof raw === "number" ? raw : Number.parseInt(String(raw ?? ""), 10);
      return Number.isFinite(id) && id > 0 ? id : null;
    }
    case "number": {
      const n = typeof raw === "number" ? raw : Number.parseInt(String(raw ?? ""), 10);
      return Number.isFinite(n) ? Math.max(0, Math.min(999, n)) : 0;
    }
    case "boolean":
      return raw === true || raw === "true" || raw === "on";
    case "select": {
      const value = asString(raw, 64);
      const allowed = (field.options ?? []).map((o) => o.value);
      return allowed.includes(value) ? value : (allowed[0] ?? "");
    }
    case "items": {
      const fields = field.itemFields ?? [];
      const rows = Array.isArray(raw) ? raw : [];
      return rows.slice(0, field.maxItems ?? 24).map((row) => itemRow(row, fields));
    }
    default:
      return field.localised ? localised(raw, MAX_TEXT) : asString(raw, MAX_TEXT);
  }
}

export function validateBlockValues(block: BlockDef, submitted: unknown): Record<string, unknown> {
  const source = (typeof submitted === "object" && submitted !== null ? submitted : {}) as Record<
    string,
    unknown
  >;
  const out: Record<string, unknown> = {};
  for (const field of block.fields) out[field.name] = fieldValue(field, source[field.name]);
  return out;
}

/** Parses the hidden JSON payload the block editor submits. */
export function parseBlockPayload(raw: string, block: BlockDef): Record<string, unknown> | null {
  if (!raw) return null;
  try {
    return validateBlockValues(block, JSON.parse(raw));
  } catch {
    return null;
  }
}
