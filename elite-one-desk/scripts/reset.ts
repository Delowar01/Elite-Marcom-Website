import "./env";

import { sql } from "drizzle-orm";

import { db } from "../src/lib/db";

/**
 * Drops the public schema and recreates it. Development only: it destroys every
 * enquiry, every edit and every account. Re-run `db:migrate` and `db:seed`
 * afterwards.
 *
 * Guarded twice — NODE_ENV, and a confirmation argument — because the command
 * next to it in package.json is `db:seed`, and the two are one keystroke apart.
 */
async function main() {
  if (process.env.NODE_ENV === "production") {
    throw new Error("Refusing to run against a production database.");
  }
  if (!process.argv.includes("--yes")) {
    console.log(
      "This deletes every table and everything in them.\n" +
        "Re-run as:  npm run db:reset -- --yes",
    );
    process.exit(1);
  }

  const url = process.env.DATABASE_URL ?? "";
  console.log(`Resetting ${url.replace(/:[^:@/]+@/, ":***@")}`);
  await db.execute(sql`drop schema public cascade`);
  await db.execute(sql`create schema public`);
  console.log("Done. Run `npm run db:migrate` and `npm run db:seed` next.");
  process.exit(0);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
