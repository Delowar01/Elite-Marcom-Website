import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { notFound } from "next/navigation";

import { Analytics } from "@/components/site/analytics";
import { CursorCompanion } from "@/components/site/cursor-companion";
import { SiteFooter } from "@/components/site/site-footer";
import { SiteHeader } from "@/components/site/site-header";
import { WhatsappFloat } from "@/components/site/whatsapp-float";
import { siteUrl } from "@/lib/env";
import { LOCALES, dirOf, isLocale } from "@/lib/i18n/config";
import { getDictionary } from "@/lib/i18n/dictionary";
import { getSettings, whatsappLink } from "@/lib/settings";

import "@/styles/globals.css";

export const viewport: Viewport = {
  themeColor: "#0b0a26",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  icons: {
    icon: [
      { url: "/brand/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/brand/favicon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/brand/favicon-180.png", sizes: "180x180" }],
    shortcut: ["/brand/favicon.ico"],
  },
  formatDetection: { telephone: false },
};

export function generateStaticParams() {
  return LOCALES.map((lang) => ({ lang }));
}

export default async function PublicLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  if (!isLocale(lang)) notFound();

  const [settings, headerList] = await Promise.all([getSettings(), headers()]);
  if (lang === "ar" && !settings.features.arabicEnabled) notFound();

  const dict = getDictionary(lang);
  const nonce = headerList.get("x-nonce") ?? undefined;
  const whatsapp = settings.whatsapp.floatingEnabled ? whatsappLink(settings, lang) : null;

  return (
    <html lang={lang} dir={dirOf(lang)} suppressHydrationWarning>
      <body className="flex min-h-dvh flex-col">
        <a
          href="#main"
          className="sr-only focus-visible:not-sr-only focus-visible:fixed focus-visible:start-4 focus-visible:top-4 focus-visible:z-100 focus-visible:rounded-full focus-visible:bg-[var(--color-orange)] focus-visible:px-5 focus-visible:py-2.5 focus-visible:text-sm focus-visible:font-semibold focus-visible:text-white"
        >
          {dict.nav.skipToContent}
        </a>

        <SiteHeader locale={lang} />

        <main id="main" className="flex-1">
          {children}
        </main>

        <SiteFooter locale={lang} />

        {whatsapp ? <WhatsappFloat href={whatsapp} label={dict.common.whatsappUs} /> : null}
        {settings.features.customCursor ? <CursorCompanion /> : null}

        <Analytics
          ga4Id={settings.analytics.ga4Id}
          gtmId={settings.analytics.gtmId}
          metaPixelId={settings.analytics.metaPixelId}
          nonce={nonce}
        />
      </body>
    </html>
  );
}
