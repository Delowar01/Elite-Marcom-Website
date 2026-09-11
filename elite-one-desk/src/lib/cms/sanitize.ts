/**
 * Rich-text whitelist.
 *
 * Nothing from the panel is ever echoed into a page as-is. The input is
 * tokenised, every run of text is escaped, and only the tags on the list below
 * are re-emitted — rebuilt from the parsed name and a validated attribute set,
 * never copied through. A tag that is not on the list loses its markup and
 * keeps its text, which is what an editor pasting from Word actually wants.
 */

const ALLOWED_TAGS = new Set([
  "p",
  "br",
  "strong",
  "b",
  "em",
  "i",
  "u",
  "h3",
  "h4",
  "ul",
  "ol",
  "li",
  "a",
  "blockquote",
]);

/** Tags that never have a closing partner. */
const VOID_TAGS = new Set(["br"]);

/** Normalised so `<b>` and `<i>` come out as the semantic element. */
const TAG_ALIASES: Record<string, string> = { b: "strong", i: "em" };

const SAFE_HREF = /^(https?:\/\/|\/(?!\/)|mailto:|tel:|#)/i;

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** `/services` stays internal; anything off-site opens safely in a new tab. */
function anchorAttributes(raw: string): string | null {
  const match = /href\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))/i.exec(raw);
  const href = (match?.[2] ?? match?.[3] ?? match?.[4] ?? "").trim();
  if (!href || !SAFE_HREF.test(href)) return null;
  const external = /^https?:\/\//i.test(href);
  const attrs = ` href="${escapeHtml(href)}"`;
  return external ? `${attrs} target="_blank" rel="noopener noreferrer"` : attrs;
}

export function sanitizeRichText(input: string): string {
  if (!input) return "";
  const stack: string[] = [];
  let out = "";
  let cursor = 0;

  const tagPattern = /<\/?([a-zA-Z][a-zA-Z0-9-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/g;
  let match: RegExpExecArray | null;

  while ((match = tagPattern.exec(input)) !== null) {
    out += escapeHtml(input.slice(cursor, match.index));
    cursor = tagPattern.lastIndex;

    const closing = match[0].startsWith("</");
    const rawName = match[1]!.toLowerCase();
    const name = TAG_ALIASES[rawName] ?? rawName;
    if (!ALLOWED_TAGS.has(rawName)) continue;

    if (VOID_TAGS.has(name)) {
      if (!closing) out += `<${name}>`;
      continue;
    }

    if (closing) {
      const at = stack.lastIndexOf(name);
      if (at === -1) continue;
      // Close anything opened inside it, so the output is always well formed.
      while (stack.length > at) out += `</${stack.pop()}>`;
      continue;
    }

    if (name === "a") {
      const attrs = anchorAttributes(match[2] ?? "");
      if (!attrs) continue;
      out += `<a${attrs}>`;
    } else {
      out += `<${name}>`;
    }
    stack.push(name);
  }

  out += escapeHtml(input.slice(cursor));
  while (stack.length) out += `</${stack.pop()}>`;
  return out.trim();
}

/** Strips every tag — used for meta descriptions and search indexing. */
export function toPlainText(html: string, limit = 0): string {
  const text = html
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
  if (!limit || text.length <= limit) return text;
  return `${text.slice(0, limit - 1).replace(/\s+\S*$/, "")}…`;
}

/**
 * Links stored in fields (a CTA href, a nav item). Only site-relative paths and
 * https/mailto/tel survive — `javascript:` and protocol-relative `//host` do not.
 */
export function sanitizeHref(input: string): string {
  const href = (input ?? "").trim();
  if (!href) return "";
  if (!SAFE_HREF.test(href)) return "";
  if (/^\/\//.test(href)) return "";
  return href;
}
