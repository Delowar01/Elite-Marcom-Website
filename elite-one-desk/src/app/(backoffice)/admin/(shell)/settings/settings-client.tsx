"use client";

import { useState } from "react";

import { AdminForm, ConfirmSubmit, Field, InlineAction, SubmitButton } from "@/components/admin/form";
import { Icon } from "@/components/ui/icon";
import type { SiteSettings } from "@/lib/settings-defaults";
import {
  deleteSocialLink,
  saveBrand,
  saveContact,
  saveDisclaimers,
  saveFeatures,
  saveSocialLink,
  saveWhatsapp,
} from "./actions";

export type SocialRow = {
  id: number;
  platform: string;
  url: string;
  sortOrder: number;
  isPublished: boolean;
};

const TABS = [
  { key: "brand", label: "Brand" },
  { key: "contact", label: "Contact" },
  { key: "whatsapp", label: "WhatsApp" },
  { key: "social", label: "Social links" },
  { key: "disclaimers", label: "Disclaimers" },
  { key: "features", label: "Features" },
] as const;

const text = (
  id: string,
  name: string,
  label: string,
  value: string,
  opts: { rtl?: boolean; hint?: string; rows?: number; type?: string } = {},
) => (
  <Field key={id} label={label} name={id} hint={opts.hint}>
    {opts.rows ? (
      <textarea
        id={id}
        name={name}
        rows={opts.rows}
        defaultValue={value}
        dir={opts.rtl ? "rtl" : undefined}
        className="admin-textarea"
      />
    ) : (
      <input
        id={id}
        name={name}
        type={opts.type ?? "text"}
        defaultValue={value}
        dir={opts.rtl ? "rtl" : undefined}
        className="admin-input"
      />
    )}
  </Field>
);

