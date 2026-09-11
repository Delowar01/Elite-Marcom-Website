/**
 * The section catalogue.
 *
 * §15 of the brief asks for "a controlled section-based visual CMS", not a page
 * builder that can destroy the design. That is exactly what this registry is:
 * an editor picks a block from this fixed list, fills in its declared fields and
 * orders it. The markup is always ours — nothing typed in the panel is ever
 * parsed as HTML except the `richtext` fields, and those go through
 * `lib/cms/sanitize.ts` on the way in.
 *
 * One registry drives three things, so they can never drift apart:
 *   · the admin form (rendered generically from `fields`)
 *   · the Zod validation on save (built from `fields`)
 *   · the renderer's prop types (`lib/cms/values.ts` reads by field name)
 */

export type FieldType =
  | "text"
  | "textarea"
  | "richtext"
  | "media"
  | "link"
  | "select"
  | "boolean"
  | "number"
  | "items";

export type ItemFieldDef = {
  name: string;
  label: string;
  type?: "text" | "textarea";
  localised?: boolean;
};

export type FieldDef = {
  name: string;
  label: string;
  type: FieldType;
  /** Stored as `{ en, ar }` and read through `pick()` at render time. */
  localised?: boolean;
  help?: string;
  placeholder?: string;
  options?: Array<{ value: string; label: string }>;
  itemFields?: ItemFieldDef[];
  /** Repeatable lists only. Keeps a section from becoming a page of its own. */
  maxItems?: number;
  rows?: number;
};

export type BlockDef = {
  type: string;
  name: string;
  description: string;
  /** `home` blocks are offered on the homepage; `any` on every page. */
  scope: "home" | "any";
  fields: FieldDef[];
};

const localisedText = (name: string, label: string, extra: Partial<FieldDef> = {}): FieldDef => ({
  name,
  label,
  type: "text",
  localised: true,
  ...extra,
});

const localisedArea = (name: string, label: string, rows = 3): FieldDef => ({
  name,
  label,
  type: "textarea",
  localised: true,
  rows,
});

const ctaFields = (prefix = "", label = "Call to action"): FieldDef[] => [
  localisedText(`${prefix}CtaLabel`, `${label} — button text`),
  {
    name: `${prefix}CtaHref`,
    label: `${label} — link`,
    type: "link",
    placeholder: "/contact",
    help: "A site path such as /services/business-setup, or a full https:// address.",
  },
];

const ANIMATION_PRESETS = [
  { value: "fade-up", label: "Fade up" },
  { value: "fade", label: "Fade only" },
  { value: "slide-in", label: "Slide in from the leading edge" },
  { value: "scale-in", label: "Scale in" },
  { value: "none", label: "No animation" },
] as const;

export const ANIMATIONS = ANIMATION_PRESETS;

