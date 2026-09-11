import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/env";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        // The admin and the API are not content. `/search` is deliberately
        // crawlable but carries its own noindex, so a crawler reads the tag
        // rather than being blocked from ever seeing it.
        disallow: ["/admin", "/api/", "/media/*@*"],
      },
    ],
    sitemap: `${siteUrl}/sitemap.xml`,
    host: siteUrl,
  };
}
