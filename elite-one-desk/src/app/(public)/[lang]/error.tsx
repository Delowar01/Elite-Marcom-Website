"use client";

import Link from "next/link";
import { useEffect } from "react";

/**
 * The public error boundary. It shows a sentence and a retry button and nothing
 * else — §44: a raw server error never reaches a visitor. The real detail goes
 * to the server log, where an operator can find it.
 */
export default function PublicError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[public]", error.digest ?? "", error.message);
  }, [error]);

  return (
    <div className="shell flex min-h-[65vh] flex-col justify-center py-[clamp(5rem,10vw,9rem)]">
      <p className="eyebrow">Error</p>
      <h1 className="mt-5 max-w-2xl text-[length:var(--text-h1)]">Something went wrong at our end</h1>
      <p className="lede mt-4 max-w-xl">
        The page could not be loaded. Please try again in a moment, or reach us directly if it keeps
        happening.
      </p>
      <div className="mt-8 flex flex-wrap gap-3">
        <button type="button" onClick={reset} className="btn btn-primary">
          Try again
        </button>
        <Link href="/contact" className="btn btn-ghost">
          Contact us
        </Link>
      </div>
      {error.digest ? (
        <p className="mt-6 text-[0.75rem] text-muted">Reference: {error.digest}</p>
      ) : null}
    </div>
  );
}