export const BLOCKS: BlockDef[] = [
  {
    type: "hero",
    name: "Hero",
    description: "The opening screen: rotating service words, headline and the two main calls to action.",
    scope: "home",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      {
        name: "words",
        label: "Rotating words",
        type: "items",
        maxItems: 6,
        help: "Animated one after another above the headline. Three or four reads best.",
        itemFields: [{ name: "label", label: "Word", localised: true }],
      },
      localisedText("headline", "Headline"),
      localisedArea("lead", "Supporting sentence", 3),
      ...ctaFields("primary", "Primary"),
      ...ctaFields("secondary", "Secondary"),
      { name: "backgroundImage", label: "Background image", type: "media", help: "Optional. The animated composition shows through it." },
    ],
  },
  {
    type: "quick-links",
    name: "Quick service navigation",
    description: "The row of direct links under the hero — plan a trip, investor licence, Iqama and so on.",
    scope: "home",
    fields: [
      localisedText("title", "Title"),
      localisedArea("intro", "Intro", 2),
      {
        name: "links",
        label: "Links",
        type: "items",
        maxItems: 10,
        itemFields: [
          { name: "label", label: "Label", localised: true },
          { name: "href", label: "Link" },
          { name: "icon", label: "Icon key", type: "text" },
        ],
      },
    ],
  },
  {
    type: "one-desk",
    name: "One Desk concept",
    description: "The animated explanation that several service paths converge on one point of contact.",
    scope: "home",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      localisedArea("body", "Body", 4),
      {
        name: "paths",
        label: "Incoming paths",
        type: "items",
        maxItems: 6,
        help: "Each becomes a line converging on the desk. Four to six works best.",
        itemFields: [{ name: "label", label: "Label", localised: true }],
      },
      ...ctaFields("", "Call to action"),
    ],
  },
  {
    type: "service-grid",
    name: "Main services",
    description: "The six core categories, drawn live from Service Categories.",
    scope: "home",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      localisedArea("intro", "Intro", 3),
      { name: "limit", label: "How many to show", type: "number", help: "0 shows every published category." },
      { name: "showCounts", label: "Show the number of services in each category", type: "boolean" },
    ],
  },
  {
    type: "featured-service",
    name: "Featured service (Investor Licence)",
    description: "A full-width feature for one strategically important service.",
    scope: "any",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      localisedArea("body", "Body", 4),
      {
        name: "points",
        label: "What is included",
        type: "items",
        maxItems: 8,
        itemFields: [{ name: "label", label: "Item", localised: true }],
      },
      ...ctaFields("", "Call to action"),
      { name: "image", label: "Image", type: "media" },
    ],
  },
  {
    type: "travel-feature",
    name: "Travel experience",
    description: "The Travel & Tourism feature area with its list of capabilities.",
    scope: "any",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      localisedArea("body", "Body", 3),
      {
        name: "capabilities",
        label: "Capabilities",
        type: "items",
        maxItems: 12,
        itemFields: [{ name: "label", label: "Label", localised: true }],
      },
      ...ctaFields("", "Call to action"),
      { name: "image", label: "Image", type: "media" },
    ],
  },
  {
    type: "egypt-feature",
    name: "Egypt destination feature",
    description: "Discover Egypt — destinations, packages and the custom-package request.",
    scope: "any",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      localisedArea("body", "Body", 3),
      {
        name: "destinations",
        label: "Destinations",
        type: "items",
        maxItems: 12,
        itemFields: [
          { name: "label", label: "Name", localised: true },
          { name: "note", label: "Short note", localised: true },
        ],
      },
      ...ctaFields("primary", "Primary"),
      ...ctaFields("secondary", "Secondary"),
      { name: "image", label: "Image", type: "media" },
    ],
  },
  {
    type: "packages-grid",
    name: "Package grid",
    description: "Travel or Egypt packages drawn live from the Packages screen.",
    scope: "any",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      localisedArea("intro", "Intro", 2),
      {
        name: "region",
        label: "Which packages",
        type: "select",
        options: [
          { value: "", label: "All regions" },
          { value: "egypt", label: "Egypt" },
          { value: "international", label: "International" },
          { value: "holiday", label: "Holiday" },
          { value: "corporate", label: "Corporate" },
        ],
      },
      { name: "limit", label: "How many to show", type: "number" },
    ],
  },
  {
    type: "video-showcase",
    name: "Video showcase",
    description: "Poster-first YouTube gallery. Nothing loads from YouTube until a visitor presses play.",
    scope: "any",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      localisedArea("intro", "Intro", 2),
      { name: "category", label: "Only this category", type: "text", help: "Leave empty for all published videos." },
      { name: "limit", label: "How many to show", type: "number" },
    ],
  },
  {
    type: "process",
    name: "How it works",
    description: "The numbered path from choosing a service to completion.",
    scope: "any",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      {
        name: "steps",
        label: "Steps",
        type: "items",
        maxItems: 8,
        itemFields: [
          { name: "label", label: "Step title", localised: true },
          { name: "text", label: "Step description", type: "textarea", localised: true },
        ],
      },
    ],
  },
  {
    type: "why-us",
    name: "Why Elite One Desk",
    description: "The trust section. Keep every line to something the business can stand behind.",
    scope: "any",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      localisedArea("intro", "Intro", 2),
      {
        name: "points",
        label: "Points",
        type: "items",
        maxItems: 8,
        itemFields: [
          { name: "label", label: "Title", localised: true },
          { name: "text", label: "Description", type: "textarea", localised: true },
        ],
      },
    ],
  },
  {
    type: "stats",
    name: "Statistics",
    description: "Counters. Stays hidden until real figures are entered — never publish a number you cannot evidence.",
    scope: "any",
    fields: [
      localisedText("title", "Title"),
      {
        name: "items",
        label: "Figures",
        type: "items",
        maxItems: 4,
        itemFields: [
          { name: "value", label: "Figure" },
          { name: "label", label: "Label", localised: true },
        ],
      },
    ],
  },
  {
    type: "testimonials",
    name: "Testimonials",
    description: "Published testimonials, featured ones first.",
    scope: "any",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      { name: "limit", label: "How many to show", type: "number" },
    ],
  },
  {
    type: "faq",
    name: "FAQ",
    description: "Questions from the FAQ screen. Choose global questions or one category's.",
    scope: "any",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      {
        name: "scope",
        label: "Which questions",
        type: "select",
        options: [
          { value: "global", label: "Global questions" },
          { value: "all", label: "Everything published" },
        ],
      },
      { name: "limit", label: "How many to show", type: "number" },
    ],
  },
  {
    type: "final-cta",
    name: "Closing call to action",
    description: "The large closing panel with the request and WhatsApp buttons.",
    scope: "any",
    fields: [
      localisedText("title", "Title"),
      localisedArea("body", "Body", 3),
      ...ctaFields("primary", "Primary"),
      { name: "showWhatsapp", label: "Show the WhatsApp button", type: "boolean" },
    ],
  },
  {
    type: "page-hero",
    name: "Page hero",
    description: "A compact hero for an inner page.",
    scope: "any",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      localisedArea("lead", "Lead paragraph", 3),
      { name: "backgroundImage", label: "Background image", type: "media" },
    ],
  },
  {
    type: "rich-text",
    name: "Rich text",
    description: "A column of formatted text — headings, paragraphs, lists and links.",
    scope: "any",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      { name: "body", label: "Body", type: "richtext", localised: true },
    ],
  },
  {
    type: "image-text",
    name: "Image and text",
    description: "A picture beside a column of text, with an optional button.",
    scope: "any",
    fields: [
      localisedText("eyebrow", "Eyebrow"),
      localisedText("title", "Title"),
      { name: "body", label: "Body", type: "richtext", localised: true },
      { name: "image", label: "Image", type: "media" },
      {
        name: "imageSide",
        label: "Image position",
        type: "select",
        options: [
          { value: "start", label: "Leading edge (left in English, right in Arabic)" },
          { value: "end", label: "Trailing edge" },
        ],
      },
      ...ctaFields("", "Call to action"),
    ],
  },
  {
    type: "contact-details",
    name: "Contact details",
    description: "Address, phone, email, hours and the map — all read from Contact settings.",
    scope: "any",
    fields: [
      localisedText("title", "Title"),
      localisedArea("intro", "Intro", 2),
      { name: "showMap", label: "Show the map", type: "boolean" },
      { name: "showForm", label: "Show the enquiry form", type: "boolean" },
    ],
  },
];

export const BLOCK_MAP = new Map(BLOCKS.map((b) => [b.type, b]));

export const getBlock = (type: string): BlockDef | undefined => BLOCK_MAP.get(type);

export const blocksForPage = (slug: string): BlockDef[] =>
  BLOCKS.filter((b) => b.scope === "any" || slug === "home");