export function SettingsClient({
  csrf,
  settings,
  social,
}: {
  csrf: string;
  settings: SiteSettings;
  social: SocialRow[];
}) {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("brand");

  return (
    <>
      <nav aria-label="Settings sections" className="mb-4 flex flex-wrap gap-1.5">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            aria-current={tab === item.key ? "page" : undefined}
            className="admin-btn admin-btn-sm"
            style={tab === item.key ? { borderColor: "var(--color-orange)" } : undefined}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {tab === "brand" ? (
        <AdminForm action={saveBrand} className="admin-card max-w-3xl p-5">
          <input type="hidden" name="_csrf" value={csrf} />
          <h2 className="mb-4">Brand</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {text("siteNameEn", "siteNameEn", "Site name (English)", settings.brand.siteNameEn)}
            {text("siteNameAr", "siteNameAr", "Site name (العربية)", settings.brand.siteNameAr, { rtl: true })}
            {text("taglineEn", "taglineEn", "Tagline (English)", settings.brand.taglineEn)}
            {text("taglineAr", "taglineAr", "Tagline (العربية)", settings.brand.taglineAr, { rtl: true })}
            {text("legalNameEn", "legalNameEn", "Legal name (English)", settings.brand.legalNameEn, {
              hint: "Used in the copyright line and the Organization structured data.",
            })}
            {text("legalNameAr", "legalNameAr", "Legal name (العربية)", settings.brand.legalNameAr, { rtl: true })}
          </div>
          <div className="mt-5">
            <SubmitButton />
          </div>
        </AdminForm>
      ) : null}

      {tab === "contact" ? (
        <AdminForm action={saveContact} className="admin-card max-w-3xl p-5">
          <input type="hidden" name="_csrf" value={csrf} />
          <h2 className="mb-1">Contact details</h2>
          <p className="mb-4 text-[0.8rem] text-muted">
            These appear in the footer, on the contact page and in the structured data. A field left
            empty is not shown at all — nothing is invented to fill a gap.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            {text("phone", "phone", "Phone (for the tel: link)", settings.contact.phone, {
              hint: "International format, e.g. +9665XXXXXXXX.",
            })}
            {text("phoneDisplay", "phoneDisplay", "Phone (as shown)", settings.contact.phoneDisplay, {
              hint: "Optional. Leave empty to show the number above.",
            })}
            {text("email", "email", "Email", settings.contact.email, { type: "email" })}
            {text("hoursEn", "hoursEn", "Opening hours (English)", settings.contact.hoursEn)}
            {text("hoursAr", "hoursAr", "Opening hours (العربية)", settings.contact.hoursAr, { rtl: true })}
            {text("addressEn", "addressEn", "Street address (English)", settings.contact.addressEn)}
            {text("addressAr", "addressAr", "Street address (العربية)", settings.contact.addressAr, { rtl: true })}
            {text("cityEn", "cityEn", "City (English)", settings.contact.cityEn)}
            {text("cityAr", "cityAr", "City (العربية)", settings.contact.cityAr, { rtl: true })}
            {text("countryEn", "countryEn", "Country (English)", settings.contact.countryEn)}
            {text("countryAr", "countryAr", "Country (العربية)", settings.contact.countryAr, { rtl: true })}
          </div>
          <div className="mt-4">
            {text("mapEmbedUrl", "mapEmbedUrl", "Google Maps embed address", settings.contact.mapEmbedUrl, {
              hint: "In Google Maps: Share → Embed a map → copy the src address. Leave empty to hide the map.",
            })}
          </div>
          <div className="mt-5">
            <SubmitButton />
          </div>
        </AdminForm>
      ) : null}

      {tab === "whatsapp" ? (
        <AdminForm action={saveWhatsapp} className="admin-card max-w-3xl p-5">
          <input type="hidden" name="_csrf" value={csrf} />
          <h2 className="mb-1">WhatsApp</h2>
          <p className="mb-4 text-[0.8rem] text-muted">
            The floating button and every WhatsApp link on the site. On a service page the message is
            filled in with that service&rsquo;s name.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            {text("number", "number", "WhatsApp number", settings.whatsapp.number, {
              hint: "Digits only, with the country code — for example 9665XXXXXXXX.",
            })}
          </div>
          <div className="mt-4 grid gap-4">
            {text(
              "defaultMessageEn",
              "defaultMessageEn",
              "Default message (English)",
              settings.whatsapp.defaultMessageEn,
              { rows: 2 },
            )}
            {text(
              "defaultMessageAr",
              "defaultMessageAr",
              "Default message (العربية)",
              settings.whatsapp.defaultMessageAr,
              { rows: 2, rtl: true },
            )}
          </div>
          <div className="mt-4 space-y-2.5">
            <label className="flex cursor-pointer items-center gap-2 text-[0.85rem]">
              <input
                type="checkbox"
                name="enabled"
                defaultChecked={settings.whatsapp.enabled}
                className="size-4 accent-[var(--color-orange)]"
              />
              WhatsApp is switched on
            </label>
            <label className="flex cursor-pointer items-center gap-2 text-[0.85rem]">
              <input
                type="checkbox"
                name="floatingEnabled"
                defaultChecked={settings.whatsapp.floatingEnabled}
                className="size-4 accent-[var(--color-orange)]"
              />
              Show the floating button on every page
            </label>
          </div>
          <div className="mt-5">
            <SubmitButton />
          </div>
        </AdminForm>
      ) : null}

      {tab === "social" ? <SocialPanel csrf={csrf} rows={social} /> : null}

      {tab === "disclaimers" ? (
        <AdminForm action={saveDisclaimers} className="admin-card max-w-3xl p-5">
          <input type="hidden" name="_csrf" value={csrf} />
          <h2 className="mb-1">Disclaimers</h2>
          <p className="mb-4 text-[0.8rem] text-muted">
            The government notice appears in the footer and, when switched on below, at the bottom of
            every service page. The visa notice is added on visa services automatically.
          </p>
          <div className="grid gap-4">
            {text("governmentEn", "governmentEn", "Government services notice (English)", settings.disclaimers.governmentEn, { rows: 4 })}
            {text("governmentAr", "governmentAr", "Government services notice (العربية)", settings.disclaimers.governmentAr, { rows: 4, rtl: true })}
            {text("visaEn", "visaEn", "Visa notice (English)", settings.disclaimers.visaEn, { rows: 3 })}
            {text("visaAr", "visaAr", "Visa notice (العربية)", settings.disclaimers.visaAr, { rows: 3, rtl: true })}
          </div>
          <label className="mt-4 flex cursor-pointer items-start gap-2.5">
            <input
              type="checkbox"
              name="showOnServicePages"
              defaultChecked={settings.disclaimers.showOnServicePages}
              className="mt-0.5 size-4 accent-[var(--color-orange)]"
            />
            <span>
              <span className="block text-[0.85rem] text-strong">Show on every service page</span>
              <span className="block text-[0.73rem] text-muted">
                Recommended. It is what keeps the site from reading as an official channel.
              </span>
            </span>
          </label>
          <div className="mt-5">
            <SubmitButton />
          </div>
        </AdminForm>
      ) : null}

      {tab === "features" ? (
        <AdminForm action={saveFeatures} className="admin-card max-w-3xl p-5">
          <input type="hidden" name="_csrf" value={csrf} />
          <h2 className="mb-4">Features</h2>
          <div className="space-y-3">
            {[
              {
                name: "arabicEnabled",
                label: "Arabic edition",
                hint: "Publishes /ar and shows the language switch. Turning it off hides both.",
                value: settings.features.arabicEnabled,
              },
              {
                name: "searchEnabled",
                label: "Site search",
                hint: "The search control in the header and the /search page.",
                value: settings.features.searchEnabled,
              },
              {
                name: "showVideos",
                label: "Video showcase",
                hint: "Video sections render only when this is on.",
                value: settings.features.showVideos,
              },
              {
                name: "showTestimonials",
                label: "Testimonials",
                hint: "Testimonial sections render only when this is on.",
                value: settings.features.showTestimonials,
              },
              {
                name: "showStats",
                label: "Statistics",
                hint: "Off until you have figures you can evidence. An empty statistics section never renders.",
                value: settings.features.showStats,
              },
              {
                name: "customCursor",
                label: "Pointer companion",
                hint: "A small ring that follows the pointer on desktop. Never shown on touch devices or with reduced motion.",
                value: settings.features.customCursor,
              },
            ].map((item) => (
              <label key={item.name} className="flex cursor-pointer items-start gap-2.5">
                <input
                  type="checkbox"
                  name={item.name}
                  defaultChecked={item.value}
                  className="mt-0.5 size-4 accent-[var(--color-orange)]"
                />
                <span>
                  <span className="block text-[0.85rem] text-strong">{item.label}</span>
                  <span className="block text-[0.73rem] text-muted">{item.hint}</span>
                </span>
              </label>
            ))}
          </div>
          <div className="mt-5">
            <SubmitButton />
          </div>
        </AdminForm>
      ) : null}
    </>
  );
}

