"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Icon } from "@/components/ui/icon";
import { fieldsForPreset } from "@/lib/forms/presets";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/dictionary";
import { UTM_KEYS } from "@/lib/validation/enquiry";

export type FormCategory = { id: number; title: string };
export type FormService = { id: number; categoryId: number; title: string; preset: string };

type Props = {
  locale: Locale;
  dict: Dictionary;
  categories: FormCategory[];
  services: FormService[];
  /** Pre-selects the service on a service page; the visitor can still change it. */
  initialServiceId?: number;
  initialCategoryId?: number;
  /** Fixes the preset on a page that is about one service only. */
  forcedPreset?: string;
  compact?: boolean;
};

type FieldErrors = Record<string, string>;

export function EnquiryForm({
  locale,
  dict,
  categories,
  services,
  initialServiceId,
  initialCategoryId,
  forcedPreset,
  compact = false,
}: Props) {
  const [categoryId, setCategoryId] = useState<string>(
    initialCategoryId ? String(initialCategoryId) : "",
  );
  const [serviceId, setServiceId] = useState<string>(
    initialServiceId ? String(initialServiceId) : "",
  );
  const [sameWhatsapp, setSameWhatsapp] = useState(true);
  const [phone, setPhone] = useState("");
  const [pending, setPending] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [reference, setReference] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const successRef = useRef<HTMLDivElement>(null);
  const mountedAt = useRef(Date.now());

  const visibleServices = useMemo(
    () => (categoryId ? services.filter((s) => s.categoryId === Number(categoryId)) : services),
    [categoryId, services],
  );

  const preset =
    forcedPreset ?? services.find((s) => s.id === Number(serviceId))?.preset ?? "general";
  const extraFields = fieldsForPreset(preset);

  // Selecting a category that no longer contains the chosen service clears it,
  // so the two selects can never disagree.
  useEffect(() => {
    if (!serviceId) return;
    const found = services.find((s) => s.id === Number(serviceId));
    if (found && categoryId && found.categoryId !== Number(categoryId)) setServiceId("");
  }, [categoryId, serviceId, services]);

  useEffect(() => {
    if (reference) successRef.current?.focus();
  }, [reference]);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setErrors({});
    setFormError(null);

    const data = new FormData(event.currentTarget);
    const details: Record<string, string> = {};
    for (const field of extraFields) {
      const value = String(data.get(`detail_${field.name}`) ?? "").trim();
      if (value) details[field.name] = value;
    }

    const utm: Record<string, string> = {};
    const params = new URLSearchParams(window.location.search);
    for (const key of UTM_KEYS) {
      const value = params.get(key);
      if (value) utm[key] = value.slice(0, 190);
    }

    const phoneValue = String(data.get("phone") ?? "").trim();
    const payload = {
      name: String(data.get("name") ?? "").trim(),
      email: String(data.get("email") ?? "").trim(),
      phone: phoneValue,
      whatsapp: sameWhatsapp ? phoneValue : String(data.get("whatsapp") ?? "").trim(),
      nationality: String(data.get("nationality") ?? "").trim(),
      categoryId: categoryId ? Number(categoryId) : null,
      serviceId: serviceId ? Number(serviceId) : null,
      message: String(data.get("message") ?? "").trim(),
      preferredContact: String(data.get("preferredContact") ?? "whatsapp"),
      sourcePage: window.location.pathname,
      locale,
      details,
      utm,
      company_website: String(data.get("company_website") ?? ""),
      elapsed: Date.now() - mountedAt.current,
    };

    try {
      const response = await fetch("/api/enquiries", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = (await response.json()) as {
        ok: boolean;
        reference?: string;
        errors?: FieldErrors;
        message?: string;
      };

      if (!response.ok || !result.ok) {
        setErrors(result.errors ?? {});
        setFormError(result.message ?? dict.form.errorBody);
        // Move the reader to the first thing that needs fixing.
        const firstKey = Object.keys(result.errors ?? {})[0];
        if (firstKey) {
          formRef.current
            ?.querySelector<HTMLElement>(`[name="${firstKey}"]`)
            ?.focus({ preventScroll: false });
        }
        return;
      }
      setReference(result.reference ?? "");
      formRef.current?.reset();
    } catch {
      setFormError(dict.form.networkError);
    } finally {
      setPending(false);
    }
  }

  if (reference !== null) {
    return (
      <div
        ref={successRef}
        tabIndex={-1}
        role="status"
        className="panel flex flex-col items-start gap-4 p-7 outline-none sm:p-9"
      >
        <span
          className="flex size-12 items-center justify-center rounded-full"
          style={{ background: "color-mix(in oklab, var(--color-orange) 18%, transparent)", color: "var(--color-orange)" }}
        >
          <Icon name="check" size={24} />
        </span>
        <h3 className="text-[length:var(--text-h3)]">{dict.form.successTitle}</h3>
        <p className="text-body">{dict.form.successBody.replace("{ref}", reference)}</p>
      </div>
    );
  }

  const inputClass =
    "w-full rounded-[var(--radius-sm)] border border-line bg-[color-mix(in_oklab,var(--color-ink-900)_35%,transparent)] px-3.5 py-3 text-[0.92rem] text-strong outline-none transition-colors placeholder:text-muted focus:border-[color-mix(in_oklab,var(--color-peach)_65%,transparent)] aria-[invalid=true]:border-[#ef5350]";

  const field = (name: string, label: string, node: React.ReactNode, hint?: string) => (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={`eod-${name}`} className="text-[0.8rem] font-medium text-body">
        {label}
      </label>
      {node}
      {errors[name] ? (
        <p id={`eod-${name}-error`} role="alert" className="text-[0.78rem]" style={{ color: "#ff8a80" }}>
          {errors[name]}
        </p>
      ) : hint ? (
        <p className="text-[0.75rem] text-muted">{hint}</p>
      ) : null}
    </div>
  );

  return (
    <form ref={formRef} onSubmit={onSubmit} noValidate className={compact ? "" : "panel p-6 sm:p-8"}>
      {formError ? (
        <div
          role="alert"
          className="mb-6 rounded-[var(--radius-sm)] border p-4 text-small"
          style={{ borderColor: "#ef535066", background: "#ef535014", color: "#ffb4ad" }}
        >
          <strong className="block font-semibold">{dict.form.errorTitle}</strong>
          {formError}
        </div>
      ) : null}

      {/* Honeypot. Off-screen rather than display:none, which some bots skip. */}
      <div aria-hidden="true" className="sr-only">
        <label htmlFor="eod-company_website">Company website</label>
        <input id="eod-company_website" name="company_website" tabIndex={-1} autoComplete="off" />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {field(
          "name",
          dict.form.name,
          <input
            id="eod-name"
            name="name"
            required
            autoComplete="name"
            aria-invalid={Boolean(errors.name)}
            aria-describedby={errors.name ? "eod-name-error" : undefined}
            className={inputClass}
          />,
        )}
        {field(
          "phone",
          dict.form.phone,
          <input
            id="eod-phone"
            name="phone"
            type="tel"
            dir="ltr"
            inputMode="tel"
            autoComplete="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            aria-invalid={Boolean(errors.phone)}
            className={inputClass}
          />,
        )}
        {field(
          "email",
          dict.form.email,
          <input
            id="eod-email"
            name="email"
            type="email"
            dir="ltr"
            autoComplete="email"
            aria-invalid={Boolean(errors.email)}
            aria-describedby={errors.email ? "eod-email-error" : undefined}
            className={inputClass}
          />,
        )}

        <div className="flex flex-col gap-1.5">
          <label htmlFor="eod-whatsapp" className="text-[0.8rem] font-medium text-body">
            {dict.form.whatsapp}
          </label>
          <input
            id="eod-whatsapp"
            name="whatsapp"
            type="tel"
            dir="ltr"
            inputMode="tel"
            disabled={sameWhatsapp}
            value={sameWhatsapp ? phone : undefined}
            className={`${inputClass} disabled:opacity-55`}
          />
          <label className="mt-0.5 inline-flex items-center gap-2 text-[0.75rem] text-muted">
            <input
              type="checkbox"
              checked={sameWhatsapp}
              onChange={(e) => setSameWhatsapp(e.target.checked)}
              className="size-3.5 accent-[var(--color-orange)]"
            />
            {dict.form.whatsappSame}
          </label>
        </div>

        {categories.length ? (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="eod-categoryId" className="text-[0.8rem] font-medium text-body">
              {dict.form.category}
            </label>
            <select
              id="eod-categoryId"
              name="categoryId"
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              className={inputClass}
            >
              <option value="">{dict.form.selectCategory}</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.title}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {visibleServices.length ? (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="eod-serviceId" className="text-[0.8rem] font-medium text-body">
              {dict.form.service}
            </label>
            <select
              id="eod-serviceId"
              name="serviceId"
              value={serviceId}
              onChange={(e) => setServiceId(e.target.value)}
              className={inputClass}
            >
              <option value="">{dict.form.anyService}</option>
              {visibleServices.map((service) => (
                <option key={service.id} value={service.id}>
                  {service.title}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {extraFields.map((extra) => (
          <div
            key={extra.name}
            className={`flex flex-col gap-1.5 ${extra.half ? "" : "sm:col-span-2"}`}
          >
            <label htmlFor={`eod-detail_${extra.name}`} className="text-[0.8rem] font-medium text-body">
              {extra.label(dict)}{" "}
              <span className="text-muted">({dict.common.optional})</span>
            </label>
            {extra.type === "select" ? (
              <select id={`eod-detail_${extra.name}`} name={`detail_${extra.name}`} className={inputClass} defaultValue="">
                <option value="" />
                {extra.options?.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label(dict)}
                  </option>
                ))}
              </select>
            ) : extra.type === "textarea" ? (
              <textarea id={`eod-detail_${extra.name}`} name={`detail_${extra.name}`} rows={3} className={inputClass} />
            ) : (
              <input
                id={`eod-detail_${extra.name}`}
                name={`detail_${extra.name}`}
                type={extra.type === "number" ? "number" : extra.type === "date" ? "date" : "text"}
                min={extra.type === "number" ? 0 : undefined}
                className={inputClass}
              />
            )}
          </div>
        ))}

        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <label htmlFor="eod-message" className="text-[0.8rem] font-medium text-body">
            {dict.form.message}
          </label>
          <textarea
            id="eod-message"
            name="message"
            rows={4}
            placeholder={dict.form.messagePlaceholder}
            className={inputClass}
          />
        </div>

        <fieldset className="sm:col-span-2">
          <legend className="mb-2 text-[0.8rem] font-medium text-body">{dict.form.preferredContact}</legend>
          <div className="flex flex-wrap gap-2">
            {(["whatsapp", "phone", "email"] as const).map((method, index) => (
              <label
                key={method}
                className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-line px-3.5 py-2 text-[0.82rem] text-body transition-colors has-[:checked]:border-[var(--color-orange)] has-[:checked]:text-strong"
              >
                <input
                  type="radio"
                  name="preferredContact"
                  value={method}
                  defaultChecked={index === 0}
                  className="size-3.5 accent-[var(--color-orange)]"
                />
                {method === "whatsapp"
                  ? dict.common.whatsappUs
                  : method === "phone"
                    ? dict.common.callUs
                    : dict.common.emailUs}
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      <p className="mt-6 text-[0.75rem] text-muted">{dict.form.consent}</p>

      <button type="submit" disabled={pending} className="btn btn-primary mt-5 w-full sm:w-auto">
        {pending ? dict.form.submitting : dict.form.submit}
        {pending ? null : <Icon name="arrowRight" size={16} className="flip-rtl" />}
      </button>
    </form>
  );
}
