import { z } from "zod";

/**
 * One schema, used by the browser before submit and again by the route handler
 * before anything is written. The server copy is the one that counts — the
 * client copy only exists so a visitor is told about a problem without a round
 * trip.
 */
export const enquirySchema = z.object({
  name: z.string().trim().min(2, "Please enter your name.").max(120),
  email: z
    .union([z.string().trim().max(190).email("That email address does not look right."), z.literal("")])
    .default(""),
  phone: z.string().trim().max(40).default(""),
  whatsapp: z.string().trim().max(40).default(""),
  nationality: z.string().trim().max(80).default(""),
  categoryId: z.coerce.number().int().positive().nullable().catch(null),
  serviceId: z.coerce.number().int().positive().nullable().catch(null),
  message: z.string().trim().max(4000).default(""),
  preferredContact: z.enum(["phone", "whatsapp", "email"]).default("whatsapp"),
  sourcePage: z.string().trim().max(255).default(""),
  locale: z.enum(["en", "ar"]).default("en"),
  details: z.record(z.string(), z.string().max(500)).default({}),
  utm: z.record(z.string(), z.string().max(190)).default({}),
  /**
   * Honeypot. Not constrained here on purpose: a schema error would tell a bot
   * exactly which field gave it away. The route checks it after parsing and
   * answers 200 as though the submission succeeded.
   */
  company_website: z.string().max(300).optional().default(""),
  /** Milliseconds the form was on screen. Submissions under a second are bots. */
  elapsed: z.coerce.number().int().nonnegative().default(0),
});

export type EnquiryInput = z.infer<typeof enquirySchema>;

/**
 * A request with neither a phone number nor an email address cannot be answered,
 * so it is rejected rather than stored as a dead lead. Zod cannot express this
 * inside a field, so it is checked here and reported against both.
 */
export function contactProblem(input: Pick<EnquiryInput, "email" | "phone" | "whatsapp">): string | null {
  if (input.email || input.phone || input.whatsapp) return null;
  return "Please leave a phone number or an email address so we can reply.";
}

export const UTM_KEYS = [
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_term",
  "utm_content",
  "gclid",
  "fbclid",
] as const;
