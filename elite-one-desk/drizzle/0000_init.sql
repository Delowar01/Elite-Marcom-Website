CREATE TYPE "public"."contact_method" AS ENUM('phone', 'whatsapp', 'email');--> statement-breakpoint
CREATE TYPE "public"."enquiry_status" AS ENUM('new', 'contacted', 'in_progress', 'waiting_customer', 'completed', 'closed', 'spam');--> statement-breakpoint
CREATE TYPE "public"."faq_scope" AS ENUM('global', 'category', 'service');--> statement-breakpoint
CREATE TYPE "public"."nav_menu" AS ENUM('header', 'footer_services', 'footer_company', 'footer_legal');--> statement-breakpoint
CREATE TYPE "public"."package_region" AS ENUM('egypt', 'international', 'holiday', 'corporate');--> statement-breakpoint
CREATE TYPE "public"."page_kind" AS ENUM('builtin', 'custom');--> statement-breakpoint
CREATE TYPE "public"."role_key" AS ENUM('owner', 'admin', 'editor', 'viewer');--> statement-breakpoint
CREATE TABLE "activity_logs" (
	"id" serial PRIMARY KEY NOT NULL,
	"user_id" integer,
	"actor_name" varchar(120) DEFAULT 'System' NOT NULL,
	"action" varchar(64) NOT NULL,
	"entity_type" varchar(48) DEFAULT '' NOT NULL,
	"entity_id" varchar(64) DEFAULT '' NOT NULL,
	"summary" varchar(255) DEFAULT '' NOT NULL,
	"metadata" jsonb,
	"ip_hash" varchar(64) DEFAULT '' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "enquiries" (
	"id" serial PRIMARY KEY NOT NULL,
	"reference" varchar(24) NOT NULL,
	"name" varchar(120) NOT NULL,
	"email" varchar(190) DEFAULT '' NOT NULL,
	"phone" varchar(40) DEFAULT '' NOT NULL,
	"whatsapp" varchar(40) DEFAULT '' NOT NULL,
	"nationality" varchar(80) DEFAULT '' NOT NULL,
	"category_id" integer,
	"service_id" integer,
	"category_label" varchar(190) DEFAULT '' NOT NULL,
	"service_label" varchar(190) DEFAULT '' NOT NULL,
	"message" text DEFAULT '' NOT NULL,
	"details" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"preferred_contact" "contact_method" DEFAULT 'whatsapp' NOT NULL,
	"source_page" varchar(255) DEFAULT '' NOT NULL,
	"locale" varchar(5) DEFAULT 'en' NOT NULL,
	"utm" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"status" "enquiry_status" DEFAULT 'new' NOT NULL,
	"assigned_to" integer,
	"is_read" boolean DEFAULT false NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "enquiries_reference_unique" UNIQUE("reference")
);
--> statement-breakpoint
CREATE TABLE "enquiry_notes" (
	"id" serial PRIMARY KEY NOT NULL,
	"enquiry_id" integer NOT NULL,
	"user_id" integer,
	"author_name" varchar(120) DEFAULT '' NOT NULL,
	"body" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "faqs" (
	"id" serial PRIMARY KEY NOT NULL,
	"scope" "faq_scope" DEFAULT 'global' NOT NULL,
	"category_id" integer,
	"service_id" integer,
	"question_en" varchar(255) NOT NULL,
	"question_ar" varchar(255) DEFAULT '' NOT NULL,
	"answer_en" text DEFAULT '' NOT NULL,
	"answer_ar" text DEFAULT '' NOT NULL,
	"sort_order" integer DEFAULT 0 NOT NULL,
	"is_published" boolean DEFAULT true NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "login_attempts" (
	"id" serial PRIMARY KEY NOT NULL,
	"identifier" varchar(190) NOT NULL,
	"ip_hash" varchar(64) DEFAULT '' NOT NULL,
	"successful" boolean DEFAULT false NOT NULL,
	"attempted_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "media" (
	"id" serial PRIMARY KEY NOT NULL,
	"filename" varchar(190) NOT NULL,
	"original_name" varchar(190) DEFAULT '' NOT NULL,
	"mime_type" varchar(64) NOT NULL,
	"byte_size" integer DEFAULT 0 NOT NULL,
	"width" integer DEFAULT 0 NOT NULL,
	"height" integer DEFAULT 0 NOT NULL,
	"derivatives" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"title" varchar(190) DEFAULT '' NOT NULL,
	"alt_en" varchar(255) DEFAULT '' NOT NULL,
	"alt_ar" varchar(255) DEFAULT '' NOT NULL,
	"folder" varchar(64) DEFAULT 'general' NOT NULL,
	"uploaded_by" integer,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "media_filename_unique" UNIQUE("filename")
);
--> statement-breakpoint
CREATE TABLE "navigation_items" (
	"id" serial PRIMARY KEY NOT NULL,
	"menu" "nav_menu" DEFAULT 'header' NOT NULL,
	"parent_id" integer,
	"label_en" varchar(120) NOT NULL,
	"label_ar" varchar(120) DEFAULT '' NOT NULL,
	"href" varchar(255) NOT NULL,
	"sort_order" integer DEFAULT 0 NOT NULL,
	"is_published" boolean DEFAULT true NOT NULL,
	"is_highlighted" boolean DEFAULT false NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "page_sections" (
	"id" serial PRIMARY KEY NOT NULL,
	"page_id" integer NOT NULL,
	"block_type" varchar(48) NOT NULL,
	"position" integer DEFAULT 0 NOT NULL,
	"is_published" boolean DEFAULT true NOT NULL,
	"published" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"draft" jsonb,
	"animation" varchar(32) DEFAULT 'fade-up' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "pages" (
	"id" serial PRIMARY KEY NOT NULL,
	"slug" varchar(120) NOT NULL,
	"kind" "page_kind" DEFAULT 'custom' NOT NULL,
	"title_en" varchar(190) NOT NULL,
	"title_ar" varchar(190) DEFAULT '' NOT NULL,
	"is_published" boolean DEFAULT false NOT NULL,
	"sort_order" integer DEFAULT 0 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "pages_slug_unique" UNIQUE("slug")
);
--> statement-breakpoint
CREATE TABLE "permissions" (
	"id" serial PRIMARY KEY NOT NULL,
	"key" varchar(64) NOT NULL,
	"label" varchar(128) NOT NULL,
	"group_name" varchar(64) DEFAULT 'General' NOT NULL,
	CONSTRAINT "permissions_key_unique" UNIQUE("key")
);
--> statement-breakpoint
CREATE TABLE "role_permissions" (
	"role_id" integer NOT NULL,
	"permission_id" integer NOT NULL,
	CONSTRAINT "role_permissions_role_id_permission_id_pk" PRIMARY KEY("role_id","permission_id")
);
--> statement-breakpoint
CREATE TABLE "roles" (
	"id" serial PRIMARY KEY NOT NULL,
	"key" "role_key" NOT NULL,
	"name" varchar(64) NOT NULL,
	"description" text DEFAULT '' NOT NULL,
	"is_system" boolean DEFAULT true NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "roles_key_unique" UNIQUE("key")
);
--> statement-breakpoint
CREATE TABLE "seo_metadata" (
	"id" serial PRIMARY KEY NOT NULL,
	"entity_type" varchar(32) NOT NULL,
	"entity_key" varchar(190) NOT NULL,
	"title_en" varchar(190) DEFAULT '' NOT NULL,
	"title_ar" varchar(190) DEFAULT '' NOT NULL,
	"description_en" varchar(320) DEFAULT '' NOT NULL,
	"description_ar" varchar(320) DEFAULT '' NOT NULL,
	"canonical_url" varchar(255) DEFAULT '' NOT NULL,
	"og_title" varchar(190) DEFAULT '' NOT NULL,
	"og_description" varchar(320) DEFAULT '' NOT NULL,
	"og_image_id" integer,
	"noindex" boolean DEFAULT false NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "service_categories" (
	"id" serial PRIMARY KEY NOT NULL,
	"slug" varchar(120) NOT NULL,
	"title_en" varchar(190) NOT NULL,
	"title_ar" varchar(190) DEFAULT '' NOT NULL,
	"tagline_en" varchar(255) DEFAULT '' NOT NULL,
	"tagline_ar" varchar(255) DEFAULT '' NOT NULL,
	"summary_en" text DEFAULT '' NOT NULL,
	"summary_ar" text DEFAULT '' NOT NULL,
	"body_en" text DEFAULT '' NOT NULL,
	"body_ar" text DEFAULT '' NOT NULL,
	"icon" varchar(48) DEFAULT 'desk' NOT NULL,
	"image_id" integer,
	"cta_label_en" varchar(64) DEFAULT '' NOT NULL,
	"cta_label_ar" varchar(64) DEFAULT '' NOT NULL,
	"sort_order" integer DEFAULT 0 NOT NULL,
	"is_published" boolean DEFAULT true NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "service_categories_slug_unique" UNIQUE("slug")
);
--> statement-breakpoint
CREATE TABLE "service_subcategories" (
	"id" serial PRIMARY KEY NOT NULL,
	"category_id" integer NOT NULL,
	"slug" varchar(120) NOT NULL,
	"title_en" varchar(190) NOT NULL,
	"title_ar" varchar(190) DEFAULT '' NOT NULL,
	"summary_en" text DEFAULT '' NOT NULL,
	"summary_ar" text DEFAULT '' NOT NULL,
	"sort_order" integer DEFAULT 0 NOT NULL,
	"is_published" boolean DEFAULT true NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "services" (
	"id" serial PRIMARY KEY NOT NULL,
	"category_id" integer NOT NULL,
	"subcategory_id" integer,
	"slug" varchar(120) NOT NULL,
	"title_en" varchar(190) NOT NULL,
	"title_ar" varchar(190) DEFAULT '' NOT NULL,
	"intro_en" text DEFAULT '' NOT NULL,
	"intro_ar" text DEFAULT '' NOT NULL,
	"body_en" text DEFAULT '' NOT NULL,
	"body_ar" text DEFAULT '' NOT NULL,
	"benefits" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"audience" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"requirements" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"process_steps" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"timeline_en" varchar(190) DEFAULT '' NOT NULL,
	"timeline_ar" varchar(190) DEFAULT '' NOT NULL,
	"notes_en" text DEFAULT '' NOT NULL,
	"notes_ar" text DEFAULT '' NOT NULL,
	"form_preset" varchar(32) DEFAULT 'general' NOT NULL,
	"image_id" integer,
	"is_featured" boolean DEFAULT false NOT NULL,
	"is_published" boolean DEFAULT true NOT NULL,
	"sort_order" integer DEFAULT 0 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "sessions" (
	"id" varchar(48) PRIMARY KEY NOT NULL,
	"user_id" integer NOT NULL,
	"token_hash" varchar(64) NOT NULL,
	"csrf_token" varchar(64) NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"ip_hash" varchar(64) DEFAULT '' NOT NULL,
	"user_agent" varchar(255) DEFAULT '' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"last_seen_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "site_settings" (
	"key" varchar(64) PRIMARY KEY NOT NULL,
	"value" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_by" integer
);
--> statement-breakpoint
CREATE TABLE "social_links" (
	"id" serial PRIMARY KEY NOT NULL,
	"platform" varchar(32) NOT NULL,
	"url" varchar(255) NOT NULL,
	"sort_order" integer DEFAULT 0 NOT NULL,
	"is_published" boolean DEFAULT true NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "testimonials" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" varchar(120) NOT NULL,
	"company" varchar(120) DEFAULT '' NOT NULL,
	"country" varchar(80) DEFAULT '' NOT NULL,
	"quote_en" text DEFAULT '' NOT NULL,
	"quote_ar" text DEFAULT '' NOT NULL,
	"image_id" integer,
	"rating" integer,
	"is_featured" boolean DEFAULT false NOT NULL,
	"is_published" boolean DEFAULT false NOT NULL,
	"sort_order" integer DEFAULT 0 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "travel_packages" (
	"id" serial PRIMARY KEY NOT NULL,
	"slug" varchar(120) NOT NULL,
	"region" "package_region" DEFAULT 'international' NOT NULL,
	"title_en" varchar(190) NOT NULL,
	"title_ar" varchar(190) DEFAULT '' NOT NULL,
	"destination_en" varchar(120) DEFAULT '' NOT NULL,
	"destination_ar" varchar(120) DEFAULT '' NOT NULL,
	"duration_en" varchar(80) DEFAULT '' NOT NULL,
	"duration_ar" varchar(80) DEFAULT '' NOT NULL,
	"summary_en" text DEFAULT '' NOT NULL,
	"summary_ar" text DEFAULT '' NOT NULL,
	"body_en" text DEFAULT '' NOT NULL,
	"body_ar" text DEFAULT '' NOT NULL,
	"highlights" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"image_id" integer,
	"is_featured" boolean DEFAULT false NOT NULL,
	"is_published" boolean DEFAULT true NOT NULL,
	"sort_order" integer DEFAULT 0 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "travel_packages_slug_unique" UNIQUE("slug")
);
--> statement-breakpoint
CREATE TABLE "users" (
	"id" serial PRIMARY KEY NOT NULL,
	"email" varchar(190) NOT NULL,
	"name" varchar(120) NOT NULL,
	"password_hash" text NOT NULL,
	"role_id" integer NOT NULL,
	"is_active" boolean DEFAULT true NOT NULL,
	"must_change_password" boolean DEFAULT false NOT NULL,
	"last_login_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "videos" (
	"id" serial PRIMARY KEY NOT NULL,
	"youtube_id" varchar(16) NOT NULL,
	"source_url" varchar(255) DEFAULT '' NOT NULL,
	"title_en" varchar(190) NOT NULL,
	"title_ar" varchar(190) DEFAULT '' NOT NULL,
	"description_en" text DEFAULT '' NOT NULL,
	"description_ar" text DEFAULT '' NOT NULL,
	"category" varchar(64) DEFAULT 'general' NOT NULL,
	"thumbnail_id" integer,
	"duration_label" varchar(16) DEFAULT '' NOT NULL,
	"is_featured" boolean DEFAULT false NOT NULL,
	"is_published" boolean DEFAULT true NOT NULL,
	"sort_order" integer DEFAULT 0 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "activity_logs" ADD CONSTRAINT "activity_logs_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "enquiries" ADD CONSTRAINT "enquiries_category_id_service_categories_id_fk" FOREIGN KEY ("category_id") REFERENCES "public"."service_categories"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "enquiries" ADD CONSTRAINT "enquiries_service_id_services_id_fk" FOREIGN KEY ("service_id") REFERENCES "public"."services"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "enquiries" ADD CONSTRAINT "enquiries_assigned_to_users_id_fk" FOREIGN KEY ("assigned_to") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "enquiry_notes" ADD CONSTRAINT "enquiry_notes_enquiry_id_enquiries_id_fk" FOREIGN KEY ("enquiry_id") REFERENCES "public"."enquiries"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "enquiry_notes" ADD CONSTRAINT "enquiry_notes_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "faqs" ADD CONSTRAINT "faqs_category_id_service_categories_id_fk" FOREIGN KEY ("category_id") REFERENCES "public"."service_categories"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "faqs" ADD CONSTRAINT "faqs_service_id_services_id_fk" FOREIGN KEY ("service_id") REFERENCES "public"."services"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "media" ADD CONSTRAINT "media_uploaded_by_users_id_fk" FOREIGN KEY ("uploaded_by") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "page_sections" ADD CONSTRAINT "page_sections_page_id_pages_id_fk" FOREIGN KEY ("page_id") REFERENCES "public"."pages"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "role_permissions" ADD CONSTRAINT "role_permissions_role_id_roles_id_fk" FOREIGN KEY ("role_id") REFERENCES "public"."roles"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "role_permissions" ADD CONSTRAINT "role_permissions_permission_id_permissions_id_fk" FOREIGN KEY ("permission_id") REFERENCES "public"."permissions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "seo_metadata" ADD CONSTRAINT "seo_metadata_og_image_id_media_id_fk" FOREIGN KEY ("og_image_id") REFERENCES "public"."media"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "service_categories" ADD CONSTRAINT "service_categories_image_id_media_id_fk" FOREIGN KEY ("image_id") REFERENCES "public"."media"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "service_subcategories" ADD CONSTRAINT "service_subcategories_category_id_service_categories_id_fk" FOREIGN KEY ("category_id") REFERENCES "public"."service_categories"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "services" ADD CONSTRAINT "services_category_id_service_categories_id_fk" FOREIGN KEY ("category_id") REFERENCES "public"."service_categories"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "services" ADD CONSTRAINT "services_subcategory_id_service_subcategories_id_fk" FOREIGN KEY ("subcategory_id") REFERENCES "public"."service_subcategories"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "services" ADD CONSTRAINT "services_image_id_media_id_fk" FOREIGN KEY ("image_id") REFERENCES "public"."media"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "sessions" ADD CONSTRAINT "sessions_user_id_users_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "site_settings" ADD CONSTRAINT "site_settings_updated_by_users_id_fk" FOREIGN KEY ("updated_by") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "testimonials" ADD CONSTRAINT "testimonials_image_id_media_id_fk" FOREIGN KEY ("image_id") REFERENCES "public"."media"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "travel_packages" ADD CONSTRAINT "travel_packages_image_id_media_id_fk" FOREIGN KEY ("image_id") REFERENCES "public"."media"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "users" ADD CONSTRAINT "users_role_id_roles_id_fk" FOREIGN KEY ("role_id") REFERENCES "public"."roles"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "videos" ADD CONSTRAINT "videos_thumbnail_id_media_id_fk" FOREIGN KEY ("thumbnail_id") REFERENCES "public"."media"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "activity_logs_created_idx" ON "activity_logs" USING btree ("created_at");--> statement-breakpoint
CREATE INDEX "enquiries_status_idx" ON "enquiries" USING btree ("status","created_at");--> statement-breakpoint
CREATE INDEX "enquiries_created_idx" ON "enquiries" USING btree ("created_at");--> statement-breakpoint
CREATE INDEX "enquiry_notes_enquiry_idx" ON "enquiry_notes" USING btree ("enquiry_id");--> statement-breakpoint
CREATE INDEX "faqs_scope_idx" ON "faqs" USING btree ("scope","category_id","service_id");--> statement-breakpoint
CREATE INDEX "login_attempts_lookup_idx" ON "login_attempts" USING btree ("identifier","attempted_at");--> statement-breakpoint
CREATE INDEX "media_folder_idx" ON "media" USING btree ("folder");--> statement-breakpoint
CREATE INDEX "media_created_idx" ON "media" USING btree ("created_at");--> statement-breakpoint
CREATE INDEX "navigation_menu_idx" ON "navigation_items" USING btree ("menu","sort_order");--> statement-breakpoint
CREATE INDEX "page_sections_page_idx" ON "page_sections" USING btree ("page_id","position");--> statement-breakpoint
CREATE UNIQUE INDEX "seo_entity_idx" ON "seo_metadata" USING btree ("entity_type","entity_key");--> statement-breakpoint
CREATE UNIQUE INDEX "service_subcategories_slug_idx" ON "service_subcategories" USING btree ("category_id","slug");--> statement-breakpoint
CREATE UNIQUE INDEX "services_slug_idx" ON "services" USING btree ("category_id","slug");--> statement-breakpoint
CREATE INDEX "services_category_idx" ON "services" USING btree ("category_id","sort_order");--> statement-breakpoint
CREATE INDEX "sessions_user_idx" ON "sessions" USING btree ("user_id");--> statement-breakpoint
CREATE UNIQUE INDEX "users_email_lower_idx" ON "users" USING btree (lower("email"));