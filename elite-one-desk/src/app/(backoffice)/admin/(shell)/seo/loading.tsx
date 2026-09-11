/**
 * Route-level loading state. Streams in while the screen's queries run, so a
 * click always produces something immediately rather than a frozen page.
 */
export default function Loading() {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading…</span>
      <div className="mb-6 space-y-2">
        <div className="h-6 w-56 animate-pulse rounded bg-[color-mix(in_oklab,var(--color-warm)_8%,transparent)]" />
        <div className="h-3.5 w-96 max-w-full animate-pulse rounded bg-[color-mix(in_oklab,var(--color-warm)_5%,transparent)]" />
      </div>
      <div className="space-y-2.5">
        {[0, 1, 2, 3, 4].map((row) => (
          <div
            key={row}
            className="h-14 animate-pulse rounded-[var(--radius-md)] border border-[var(--admin-line)] bg-[color-mix(in_oklab,var(--color-warm)_3%,transparent)]"
            style={{ animationDelay: `${row * 70}ms` }}
          />
        ))}
      </div>
    </div>
  );
}
