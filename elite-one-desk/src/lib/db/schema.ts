/**
 * Elite One Desk — database schema.
 *
 * Two conventions run through the whole file:
 *
 *  1. Localised text is a pair of columns (`titleEn` / `titleAr`) rather than a
 *     translations table. Every localisable field is known at build time, so a
 *     pair of columns keeps the types honest and a page render to one query.
 *     Arabic is optional everywhere: an empty Arabic field falls back to
 *     English at read time (see `lib/i18n/pick.ts`), which is what lets the
 *     Arabic edition ship before it is fully translated.
 *
 *  2. Anything an editor arranges freely — a list of benefits, the fields of a
 *     homepage block — is `jsonb` validated by a Zod schema on the way in
 *     (`lib/validation`). Anything queried, filtered or joined is a column.
 */
import { relations, sql } from "drizzle-orm";
import {
  boolean,
  index,
  integer,
  jsonb,
  pgEnum,
  pgTable,
  primaryKey,
  serial,
  text,
  timestamp,
  uniqueIndex,
  varchar,
} from "drizzle-orm/pg-core";

/* -------------------------------------------------------------------------- */
/* Enums                                                                      */
/* -------------------------------------------------------------------------- */

export const roleKeyEnum = pgEnum("role_key", ["owner", "admin", "editor", "viewer"]);

export const enquiryStatusEnum = pgEnum("enquiry_status", [
  "new",
  "contacted",
  "in_progress",
  "waiting_customer",
  "completed",
  "closed",
  "spam",
]);

export const contactMethodEnum = pgEnum("contact_method", [
  "phone",
  "whatsapp",
  "email",
]);

export const pageKindEnum = pgEnum("page_kind", ["builtin", "custom"]);

export const navMenuEnum = pgEnum("nav_menu", [
  "header",
  "footer_services",
  "footer_company",
  "footer_legal",
]);

export const faqScopeEnum = pgEnum("faq_scope", ["global", "category", "service"]);

export const packageRegionEnum = pgEnum("package_region", [
  "egypt",
  "international",
  "holiday",
  "corporate",
]);

const timestamps = {
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
};

/* -------------------------------------------------------------------------- */
/* Identity, access control and audit                                          */
/* -------------------------------------------------------------------------- */

export const roles = pgTable("roles", {
  id: serial("id").primaryKey(),
  key: roleKeyEnum("key").notNull().unique(),
  name: varchar("name", { length: 64 }).notNull(),
  description: text("description").notNull().default(""),
  /** System roles cannot be renamed or deleted from the panel. */
  isSystem: boolean("is_system").notNull().default(true),
  ...timestamps,
});

export const permissions = pgTable("permissions", {
  id: serial("id").primaryKey(),
  /** Dotted key, e.g. `services.manage`. */
  key: varchar("key", { length: 64 }).notNull().unique(),
  label: varchar("label", { length: 128 }).notNull(),
  groupName: varchar("group_name", { length: 64 }).notNull().default("General"),
});

export const rolePermissions = pgTable(
  "role_permissions",
  {
    roleId: integer("role_id")
      .notNull()
      .references(() => roles.id, { onDelete: "cascade" }),
    permissionId: integer("permission_id")
      .notNull()
      .references(() => permissions.id, { onDelete: "cascade" }),
  },
  (t) => [primaryKey({ columns: [t.roleId, t.permissionId] })],
);

export const users = pgTable(
  "users",
  {
    id: serial("id").primaryKey(),
    email: varchar("email", { length: 190 }).notNull(),
    name: varchar("name", { length: 120 }).notNull(),
    /** `scrypt$N$r$p$saltB64$hashB64` — see lib/auth/password.ts. */
    passwordHash: text("password_hash").notNull(),
    roleId: integer("role_id")
      .notNull()
      .references(() => roles.id, { onDelete: "restrict" }),
    isActive: boolean("is_active").notNull().default(true),
    mustChangePassword: boolean("must_change_password").notNull().default(false),
    lastLoginAt: timestamp("last_login_at", { withTimezone: true }),
    ...timestamps,
  },
  (t) => [uniqueIndex("users_email_lower_idx").on(sql`lower(${t.email})`)],
);

