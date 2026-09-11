import "server-only";

import { redirect } from "next/navigation";
import { timingSafeEqual } from "node:crypto";

import type { PermissionKey } from "./permissions";
import { getSession, type AdminSession } from "./session";

export class AccessError extends Error {
  constructor(message = "You do not have permission to do that.") {
    super(message);
    this.name = "AccessError";
  }
}

/** For pages: bounce anonymous callers to the login screen, keeping their target. */
export async function requireSession(returnTo?: string): Promise<AdminSession> {
  const session = await getSession();
  if (!session) {
    redirect(returnTo ? `/admin/login?next=${encodeURIComponent(returnTo)}` : "/admin/login");
  }
  return session;
}

export async function requirePermission(
  permission: PermissionKey,
  returnTo?: string,
): Promise<AdminSession> {
  const session = await requireSession(returnTo);
  if (!session.permissions.has(permission)) redirect("/admin?denied=1");
  return session;
}

export function can(session: AdminSession | null, permission: PermissionKey): boolean {
  return Boolean(session?.permissions.has(permission));
}

function tokensMatch(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}

/**
 * Every admin mutation runs through here. Server Actions already reject
 * cross-origin POSTs, but a synchroniser token tied to the session row is the
 * check that does not depend on a header an intermediary might rewrite — and it
 * is the one an auditor can see in the form markup.
 */
export async function guardAction(
  permission: PermissionKey,
  formData: FormData,
): Promise<AdminSession> {
  const session = await getSession();
  if (!session) throw new AccessError("Your session has expired. Sign in again.");

  const token = String(formData.get("_csrf") ?? "");
  if (!token || !tokensMatch(token, session.csrfToken)) {
    throw new AccessError("This form expired. Reload the page and try again.");
  }
  if (!session.permissions.has(permission)) throw new AccessError();
  return session;
}

/**
 * Owner accounts are the one thing an admin may not touch: whoever can rewrite
 * an owner's password owns the site. Checked against the target row, not the UI.
 */
export function assertMayManageUser(session: AdminSession, targetRoleKey: string): void {
  if (targetRoleKey === "owner" && session.user.roleKey !== "owner") {
    throw new AccessError("Only an owner can manage owner accounts.");
  }
}
