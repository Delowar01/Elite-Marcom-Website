"use client";

import { AdminForm, Field, SubmitButton } from "@/components/admin/form";
import { ENQUIRY_STATUSES, STATUS_LABEL } from "@/lib/admin/enquiry";
import { addEnquiryNote, updateEnquiry } from "../actions";

export function StatusPanel({
  id,
  csrf,
  status,
  assignedTo,
  assignees,
  readOnly,
}: {
  id: number;
  csrf: string;
  status: string;
  assignedTo: number | null;
  assignees: Array<{ id: number; name: string }>;
  readOnly: boolean;
}) {
  if (readOnly) {
    return (
      <p className="text-[0.8rem] text-muted">
        You have read-only access to enquiries. Ask an administrator for the
        &ldquo;Update enquiries&rdquo; permission to change a status.
      </p>
    );
  }

  return (
    <AdminForm action={updateEnquiry} successMessage="Enquiry updated." guardUnsaved={false}>
      <input type="hidden" name="_csrf" value={csrf} />
      <input type="hidden" name="id" value={id} />
      <div className="space-y-3">
        <Field label="Status" name="status">
          <select id="status" name="status" defaultValue={status} className="admin-select">
            {ENQUIRY_STATUSES.map((key) => (
              <option key={key} value={key}>
                {STATUS_LABEL[key]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Assigned to" name="assignedTo" hint="Who is answering this one.">
          <select
            id="assignedTo"
            name="assignedTo"
            defaultValue={assignedTo ? String(assignedTo) : ""}
            className="admin-select"
          >
            <option value="">Nobody yet</option>
            {assignees.map((user) => (
              <option key={user.id} value={user.id}>
                {user.name}
              </option>
            ))}
          </select>
        </Field>
        <SubmitButton>Update</SubmitButton>
      </div>
    </AdminForm>
  );
}

export function NotePanel({ id, csrf }: { id: number; csrf: string }) {
  return (
    <AdminForm action={addEnquiryNote} successMessage="Note added." guardUnsaved={false}>
      <input type="hidden" name="_csrf" value={csrf} />
      <input type="hidden" name="id" value={id} />
      <Field
        label="Internal note"
        name="body"
        hint="Only visible in this panel. The customer never sees it."
      >
        <textarea id="body" name="body" rows={3} className="admin-textarea" />
      </Field>
      <div className="mt-3">
        <SubmitButton>Add note</SubmitButton>
      </div>
    </AdminForm>
  );
}
