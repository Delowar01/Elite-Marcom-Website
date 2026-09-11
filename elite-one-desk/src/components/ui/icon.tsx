import type { SVGProps } from "react";

/**
 * One stroke-based icon set, drawn inline. A fixed set keeps the visual
 * language consistent and means the panel stores an icon *key* rather than
 * markup — an editor picks from this list and nothing they type is ever
 * rendered as SVG.
 */
const PATHS: Record<string, React.ReactNode> = {
  plane: <path d="M3.5 13.5 21 4l-4.2 9.5L21 20l-4.3-1.6-3.4 2.9-.8-4.7-4.6-1.2 3.1-2.6-7.5-.3Z" />,
  globe: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.6 2.7 2.6 15.3 0 18-2.6-2.7-2.6-15.3 0-18Z" />
    </>
  ),
  passport: (
    <>
      <rect x="4" y="2.5" width="16" height="19" rx="2.5" />
      <circle cx="12" cy="10" r="3" />
      <path d="M8.5 17.5h7" />
    </>
  ),
  briefcase: (
    <>
      <rect x="2.5" y="7" width="19" height="13" rx="2.5" />
      <path d="M8.5 7V5.2A1.7 1.7 0 0 1 10.2 3.5h3.6A1.7 1.7 0 0 1 15.5 5.2V7M2.5 12.5h19" />
    </>
  ),
  building: (
    <>
      <path d="M4 21V5.5A1.5 1.5 0 0 1 5.5 4h7A1.5 1.5 0 0 1 14 5.5V21" />
      <path d="M14 10h4.5A1.5 1.5 0 0 1 20 11.5V21M2.5 21h19M7 8h4M7 12h4M7 16h4M17 14h.01M17 17.5h.01" />
    </>
  ),
  idCard: (
    <>
      <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
      <circle cx="8.5" cy="11" r="2" />
      <path d="M5.5 16c.6-1.6 1.7-2.4 3-2.4s2.4.8 3 2.4M14.5 10h4M14.5 13.5h4" />
    </>
  ),
  refresh: (
    <>
      <path d="M20.5 12a8.5 8.5 0 1 1-2.6-6.1" />
      <path d="M20.5 4v5h-5" />
    </>
  ),
  landmark: (
    <>
      <path d="M3 9.5 12 4l9 5.5M5 10v8M9.5 10v8M14.5 10v8M19 10v8M2.5 21h19" />
    </>
  ),
  desk: (
    <>
      <rect x="3" y="4.5" width="18" height="11" rx="2" />
      <path d="M9 19.5h6M12 15.5v4" />
    </>
  ),
  pyramid: (
    <>
      <path d="M12 3.5 22 20H2Z" />
      <path d="m12 3.5-3.4 16.5M12 3.5l3.4 16.5" />
    </>
  ),
  ship: (
    <>
      <path d="M3 18.5c1.6 0 1.6 1.5 3.2 1.5s1.6-1.5 3.3-1.5 1.6 1.5 3.2 1.5 1.7-1.5 3.3-1.5 1.6 1.5 3.2 1.5" />
      <path d="M4.5 15 6 9.5h12L19.5 15M12 9.5V5M9 5h6" />
    </>
  ),
  hotel: (
    <>
      <path d="M3 20V5.5A1.5 1.5 0 0 1 4.5 4h15A1.5 1.5 0 0 1 21 5.5V20M2 20h20" />
      <path d="M7 8h3M14 8h3M7 12h3M14 12h3M10 20v-3.5h4V20" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3 20 6v5.5c0 4.6-3.2 7.9-8 9.5-4.8-1.6-8-4.9-8-9.5V6Z" />
      <path d="m9 12 2.2 2.2L15.5 10" />
    </>
  ),
  phone: (
    <path d="M6.2 3.5h2.9l1.5 3.7-1.9 1.4a11.6 11.6 0 0 0 5.7 5.7l1.4-1.9 3.7 1.5v2.9a2 2 0 0 1-2.2 2 17.8 17.8 0 0 1-15-15 2 2 0 0 1 2-2.3Z" />
  ),
  mail: (
    <>
      <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
      <path d="m3.5 7 8.5 6 8.5-6" />
    </>
  ),
  whatsapp: (
    <path d="M3.5 20.5 4.9 16a8 8 0 1 1 3.1 3.1ZM9 8.5c-.3 0-.6.1-.8.4-.3.3-.9.9-.9 2.1s.9 2.4 1.1 2.6c1 1.4 2.3 2.2 3.9 2.7 1 .3 1.4.2 1.9.1.6-.1 1.4-.6 1.6-1.2.2-.6.2-1.1.1-1.2l-.9-.5-1.1-.5c-.2 0-.4 0-.5.2l-.6.8c-.1.2-.3.2-.5.1a6.3 6.3 0 0 1-2.9-2.6c-.1-.2 0-.4.1-.5l.4-.5c.1-.2.1-.3 0-.5l-.7-1.4c-.1-.2-.2-.2-.4-.2Z" />
  ),
  arrowRight: <path d="M4 12h15m-6-6 6 6-6 6" />,
  arrowUpRight: <path d="M7 17 17 7M8.5 7H17v8.5" />,
  chevronDown: <path d="m6 9.5 6 6 6-6" />,
  chevronRight: <path d="m9.5 6 6 6-6 6" />,
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m20 20-4.2-4.2" />
    </>
  ),
  menu: <path d="M3.5 7h17M3.5 12h17M3.5 17h17" />,
  close: <path d="m5.5 5.5 13 13M18.5 5.5l-13 13" />,
  play: <path d="M8 5.5 19 12 8 18.5Z" />,
  quote: (
    <path d="M9.5 6c-2.8 1-4.5 3.3-4.5 6.4V18h5.5v-5.5H7.4c0-1.9.8-3 2.6-3.7Zm9 0c-2.8 1-4.5 3.3-4.5 6.4V18h5.5v-5.5h-3.1c0-1.9.8-3 2.6-3.7Z" />
  ),
  check: <path d="m5 12.5 4.5 4.5L19 7" />,
  star: <path d="m12 3.8 2.6 5.4 5.9.8-4.3 4.2 1 5.9-5.2-2.8-5.2 2.8 1-5.9L3.5 10l5.9-.8Z" />,
  mapPin: (
    <>
      <path d="M12 21c4.2-4.3 6.3-7.6 6.3-10.2A6.3 6.3 0 0 0 5.7 10.8C5.7 13.4 7.8 16.7 12 21Z" />
      <circle cx="12" cy="10.6" r="2.4" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 1.8" />
    </>
  ),
  sparkle: <path d="M12 3.5 13.7 9l5.5 1.7-5.5 1.7L12 18l-1.7-5.6L4.8 10.7 10.3 9Z" />,
  route: (
    <>
      <circle cx="6" cy="18" r="2.5" />
      <circle cx="18" cy="6" r="2.5" />
      <path d="M8.5 18h5a4 4 0 0 0 0-8h-3a4 4 0 0 1 0-8" />
    </>
  ),
  layers: <path d="m12 3.5 8.5 4.2L12 12 3.5 7.7Zm8.5 8.3L12 16l-8.5-4.2m17 4.5L12 20.5l-8.5-4.2" />,
  users: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3 19.5c.8-3 3.2-4.6 6-4.6s5.2 1.6 6 4.6M16 5.2a3.2 3.2 0 0 1 0 5.6M17.5 15.4c2 .7 3.3 2.1 3.9 4.1" />
    </>
  ),
  eye: (
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  eyeOff: (
    <>
      <path d="M9.9 5.8A8.9 8.9 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-3.2 4M6.4 7.6A16.7 16.7 0 0 0 2.5 12S6 18.5 12 18.5c1.3 0 2.5-.3 3.5-.8" />
      <path d="M10 10a2.8 2.8 0 0 0 4 4M3.5 3.5l17 17" />
    </>
  ),
  trash: (
    <>
      <path d="M4 6.5h16M9.5 6.5V4.8A1.3 1.3 0 0 1 10.8 3.5h2.4a1.3 1.3 0 0 1 1.3 1.3v1.7" />
      <path d="M6.5 6.5 7.4 20a1.5 1.5 0 0 0 1.5 1.4h6.2a1.5 1.5 0 0 0 1.5-1.4l.9-13.5M10 10.5v6.5M14 10.5v6.5" />
    </>
  ),
  fileText: (
    <>
      <path d="M13.5 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5Z" />
      <path d="M13.5 3v5.5H19M8.5 13h7M8.5 16.5h5" />
    </>
  ),
};

export type IconName = keyof typeof PATHS;
export const ICON_NAMES = Object.keys(PATHS) as IconName[];

type Props = SVGProps<SVGSVGElement> & { name: string; size?: number };

export function Icon({ name, size = 24, ...rest }: Props) {
  const path = PATHS[name] ?? PATHS.sparkle;
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {path}
    </svg>
  );
}
