import "server-only";

import { AccessError } from "@/lib/auth/guard";

/** The shape every admin Server Action returns, so one client hook reads them all. */
export type ActionState = {
  ok: boolean;
  message?: string;
  /** Field name → message, for inline validation. */
  errors?: Record<string, string>;
  /** Echoed back so a client can act on what was created. */
  id?: number;
};

export const ok = (message?: string, id?: number): ActionState => ({ ok: true, message, id });

export const fail = (message: string, errors?: Record<string, string>): ActionState => ({
  ok: false,
  message,
  errors,
});

/**
 * Wraps an action body so a permission or validation failure comes back as a
 * message the form can render, while anything unexpected is logged server-side
 * and reported as one safe sentence (§44).
 */
export async function runAction(
  label: string,
  body: () => Promise<ActionState>,
): Promise<ActionState> {
  try {
    return await body();
  } catch (error) {
    if (error instanceof AccessError) return fail(error.message);
    // A redirect() inside an action throws by design; let it through.
    if (error && typeof error === "object" && "digest" in error) throw error;
    console.error(`[admin:${label}]`, error);
    return fail("Something went wrong. The change was not saved.");
  }
}

/** Reads a trimmed string from a form, with a length cap. */
export const field = (form: FormData, name: string, max = 5000): string =>
  String(form.get(name) ?? "").trim().slice(0, max);

export const checkbox = (form: FormData, name: string): boolean =>
  form.get(name) === "on" || form.get(name) === "true";

export const numberField = (form: FormData, name: string, fallback = 0): number => {
  const raw = String(form.get(name) ?? "").trim();
  if (!raw) return fallback;
  const value = Number(raw);
  return Number.isFinite(value) ? value : fallback;
};

export const optionalId = (form: FormData, name: string): number | null => {
  const value = numberField(form, name, 0);
  return value > 0 ? value : null;
};
