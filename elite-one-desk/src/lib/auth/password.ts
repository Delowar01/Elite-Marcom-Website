import {
  randomBytes,
  scrypt as scryptCb,
  timingSafeEqual,
  type ScryptOptions,
} from "node:crypto";
import { promisify } from "node:util";

// promisify picks the three-argument overload; the options form is the one we
// need, so the signature is restated rather than inferred.
const scrypt = promisify(scryptCb) as (
  password: string,
  salt: Buffer,
  keylen: number,
  options: ScryptOptions,
) => Promise<Buffer>;

/**
 * scrypt rather than bcrypt/argon2: it is memory-hard, it is in Node's standard
 * library, and it needs no native module — so a Hostinger VPS build never turns
 * into a compiler problem. Parameters follow the OWASP minimum (N=2^15, r=8, p=1).
 */
const N = 32768;
const R = 8;
const P = 1;
const KEYLEN = 64;
const SALT_BYTES = 16;

export async function hashPassword(plain: string): Promise<string> {
  const salt = randomBytes(SALT_BYTES);
  const derived = await scrypt(plain.normalize("NFKC"), salt, KEYLEN, {
    N,
    r: R,
    p: P,
    maxmem: 64 * 1024 * 1024,
  });
  return ["scrypt", N, R, P, salt.toString("base64"), derived.toString("base64")].join("$");
}

export async function verifyPassword(plain: string, stored: string): Promise<boolean> {
  const parts = stored.split("$");
  if (parts.length !== 6 || parts[0] !== "scrypt") return false;
  const [, n, r, p, saltB64, hashB64] = parts;
  const salt = Buffer.from(saltB64, "base64");
  const expected = Buffer.from(hashB64, "base64");
  let derived: Buffer;
  try {
    derived = await scrypt(plain.normalize("NFKC"), salt, expected.length, {
      N: Number(n),
      r: Number(r),
      p: Number(p),
      maxmem: 128 * 1024 * 1024,
    });
  } catch {
    return false;
  }
  return derived.length === expected.length && timingSafeEqual(derived, expected);
}

/** Rejects the passwords that make a rate limiter the only line of defence. */
export function passwordProblem(plain: string): string | null {
  if (plain.length < 12) return "Use at least 12 characters.";
  if (!/[a-z]/.test(plain)) return "Include a lower-case letter.";
  if (!/[A-Z]/.test(plain)) return "Include an upper-case letter.";
  if (!/[0-9]/.test(plain)) return "Include a digit.";
  return null;
}
