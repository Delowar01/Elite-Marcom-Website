/**
 * Shown only when an authorised editor is looking at drafts. It is deliberately
 * loud: mistaking a preview for the live site is how an unpublished price or a
 * half-written paragraph gets reported as a bug.
 */
export function PreviewBanner() {
  return (
    <div
      className="no-print sticky top-0 z-100 flex items-center justify-center gap-2 px-4 py-1.5 text-[0.75rem] font-semibold"
      style={{ background: "var(--color-orange)", color: "#fff" }}
    >
      Preview — showing unpublished drafts and hidden sections.
    </div>
  );
}
