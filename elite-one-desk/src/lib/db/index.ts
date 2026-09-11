import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";

import { getDatabaseUrl } from "@/lib/env";
import * as schema from "./schema";

/**
 * One pool per process. Next.js reloads modules in development, so the client
 * is parked on globalThis to stop each reload opening another pool.
 */
const globalForDb = globalThis as unknown as {
  __eodSql?: ReturnType<typeof postgres>;
};

const client =
  globalForDb.__eodSql ??
  postgres(getDatabaseUrl(), {
    max: Number(process.env.DATABASE_POOL_MAX ?? 10),
    idle_timeout: 30,
    connect_timeout: 10,
    prepare: false,
  });

if (process.env.NODE_ENV !== "production") globalForDb.__eodSql = client;

export const db = drizzle(client, { schema });
export { schema };
export type Database = typeof db;
