"use client";

import { useActionState, useEffect, useRef, useState, type ReactNode } from "react";
import { useFormStatus } from "react-dom";

import { Icon } from "@/components/ui/icon";
import type { ActionState } from "@/lib/admin/actions";

const EMPTY: ActionState = { ok: false };

export function SubmitButton({
  children = "Save changes",
  pendingLabel = "Saving…",
  variant = "primary",
  className = "",
}: {
  children?: ReactNode;
  pendingLabel?: string;
  variant?: "primary" | "ghost" | "danger";
  className?: string;
}) {
  const { pending } = useFormStatus();
  const variantClass =
    variant === "primary" ? "admin-btn-primary" : variant === "danger" ? "admin-btn-danger" : "";
  return (
    <button type="submit" disabled={pending} className={`admin-btn ${variantClass} ${className}`}>
      {pending ? pendingLabel : children}
    </button>
  );
}

/**
 * The shared wrapper for every admin form.
 *
 * It owns three things that would otherwise be re-implemented on each screen:
 * the result banner, the "you have unsaved changes" guard, and resetting the
 * dirty flag once a save comes back clean. `onSaved` lets a screen refresh a
 * list without the form knowing anything about it.
 */
export function AdminForm({
  action,
  children,
  footer,
  className = "",
  guardUnsaved = true,
  onSaved,
  successMessage = "Saved.",
}: {
  action: (prev: ActionState, form: FormData) => Promise<ActionState>;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  guardUnsaved?: boolean;
  onSaved?: (state: ActionState) => void;
  successMessage?: string;
}) {
  const [state, formAction] = useActionState<ActionState, FormData>(action, EMPTY);
  const [dirty, setDirty] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const lastHandled = useRef<ActionState | null>(null);

  useEffect(() => {
    if (state === EMPTY || lastHandled.current === state) return;
    lastHandled.current = state;
    if (state.ok) {
      setDirty(false);
      onSaved?.(state);
    }
  }, [state, onSaved]);

  // §45: leaving a half-edited form should cost a confirmation, not the work.
  useEffect(() => {
    if (!guardUnsaved || !dirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty, guardUnsaved]);

  return (
    <form
      ref={formRef}
      action={formAction}
      onChange={() => setDirty(true)}
      className={className}
      noValidate
    >
      {state !== EMPTY && (state.message || state.ok) ? (
        <p
          role="status"
          className="mb-4 flex items-start gap-2 rounded-[var(--radius-sm)] border p-3 text-[0.8rem]"
          style={
            state.ok
              ? { borderColor: "#3ddc8466", background: "#3ddc840f", color: "#9ff0c4" }
              : { borderColor: "#ef535066", background: "#ef53500f", color: "#ffb4ad" }
          }
        >
          <Icon name={state.ok ? "check" : "close"} size={14} className="mt-0.5 shrink-0" />
          {state.message ?? successMessage}
        </p>
      ) : null}

      {children}

      {footer ? (
        <div className="mt-6 flex flex-wrap items-center gap-2">
          {footer}
          {dirty ? <span className="text-[0.74rem] text-muted">Unsaved changes</span> : null}
        </div>
      ) : null}
    </form>
  );
}

/** A labelled field with optional hint and inline error. */
export function Field({
  label,
  name,
  hint,
  error,
  children,
  className = "",
}: {
  label: string;
  name?: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="admin-label" htmlFor={name}>
        {label}
      </label>
      {children}
      {error ? (
        <p role="alert" className="mt-1 text-[0.74rem]" style={{ color: "#ff9a95" }}>
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1 text-[0.73rem] text-muted">{hint}</p>
      ) : null}
    </div>
  );
}

/**
 * Confirmation for anything destructive. A native dialog rather than a custom
 * modal: it cannot be missed, it cannot be styled into looking harmless, and it
 * works before hydration finishes.
 */
export function ConfirmSubmit({
  children,
  message,
  variant = "danger",
  className = "",
}: {
  children: ReactNode;
  message: string;
  variant?: "primary" | "ghost" | "danger";
  className?: string;
}) {
  const { pending } = useFormStatus();
  const variantClass =
    variant === "primary" ? "admin-btn-primary" : variant === "danger" ? "admin-btn-danger" : "";
  return (
    <button
      type="submit"
      disabled={pending}
      className={`admin-btn ${variantClass} ${className}`}
      onClick={(event) => {
        if (!window.confirm(message)) event.preventDefault();
      }}
    >
      {pending ? "Working…" : children}
    </button>
  );
}

/**
 * A one-control form for a single action — reorder, hide, publish, delete.
 *
 * Server Actions return an `ActionState`, which a bare `<form action={…}>` will
 * not accept, so the state hook is what makes these usable inline. The result is
 * surfaced through `onResult` where a screen wants to show it; most of these
 * actions revalidate the page and need no banner of their own.
 */
export function InlineAction({
  action,
  hidden,
  children,
  className = "inline",
  onResult,
}: {
  action: (prev: ActionState, form: FormData) => Promise<ActionState>;
  hidden: Record<string, string | number>;
  children: ReactNode;
  className?: string;
  onResult?: (state: ActionState) => void;
}) {
  const [state, formAction] = useActionState<ActionState, FormData>(action, EMPTY);
  const seen = useRef<ActionState | null>(null);

  useEffect(() => {
    if (state === EMPTY || seen.current === state) return;
    seen.current = state;
    onResult?.(state);
  }, [state, onResult]);

  return (
    <form action={formAction} className={className}>
      {Object.entries(hidden).map(([key, value]) => (
        <input key={key} type="hidden" name={key} value={value} />
      ))}
      {children}
    </form>
  );
}
