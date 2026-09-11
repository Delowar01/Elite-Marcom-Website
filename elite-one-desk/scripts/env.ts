import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

/**
 * Loads .env for the standalone scripts. Next injects these itself when the app
 * runs; a `tsx` script gets no such help, and a dependency for three lines of
 * parsing is not worth carrying.
 */
for (const file of [".env.local", ".env"]) {
  const full = path.resolve(process.cwd(), file);
  if (!existsSync(full)) continue;
  for (const line of readFileSync(full, "utf8").split("\n")) {
    const match = /^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/.exec(line);
    if (!match) continue;
    const key = match[1]!;
    if (process.env[key] !== undefined) continue;
    let value = match[2]!;
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    process.env[key] = value;
  }
}
