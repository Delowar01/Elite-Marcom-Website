import "server-only";

import { db } from "@/lib/db";
import { activityLogs } from "@/lib/db/schema";
import type { AdminSession } from "@/lib/auth/session";
import { clientIp, hashIp } from "@/lib/auth/session";

type LogInput = {
  action: string;
  entityType?: string;
  entityId?: string | number;
  summary?: string;
  metadata?: Record<string, unknown>;
};

/**
 * Audit trail. Never throws: a logging failure must not roll back the change
 * the operator actually asked for, but it is reported to the server log.
 */
export async function logActivity(
  session: AdminSession | null,
  input: LogInput,
): Promise<void> {
  try {
    await db.insert(activityLogs).values({
      userId: session?.user.id ?? null,
      actorName: session?.user.name ?? "System",
      action: input.action,
      entityType: input.entityType ?? "",
      entityId: input.entityId === undefined ? "" : String(input.entityId),
      summary: (input.summary ?? "").slice(0, 255),
      metadata: input.metadata ?? null,
      ipHash: hashIp(await clientIp()),
    });
  } catch (error) {
    console.error("[activity] failed to record", input.action, error);
  }
}
