import "server-only";

import { and, eq, gt, sql } from "drizzle-orm";

import { db } from "@/lib/db";
import { loginAttempts } from "@/lib/db/schema";

const WINDOW_MINUTES = 15;
const MAX_PER_IDENTIFIER = 6;
const MAX_PER_IP = 20;

export type RateVerdict = { blocked: boolean; retryAfterMinutes: number };

/**
 * Login throttling, counted in the database rather than in memory: the app runs
 * behind PM2/systemd and may be restarted or clustered, and an in-process
 * counter would reset the moment an attacker's traffic caused a restart.
 */
export async function checkLoginRate(identifier: string, ipHash: string): Promise<RateVerdict> {
  const since = new Date(Date.now() - WINDOW_MINUTES * 60 * 1000);

  const [byIdentifier] = await db
    .select({ n: sql<number>`count(*)::int` })
    .from(loginAttempts)
    .where(
      and(
        eq(loginAttempts.identifier, identifier),
        eq(loginAttempts.successful, false),
        gt(loginAttempts.attemptedAt, since),
      ),
    );

  const [byIp] = ipHash
    ? await db
        .select({ n: sql<number>`count(*)::int` })
        .from(loginAttempts)
        .where(
          and(
            eq(loginAttempts.ipHash, ipHash),
            eq(loginAttempts.successful, false),
            gt(loginAttempts.attemptedAt, since),
          ),
        )
    : [{ n: 0 }];

  const blocked =
    (byIdentifier?.n ?? 0) >= MAX_PER_IDENTIFIER || (byIp?.n ?? 0) >= MAX_PER_IP;
  return { blocked, retryAfterMinutes: WINDOW_MINUTES };
}

export async function recordLoginAttempt(
  identifier: string,
  ipHash: string,
  successful: boolean,
): Promise<void> {
  await db.insert(loginAttempts).values({ identifier, ipHash, successful });
  // Opportunistic prune so the table stays small without a cron job.
  if (Math.random() < 0.05) {
    await db
      .delete(loginAttempts)
      .where(sql`${loginAttempts.attemptedAt} < now() - interval '2 days'`);
  }
}
