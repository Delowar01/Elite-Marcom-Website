"use client";

import Link from "next/link";
import { useActionState, useEffect, useRef, useState } from "react";

import { ConfirmSubmit, InlineAction, SubmitButton } from "@/components/admin/form";
import { Icon } from "@/components/ui/icon";
import type { ActionState } from "@/lib/admin/actions";
import type { BlockDef } from "@/lib/cms/blocks";
import {
  addSection,
  deleteSection,
  duplicateSection,
  moveSection,
  reorderSections,
  toggleSection,
} from "../actions";

export type SectionRow = {
  id: number;
  blockType: string;
  blockName: string;
  blockDescription: string;
  summary: string;
  isPublished: boolean;
  hasDraft: boolean;
  position: number;
};

const EMPTY: ActionState = { ok: false };

/**
 * The section list is the page.
 *
 * Order, visibility, duplication and deletion all happen here; the content of a
 * section is edited on its own screen. Each control is its own tiny form, so
 * every one of them is a real POST that works before hydration and is checked
 * against the same permission on the server.
 */
export function SectionList({
  csrf,
  pageId,
  sections,
  blocks,
  canManage,
}: {
  csrf: string;
  pageId: number;
  sections: SectionRow[];
  blocks: BlockDef[];
  canManage: boolean;
}) {
  const [addState, addAction] = useActionState<ActionState, FormData>(addSection, EMPTY);
  const [reorderState, reorderAction] = useActionState<ActionState, FormData>(reorderSections, EMPTY);

  // Local order, so a drag lands immediately rather than after a round trip.
  // The server is the authority: once it answers, the page revalidates and the
  // prop below replaces this.
  const [order, setOrder] = useState<SectionRow[]>(sections);
  const [dragging, setDragging] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const submitRef = useRef<HTMLButtonElement>(null);
  const signature = sections.map((s) => s.id).join(",");

  useEffect(() => {
    setOrder(sections);
    // Re-syncs whenever the page sends a different set or a different order.
  }, [signature, sections]);

  const dropOnto = (target: number) => {
    if (dragging === null || dragging === target) return;
    const next = [...order];
    const [moved] = next.splice(dragging, 1);
    next.splice(target, 0, moved!);
    setOrder(next);
    setDragging(null);
    setOver(null);
    // Persist on the next tick, once the hidden input carries the new order.
    queueMicrotask(() => submitRef.current?.click());
  };

  return (
    <div className="space-y-5">
      <section className="admin-card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--admin-line)] px-4 py-3">
          <h2>Sections</h2>
          <p className="text-[0.74rem] text-muted">
            {order.length} section{order.length === 1 ? "" : "s"} · top to bottom
            {canManage ? " · drag a row, or use the arrows" : null}
          </p>
        </div>

        {reorderState.message && !reorderState.ok ? (
          <p
            role="alert"
            className="border-b border-[var(--admin-line)] px-4 py-2 text-[0.78rem]"
            style={{ color: "#ffb4ad" }}
          >
            {reorderState.message}
          </p>
        ) : null}

        {/* Submitted by the drop handler. Keyboard users reorder with the
            arrow buttons on each row, which post the same way. */}
        <form action={reorderAction} className="hidden">
          <input type="hidden" name="_csrf" value={csrf} />
          <input type="hidden" name="pageId" value={pageId} />
          <input type="hidden" name="order" value={JSON.stringify(order.map((s) => s.id))} />
          <button ref={submitRef} type="submit" tabIndex={-1} aria-hidden />
        </form>

        {order.length === 0 ? (
          <p className="px-4 py-10 text-center text-[0.83rem] text-muted">
            This page has no sections yet. Add one below.
          </p>
        ) : (
          <ul className="divide-y divide-[var(--admin-line)]">
            {order.map((section, index) => (
              <li
                key={section.id}
                draggable={canManage}
                onDragStart={(event) => {
                  setDragging(index);
                  event.dataTransfer.effectAllowed = "move";
                  // Firefox will not start a drag without data on the transfer.
                  event.dataTransfer.setData("text/plain", String(section.id));
                }}
                onDragOver={(event) => {
                  if (dragging === null) return;
                  event.preventDefault();
                  event.dataTransfer.dropEffect = "move";
                  setOver(index);
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  dropOnto(index);
                }}
                onDragEnd={() => {
                  setDragging(null);
                  setOver(null);
                }}
                data-dragging={dragging === index || undefined}
                data-over={over === index && dragging !== index ? true : undefined}
                className="flex flex-wrap items-start gap-3 px-4 py-3.5 transition-colors data-[dragging]:opacity-45 data-[over]:bg-[color-mix(in_oklab,var(--color-orange)_12%,transparent)]"
              >
                {canManage ? (
                  <span
                    aria-hidden
                    title="Drag to reorder"
                    className="mt-1.5 shrink-0 cursor-grab select-none text-[0.8rem] leading-none text-muted active:cursor-grabbing"
                  >
                    ⠿
                  </span>
                ) : null}
                <span className="mt-1 w-6 shrink-0 text-[0.72rem] tabular-nums text-muted">
                  {String(index + 1).padStart(2, "0")}
                </span>

                <div className="min-w-52 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={`/admin/pages/section/${section.id}`}
                      className="font-semibold text-strong hover:text-[var(--color-peach)]"
                    >
                      {section.blockName}
                    </Link>
                    {!section.isPublished ? (
                      <span className="admin-badge" style={{ color: "#9aa2b5" }}>
                        Hidden
                      </span>
                    ) : null}
                    {section.hasDraft ? (
                      <span className="admin-badge" style={{ color: "#ffd166" }}>
                        Draft
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-0.5 line-clamp-1 text-[0.78rem] text-muted">
                    {section.summary || section.blockDescription}
                  </p>
                </div>

                {canManage ? (
                  <div className="flex flex-wrap items-center gap-1">
                    <InlineAction action={moveSection} hidden={{ _csrf: csrf, id: section.id, direction: "up" }} className="contents">
                      <IconButton label="Move up" icon="chevronDown" rotate disabled={index === 0} />
                    </InlineAction>
                    <InlineAction action={moveSection} hidden={{ _csrf: csrf, id: section.id, direction: "down" }} className="contents">
                      <IconButton
                        label="Move down"
                        icon="chevronDown"
                        disabled={index === order.length - 1}
                      />
                    </InlineAction>
                    <InlineAction action={duplicateSection} hidden={{ _csrf: csrf, id: section.id }} className="contents">
                      <IconButton label="Duplicate" icon="layers" />
                    </InlineAction>
                    <InlineAction action={toggleSection} hidden={{ _csrf: csrf, id: section.id }} className="contents">
                      <IconButton
                        label={section.isPublished ? "Hide from the site" : "Show on the site"}
                        icon={section.isPublished ? "eyeOff" : "eye"}
                      />
                    </InlineAction>
                    <InlineAction action={deleteSection} hidden={{ _csrf: csrf, id: section.id }} className="contents">
                      <ConfirmSubmit
                        className="admin-btn-sm"
                        message={`Delete the ${section.blockName} section? This cannot be undone.`}
                      >
                        <Icon name="trash" size={12} />
                        <span className="sr-only">Delete section</span>
                      </ConfirmSubmit>
                    </InlineAction>
                    <Link
                      href={`/admin/pages/section/${section.id}`}
                      className="admin-btn admin-btn-sm ms-1"
                    >
                      Edit
                    </Link>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {canManage ? (
        <section className="admin-card p-5">
          <h2 className="mb-1">Add a section</h2>
          <p className="mb-4 text-[0.8rem] text-muted">
            Sections come from a fixed set, which is what keeps the design consistent. A new one is
            added at the bottom and stays hidden until you publish it.
          </p>

          {addState.message ? (
            <p
              role="status"
              className="mb-4 rounded-[var(--radius-sm)] border p-3 text-[0.8rem]"
              style={
                addState.ok
                  ? { borderColor: "#3ddc8466", background: "#3ddc840f", color: "#9ff0c4" }
                  : { borderColor: "#ef535066", background: "#ef53500f", color: "#ffb4ad" }
              }
            >
              {addState.message}
            </p>
          ) : null}

          <form action={addAction} className="flex flex-wrap items-end gap-3">
            <input type="hidden" name="_csrf" value={csrf} />
            <input type="hidden" name="pageId" value={pageId} />
            <div className="min-w-56 flex-1">
              <label className="admin-label" htmlFor="blockType">
                Section type
              </label>
              <select id="blockType" name="blockType" className="admin-select" defaultValue="">
                <option value="" disabled>
                  Choose a section…
                </option>
                {blocks.map((block) => (
                  <option key={block.type} value={block.type}>
                    {block.name} — {block.description}
                  </option>
                ))}
              </select>
            </div>
            <SubmitButton pendingLabel="Adding…">Add section</SubmitButton>
          </form>
        </section>
      ) : null}
    </div>
  );
}

function IconButton({
  label,
  icon,
  rotate,
  disabled,
}: {
  label: string;
  icon: string;
  rotate?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="submit"
      disabled={disabled}
      aria-label={label}
      title={label}
      className="admin-btn admin-btn-sm"
    >
      <Icon name={icon} size={12} className={rotate ? "rotate-180" : undefined} />
    </button>
  );
}
