/**
 * SVG whitelist.
 *
 * §17 asks for SVG "where safely sanitized". An SVG served from our own origin
 * is a document that can run script, so it is rebuilt here from a fixed list of
 * elements and attributes — anything else is dropped, not escaped. The media
 * route adds a locked-down CSP on top, so even a sanitiser mistake has no
 * capability to reach.
 */
const ALLOWED_ELEMENTS = new Set([
  "svg", "g", "path", "circle", "ellipse", "line", "polyline", "polygon", "rect",
  "text", "tspan", "defs", "linearGradient", "radialGradient", "stop", "clipPath",
  "mask", "pattern", "title", "desc", "symbol", "use", "marker",
]);

const ALLOWED_ATTRIBUTES = new Set([
  "d", "cx", "cy", "r", "rx", "ry", "x", "y", "x1", "x2", "y1", "y2", "points",
  "width", "height", "viewBox", "fill", "fill-rule", "fill-opacity", "stroke",
  "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray",
  "stroke-dashoffset", "stroke-opacity", "stroke-miterlimit", "opacity",
  "transform", "gradientUnits", "gradientTransform", "offset", "stop-color",
  "stop-opacity", "clip-path", "clip-rule", "mask", "patternUnits", "id",
  "xmlns", "preserveAspectRatio", "font-family", "font-size", "font-weight",
  "text-anchor", "letter-spacing", "dominant-baseline", "class",
  "marker-end", "marker-start", "orient", "refX", "refY", "markerWidth", "markerHeight",
]);

const escape = (value: string) =>
  value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function sanitizeSvg(source: string): string | null {
  if (!/<svg[\s>]/i.test(source)) return null;

  const stack: string[] = [];
  let out = "";
  let cursor = 0;
  let sawSvg = false;

  const tagPattern = /<\/?([a-zA-Z][a-zA-Z0-9:-]*)((?:[^>"']|"[^"]*"|'[^']*')*)\/?>/g;
  let match: RegExpExecArray | null;

  while ((match = tagPattern.exec(source)) !== null) {
    // Only text inside <text>/<tspan> is meaningful; everything else between
    // tags in an SVG is whitespace, and dropping it avoids re-emitting any
    // stray markup the tokeniser did not recognise.
    const between = source.slice(cursor, match.index);
    const inText = stack[stack.length - 1] === "text" || stack[stack.length - 1] === "tspan";
    if (inText && between.trim()) out += escape(between);
    cursor = tagPattern.lastIndex;

    const closing = match[0].startsWith("</");
    const selfClosing = match[0].endsWith("/>");
    const name = match[1]!;
    if (!ALLOWED_ELEMENTS.has(name)) continue;
    if (name === "svg") sawSvg = true;

    if (closing) {
      const at = stack.lastIndexOf(name);
      if (at === -1) continue;
      while (stack.length > at) out += `</${stack.pop()}>`;
      continue;
    }

    let attrs = "";
    const attrPattern = /([a-zA-Z][a-zA-Z0-9:_-]*)\s*=\s*("([^"]*)"|'([^']*)')/g;
    let attr: RegExpExecArray | null;
    while ((attr = attrPattern.exec(match[2] ?? "")) !== null) {
      const key = attr[1]!;
      const value = attr[3] ?? attr[4] ?? "";
      if (!ALLOWED_ATTRIBUTES.has(key)) continue;
      // No url(), no data:, no external reference of any kind.
      if (/url\s*\(|javascript:|data:|&#/i.test(value)) continue;
      // `use` may only point inside the same document.
      if (key === "href" || key === "xlink:href") continue;
      attrs += ` ${key}="${escape(value)}"`;
    }

    if (selfClosing) {
      out += `<${name}${attrs}/>`;
    } else {
      out += `<${name}${attrs}>`;
      stack.push(name);
    }
  }

  while (stack.length) out += `</${stack.pop()}>`;
  if (!sawSvg) return null;
  return `<?xml version="1.0" encoding="UTF-8"?>\n${out}`;
}
