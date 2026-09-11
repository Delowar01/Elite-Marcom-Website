/** Environment access, validated once so a missing value fails loudly at boot. */
const required = (name: string, value: string | undefined): string => {
  if (!value || !value.trim()) {
    throw new Error(
      `Missing required environment variable ${name}. Copy .env.example to .env and fill it in.`,
    );
  }
  return value.trim();
};

export const isProduction = process.env.NODE_ENV === "production";

/** Trailing slashes are stripped so `${siteUrl}${path}` is always well formed. */
export const siteUrl = (process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000").replace(
  /\/+$/,
  "",
);

export const getDatabaseUrl = () => required("DATABASE_URL", process.env.DATABASE_URL);

/**
 * Signs session cookies, preview tokens and the IP hash pepper. A short secret
 * is refused rather than silently weakening every derived value.
 */
export const getAuthSecret = () => {
  const secret = required("AUTH_SECRET", process.env.AUTH_SECRET);
  if (secret.length < 32) {
    throw new Error("AUTH_SECRET must be at least 32 characters. Generate one with `openssl rand -base64 48`.");
  }
  return secret;
};

/**
 * Uploads live outside the build output on purpose: a deployment replaces the
 * app directory, and anything inside it would go with the old release.
 */
export const getUploadDir = () =>
  (process.env.UPLOAD_DIR || (isProduction ? "" : ".data/uploads")).trim() ||
  (() => {
    throw new Error("UPLOAD_DIR must be set in production so media survives a deployment.");
  })();

export const adminAllowedOrigins = (process.env.ADMIN_ALLOWED_ORIGINS || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);
