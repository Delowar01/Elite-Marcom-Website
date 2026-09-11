/** Widths written beside every raster upload and offered through srcset. */
export const DERIVATIVE_WIDTHS = [400, 800, 1600] as const;

export type MediaRef = {
  id: number;
  filename: string;
  width: number;
  height: number;
  altEn: string;
  altAr: string;
  title: string;
  derivatives: number[];
};

/**
 * Uploaded files are served by /media/<filename>, a route handler that streams
 * from UPLOAD_DIR. Derivatives are written beside the original as
 * `<stem>@<width>.webp`, so a srcset is a pure string operation with no
 * per-request work and no image optimiser in the path.
 */
export function mediaSrc(ref: Pick<MediaRef, "filename">, width?: number): string {
  if (!width) return `/media/${ref.filename}`;
  const stem = ref.filename.replace(/\.[^.]+$/, "");
  return `/media/${stem}@${width}.webp`;
}

export function mediaSrcSet(ref: MediaRef): string | undefined {
  if (!ref.derivatives?.length) return undefined;
  const entries = ref.derivatives
    .filter((w) => w < ref.width || ref.derivatives.length === 1)
    .map((w) => `${mediaSrc(ref, w)} ${w}w`);
  entries.push(`${mediaSrc(ref)} ${ref.width}w`);
  return entries.join(", ");
}
