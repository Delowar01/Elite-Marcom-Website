"use server";

import { eq, sql } from "drizzle-orm";
import { redirect } from "next/navigation";

import { logActivity } from "@/lib/activity";
import { verifyPassword } from "@/lib/auth/password";
import { checkLoginRate, recordLoginAttempt } from "@/lib/auth/rate-limit";
import { clientIp, createSession, destroySession, getSession, hashIp } from "@/lib/auth/session";
import { db } from "@/lib/db";
import { roles, users } from "@/lib/db/schema";
import { type ActionState, fail, runAction } from "@/lib/admin/actions";

/** Only site-relative paths inside the panel are accepted as a return target. */
function safeNext(value: string): string {
  if (!value.startsWith("/admin") || value.startsWith("//")) return "/admin";
  return value;
}

export async function signIn(_prev: ActionState, form: FormData): Promise<ActionState> {
  const email = String(form.get("email") ?? "").trim().toLowerCase().slice(0, 190);
  const password = String(form.get("password") ?? "");
  const next = safeNext(String(form.get("next") ?? "/admin"));

  const result = await runAction("sign-in", async () => {
    if (!email || !password) return fail("Enter your email address and password.");

    const ipHash = hashIp(await clientIp());
    const rate = await checkLoginRate(email, ipHash);
    if (rate.blocked) {
      return fail(
        `Too many failed attempts. Try again in about ${rate.retryAfterMinutes} minutes.`,
      );
    }

    const [found] = await db
      .select({ user: users, roleKey: roles.key })
      .from(users)
      .innerJoin(roles, eq(roles.id, users.roleId))
      .where(sql`lower(${users.email}) = ${email}`)
      .limit(1);

    // The password is verified even when the account is missing, so a wrong
    // address and a wrong password take the same amount of time to answer.
    const hash =
      found?.user.passwordHash ??
      "scrypt$32768$8$1$AAAAAAAAAAAAAAAAAAAAAA==$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==";
    const valid = await verifyPassword(password, hash);

    if (!found || !valid || !found.user.isActive) {
      await recordLoginAttempt(email, ipHash, false);
      return fail("That email address and password do not match an active account.");
    }

    await recordLoginAttempt(email, ipHash, true);
    await createSession(found.user.id);
    await db.update(users).set({ lastLoginAt: new Date() }).where(eq(users.id, found.user.id));
    await logActivity(
      {
        sessionId: "",
        csrfToken: "",
        user: {
          id: found.user.id,
          name: found.user.name,
          email: found.user.email,
          roleKey: found.roleKey,
          roleName: found.roleKey,
        },
        permissions: new Set(),
      },
      { action: "login", entityType: "user", entityId: found.user.id, summary: "Signed in" },
    );
    return { ok: true };
  });

  if (!result.ok) return result;
  redirect(next);
}

export async function signOut(): Promise<void> {
  const session = await getSession();
  if (session) {
    await logActivity(session, { action: "logout", entityType: "user", entityId: session.user.id });
  }
  await destroySession();
  redirect("/admin/login");
}
