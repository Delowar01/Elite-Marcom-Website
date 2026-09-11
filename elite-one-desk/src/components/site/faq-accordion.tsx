"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useId, useState } from "react";

import { Icon } from "@/components/ui/icon";

export type FaqEntry = { id: number; question: string; answer: string };

/**
 * Accordion built on real buttons and `aria-expanded`, with the answer kept in
 * the DOM as sanitised HTML. One open at a time: a page of FAQs where every
 * panel can be open at once stops being scannable.
 */
export function FaqAccordion({ entries }: { entries: FaqEntry[] }) {
  const [openId, setOpenId] = useState<number | null>(entries[0]?.id ?? null);
  const reduce = useReducedMotion();
  const uid = useId().replace(/:/g, "");

  if (!entries.length) return null;

  return (
    <ul className="border-t border-line">
      {entries.map((entry) => {
        const open = openId === entry.id;
        return (
          <li key={entry.id} className="border-b border-line">
            <h3>
              <button
                type="button"
                onClick={() => setOpenId(open ? null : entry.id)}
                aria-expanded={open}
                aria-controls={`${uid}-${entry.id}`}
                className="group flex w-full items-start gap-4 py-5 text-start"
              >
                <span className="flex-1 font-display text-[1rem] font-semibold text-strong">
                  {entry.question}
                </span>
                <span
                  className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border border-line text-muted transition-colors group-hover:text-strong"
                  style={open ? { borderColor: "var(--color-orange)", color: "var(--color-orange)" } : undefined}
                >
                  <Icon
                    name="chevronDown"
                    size={14}
                    style={{ transform: open ? "rotate(180deg)" : undefined, transition: "transform .25s var(--ease-out-soft)" }}
                  />
                </span>
              </button>
            </h3>
            <AnimatePresence initial={false}>
              {open ? (
                <motion.div
                  id={`${uid}-${entry.id}`}
                  role="region"
                  initial={reduce ? false : { height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={reduce ? undefined : { height: 0, opacity: 0 }}
                  transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                  className="overflow-hidden"
                >
                  <div
                    className="prose-eod max-w-2xl pb-6 pe-10 text-small"
                    dangerouslySetInnerHTML={{ __html: entry.answer }}
                  />
                </motion.div>
              ) : null}
            </AnimatePresence>
          </li>
        );
      })}
    </ul>
  );
}
