import type { Dictionary } from "@/lib/i18n/dictionary";

/**
 * Service request forms adapt to what is being asked for (§19). The extra
 * fields live here rather than in each page so the public form, the admin
 * detail view and the CSV export all read the same list — a preset that gains a
 * field shows up in all three at once.
 *
 * Deliberately nothing sensitive: no passport numbers, no document uploads, no
 * identifiers. A public form is the wrong place to collect them.
 */
export type PresetField = {
  name: string;
  label: (d: Dictionary) => string;
  type: "text" | "date" | "number" | "select" | "textarea";
  options?: Array<{ value: string; label: (d: Dictionary) => string }>;
  half?: boolean;
};

export type PresetKey = "general" | "travel" | "visa" | "business" | "iqama";

const yesNo: PresetField["options"] = [
  { value: "yes", label: (d) => d.form.yes },
  { value: "no", label: (d) => d.form.no },
  { value: "unsure", label: (d) => d.form.notSure },
];

export const FORM_PRESETS: Record<PresetKey, PresetField[]> = {
  general: [],
  travel: [
    { name: "destination", label: (d) => d.form.destination, type: "text", half: true },
    { name: "departureCity", label: (d) => d.form.departureCity, type: "text", half: true },
    { name: "travelDates", label: (d) => d.form.travelDates, type: "text", half: true },
    { name: "budget", label: (d) => d.form.budget, type: "text", half: true },
    { name: "adults", label: (d) => d.form.adults, type: "number", half: true },
    { name: "children", label: (d) => d.form.children, type: "number", half: true },
  ],
  visa: [
    { name: "destinationCountry", label: (d) => d.form.destinationCountry, type: "text", half: true },
    { name: "nationality", label: (d) => d.form.nationality, type: "text", half: true },
    { name: "purpose", label: (d) => d.form.purpose, type: "text", half: true },
    { name: "travelDate", label: (d) => d.form.travelDate, type: "date", half: true },
  ],
  business: [
    { name: "nationality", label: (d) => d.form.nationality, type: "text", half: true },
    { name: "businessActivity", label: (d) => d.form.businessActivity, type: "text", half: true },
    { name: "companyStatus", label: (d) => d.form.companyStatus, type: "text", half: true },
    {
      name: "investorLicence",
      label: (d) => d.form.investorLicenceNeeded,
      type: "select",
      options: yesNo,
      half: true,
    },
  ],
  iqama: [
    { name: "serviceRequired", label: (d) => d.form.serviceRequired, type: "text", half: true },
    { name: "employees", label: (d) => d.form.employees, type: "number", half: true },
  ],
};

export const PRESET_KEYS = Object.keys(FORM_PRESETS) as PresetKey[];

export const isPresetKey = (value: string): value is PresetKey =>
  (PRESET_KEYS as string[]).includes(value);

export const fieldsForPreset = (preset: string): PresetField[] =>
  FORM_PRESETS[isPresetKey(preset) ? preset : "general"];
