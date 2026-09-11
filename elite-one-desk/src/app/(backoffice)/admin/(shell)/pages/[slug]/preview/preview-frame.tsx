"use client";

import { useState } from "react";

import { Icon } from "@/components/ui/icon";

const DEVICES = [
  { key: "desktop", label: "Desktop", width: 0, icon: "desk" },
  { key: "tablet", label: "Tablet", width: 834, icon: "fileText" },
  { key: "mobile", label: "Mobile", width: 390, icon: "idCard" },
] as const;

/**
 * Live preview (§16). The frame loads the real public page with `?preview=1`,
 * so what is shown is the actual site — the same header, footer, fonts and
 * animations — rendered from drafts rather than from the published values.
 */
export function PreviewFrame({ src, title }: { src: string; title: string }) {
  const [device, setDevice] = useState<(typeof DEVICES)[number]["key"]>("desktop");
  const [language, setLanguage] = useState<"en" | "ar">("en");
  const [nonce, setNonce] = useState(0);

  const width = DEVICES.find((d) => d.key === device)?.width ?? 0;
  const url = `${language === "ar" ? "/ar" : ""}${src}${src.includes("?") ? "&" : "?"}preview=1&r=${nonce}`;

  return (
    <div>
      <div className="admin-card mb-4 flex flex-wrap items-center gap-2 p-2.5">
        <div className="flex gap-1" role="group" aria-label="Preview width">
          {DEVICES.map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => setDevice(option.key)}
              aria-pressed={device === option.key}
              className="admin-btn admin-btn-sm aria-pressed:border-[var(--color-orange)]"
              style={device === option.key ? { borderColor: "var(--color-orange)" } : undefined}
            >
              <Icon name={option.icon} size={12} />
              {option.label}
            </button>
          ))}
        </div>

        <div className="flex gap-1" role="group" aria-label="Preview language">
          {(["en", "ar"] as const).map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => setLanguage(code)}
              aria-pressed={language === code}
              className="admin-btn admin-btn-sm"
              style={language === code ? { borderColor: "var(--color-orange)" } : undefined}
            >
              {code === "en" ? "English" : "العربية"}
            </button>
          ))}
        </div>

        <button type="button" onClick={() => setNonce((n) => n + 1)} className="admin-btn admin-btn-sm ms-auto">
          <Icon name="refresh" size={12} />
          Reload
        </button>
        <a href={url} target="_blank" rel="noopener" className="admin-btn admin-btn-sm">
          <Icon name="arrowUpRight" size={12} />
          Open in a tab
        </a>
      </div>

      <div className="admin-card overflow-hidden p-3">
        <div
          className="mx-auto overflow-hidden rounded-[var(--radius-sm)] border border-[var(--admin-line)] bg-black transition-[max-width] duration-300"
          style={{ maxWidth: width ? `${width}px` : "100%" }}
        >
          <iframe
            key={`${device}-${language}-${nonce}`}
            src={url}
            title={`Preview of ${title}`}
            className="h-[75vh] w-full border-0 bg-[#0b0a26]"
          />
        </div>
      </div>
    </div>
  );
}