export const sessions = pgTable(
  "sessions",
  {
    id: varchar("id", { length: 48 }).primaryKey(),
    userId: integer("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    /** SHA-256 of the cookie secret half; the raw value never touches the DB. */
    tokenHash: varchar("token_hash", { length: 64 }).notNull(),
    /** Double-submit CSRF token for admin mutations. */
    csrfToken: varchar("csrf_token", { length: 64 }).notNull(),
    expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
    ipHash: varchar("ip_hash", { length: 64 }).notNull().default(""),
    userAgent: varchar("user_agent", { length: 255 }).notNull().default(""),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    lastSeenAt: timestamp("last_seen_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("sessions_user_idx").on(t.userId)],
);

export const loginAttempts = pgTable(
  "login_attempts",
  {
    id: serial("id").primaryKey(),
    /** Lower-cased email, or `ip:<hash>` when the email is unknown. */
    identifier: varchar("identifier", { length: 190 }).notNull(),
    ipHash: varchar("ip_hash", { length: 64 }).notNull().default(""),
    successful: boolean("successful").notNull().default(false),
    attemptedAt: timestamp("attempted_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("login_attempts_lookup_idx").on(t.identifier, t.attemptedAt)],
);

export const activityLogs = pgTable(
  "activity_logs",
  {
    id: serial("id").primaryKey(),
    userId: integer("user_id").references(() => users.id, { onDelete: "set null" }),
    /** Actor name captured at write time so the log survives a deleted user. */
    actorName: varchar("actor_name", { length: 120 }).notNull().default("System"),
    action: varchar("action", { length: 64 }).notNull(),
    entityType: varchar("entity_type", { length: 48 }).notNull().default(""),
    entityId: varchar("entity_id", { length: 64 }).notNull().default(""),
    summary: varchar("summary", { length: 255 }).notNull().default(""),
    metadata: jsonb("metadata").$type<Record<string, unknown>>(),
    ipHash: varchar("ip_hash", { length: 64 }).notNull().default(""),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("activity_logs_created_idx").on(t.createdAt)],
);

/* -------------------------------------------------------------------------- */
/* Media                                                                       */
/* -------------------------------------------------------------------------- */

export const media = pgTable(
  "media",
  {
    id: serial("id").primaryKey(),
    /** Stored file name inside UPLOAD_DIR; the public path is /media/<name>. */
    filename: varchar("filename", { length: 190 }).notNull().unique(),
    originalName: varchar("original_name", { length: 190 }).notNull().default(""),
    mimeType: varchar("mime_type", { length: 64 }).notNull(),
    byteSize: integer("byte_size").notNull().default(0),
    width: integer("width").notNull().default(0),
    height: integer("height").notNull().default(0),
    /** Derivative widths written next to the original, e.g. [400, 800, 1600]. */
    derivatives: jsonb("derivatives").$type<number[]>().notNull().default(sql`'[]'::jsonb`),
    title: varchar("title", { length: 190 }).notNull().default(""),
    altEn: varchar("alt_en", { length: 255 }).notNull().default(""),
    altAr: varchar("alt_ar", { length: 255 }).notNull().default(""),
    folder: varchar("folder", { length: 64 }).notNull().default("general"),
    uploadedBy: integer("uploaded_by").references(() => users.id, { onDelete: "set null" }),
    ...timestamps,
  },
  (t) => [index("media_folder_idx").on(t.folder), index("media_created_idx").on(t.createdAt)],
);

/* -------------------------------------------------------------------------- */
/* Pages and the section-based homepage CMS                                    */
/* -------------------------------------------------------------------------- */

export const pages = pgTable("pages", {
  id: serial("id").primaryKey(),
  slug: varchar("slug", { length: 120 }).notNull().unique(),
  kind: pageKindEnum("kind").notNull().default("custom"),
  titleEn: varchar("title_en", { length: 190 }).notNull(),
  titleAr: varchar("title_ar", { length: 190 }).notNull().default(""),
  isPublished: boolean("is_published").notNull().default(false),
  sortOrder: integer("sort_order").notNull().default(0),
  ...timestamps,
});

export const pageSections = pgTable(
  "page_sections",
  {
    id: serial("id").primaryKey(),
    pageId: integer("page_id")
      .notNull()
      .references(() => pages.id, { onDelete: "cascade" }),
    /** One of the fixed block types in lib/cms/blocks.ts — never free markup. */
    blockType: varchar("block_type", { length: 48 }).notNull(),
    position: integer("position").notNull().default(0),
    isPublished: boolean("is_published").notNull().default(true),
    /** What the live site renders. */
    published: jsonb("published").$type<Record<string, unknown>>().notNull().default(sql`'{}'::jsonb`),
    /** Pending edits. Never rendered publicly; visible in preview mode only. */
    draft: jsonb("draft").$type<Record<string, unknown>>(),
    animation: varchar("animation", { length: 32 }).notNull().default("fade-up"),
    ...timestamps,
  },
  (t) => [index("page_sections_page_idx").on(t.pageId, t.position)],
);

/* -------------------------------------------------------------------------- */
/* Service taxonomy                                                            */
/* -------------------------------------------------------------------------- */

export const serviceCategories = pgTable("service_categories", {
  id: serial("id").primaryKey(),
  slug: varchar("slug", { length: 120 }).notNull().unique(),
  titleEn: varchar("title_en", { length: 190 }).notNull(),
  titleAr: varchar("title_ar", { length: 190 }).notNull().default(""),
  /** Short line under the title on cards and category heroes. */
  taglineEn: varchar("tagline_en", { length: 255 }).notNull().default(""),
  taglineAr: varchar("tagline_ar", { length: 255 }).notNull().default(""),
  summaryEn: text("summary_en").notNull().default(""),
  summaryAr: text("summary_ar").notNull().default(""),
  bodyEn: text("body_en").notNull().default(""),
  bodyAr: text("body_ar").notNull().default(""),
  /** Key into the in-code icon set — never raw SVG from the panel. */
  icon: varchar("icon", { length: 48 }).notNull().default("desk"),
  imageId: integer("image_id").references(() => media.id, { onDelete: "set null" }),
  ctaLabelEn: varchar("cta_label_en", { length: 64 }).notNull().default(""),
  ctaLabelAr: varchar("cta_label_ar", { length: 64 }).notNull().default(""),
  sortOrder: integer("sort_order").notNull().default(0),
  isPublished: boolean("is_published").notNull().default(true),
  ...timestamps,
});

export const serviceSubcategories = pgTable(
  "service_subcategories",
  {
    id: serial("id").primaryKey(),
    categoryId: integer("category_id")
      .notNull()
      .references(() => serviceCategories.id, { onDelete: "cascade" }),
    slug: varchar("slug", { length: 120 }).notNull(),
    titleEn: varchar("title_en", { length: 190 }).notNull(),
    titleAr: varchar("title_ar", { length: 190 }).notNull().default(""),
    summaryEn: text("summary_en").notNull().default(""),
    summaryAr: text("summary_ar").notNull().default(""),
    sortOrder: integer("sort_order").notNull().default(0),
    isPublished: boolean("is_published").notNull().default(true),
    ...timestamps,
  },
  (t) => [uniqueIndex("service_subcategories_slug_idx").on(t.categoryId, t.slug)],
);

export const services = pgTable(
  "services",
  {
    id: serial("id").primaryKey(),
    categoryId: integer("category_id")
      .notNull()
      .references(() => serviceCategories.id, { onDelete: "cascade" }),
    subcategoryId: integer("subcategory_id").references(() => serviceSubcategories.id, {
      onDelete: "set null",
    }),
    slug: varchar("slug", { length: 120 }).notNull(),
    titleEn: varchar("title_en", { length: 190 }).notNull(),
    titleAr: varchar("title_ar", { length: 190 }).notNull().default(""),
    introEn: text("intro_en").notNull().default(""),
    introAr: text("intro_ar").notNull().default(""),
    /** Sanitised rich text (p / h3 / h4 / lists / emphasis / safe links). */
    bodyEn: text("body_en").notNull().default(""),
    bodyAr: text("body_ar").notNull().default(""),
    /** Editor-ordered lists: [{ en, ar }] — see lib/validation/service.ts. */
    benefits: jsonb("benefits").$type<LocalisedItem[]>().notNull().default(sql`'[]'::jsonb`),
    audience: jsonb("audience").$type<LocalisedItem[]>().notNull().default(sql`'[]'::jsonb`),
    requirements: jsonb("requirements").$type<LocalisedItem[]>().notNull().default(sql`'[]'::jsonb`),
    processSteps: jsonb("process_steps").$type<LocalisedStep[]>().notNull().default(sql`'[]'::jsonb`),
    /** Free text, not a promise: "typically 5–10 working days", or empty. */
    timelineEn: varchar("timeline_en", { length: 190 }).notNull().default(""),
    timelineAr: varchar("timeline_ar", { length: 190 }).notNull().default(""),
    notesEn: text("notes_en").notNull().default(""),
    notesAr: text("notes_ar").notNull().default(""),
    /** Which extra fields the request form shows: travel | visa | business | iqama | general. */
    formPreset: varchar("form_preset", { length: 32 }).notNull().default("general"),
    imageId: integer("image_id").references(() => media.id, { onDelete: "set null" }),
    isFeatured: boolean("is_featured").notNull().default(false),
    isPublished: boolean("is_published").notNull().default(true),
    sortOrder: integer("sort_order").notNull().default(0),
    ...timestamps,
  },
  (t) => [
    uniqueIndex("services_slug_idx").on(t.categoryId, t.slug),
    index("services_category_idx").on(t.categoryId, t.sortOrder),
  ],
);

export type LocalisedItem = { en: string; ar: string };
export type LocalisedStep = { en: string; ar: string; detailEn: string; detailAr: string };

/* -------------------------------------------------------------------------- */
/* Travel and Egypt packages                                                   */
/* -------------------------------------------------------------------------- */

export const travelPackages = pgTable("travel_packages", {
  id: serial("id").primaryKey(),
  slug: varchar("slug", { length: 120 }).notNull().unique(),
  region: packageRegionEnum("region").notNull().default("international"),
  titleEn: varchar("title_en", { length: 190 }).notNull(),
  titleAr: varchar("title_ar", { length: 190 }).notNull().default(""),
  destinationEn: varchar("destination_en", { length: 120 }).notNull().default(""),
  destinationAr: varchar("destination_ar", { length: 120 }).notNull().default(""),
  /** Deliberately free text — "5 nights", "flexible" — never a computed price. */
  durationEn: varchar("duration_en", { length: 80 }).notNull().default(""),
  durationAr: varchar("duration_ar", { length: 80 }).notNull().default(""),
  summaryEn: text("summary_en").notNull().default(""),
  summaryAr: text("summary_ar").notNull().default(""),
  bodyEn: text("body_en").notNull().default(""),
  bodyAr: text("body_ar").notNull().default(""),
  highlights: jsonb("highlights").$type<LocalisedItem[]>().notNull().default(sql`'[]'::jsonb`),
  imageId: integer("image_id").references(() => media.id, { onDelete: "set null" }),
  isFeatured: boolean("is_featured").notNull().default(false),
  isPublished: boolean("is_published").notNull().default(true),
  sortOrder: integer("sort_order").notNull().default(0),
  ...timestamps,
});

/* -------------------------------------------------------------------------- */
/* Videos, testimonials, FAQs                                                  */
/* -------------------------------------------------------------------------- */

export const videos = pgTable("videos", {
  id: serial("id").primaryKey(),
  /** Validated 11-character YouTube id; the pasted URL is kept for reference. */
  youtubeId: varchar("youtube_id", { length: 16 }).notNull(),
  sourceUrl: varchar("source_url", { length: 255 }).notNull().default(""),
  titleEn: varchar("title_en", { length: 190 }).notNull(),
  titleAr: varchar("title_ar", { length: 190 }).notNull().default(""),
  descriptionEn: text("description_en").notNull().default(""),
  descriptionAr: text("description_ar").notNull().default(""),
  category: varchar("category", { length: 64 }).notNull().default("general"),
  /** Uploaded still. When absent the page falls back to YouTube's own poster. */
  thumbnailId: integer("thumbnail_id").references(() => media.id, { onDelete: "set null" }),
  durationLabel: varchar("duration_label", { length: 16 }).notNull().default(""),
  isFeatured: boolean("is_featured").notNull().default(false),
  isPublished: boolean("is_published").notNull().default(true),
  sortOrder: integer("sort_order").notNull().default(0),
  ...timestamps,
});

export const testimonials = pgTable("testimonials", {
  id: serial("id").primaryKey(),
  name: varchar("name", { length: 120 }).notNull(),
  company: varchar("company", { length: 120 }).notNull().default(""),
  country: varchar("country", { length: 80 }).notNull().default(""),
  quoteEn: text("quote_en").notNull().default(""),
  quoteAr: text("quote_ar").notNull().default(""),
  imageId: integer("image_id").references(() => media.id, { onDelete: "set null" }),
  /** 1–5, or null when the client did not give one. */
  rating: integer("rating"),
  isFeatured: boolean("is_featured").notNull().default(false),
  isPublished: boolean("is_published").notNull().default(false),
  sortOrder: integer("sort_order").notNull().default(0),
  ...timestamps,
});

export const faqs = pgTable(
  "faqs",
  {
    id: serial("id").primaryKey(),
    scope: faqScopeEnum("scope").notNull().default("global"),
    categoryId: integer("category_id").references(() => serviceCategories.id, {
      onDelete: "cascade",
    }),
    serviceId: integer("service_id").references(() => services.id, { onDelete: "cascade" }),
    questionEn: varchar("question_en", { length: 255 }).notNull(),
    questionAr: varchar("question_ar", { length: 255 }).notNull().default(""),
    answerEn: text("answer_en").notNull().default(""),
    answerAr: text("answer_ar").notNull().default(""),
    sortOrder: integer("sort_order").notNull().default(0),
    isPublished: boolean("is_published").notNull().default(true),
    ...timestamps,
  },
  (t) => [index("faqs_scope_idx").on(t.scope, t.categoryId, t.serviceId)],
);

/* -------------------------------------------------------------------------- */
/* Enquiries                                                                   */
/* -------------------------------------------------------------------------- */

export const enquiries = pgTable(
  "enquiries",
  {
    id: serial("id").primaryKey(),
    /** Human reference shown to the customer, e.g. EOD-26-0148. */
    reference: varchar("reference", { length: 24 }).notNull().unique(),
    name: varchar("name", { length: 120 }).notNull(),
    email: varchar("email", { length: 190 }).notNull().default(""),
    phone: varchar("phone", { length: 40 }).notNull().default(""),
    whatsapp: varchar("whatsapp", { length: 40 }).notNull().default(""),
    nationality: varchar("nationality", { length: 80 }).notNull().default(""),
    categoryId: integer("category_id").references(() => serviceCategories.id, {
      onDelete: "set null",
    }),
    serviceId: integer("service_id").references(() => services.id, { onDelete: "set null" }),
    /** Names captured at submit time so the record survives a renamed service. */
    categoryLabel: varchar("category_label", { length: 190 }).notNull().default(""),
    serviceLabel: varchar("service_label", { length: 190 }).notNull().default(""),
    message: text("message").notNull().default(""),
    /** Preset-specific answers (travel dates, business activity, …). */
    details: jsonb("details").$type<Record<string, string>>().notNull().default(sql`'{}'::jsonb`),
    preferredContact: contactMethodEnum("preferred_contact").notNull().default("whatsapp"),
    sourcePage: varchar("source_page", { length: 255 }).notNull().default(""),
    locale: varchar("locale", { length: 5 }).notNull().default("en"),
    utm: jsonb("utm").$type<Record<string, string>>().notNull().default(sql`'{}'::jsonb`),
    status: enquiryStatusEnum("status").notNull().default("new"),
    assignedTo: integer("assigned_to").references(() => users.id, { onDelete: "set null" }),
    isRead: boolean("is_read").notNull().default(false),
    ...timestamps,
  },
  (t) => [
    index("enquiries_status_idx").on(t.status, t.createdAt),
    index("enquiries_created_idx").on(t.createdAt),
  ],
);

export const enquiryNotes = pgTable(
  "enquiry_notes",
  {
    id: serial("id").primaryKey(),
    enquiryId: integer("enquiry_id")
      .notNull()
      .references(() => enquiries.id, { onDelete: "cascade" }),
    userId: integer("user_id").references(() => users.id, { onDelete: "set null" }),
    authorName: varchar("author_name", { length: 120 }).notNull().default(""),
    body: text("body").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("enquiry_notes_enquiry_idx").on(t.enquiryId)],
);

/* -------------------------------------------------------------------------- */
/* Navigation, settings, SEO, social                                           */
/* -------------------------------------------------------------------------- */

export const navigationItems = pgTable(
  "navigation_items",
  {
    id: serial("id").primaryKey(),
    menu: navMenuEnum("menu").notNull().default("header"),
    parentId: integer("parent_id"),
    labelEn: varchar("label_en", { length: 120 }).notNull(),
    labelAr: varchar("label_ar", { length: 120 }).notNull().default(""),
    /** Always a site-relative path without a language prefix, e.g. /services. */
    href: varchar("href", { length: 255 }).notNull(),
    sortOrder: integer("sort_order").notNull().default(0),
    isPublished: boolean("is_published").notNull().default(true),
    isHighlighted: boolean("is_highlighted").notNull().default(false),
    ...timestamps,
  },
  (t) => [index("navigation_menu_idx").on(t.menu, t.sortOrder)],
);

export const siteSettings = pgTable("site_settings", {
  key: varchar("key", { length: 64 }).primaryKey(),
  value: jsonb("value").$type<Record<string, unknown>>().notNull().default(sql`'{}'::jsonb`),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  updatedBy: integer("updated_by").references(() => users.id, { onDelete: "set null" }),
});

export const seoMetadata = pgTable(
  "seo_metadata",
  {
    id: serial("id").primaryKey(),
    /** page | category | service | package | video */
    entityType: varchar("entity_type", { length: 32 }).notNull(),
    /** Slug or numeric id, as text, so one table covers every entity. */
    entityKey: varchar("entity_key", { length: 190 }).notNull(),
    titleEn: varchar("title_en", { length: 190 }).notNull().default(""),
    titleAr: varchar("title_ar", { length: 190 }).notNull().default(""),
    descriptionEn: varchar("description_en", { length: 320 }).notNull().default(""),
    descriptionAr: varchar("description_ar", { length: 320 }).notNull().default(""),
    canonicalUrl: varchar("canonical_url", { length: 255 }).notNull().default(""),
    ogTitle: varchar("og_title", { length: 190 }).notNull().default(""),
    ogDescription: varchar("og_description", { length: 320 }).notNull().default(""),
    ogImageId: integer("og_image_id").references(() => media.id, { onDelete: "set null" }),
    noindex: boolean("noindex").notNull().default(false),
    ...timestamps,
  },
  (t) => [uniqueIndex("seo_entity_idx").on(t.entityType, t.entityKey)],
);

export const socialLinks = pgTable("social_links", {
  id: serial("id").primaryKey(),
  platform: varchar("platform", { length: 32 }).notNull(),
  url: varchar("url", { length: 255 }).notNull(),
  sortOrder: integer("sort_order").notNull().default(0),
  isPublished: boolean("is_published").notNull().default(true),
  ...timestamps,
});

/* -------------------------------------------------------------------------- */
/* Relations                                                                   */
/* -------------------------------------------------------------------------- */

export const rolesRelations = relations(roles, ({ many }) => ({
  users: many(users),
  rolePermissions: many(rolePermissions),
}));

export const usersRelations = relations(users, ({ one }) => ({
  role: one(roles, { fields: [users.roleId], references: [roles.id] }),
}));

export const rolePermissionsRelations = relations(rolePermissions, ({ one }) => ({
  role: one(roles, { fields: [rolePermissions.roleId], references: [roles.id] }),
  permission: one(permissions, {
    fields: [rolePermissions.permissionId],
    references: [permissions.id],
  }),
}));

export const serviceCategoriesRelations = relations(serviceCategories, ({ many, one }) => ({
  services: many(services),
  subcategories: many(serviceSubcategories),
  image: one(media, { fields: [serviceCategories.imageId], references: [media.id] }),
}));

export const serviceSubcategoriesRelations = relations(serviceSubcategories, ({ one, many }) => ({
  category: one(serviceCategories, {
    fields: [serviceSubcategories.categoryId],
    references: [serviceCategories.id],
  }),
  services: many(services),
}));

export const servicesRelations = relations(services, ({ one, many }) => ({
  category: one(serviceCategories, {
    fields: [services.categoryId],
    references: [serviceCategories.id],
  }),
  subcategory: one(serviceSubcategories, {
    fields: [services.subcategoryId],
    references: [serviceSubcategories.id],
  }),
  image: one(media, { fields: [services.imageId], references: [media.id] }),
  faqs: many(faqs),
}));

export const pagesRelations = relations(pages, ({ many }) => ({
  sections: many(pageSections),
}));

export const pageSectionsRelations = relations(pageSections, ({ one }) => ({
  page: one(pages, { fields: [pageSections.pageId], references: [pages.id] }),
}));

export const enquiriesRelations = relations(enquiries, ({ one, many }) => ({
  category: one(serviceCategories, {
    fields: [enquiries.categoryId],
    references: [serviceCategories.id],
  }),
  service: one(services, { fields: [enquiries.serviceId], references: [services.id] }),
  assignee: one(users, { fields: [enquiries.assignedTo], references: [users.id] }),
  notes: many(enquiryNotes),
}));

export const enquiryNotesRelations = relations(enquiryNotes, ({ one }) => ({
  enquiry: one(enquiries, { fields: [enquiryNotes.enquiryId], references: [enquiries.id] }),
  user: one(users, { fields: [enquiryNotes.userId], references: [users.id] }),
}));

export const videosRelations = relations(videos, ({ one }) => ({
  thumbnail: one(media, { fields: [videos.thumbnailId], references: [media.id] }),
}));

export const testimonialsRelations = relations(testimonials, ({ one }) => ({
  image: one(media, { fields: [testimonials.imageId], references: [media.id] }),
}));

export const travelPackagesRelations = relations(travelPackages, ({ one }) => ({
  image: one(media, { fields: [travelPackages.imageId], references: [media.id] }),
}));

export const faqsRelations = relations(faqs, ({ one }) => ({
  category: one(serviceCategories, {
    fields: [faqs.categoryId],
    references: [serviceCategories.id],
  }),
  service: one(services, { fields: [faqs.serviceId], references: [services.id] }),
}));
