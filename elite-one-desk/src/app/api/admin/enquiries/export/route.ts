import { and, desc, eq, ilike, or, type SQL } from "drizzle-orm";

import { logActivity } from "@/lib/activity";
import { isEnquiryStatus, STATUS_LABEL } from "@/lib/admin/enquiry";
import { getSession } from "@/lib/auth/session";
import { db } from "@/lib/db";
import { enquiries } from "@/lib/db/schema";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Excel reads a leading `=`, `+`, `-` or `@` in a cell as a formula, and an
 * enquiry is visitor-supplied text. Prefixing an apostrophe keeps the value
 * visible and inert.
 */
function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  const guarded = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;
  return `"${guarded.replace(/"/g, '""')}"`;
}

const COLUMNS = [
  "Reference",
  "Received",
  "Name",
  "Email",
  "Phone",
  "WhatsApp",
  "Nationality",
  "Category",
  "Service",
  "Preferred contact",
  "Status",
  "Language",
  "Source page",
  "Message",
  "Details",
  "Campaign",
] as const;

export async function GET(request: Request) {
  const session = await getSession();
  if (!session || !session.permissions.has("enquiries.export")) {
    return new Response("Not found", { status: 404 });
  }

  const url = new URL(request.url);
  const query = (url.searchParams.get("q") ?? "").trim().slice(0, 120);
  const status = url.searchParams.get("status") ?? "";
  const categoryId = Number(url.searchParams.get("category")) || 0;

  const filters: SQL[] = [];
  if (query) {
    const like = `%${query}%`;
    const match = or(
      ilike(enquiries.reference, like),
      ilike(enquiries.name, like),
      ilike(enquiries.email, like),
      ilike(enquiries.phone, like),
      ilike(enquiries.serviceLabel, like),
      ilike(enquiries.message, like),
    );
    if (match) filters.push(match);
  }
  if (status && isEnquiryStatus(status)) filters.push(eq(enquiries.status, status));
  if (categoryId) filters.push(eq(enquiries.categoryId, categoryId));

  const rows = await db
    .select()
    .from(enquiries)
    .where(filters.length ? and(...filters) : undefined)
    .orderBy(desc(enquiries.createdAt))
    .limit(10000);

  const lines = [COLUMNS.map(csvCell).join(",")];
  for (const row of rows) {
    lines.push(
      [
        row.reference,
        row.createdAt.toISOString(),
        row.name,
        row.email,
        row.phone,
        row.whatsapp,
        row.nationality,
        row.categoryLabel,
        row.serviceLabel,
        row.preferredContact,
        STATUS_LABEL[row.status],
        row.locale,
        row.sourcePage,
        row.message,
        Object.entries(row.details ?? {})
          .map(([k, v]) => `${k}: ${v}`)
          .join(" | "),
        Object.entries(row.utm ?? {})
          .map(([k, v]) => `${k}=${v}`)
          .join(" | "),
      ].map(csvCell).join(","),
    );
  }

  await logActivity(session, {
    action: "enquiry.exported",
    entityType: "enquiry",
    summary: `Exported ${rows.length} enquiries`,
    metadata: { query, status, categoryId },
  });

  const stamp = new Date().toISOString().slice(0, 10);
  return new Response(`﻿${lines.join("\r\n")}`, {
    headers: {
      // The BOM is what makes Excel open a UTF-8 file as UTF-8 — without it,
      // every Arabic name in the export is mojibake.
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": `attachment; filename="elite-one-desk-enquiries-${stamp}.csv"`,
      "cache-control": "no-store",
    },
  });
}
