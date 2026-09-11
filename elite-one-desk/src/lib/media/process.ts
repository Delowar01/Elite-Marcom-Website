import "server-only";

import { unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import sharp from "sharp";

import { db } from "@/lib/db";
import { media } from "@/lib/db/schema";
import { sanitizeSvg } from "./svg";
import { buildFilename, uploadRoot } from "./store";
import { DERIVATIVE_WIDTHS } from "./url";

export { DERIVATIVE_WIDTHS };

const MAX_BYTES = 10 * 1024 * 1024;
const MAX_DIMENSION = 8000;

/**
 * The declared MIME type of an upload is whatever the client said it was, so
 * the real format is read from the first bytes instead.
 */
function sniff(buffer: Buffer): "jpeg" | "png" | "webp" | "avif" | "gif" | "svg" | null {
  if (buffer.length < 12) return null;
  if (buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff) return "jpeg";
  if (buffer.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return "png";
  if (buffer.subarray(0, 4).toString("ascii") === "RIFF" && buffer.subarray(8, 12).toString("ascii") === "WEBP")
    return "webp";
  if (buffer.subarray(4, 8).toString("ascii") === "ftyp") {
    const brand = buffer.subarray(8, 12).toString("ascii");
    if (brand.startsWith("avif") || brand.startsWith("avis") || brand.startsWith("mif1")) return "avif";
  }
  if (buffer.subarray(0, 3).toString("ascii") === "GIF") return "gif";
  const head = buffer.subarray(0, 1024).toString("utf8").trimStart();
  if (head.startsWith("<?xml") || head.startsWith("<svg")) return "svg";
  return null;
}

export type ProcessResult =
  | { ok: true; id: number; filename: string }
  | { ok: false; error: string };

export type ProcessOptions = {
  originalName: string;
  folder?: string;
  title?: string;
  altEn?: string;
  altAr?: string;
  uploadedBy?: number | null;
};

/**
 * Validate, re-encode and store one upload.
 *
 * Rasters are decoded by sharp and written back out as WebP, which means the
 * stored file is one this process produced rather than one a visitor uploaded —
 * any payload hidden in the original's metadata does not survive the round
 * trip. SVG cannot be re-encoded, so it goes through the element whitelist
 * instead and is served under a locked-down CSP.
 */
export async function processUpload(
  input: ArrayBuffer | Buffer,
  options: ProcessOptions,
): Promise<ProcessResult> {
  const buffer = Buffer.isBuffer(input) ? input : Buffer.from(input);
  if (!buffer.length) return { ok: false, error: "The file was empty." };
  if (buffer.length > MAX_BYTES) {
    return { ok: false, error: `Images must be ${MAX_BYTES / 1024 / 1024} MB or smaller.` };
  }

  const kind = sniff(buffer);
  if (!kind) {
    return { ok: false, error: "That file is not a JPG, PNG, WebP, AVIF, GIF or SVG image." };
  }

  const root = await uploadRoot();
  const written: string[] = [];

  try {
    if (kind === "svg") {
      const cleaned = sanitizeSvg(buffer.toString("utf8"));
      if (!cleaned) return { ok: false, error: "That SVG could not be read safely." };
      const filename = buildFilename(options.originalName, "svg");
      await writeFile(path.join(root, filename), cleaned, "utf8");
      written.push(filename);

      // An SVG has no pixel size of its own; the viewBox is what a browser
      // scales, and a 0 here tells the renderer not to reserve a fixed box.
      const viewBox = /viewBox="([\d.\s-]+)"/.exec(cleaned)?.[1]?.trim().split(/\s+/);
      const width = viewBox?.length === 4 ? Math.round(Number(viewBox[2])) : 0;
      const height = viewBox?.length === 4 ? Math.round(Number(viewBox[3])) : 0;

      const [row] = await db
        .insert(media)
        .values({
          filename,
          originalName: options.originalName.slice(0, 190),
          mimeType: "image/svg+xml",
          byteSize: Buffer.byteLength(cleaned),
          width: Number.isFinite(width) ? width : 0,
          height: Number.isFinite(height) ? height : 0,
          derivatives: [],
          title: options.title ?? "",
          altEn: options.altEn ?? "",
          altAr: options.altAr ?? "",
          folder: options.folder || "general",
          uploadedBy: options.uploadedBy ?? null,
        })
        .returning({ id: media.id });

      return { ok: true, id: row!.id, filename };
    }

    const image = sharp(buffer, { failOn: "error", animated: false });
    const meta = await image.metadata();
    const width = meta.width ?? 0;
    const height = meta.height ?? 0;
    if (!width || !height) return { ok: false, error: "That image could not be read." };
    if (width > MAX_DIMENSION || height > MAX_DIMENSION) {
      return { ok: false, error: `Images must be ${MAX_DIMENSION}px or smaller on each side.` };
    }

    const filename = buildFilename(options.originalName, "webp");
    const stem = filename.replace(/\.webp$/, "");

    const master = await sharp(buffer, { failOn: "error", animated: false })
      .rotate() // Applies EXIF orientation, then drops the metadata with it.
      .webp({ quality: 86, effort: 5 })
      .toBuffer();
    await writeFile(path.join(root, filename), master);
    written.push(filename);

    const derivatives: number[] = [];
    for (const target of DERIVATIVE_WIDTHS) {
      if (target >= width) continue;
      const name = `${stem}@${target}.webp`;
      const resized = await sharp(buffer, { failOn: "error", animated: false })
        .rotate()
        .resize({ width: target, withoutEnlargement: true })
        .webp({ quality: 82, effort: 5 })
        .toBuffer();
      await writeFile(path.join(root, name), resized);
      written.push(name);
      derivatives.push(target);
    }

    const [row] = await db
      .insert(media)
      .values({
        filename,
        originalName: options.originalName.slice(0, 190),
        mimeType: "image/webp",
        byteSize: master.byteLength,
        width,
        height,
        derivatives,
        title: options.title ?? "",
        altEn: options.altEn ?? "",
        altAr: options.altAr ?? "",
        folder: options.folder || "general",
        uploadedBy: options.uploadedBy ?? null,
      })
      .returning({ id: media.id });

    return { ok: true, id: row!.id, filename };
  } catch (error) {
    // A half-written set of derivatives would show up later as a broken
    // srcset entry, so the whole upload is rolled back.
    await Promise.all(written.map((name) => unlink(path.join(root, name)).catch(() => {})));
    console.error("[media] upload failed", error);
    return { ok: false, error: "That image could not be processed." };
  }
}

/** Removes a row and every file it wrote. Missing files are not an error. */
export async function deleteMediaFiles(filename: string, derivatives: number[]): Promise<void> {
  const root = await uploadRoot();
  const stem = filename.replace(/\.[^.]+$/, "");
  const names = [filename, ...derivatives.map((w) => `${stem}@${w}.webp`)];
  await Promise.all(names.map((name) => unlink(path.join(root, name)).catch(() => {})));
}
