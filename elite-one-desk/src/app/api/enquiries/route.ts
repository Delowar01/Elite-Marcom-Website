import { createHash } from "node:crypto";
import { eq, gte, sql } from "drizzle-orm";
import { NextResponse } from "next/server";

import { db } from "@/lib/db";
import { enquiries } from "@/lib/db/schema";
import { getAuthSecret } from "@/lib/env";
import { getCatalog } from "@/lib/queries/catalog";
import { contactProblem, enquirySchema } from "@/lib/validation/enquiry";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * A small in-process bucket, on purpose: the alternative is storing a visitor's
 * IP address to count against, and an enquiry form does not justify that. The
 * hash is peppered and never written anywhere. A restart clears it, which is
 * acceptable — the honeypot and the timing check are the real filters, and this
 * only stops one client hammering the endpoint.
 */
const BUCKET = new Map<string, { count: number; resetAt: number }>();
const WINDOW_MS = 10 * 60 * 1000;
const MAX_PER_WINDOW = 6;

function overLimit(key: string): boolean {
  const now = Date.now();
  const entry = BUCKET.get(key);
  if (!entry || entry.resetAt < now) {
    BUCKET.set(key, { count: 1, resetAt: now + WINDOW_MS });
    if (BUCKET.size > 5000) {
      for (const [k, v] of BUCKET) if (v.resetAt < now) BUCKET.delete(k);
    }
    return false;
  }
  entry.count += 1;
  return entry.count > MAX_PER_WINDOW;
}

/** EOD-26-0148 — short enough to read out over the phone. */
async function nextReference(): Promise<string> {
  const year = new Date().getFullYear();
  const prefix = `EOD-${String(year).slice(2)}-`;
  const [row] = await db
    .select({ n: sql<number>`count(*)::int` })
    .from(enquiries)
    .where(gte(enquiries.createdAt, new Date(year, 0, 1)));
  return `${prefix}${String((row?.n ?? 0) + 1).padStart(4, "0")}`;
}

export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ ok: false, message: "Invalid request." }, { status: 400 });
  }

  const parsed = enquirySchema.safeParse(payload);
  if (!parsed.success) {
    const errors: Record<string, string> = {};
    for (const issue of parsed.error.issues) {
      const key = String(issue.path[0] ?? "form");
      if (!errors[key]) errors[key] = issue.message;
    }
    return NextResponse.json(
      { ok: false, errors, message: "Please check the highlighted fields." },
      { status: 422 },
    );
  }

  const input = parsed.data;

  // Two silent filters. A bot that fills every field trips the honeypot; one
  // that posts the form faster than a person could read it trips the timer.
  // Both answer 200 so the sender learns nothing from the response.
  if (input.company_website || (input.elapsed > 0 && input.elapsed < 1200)) {
    return NextResponse.json({ ok: true, reference: "" });
  }

  const missingContact = contactProblem(input);
  if (missingContact) {
    return NextResponse.json(
      { ok: false, errors: { phone: missingContact, email: missingContact }, message: missingContact },
      { status: 422 },
    );
  }

  const forwarded = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "";
  const ipKey = createHash("sha256").update(`${forwarded}:${getAuthSecret()}`).digest("hex").slice(0, 32);
  if (overLimit(ipKey)) {
    return NextResponse.json(
      { ok: false, message: "Too many requests. Please try again shortly, or reach us on WhatsApp." },
      { status: 429 },
    );
  }

  // Names are captured alongside the ids so a record still reads correctly
  // after a service is renamed or removed.
  const catalog = await getCatalog();
  const category = input.categoryId
    ? catalog.categories.find((c) => c.id === input.categoryId)
    : undefined;
  const service = input.serviceId
    ? catalog.services.find((s) => s.id === input.serviceId)
    : undefined;

  try {
    let reference = await nextReference();
    for (let attempt = 0; attempt < 5; attempt += 1) {
      const [existing] = await db
        .select({ id: enquiries.id })
        .from(enquiries)
        .where(eq(enquiries.reference, reference))
        .limit(1);
      if (!existing) break;
      // Two submissions landing in the same millisecond would otherwise collide.
      const tail = Number(reference.slice(-4)) + 1;
      reference = `${reference.slice(0, -4)}${String(tail).padStart(4, "0")}`;
    }

    await db.insert(enquiries).values({
      reference,
      name: input.name,
      email: input.email,
      phone: input.phone,
      whatsapp: input.whatsapp,
      nationality: input.nationality,
      categoryId: category?.id ?? null,
      serviceId: service?.id ?? null,
      categoryLabel: category?.titleEn ?? "",
      serviceLabel: service?.titleEn ?? "",
      message: input.message,
      details: input.details,
      preferredContact: input.preferredContact,
      sourcePage: input.sourcePage,
      locale: input.locale,
      utm: input.utm,
      status: "new",
    });

    return NextResponse.json({ ok: true, reference });
  } catch (error) {
    console.error("[enquiries] failed to store", error);
    return NextResponse.json(
      { ok: false, message: "We could not save your request. Please try again or reach us on WhatsApp." },
      { status: 500 },
    );
  }
}

/** Never list enquiries publicly — the admin reads them through its own screens. */
export async function GET() {
  return NextResponse.json({ ok: false }, { status: 405 });
}
