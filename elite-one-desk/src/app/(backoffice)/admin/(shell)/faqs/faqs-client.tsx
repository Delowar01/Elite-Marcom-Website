"use client";

import { useState } from "react";

import { AdminForm, ConfirmSubmit, Field, InlineAction, SubmitButton } from "@/components/admin/form";
import { Icon } from "@/components/ui/icon";
import { deleteFaq, saveFaq } from "./actions";

export type FaqRow = {
  id: number;
  scope: string;
  categoryId: number | null;
  serviceId: number | null;
  questionEn: string;
  questionAr: string;
  answerEn: string;
  answerAr: string;
  isPublished: boolean;
  sortOrder: number;
  attachedTo: string;
};

type Option = { id: number; label: string };

export function FaqsClient({
  csrf,
  rows,
  categories,
  services,
}: {
  csrf: string;
  rows: FaqRow[];
  categories: Option[];
  services: Option[];
}) {
  const [editing, setEditing] = useState<number | "new" | null>(rows.length ? null : "new");
  const [filter, setFilter] = useState("all");

  const visible = filter === "all" ? rows : rows.filter((row) => row.scope === filter);

  return (
    <div className="space-y-5">
      <div className="admin-card p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2>{editing === "new" ? "Add a question" : "Questions"}</h2>
            <p className="mt-0.5 text-[0.78rem] text-muted">
              Global questions appear on the homepage and the contact page. Attach a question to a
              category or a service and it shows on that page instead.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setEditing(editing === "new" ? null : "new")}
            className="admin-btn admin-btn-sm"
          >
            {editing === "new" ? "Cancel" : "Add question"}
          </button>
        </div>
        {editing === "new" ? (
          <FaqForm csrf={csrf} row={null} categories={categories} services={services} />
        ) : null}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {[
          { key: "all", label: `All (${rows.length})` },
          { key: "global", label: `Global (${rows.filter((r) => r.scope === "global").length})` },
          { key: "category", label: `By category (${rows.filter((r) => r.scope === "category").length})` },
          { key: "service", label: `By service (${rows.filter((r) => r.scope === "service").length})` },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setFilter(tab.key)}
            className="admin-btn admin-btn-sm"
            style={filter === tab.key ? { borderColor: "var(--color-orange)" } : undefined}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <p className="admin-card px-4 py-12 text-center text-[0.85rem] text-muted">
          Nothing here yet.
        </p>
      ) : (
        <ul className="space-y-2.5">
          {visible.map((row) => (
            <li key={row.id} className="admin-card p-4">
              <div className="flex flex-wrap items-start gap-3">
                <div className="min-w-52 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-strong">{row.questionEn}</span>
                    <span className="admin-badge" style={{ color: "var(--text-muted)" }}>
                      {row.attachedTo}
                    </span>
                    {!row.isPublished ? (
                      <span className="admin-badge" style={{ color: "#9aa2b5" }}>
                        Unpublished
                      </span>
                    ) : null}
                  </div>
                  <div
                    className="mt-1 line-clamp-2 text-[0.8rem] text-muted [&_a]:underline"
                    dangerouslySetInnerHTML={{ __html: row.answerEn }}
                  />
                </div>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => setEditing(editing === row.id ? null : row.id)}
                    className="admin-btn admin-btn-sm"
                  >
                    {editing === row.id ? "Close" : "Edit"}
                  </button>
                  <InlineAction action={deleteFaq} hidden={{ _csrf: csrf, id: row.id }}>
                    <ConfirmSubmit className="admin-btn-sm" message={`Delete “${row.questionEn}”?`}>
                      <Icon name="trash" size={12} />
                      <span className="sr-only">Delete</span>
                    </ConfirmSubmit>
                  </InlineAction>
                </div>
              </div>
              {editing === row.id ? (
                <div className="mt-4 border-t border-[var(--admin-line)] pt-4">
                  <FaqForm csrf={csrf} row={row} categories={categories} services={services} />
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FaqForm({
  csrf,
  row,
  categories,
  services,
}: {
  csrf: string;
  row: FaqRow | null;
  categories: Option[];
  services: Option[];
}) {
  const [scope, setScope] = useState(row?.scope ?? "global");
  const key = row?.id ?? "new";

  return (
    <AdminForm action={saveFaq} successMessage={row ? "Question saved." : "Question added."}>
      <input type="hidden" name="_csrf" value={csrf} />
      {row ? <input type="hidden" name="id" value={row.id} /> : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Question (English)" name={`questionEn-${key}`}>
          <input
            id={`questionEn-${key}`}
            name="questionEn"
            defaultValue={row?.questionEn ?? ""}
            required
            className="admin-input"
          />
        </Field>
        <Field label="Question (العربية)" name={`questionAr-${key}`}>
          <input
            id={`questionAr-${key}`}
            name="questionAr"
            defaultValue={row?.questionAr ?? ""}
            dir="rtl"
            className="admin-input"
          />
        </Field>

        <Field
          label="Answer (English)"
          name={`answerEn-${key}`}
          hint="Paragraphs, links and lists are kept; anything else becomes plain text."
        >
          <textarea
            id={`answerEn-${key}`}
            name="answerEn"
            rows={4}
            defaultValue={row?.answerEn ?? ""}
            className="admin-textarea"
          />
        </Field>
        <Field label="Answer (العربية)" name={`answerAr-${key}`}>
          <textarea
            id={`answerAr-${key}`}
            name="answerAr"
            rows={4}
            defaultValue={row?.answerAr ?? ""}
            dir="rtl"
            className="admin-textarea"
          />
        </Field>

        <Field label="Where it appears" name={`scope-${key}`}>
          <select
            id={`scope-${key}`}
            name="scope"
            value={scope}
            onChange={(event) => setScope(event.target.value)}
            className="admin-select"
          >
            <option value="global">Everywhere (homepage and contact)</option>
            <option value="category">On one category page</option>
            <option value="service">On one service page</option>
          </select>
        </Field>

        {scope === "category" ? (
          <Field label="Category" name={`categoryId-${key}`}>
            <select
              id={`categoryId-${key}`}
              name="categoryId"
              defaultValue={row?.categoryId ? String(row.categoryId) : ""}
              className="admin-select"
            >
              <option value="">Choose…</option>
              {categories.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>
        ) : null}

        {scope === "service" ? (
          <Field label="Service" name={`serviceId-${key}`}>
            <select
              id={`serviceId-${key}`}
              name="serviceId"
              defaultValue={row?.serviceId ? String(row.serviceId) : ""}
              className="admin-select"
            >
              <option value="">Choose…</option>
              {services.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </Field>
        ) : null}

        <Field label="Order" name={`sortOrder-${key}`}>
          <input
            id={`sortOrder-${key}`}
            name="sortOrder"
            type="number"
            min={0}
            defaultValue={row?.sortOrder ?? 0}
            className="admin-input"
          />
        </Field>
      </div>

      <label className="mt-4 flex cursor-pointer items-center gap-2 text-[0.82rem]">
        <input
          type="checkbox"
          name="isPublished"
          defaultChecked={row?.isPublished ?? true}
          className="size-4 accent-[var(--color-orange)]"
        />
        Published
      </label>

      <div className="mt-5">
        <SubmitButton>{row ? "Save question" : "Add question"}</SubmitButton>
      </div>
    </AdminForm>
  );
}
