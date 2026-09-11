"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";

import { useCalmMotion } from "./use-calm-motion";

/**
 * The rotating service word in the headline.
 *
 * The box is sized by a stack of every word rendered invisibly, so the line
 * never reflows as the word changes — a headline that jumps by a few pixels
 * every two seconds is the cheapest way to make a premium page feel unfinished.
 * With reduced motion it simply prints the first word and stops.
 */
export function HeroWords({ words, interval = 2400 }: { words: string[]; interval?: number }) {
  const reduce = useCalmMotion();
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (reduce || words.length < 2) return;
    const timer = setInterval(() => setIndex((i) => (i + 1) % words.length), interval);
    return () => clearInterval(timer);
  }, [interval, reduce, words.length]);

  if (!words.length) return null;
  // A single word needs none of the machinery below, and that is a decision the
  // server can make too — `words` is a prop.
  if (words.length === 1) {
    return <span style={{ color: "var(--color-orange)" }}>{words[0]}</span>;
  }

  return (
    <span className="relative inline-grid overflow-hidden align-bottom">
      {/* Reserves the widest word's box without ever being seen or read. */}
      <span aria-hidden className="invisible col-start-1 row-start-1 grid">
        {words.map((word) => (
          <span key={word} className="col-start-1 row-start-1 whitespace-nowrap">
            {word}
          </span>
        ))}
      </span>
      <span className="col-start-1 row-start-1 grid">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={words[index]}
            initial={{ y: "0.9em", opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: "-0.9em", opacity: 0 }}
            transition={{ duration: 0.52, ease: [0.16, 1, 0.3, 1] }}
            className="col-start-1 row-start-1 whitespace-nowrap"
            style={{ color: "var(--color-orange)" }}
          >
            {words[index]}
          </motion.span>
        </AnimatePresence>
      </span>
      <span className="sr-only">{words.join(", ")}</span>
    </span>
  );
}
