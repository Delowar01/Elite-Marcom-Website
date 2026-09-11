import Link from "next/link";
import { notFound } from "next/navigation";
import { asc, eq } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { Icon } from "@/components/ui/icon";
import { CONTACT_LABEL, STATUS_LABEL, STATUS_TONE } from "@/lib/admin/enquiry";
import { requirePermission } from "@/lib/auth/guard";
import { db } from "@/lib/db";
import { enquiries, enquiryNotes, users } from "@/lib/db/schema";
import { fieldsForPreset } from "@/lib/forms/presets";
import { getDictionary } from "@/lib/i18n/dictionary";
import { NotePanel, StatusPanel } from "./enquiry-panels";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [row] = await db
    .select({ reference: enquiries.reference })
    .from(enquiries)
    .where(eq(enquiries.id, Number(id) || 0))
    .limit(1);
  return { title: row ? `Enquiry ${row.reference}` : "Enquiry" };
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  if (!children) return null;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-0.5 border-b border-[var(--admin-line)] py-2.5 last:border-b-0">
      <dt className="w-40 shrink-0 text-[0.76rem] text-muted">{label}</dt>
      <dd className="min-w-0 flex-1 text-[0.86rem] text-strong">{children}</dd>
    </div>
  );
}

export default async function EnquiryDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const session = await requirePermission("enquiries.view");
  const { id: rawId } = await params;
  const id = Number(rawId) || 0;

  const [row] = await db.select().from(enquiries).where(eq(enquiries.id, id)).limit(1);
  if (!row) notFound();

  const [notes, staff] = await Promise.all([
    db
      .select()
      .from(enquiryNotes)
      .where(eq(enquiryNotes.enquiryId, id))
      .orderBy(asc(enquiryNotes.createdAt)),
    db
      .select({ id: users.id, name: users.name })
      .from(users)
      .where(eq(users.isActive, true))
      .orderBy(asc(users.name)),
  ]);

  // Opening a record is what marks it read — no separate button to forget.
  // Written directly rather than through the action: a Server Action cannot be
  // invoked while a page is rendering, and there is nothing here to revalidate
  // that this very render is not already producing.
  if (!row.isRead) {
    await db.update(enquiries).set({ isRead: true }).where(eq(enquiries.id, id));
  }

  const dict = getDictionary("en");
  const presetFields = fieldsForPreset(
    row.details && Object.keys(row.details).length ? detectPreset(row.details) : "general",
  );
  const detailEntries = Object.entries(row.details ?? {});
  const utmEntries = Object.entries(row.utm ?? {});
  const assignee = staff.find((s) => s.id === row.assignedTo);

  return (
    <>
      <AdminPageHeader
        title={row.reference}
        description={`Received ${row.createdAt.toLocaleString("en-GB", { dateStyle: "full", timeStyle: "short" })}`}
        crumbs={[
          { label: "Enquiries", href: "/admin/enquiries" },
          { label: row.reference },
        ]}
        actions={
          <>
            <span className="admin-badge" style={{ color: STATUS_TONE[row.status] }}>
              {STATUS_LABEL[row.status]}
            </span>
            <Link href="/admin/enquiries" className="admin-btn">
              Back to list
            </Link>
          </>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <div className="space-y-5">
          <section className="admin-card p-5">
            <h2 className="mb-3">Customer</h2>
            <dl>
              <Row label="Name">{row.name}</Row>
              <Row label="Phone">
                {row.phone ? (
                  <a href={`tel:${row.phone}`} dir="ltr" className="hover:text-[var(--color-peach)]">
                    {row.phone}
                  </a>
                ) : null}
              </Row>
              <Row label="WhatsApp">
                {row.whatsapp ? (
                  <a
                    href={`https://wa.me/${row.whatsapp.replace(/\D/g, "")}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    dir="ltr"
                    className="inline-flex items-center gap-1.5 hover:text-[var(--color-peach)]"
                  >
                    {row.whatsapp}
                    <Icon name="arrowUpRight" size={12} />
                  </a>
                ) : null}
              </Row>
              <Row label="Email">
                {row.email ? (
                  <a href={`mailto:${row.email}`} className="hover:text-[var(--color-peach)]">
                    {row.email}
                  </a>
                ) : null}
              </Row>
              <Row label="Nationality">{row.nationality}</Row>
              <Row label="Prefers">{CONTACT_LABEL[row.preferredContact]}</Row>
              <Row label="Language">{row.locale === "ar" ? "Arabic" : "English"}</Row>
            </dl>
          </section>

          <section className="admin-card p-5">
            <h2 className="mb-3">Request</h2>
            <dl>
              <Row label="Category">{row.categoryLabel}</Row>
              <Row label="Service">{row.serviceLabel}</Row>
              {detailEntries.map(([key, value]) => {
                const known = presetFields.find((f) => f.name === key);
                return (
                  <Row key={key} label={known ? known.label(dict) : humanise(key)}>
                    {value}
                  </Row>
                );
              })}
            </dl>
            {row.message ? (
              <div className="mt-4">
                <p className="admin-label">Message</p>
                <p className="whitespace-pre-wrap rounded-[var(--radius-sm)] border border-[var(--admin-line)] bg-[color-mix(in_oklab,#05041a_45%,transparent)] p-3.5 text-[0.86rem] leading-relaxed text-strong">
                  {row.message}
                </p>
              </div>
            ) : null}
          </section>

          <section className="admin-card p-5">
            <h2 className="mb-3">Internal notes</h2>
            {notes.length ? (
              <ul className="mb-5 space-y-3">
                {notes.map((note) => (
                  <li
                    key={note.id}
                    className="rounded-[var(--radius-sm)] border border-[var(--admin-line)] p-3.5"
                  >
                    <p className="mb-1 flex flex-wrap items-baseline gap-2 text-[0.74rem] text-muted">
                      <span className="font-semibold text-strong">{note.authorName || "Someone"}</span>
                      {note.createdAt.toLocaleString("en-GB", {
                        day: "numeric",
                        month: "short",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                    <p className="whitespace-pre-wrap text-[0.85rem] text-body">{note.body}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mb-5 text-[0.82rem] text-muted">No notes yet.</p>
            )}
            {session.permissions.has("enquiries.manage") ? (
              <NotePanel id={id} csrf={session.csrfToken} />
            ) : null}
          </section>
        </div>

        <div className="space-y-5">
          <section className="admin-card p-5">
            <h2 className="mb-3">Handling</h2>
            <StatusPanel
              id={id}
              csrf={session.csrfToken}
              status={row.status}
              assignedTo={row.assignedTo}
              assignees={staff}
              readOnly={!session.permissions.has("enquiries.manage")}
            />
            {assignee ? (
              <p className="mt-3 text-[0.78rem] text-muted">
                Currently with <span className="text-strong">{assignee.name}</span>.
              </p>
            ) : null}
          </section>

          <section className="admin-card p-5">
            <h2 className="mb-3">Where it came from</h2>
            <dl>
              <Row label="Page">{row.sourcePage || "—"}</Row>
              {utmEntries.length ? (
                utmEntries.map(([key, value]) => (
                  <Row key={key} label={key}>
                    {value}
                  </Row>
                ))
              ) : (
                <Row label="Campaign">No campaign parameters</Row>
              )}
            </dl>
          </section>
        </div>
      </div>
    </>
  );
}

/** The preset is not stored on the row, so it is inferred from the keys present. */
function detectPreset(details: Record<string, string>): string {
  if ("destinationCountry" in details || "purpose" in details) return "visa";
  if ("businessActivity" in details || "investorLicence" in details) return "business";
  if ("serviceRequired" in details || "employees" in details) return "iqama";
  if ("destination" in details || "travelDates" in details) return "travel";
  return "general";
}

const humanise = (key: string) =>
  key.replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase());
