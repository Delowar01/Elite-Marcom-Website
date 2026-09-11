import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import sharp from "sharp";
import { eq } from "drizzle-orm";

import { db } from "../../src/lib/db";
import { media } from "../../src/lib/db/schema";
import { DERIVATIVE_WIDTHS } from "../../src/lib/media/url";

/**
 * Imports the shipped artwork into the Media library.
 *
 * It writes the same files `lib/media/process.ts` would — a WebP master plus
 * the derivative widths — rather than calling it directly, because that module
 * is marked `server-only` and this runs in a plain tsx process. The two are kept
 * in step by sharing DERIVATIVE_WIDTHS and the same naming rule.
 *
 * Idempotent: a filename already in the table is reused, so re-running the seed
 * never duplicates an image or orphans the one a section points at.
 */

export type SeedImage = {
  /** File in scripts/seed/assets, without the extension. */
  name: string;
  title: string;
  altEn: string;
  altAr: string;
  folder: string;
};

export async function importSeedImages(
  images: SeedImage[],
  uploadDir: string,
): Promise<Map<string, number>> {
  const root = path.resolve(uploadDir);
  await mkdir(root, { recursive: true });
  const result = new Map<string, number>();

  for (const image of images) {
    const filename = `${image.name}.webp`;
    const [existing] = await db
      .select({ id: media.id })
      .from(media)
      .where(eq(media.filename, filename))
      .limit(1);
    if (existing) {
      result.set(image.name, existing.id);
      continue;
    }

    const source = await readFile(
      path.resolve(import.meta.dirname ?? __dirname, "assets", `${image.name}.png`),
    );
    const meta = await sharp(source).metadata();
    const width = meta.width ?? 0;
    const height = meta.height ?? 0;

    const master = await sharp(source).webp({ quality: 86, effort: 5 }).toBuffer();
    await writeFile(path.join(root, filename), master);

    const derivatives: number[] = [];
    for (const target of DERIVATIVE_WIDTHS) {
      if (target >= width) continue;
      await writeFile(
        path.join(root, `${image.name}@${target}.webp`),
        await sharp(source)
          .resize({ width: target, withoutEnlargement: true })
          .webp({ quality: 82, effort: 5 })
          .toBuffer(),
      );
      derivatives.push(target);
    }

    const [row] = await db
      .insert(media)
      .values({
        filename,
        originalName: `${image.name}.png`,
        mimeType: "image/webp",
        byteSize: master.byteLength,
        width,
        height,
        derivatives,
        title: image.title,
        altEn: image.altEn,
        altAr: image.altAr,
        folder: image.folder,
      })
      .returning({ id: media.id });
    result.set(image.name, row!.id);
  }

  return result;
}

export const SEED_IMAGES: SeedImage[] = [
  {
    name: "travel-tourism",
    title: "Travel & tourism",
    altEn: "Abstract flight routes radiating from a single hub",
    altAr: "مسارات طيران مجردة تنطلق من نقطة واحدة",
    folder: "categories",
  },
  {
    name: "business-setup",
    title: "Business setup",
    altEn: "Abstract rising columns with the tallest highlighted",
    altAr: "أعمدة متصاعدة مجردة مع إبراز الأطول",
    folder: "categories",
  },
  {
    name: "company-formation",
    title: "Company formation",
    altEn: "Nested frames resolving into a single solid block",
    altAr: "إطارات متداخلة تتقارب إلى كتلة واحدة",
    folder: "categories",
  },
  {
    name: "general-services",
    title: "General services",
    altEn: "A stack of identity documents drawn as line art",
    altAr: "مجموعة وثائق هوية مرسومة بخطوط",
    folder: "categories",
  },
  {
    name: "license-renewal",
    title: "Licence renewal",
    altEn: "A cycle of arcs closing around a completed mark",
    altAr: "أقواس دائرية تُغلق حول علامة اكتمال",
    folder: "categories",
  },
  {
    name: "government-relations",
    title: "Government relations",
    altEn: "A colonnade drawn as line art with one column highlighted",
    altAr: "صف أعمدة مرسوم بخطوط مع إبراز عمود واحد",
    folder: "categories",
  },
  {
    name: "investor-licence",
    title: "Investor journey",
    altEn: "An ascending path through milestone nodes",
    altAr: "مسار متصاعد عبر نقاط مرحلية",
    folder: "features",
  },
  {
    name: "egypt",
    title: "Egypt",
    altEn: "Pyramids, a sun disc and the river drawn as line art",
    altAr: "أهرامات وقرص الشمس والنهر مرسومة بخطوط",
    folder: "features",
  },
  {
    name: "one-desk",
    title: "One Desk",
    altEn: "Several routes converging on a single point marked with a one",
    altAr: "مسارات متعددة تتقارب إلى نقطة واحدة تحمل الرقم واحد",
    folder: "features",
  },
];
