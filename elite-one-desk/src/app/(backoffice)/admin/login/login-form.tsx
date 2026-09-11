"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { Icon } from "@/components/ui/icon";
import type { ActionState } from "@/lib/admin/actions";
import { signIn } from "./actions";

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending} className="admin-btn admin-btn-primary w-full">
      {pending ? "Signing in…" : "Sign in"}
      {pending ? null : <Icon name="arrowRight" size={15} />}
    </button>
  );
}

export function LoginForm({ next }: { next: string }) {
  const [state, action] = useActionState<ActionState, FormData>(signIn, { ok: false });

  return (
    <form action={action} className="flex flex-col gap-4">
      <input type="hidden" name="next" value={next} />

      {state.message ? (
        <p
          role="alert"
          className="rounded-[var(--radius-sm)] border p-3 text-[0.8rem]"
          style={{ borderColor: "#ef535066", background: "#ef53500f", color: "#ffb4ad" }}
        >
          {state.message}
        </p>
      ) : null}

      <div>
        <label htmlFor="email" className="admin-label">
          Email address
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="username"
          required
          autoFocus
          className="admin-input"
        />
      </div>

      <div>
        <label htmlFor="password" className="admin-label">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          className="admin-input"
        />
      </div>

      <SubmitButton />
    </form>
  );
}
