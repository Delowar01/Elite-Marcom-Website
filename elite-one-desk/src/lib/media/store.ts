import "server-only";

import { mkdir } from "node:fs/promises";
import path from "node:path";

import { getUploadDir } from "@/lib/env";

/**
 * Every uploaded byte lives under UPLOAD_DIR, which points outside the release
 * directory (§41). A deployment replaces the app and leaves this alone.
 */
export async function uploadRoot(): Promise<string> {
  const root = path.resolve(getUploadDir());
  await mkdir(root, { recursive: true });
  return root;
}

const SAFE_NAME = /^[a-z0-9][a-z0-9._@-]{0,180}$/i;

/**
 * Resolves a requested file name to an absolute path, or null. Two independent
 * checks: the name must match the pattern the uploader produces, and the
 * resolved path must still sit inside the root — so neither `../` nor a
 * symlinked name can escape.
 */
export async function resolveUpload(name: string): Promise<string | null> {
  if (!SAFE_NAME.test(name) || name.includes("..")) return null;
  const root = await uploadRoot();
  const full = path.resolve(root, name);
  if (full !== root && !full.startsWith(root + path.sep)) return null;
  return full;
}

/** `elite-desk-photo` → `elite-desk-photo-8f3a91.webp` */
export function buildFilename(original: string, extension: string): string {
  const stem = original
    .replace(/\.[^.]+$/, "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60) || "image";
  const suffix = Math.random().toString(16).slice(2, 8);
  return `${stem}-${suffix}.${extension}`;
}