function SocialPanel({ csrf, rows }: { csrf: string; rows: SocialRow[] }) {
  const [editing, setEditing] = useState<number | "new" | null>(rows.length ? null : "new");

  return (
    <div className="max-w-3xl space-y-4">
      <div className="admin-card p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2>Social links</h2>
            <p className="mt-0.5 text-[0.78rem] text-muted">
              Shown as icons in the footer. https addresses only.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setEditing(editing === "new" ? null : "new")}
            className="admin-btn admin-btn-sm"
          >
            {editing === "new" ? "Cancel" : "Add link"}
          </button>
        </div>
        {editing === "new" ? <SocialForm csrf={csrf} row={null} /> : null}
      </div>

      {rows.length === 0 ? null : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <li key={row.id} className="admin-card p-3.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold capitalize text-strong">{row.platform}</span>
                <span className="truncate text-[0.76rem] text-muted" dir="ltr">
                  {row.url}
                </span>
                {!row.isPublished ? (
                  <span className="admin-badge" style={{ color: "#9aa2b5" }}>
                    Hidden
                  </span>
                ) : null}
                <div className="ms-auto flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => setEditing(editing === row.id ? null : row.id)}
                    className="admin-btn admin-btn-sm"
                  >
                    {editing === row.id ? "Close" : "Edit"}
                  </button>
                  <InlineAction action={deleteSocialLink} hidden={{ _csrf: csrf, id: row.id }}>
                    <ConfirmSubmit className="admin-btn-sm" message={`Remove the ${row.platform} link?`}>
                      <Icon name="trash" size={11} />
                      <span className="sr-only">Remove</span>
                    </ConfirmSubmit>
                  </InlineAction>
                </div>
              </div>
              {editing === row.id ? (
                <div className="mt-3 border-t border-[var(--admin-line)] pt-3">
                  <SocialForm csrf={csrf} row={row} />
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SocialForm({ csrf, row }: { csrf: string; row: SocialRow | null }) {
  const key = row?.id ?? "new";
  return (
    <AdminForm action={saveSocialLink} successMessage={row ? "Link saved." : "Link added."}>
      <input type="hidden" name="_csrf" value={csrf} />
      {row ? <input type="hidden" name="id" value={row.id} /> : null}
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Network" name={`platform-${key}`} hint="linkedin, instagram, x, youtube, facebook, tiktok, snapchat">
          <input
            id={`platform-${key}`}
            name="platform"
            defaultValue={row?.platform ?? ""}
            required
            className="admin-input"
          />
        </Field>
        <Field label="Address" name={`url-${key}`} className="sm:col-span-2">
          <input
            id={`url-${key}`}
            name="url"
            type="url"
            defaultValue={row?.url ?? ""}
            required
            dir="ltr"
            placeholder="https://www.linkedin.com/company/…"
            className="admin-input"
          />
        </Field>
      </div>
      <label className="mt-3 flex cursor-pointer items-center gap-2 text-[0.82rem]">
        <input
          type="checkbox"
          name="isPublished"
          defaultChecked={row?.isPublished ?? true}
          className="size-4 accent-[var(--color-orange)]"
        />
        Shown in the footer
      </label>
      <div className="mt-4">
        <SubmitButton className="admin-btn-sm">{row ? "Save link" : "Add link"}</SubmitButton>
      </div>
    </AdminForm>
  );
}
