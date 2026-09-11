type Props = {
  /** `light` is the warm-white lockup for the navy ground. */
  variant?: "light" | "dark";
  /** Rendered height in CSS pixels; the srcset covers 1x–3x from there. */
  height?: number;
  mark?: boolean;
  className?: string;
  priority?: boolean;
};

/**
 * The lockup ships as pre-sized WebP rather than the master SVG: the artwork
 * carries a 700-path Riyadh skyline inside the monitor, which is 63 KB gzipped
 * as vector and invisible below about 200px. The masters live in brand-source/.
 */
const ASPECT = { logo: 1022 / 350, mark: 352 / 350 };

export function Logo({
  variant = "light",
  height = 44,
  mark = false,
  className,
  priority = false,
}: Props) {
  const stem = mark ? "mark" : "logo";
  const suffix = variant === "light" ? "-light" : "";
  const sizes = mark ? [128, 256, 512] : [80, 160, 320];
  const base = `/brand/${stem}${suffix}`;
  const width = Math.round(height * (mark ? ASPECT.mark : ASPECT.logo));

  return (
    <img
      src={`${base}-${sizes[1]}.webp`}
      srcSet={sizes.map((s) => `${base}-${s}.webp ${Math.round(s * (mark ? ASPECT.mark : ASPECT.logo))}w`).join(", ")}
      sizes={`${width}px`}
      width={width}
      height={height}
      alt="Elite One Desk"
      className={className}
      style={{ height, width: "auto" }}
      loading={priority ? "eager" : "lazy"}
      fetchPriority={priority ? "high" : undefined}
      decoding="async"
    />
  );
}
