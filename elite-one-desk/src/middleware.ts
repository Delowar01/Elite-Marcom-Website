import { NextResponse, type NextRequest } from "next/server";

import { DEFAULT_LOCALE, LOCALES } from "@/lib/i18n/config";

/**
 * Two jobs, both of which have to happen before a route is resolved:
 *
 *  1. Language routing. English is served from the root (`/about`) and Arabic
 *     from `/ar/about`; internally both are the same `[lang]` route, so `/about`
 *     is rewritten onto `/en/about`. `/en/...` is a 301 back to the clean form
 *     so one page never has two indexable addresses.
 *
 *  2. Content-Security-Policy with a per-request nonce. Next's bootstrap is an
 *     inline script, so a policy worth having needs a nonce rather than
 *     `unsafe-inline`; the nonce travels to the renderer on a request header.
 */

const PUBLIC_FILE = /\.(?:png|jpe?g|gif|webp|avif|svg|ico|css|js|map|txt|xml|woff2?|ttf|pdf|mp4|webm)$/i;

const SKIP_PREFIXES = ["/_next", "/api", "/media", "/admin", "/monitoring"];

/**
 * Marks the request a rewrite produced.
 *
 * A rewrite re-enters middleware in a production build, so the second pass sees
 * `/en/about` and would 301 it straight back to `/about` — the request the
 * rewrite had just created. This header is how the second pass recognises
 * itself. It is a hint, not a control: a client that forged it would reach
 * `/en/about` without the redirect, which renders the same page and still
 * carries `/about` as its canonical address.
 */
const REWRITE_MARKER = "x-eod-rewritten";

function buildCsp(nonce: string, isDev: boolean): string {
  const directives: Array<[string, string]> = [
    ["default-src", "'self'"],
    ["base-uri", "'self'"],
    ["object-src", "'none'"],
    ["frame-ancestors", "'self'"],
    ["form-action", "'self'"],
    [
      "script-src",
      [
        "'self'",
        `'nonce-${nonce}'`,
        "'strict-dynamic'",
        // Ignored wherever 'strict-dynamic' is understood; the documented
        // fallback for browsers that are not there yet.
        "'unsafe-inline'",
        "https:",
        isDev ? "'unsafe-eval'" : "",
      ]
        .filter(Boolean)
        .join(" "),
    ],
    // React and Tailwind both emit inline <style>; there is no nonce path for
    // them today, and a style injection cannot exfiltrate on its own.
    ["style-src", "'self' 'unsafe-inline'"],
    ["img-src", "'self' data: blob: https://i.ytimg.com https://img.youtube.com https://*.googleusercontent.com"],
    ["font-src", "'self'"],
    [
      "connect-src",
      [
        "'self'",
        "https://www.google-analytics.com",
        "https://analytics.google.com",
        "https://*.analytics.google.com",
        "https://*.google-analytics.com",
        "https://stats.g.doubleclick.net",
        "https://connect.facebook.net",
        isDev ? "ws:" : "",
      ]
        .filter(Boolean)
        .join(" "),
    ],
    [
      // 'self' is the admin preview framing the real public page; the rest are
      // the embeds the site is allowed to show.
      "frame-src",
      "'self' https://www.youtube-nocookie.com https://www.youtube.com https://www.google.com https://maps.google.com https://www.googletagmanager.com",
    ],
    ["media-src", "'self'"],
    ["worker-src", "'self' blob:"],
    ["manifest-src", "'self'"],
  ];
  if (!isDev) directives.push(["upgrade-insecure-requests", ""]);
  return directives.map(([k, v]) => (v ? `${k} ${v}` : k)).join("; ");
}

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isDev = process.env.NODE_ENV !== "production";

  const isSubRequest = request.headers.get(REWRITE_MARKER) === "1";

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("x-pathname", pathname);

  const finish = (response: NextResponse) => {
    response.headers.set("Content-Security-Policy", buildCsp(nonce, isDev));
    return response;
  };

  const skip =
    SKIP_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`)) ||
    PUBLIC_FILE.test(pathname);

  if (skip) {
    return finish(NextResponse.next({ request: { headers: requestHeaders } }));
  }

  // `/en/about` is the internal shape, never a public address. Only a request
  // that actually arrived that way is redirected; the identical path produced
  // by the rewrite below is left alone.
  if (
    !isSubRequest &&
    (pathname === `/${DEFAULT_LOCALE}` || pathname.startsWith(`/${DEFAULT_LOCALE}/`))
  ) {
    const target = pathname.slice(DEFAULT_LOCALE.length + 1) || "/";
    return finish(NextResponse.redirect(new URL(`${target}${search}`, request.url), 301));
  }

  const hasLocale = LOCALES.some(
    (l) => pathname === `/${l}` || pathname.startsWith(`/${l}/`),
  );
  if (hasLocale) {
    return finish(NextResponse.next({ request: { headers: requestHeaders } }));
  }

  const url = request.nextUrl.clone();
  url.pathname = `/${DEFAULT_LOCALE}${pathname === "/" ? "" : pathname}`;
  requestHeaders.set(REWRITE_MARKER, "1");
  return finish(NextResponse.rewrite(url, { request: { headers: requestHeaders } }));
}

export const config = {
  matcher: [
    // Everything except Next's own asset pipeline and the favicon shortcuts.
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
