"use client";

import { useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

/**
 * `prefers-reduced-motion`, but safe to branch markup on.
 *
 * The server cannot know the visitor's motion preference, so a component that
 * renders different markup for it mismatches on hydration. This returns false
 * until after mount — server and first client render agree — and then flips,
 * which React applies as an ordinary update.
 *
 * Use this when the preference changes what is rendered. For a component where
 * it only changes an animation's parameters, `useReducedMotion` directly is
 * fine: the markup is identical either way.
 */
export function useCalmMotion(): boolean {
  const reduce = useReducedMotion();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted && Boolean(reduce);
}
