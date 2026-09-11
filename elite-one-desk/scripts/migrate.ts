import "./env";

import { drizzle } from "drizzle-orm/postgres-js";
import { migrate } from "drizzle-orm/postgres-js/migrator";
import postgres from "postgres";

/**
 * Applies every pending migration and exits. Run by `npm run db:migrate` and by
 * the deployment script before the new release is started.
 */
async function main() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set.");
  const client = postgres(url, { max: 1 });
  try {
    await migrate(drizzle(client), { migrationsFolder: "./drizzle" });
    console.log("Migrations applied.");
  } finally {
    await client.end();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
