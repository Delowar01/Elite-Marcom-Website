/**
 * The permission catalogue. Roles are collections of these keys; every server
 * mutation names the key it needs, so hiding a button is never the control.
 */
export const PERMISSIONS = [
  { key: "dashboard.view", label: "View dashboard", group: "General" },
  { key: "enquiries.view", label: "View enquiries", group: "Enquiries" },
  { key: "enquiries.manage", label: "Update enquiries, notes and status", group: "Enquiries" },
  { key: "enquiries.export", label: "Export enquiries", group: "Enquiries" },
  { key: "content.view", label: "View pages and sections", group: "Content" },
  { key: "content.manage", label: "Edit and publish pages and sections", group: "Content" },
  { key: "services.manage", label: "Manage service categories and services", group: "Content" },
  { key: "packages.manage", label: "Manage travel and Egypt packages", group: "Content" },
  { key: "videos.manage", label: "Manage the video showcase", group: "Content" },
  { key: "testimonials.manage", label: "Manage testimonials", group: "Content" },
  { key: "faqs.manage", label: "Manage FAQs", group: "Content" },
  { key: "media.manage", label: "Upload and delete media", group: "Content" },
  { key: "navigation.manage", label: "Manage navigation and footer", group: "Site" },
  { key: "seo.manage", label: "Manage SEO metadata", group: "Site" },
  { key: "settings.manage", label: "Manage site settings and contact details", group: "Site" },
  { key: "analytics.manage", label: "Manage analytics configuration", group: "Site" },
  { key: "users.manage", label: "Manage users", group: "Security" },
  { key: "roles.manage", label: "Change role permissions", group: "Security" },
  { key: "activity.view", label: "View the activity log", group: "Security" },
] as const;

export type PermissionKey = (typeof PERMISSIONS)[number]["key"];

const ALL = PERMISSIONS.map((p) => p.key) as PermissionKey[];

const EDITOR: PermissionKey[] = [
  "dashboard.view",
  "enquiries.view",
  "content.view",
  "content.manage",
  "services.manage",
  "packages.manage",
  "videos.manage",
  "testimonials.manage",
  "faqs.manage",
  "media.manage",
  "seo.manage",
];

const VIEWER: PermissionKey[] = ["dashboard.view", "enquiries.view", "content.view"];

/**
 * Admin holds everything except `roles.manage` — rewriting what a role may do
 * is the owner's call. Guarding owner *accounts* is separate and lives in
 * `lib/auth/guard.ts`, because it is about the target row, not the permission.
 */
export const ROLE_DEFAULTS: Record<string, PermissionKey[]> = {
  owner: ALL,
  admin: ALL.filter((k) => k !== "roles.manage"),
  editor: EDITOR,
  viewer: VIEWER,
};

export const ROLE_LABELS: Record<string, { name: string; description: string }> = {
  owner: { name: "Owner", description: "Full access, including users, roles and security." },
  admin: {
    name: "Admin",
    description: "Everything except changing what each role is allowed to do.",
  },
  editor: {
    name: "Editor",
    description: "Content, services, packages, media and SEO. Reads enquiries.",
  },
  viewer: { name: "Viewer", description: "Read-only access to the dashboard and enquiries." },
};
