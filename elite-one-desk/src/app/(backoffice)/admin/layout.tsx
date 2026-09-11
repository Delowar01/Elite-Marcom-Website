import type { Metadata, Viewport } from "next";

import "@/styles/globals.css";

export const metadata: Metadata = {
  title: { default: "Elite One Desk — Admin", template: "%s · Elite One Desk Admin" },
  // The panel is never a search result.
  robots: { index: false, follow: false, nocache: true },
  icons: { icon: [{ url: "/brand/favicon-32.png", sizes: "32x32", type: "image/png" }] },
};

export const viewport: Viewport = {
  themeColor: "#0a0921",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
};

/**
 * Root layout for the back office. It is a separate root from the public site
 * (route groups, no shared `app/layout.tsx`) so the panel is always LTR and
 * always English, whichever language edition the visitor was last looking at.
 */
export default function BackofficeLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" dir="ltr">
      <body className="admin min-h-dvh">{children}</body>
    </html>
  );
}
