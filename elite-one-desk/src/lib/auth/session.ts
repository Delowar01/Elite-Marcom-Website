import "server-only";

import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { cookies, headers } from "next/headers";
import { cache } from "react";
import { and, eq, gt, inArray } from "drizzle-orm";

import { db } from "@/lib/db";
import {
  permissions as permissionsTable,
  rolePermissions,
  roles,
  sessions,
  users,
} from "@/lib/db/schema";
import { getAuthSecret, isProduction } from "@/lib/env";
import type { PermissionKey } from "./permissions";

export const SESSION_COOKIE = "eod_session";
/** Absolute lifetime. A session older than this is gone regardless of activity. */
const MAX_AGE_SECONDS = 60 * 60 * 12;
/** Sliding window: activity inside the last hour pushes the expiry out again. */
const REFRESH_AFTER_MS = 15 * 60 * 1000;

const sha256 = (value: string) => createHash("sha256").update(value).digest("hex");

/** Peppered so a database copy alone cannot be reversed into visitor addresses. */
export const hashIp = (ip: string) => (ip ? sha256(`${ip}:${getAuthSecret()}`).slice(0, 64) : "");

export async function clientIp(): Promise<string> {
  const h = await headers();
  const forwarded = h.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0]!.trim();
  return h.get("x-real-ip") ?? "";
}

export type AdminSession = {
  sessionId: string;
  csrfToken: string;
  user: { id: number; name: string; email: string; roleKey: string; roleName: string };
  permissions: Set<PermissionKey>;
};

export async function createSession(userId: number): Promise<void> {
  const id = randomBytes(18).toString("base64url");
  const secret = randomBytes(32).toString("base64url");
  const csrfToken = randomBytes(24).toString("base64url");
  const ua = (await headers()).get("user-agent") ?? "";

  await db.insert(sessions).values({
    id,
    userId,
    tokenHash: sha256(secret),
    csrfToken,
    expiresAt: new Date(Date.now() + MAX_AGE_SECONDS * 1000),
    ipHash: hashIp(await clientIp()),
    userAgent: ua.slice(0, 255),
  });

  const jar = await cookies();
  jar.set(SESSION_COOKIE, `${id}.${secret}`, {
    httpOnly: true,
    sameSite: "lax",
    secure: isProduction,
    path: "/",
    maxAge: MAX_AGE_SECONDS,
  });
}

export async function destroySession(): Promise<void> {
  const jar = await cookies();
  const raw = jar.get(SESSION_COOKIE)?.value;
  if (raw) {
    const [id] = raw.split(".");
    if (id) await db.delete(sessions).where(eq(sessions.id, id));
  }
  jar.delete(SESSION_COOKIE);
}

/** Ends every session belonging to a user — used when a password or role changes. */
export async function destroyUserSessions(userId: number): Promise<void> {
  await db.delete(sessions).where(eq(sessions.userId, userId));
}

/**
 * Resolves the caller once per request. Returns null for anonymous visitors;
 * never throws, so a layout can render the login screen instead of a 500.
 */
export const getSession = cache(async (): Promise<AdminSession | null> => {
  const raw = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!raw) return null;
  const [id, secret] = raw.split(".");
  if (!id || !secret) return null;

  const row = await db
    .select({
      session: sessions,
      user: users,
      role: roles,
    })
    .from(sessions)
    .innerJoin(users, eq(users.id, sessions.userId))
    .innerJoin(roles, eq(roles.id, users.roleId))
    .where(and(eq(sessions.id, id), gt(sessions.expiresAt, new Date())))
    .limit(1);

  const found = row[0];
  if (!found) return null;

  const provided = Buffer.from(sha256(secret));
  const stored = Buffer.from(found.session.tokenHash);
  if (provided.length !== stored.length || !timingSafeEqual(provided, stored)) return null;
  if (!found.user.isActive) return null;

  // Sliding expiry, written at most once every REFRESH_AFTER_MS.
  if (Date.now() - found.session.lastSeenAt.getTime() > REFRESH_AFTER_MS) {
    await db
      .update(sessions)
      .set({
        lastSeenAt: new Date(),
        expiresAt: new Date(Date.now() + MAX_AGE_SECONDS * 1000),
      })
      .where(eq(sessions.id, found.session.id));
  }

  const granted = await db
    .select({ key: permissionsTable.key })
    .from(rolePermissions)
    .innerJoin(permissionsTable, eq(permissionsTable.id, rolePermissions.permissionId))
    .where(eq(rolePermissions.roleId, found.role.id));

  return {
    sessionId: found.session.id,
    csrfToken: found.session.csrfToken,
    user: {
      id: found.user.id,
      name: found.user.name,
      email: found.user.email,
      roleKey: found.role.key,
      roleName: found.role.name,
    },
    permissions: new Set(granted.map((g) => g.key as PermissionKey)),
  };
});

/** Replaces a role's grants wholesale. Used by the seed and the roles screen. */
export async function setRolePermissions(roleId: number, keys: string[]): Promise<void> {
  const rows = keys.length
    ? await db
        .select({ id: permissionsTable.id })
        .from(permissionsTable)
        .where(inArray(permissionsTable.key, keys))
    : [];
  await db.transaction(async (tx) => {
    await tx.delete(rolePermissions).where(eq(rolePermissions.roleId, roleId));
    if (rows.length) {
      await tx
        .insert(rolePermissions)
        .values(rows.map((r) => ({ roleId, permissionId: r.id })));
    }
  });
}
