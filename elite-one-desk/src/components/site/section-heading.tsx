import type { ReactNode } from "react";

import { Reveal } from "./reveal";

type Props = {
  eyebrow?: string;
  title?: string;
  intro?: string;
  align?: "start" | "center";
  className?: string;
  children?: ReactNode;
  /** Renders as h1 on a page's opening section. */
  level?: 1 | 2;
};

export function SectionHeading({
  eyebrow,
  title,
  intro,
  align = "start",
  className = "",
  children,
  level = 2,
}: Props) {
  if (!eyebrow && !title && !intro && !children) return null;
  const Tag = level === 1 ? "h1" : "h2";
  return (
    <Reveal
      className={`flex flex-col gap-4 ${align === "center" ? "items-center text-center" : ""} ${className}`}
    >
      {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
      {title ? (
        <Tag className={level === 1 ? "text-[length:var(--text-h1)]" : "text-[length:var(--text-h2)]"}>
          {title}
        </Tag>
      ) : null}
      {intro ? <p className={`lede ${align === "center" ? "max-w-2xl" : "max-w-xl"}`}>{intro}</p> : null}
      {children}
    </Reveal>
  );
}
