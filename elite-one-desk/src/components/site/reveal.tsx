"use client";

import { useEffect, useRef, useState, type ElementType, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  as?: ElementType;
  /** Milliseconds after the element enters the viewport. */
  delay?: number;
  variant?: "fade-up" | "fade" | "slide-in" | "scale-in" | "none";
  className?: string;
  /** Staggers direct children instead of moving the wrapper itself. */
  stagger?: number;
};

const VARIANT_CLASS: Record<string, string> = {
  "fade-up": "reveal",
  fade: "reveal",
  "slide-in": "reveal reveal-left",
  "scale-in": "reveal reveal-scale",
  none: "",
};

/**
 * Scroll reveal built on IntersectionObserver and two CSS classes rather than a
 * motion library: it is a few hundred bytes, it runs off the compositor, and it
 * fires once. The element is visible in its resting state, so a visitor with no
 * JavaScript — or a crawler — sees the finished page, never an empty one.
 */
export function Reveal({
  children,
  as: Tag = "div",
  delay = 0,
  variant = "fade-up",
  className = "",
  stagger,
}: Props) {
  const ref = useRef<HTMLElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || variant === "none") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setShown(true);
            observer.disconnect();
          }
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [variant]);

  const classes = [VARIANT_CLASS[variant] ?? "reveal", className].filter(Boolean).join(" ");
  const style: React.CSSProperties & Record<string, string | number> = {
    ["--reveal-delay"]: `${delay}ms`,
  };
  if (stagger) style[["--reveal-stagger"] as unknown as string] = `${stagger}ms`;

  return (
    <Tag
      ref={ref as never}
      className={classes}
      data-shown={shown ? "true" : "false"}
      style={style}
    >
      {children}
    </Tag>
  );
}

/**
 * Convenience wrapper for lists: each child gets its own observer-free delay,
 * so a grid animates in sequence from one parent observer.
 */
export function RevealGroup({
  children,
  step = 70,
  variant = "fade-up",
  className = "",
}: {
  children: ReactNode[];
  step?: number;
  variant?: Props["variant"];
  className?: string;
}) {
  return (
    <>
      {children.map((child, index) => (
        <Reveal key={index} delay={index * step} variant={variant} className={className}>
          {child}
        </Reveal>
      ))}
    </>
  );
}
