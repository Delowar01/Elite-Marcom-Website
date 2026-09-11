import type { MediaRef } from "@/lib/media/url";
import { mediaSrc, mediaSrcSet } from "@/lib/media/url";
import type { Locale } from "@/lib/i18n/config";
import { pick } from "@/lib/i18n/config";

type Props = {
  media: MediaRef | null | undefined;
  locale: Locale;
  /** Overrides the library's alt text — use for decorative or repeated images. */
  alt?: string;
  sizes?: string;
  className?: string;
  priority?: boolean;
  /** CSS aspect-ratio; without it the intrinsic size reserves the space. */
  ratio?: string;
};

/**
 * Renders a library image against the derivatives written at upload time.
 * Width and height always come from the stored dimensions, so the box is
 * reserved before the bytes arrive and the layout never shifts.
 */
export function MediaImage({
  media,
  locale,
  alt,
  sizes = "(max-width: 768px) 100vw, 50vw",
  className,
  priority = false,
  ratio,
}: Props) {
  if (!media) return null;
  const altText = alt ?? pick(locale, media.altEn, media.altAr) ?? "";
  return (
    <img
      src={mediaSrc(media, media.derivatives?.[1] ?? undefined)}
      srcSet={mediaSrcSet(media)}
      sizes={sizes}
      width={media.width || undefined}
      height={media.height || undefined}
      alt={altText}
      className={className}
      style={ratio ? { aspectRatio: ratio, objectFit: "cover" } : undefined}
      loading={priority ? "eager" : "lazy"}
      fetchPriority={priority ? "high" : undefined}
      decoding="async"
    />
  );
}
