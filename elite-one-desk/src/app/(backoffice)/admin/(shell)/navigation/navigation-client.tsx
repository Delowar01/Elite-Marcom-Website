"use client";

import { useState } from "react";

import { AdminForm, ConfirmSubmit, Field, InlineAction, SubmitButton } from "@/components/admin/form";
import { Icon } from "@/components/ui/icon";
import { deleteNavItem, moveNavItem, saveNavItem } from "./actions";

export type NavRow = {
  id: number;
  menu: string;
  parentId: number | null;
  labelEn: string;
  labelAr: string;
  href: string;
  sortOrder: number;
  isPublished: boolean;
};

const MENUS = [
  { key: "header", title: "Header menu", note: "The main navigation. Items can have one level of sub-links." },
  { key: "footer_services", title: "Footer — Services", note: "The services column in the footer." },
  { key: "footer_company", title: "Footer — Company", note: "The company column in the footer." },
  { key: "footer_legal", title: "Footer — Legal", note: "The small print row at the very bottom." },
];

export function NavigationClient({ csrf, rows }: { csrf: string; rows: NavRow[] }) {
  const [editing, setEditing] = useState<number | string | null>(null);

  return (
    <div className="space-y-5">
      {MENUS.map((menu) => {
        const inMenu = rows.filter((row) => row.menu === menu.key);
        const roots = inMenu.filter((row) => !row.parentId);
        const parents = roots.map((row) => ({ id: row.id, label: row.labelEn }));

        return (
          <section key={menu.key} className="admin-card p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2>{menu.title}</h2>
                <p className="mt-0.5 text-[0.78rem] text-muted">{menu.note}</p>
              </div>
              <button
                type="button"
                onClick={() => setEditing(editing === `new-${menu.key}` ? null : `new-${menu.key}`)}
                className="admin-btn admin-btn-sm"
              >
                {editing === `new-${menu.key}` ? "Cancel" : "Add link"}
              </button>
            </div>

            {editing === `new-${menu.key}` ? (
              <div className="mb-4 rounded-[var(--radius-sm)] border border-[var(--admin-line)] p-4">
                <NavForm csrf={csrf} row={null} menu={menu.key} parents={parents} />
              </div>
            ) : null}

            {roots.length === 0 ? (
              <p className="text-[0.82rem] text-muted">No links in this menu.</p>
            ) : (
              <ul className="space-y-1.5">
                {roots.map((row, index) => {
                  const children = inMenu.filter((child) => child.parentId === row.id);
                  return (
                    <li key={row.id}>
                      <NavItemRow
                        csrf={csrf}
                        row={row}
                        index={index}
                        total={roots.length}
                        editing={editing}
                        setEditing={setEditing}
                        menu={menu.key}
                        parents={parents.filter((p) => p.id !== row.id)}
                      />
                      {children.length ? (
                        <ul className="ms-6 mt-1.5 space-y-1.5 border-s border-[var(--admin-line)] ps-3">
                          {children.map((child, childIndex) => (
                            <li key={child.id}>
                              <NavItemRow
                                csrf={csrf}
                                row={child}
                                index={childIndex}
                                total={children.length}
                                editing={editing}
                                setEditing={setEditing}
                                menu={menu.key}
                                parents={parents.filter((p) => p.id !== child.id)}
                              />
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}

function NavItemRow({
  csrf,
  row,
  index,
  total,
  editing,
  setEditing,
  menu,
  parents,
}: {
  csrf: string;
  row: NavRow;
  index: number;
  total: number;
  editing: number | string | null;
  setEditing: (value: number | string | null) => void;
  menu: string;
  parents: Array<{ id: number; label: string }>;
}) {
  return (
    <div className="rounded-[var(--radius-sm)] border border-[var(--admin-line)] p-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-strong">{row.labelEn}</span>
        <span className="text-[0.74rem] text-muted" dir="ltr">
          {row.href}
        </span>
        {!row.isPublished ? (
          <span className="admin-badge" style={{ color: "#9aa2b5" }}>
            Hidden
          </span>
        ) : null}

        <div className="ms-auto flex gap-1">
          <InlineAction action={moveNavItem} hidden={{ _csrf: csrf, id: row.id, direction: "up" }}>
            <button type="submit" disabled={index === 0} aria-label="Move up" className="admin-btn admin-btn-sm">
              <Icon name="chevronDown" size={11} className="rotate-180" />
            </button>
          </InlineAction>
          <InlineAction action={moveNavItem} hidden={{ _csrf: csrf, id: row.id, direction: "down" }}>
            <button
              type="submit"
              disabled={index === total - 1}
              aria-label="Move down"
              className="admin-btn admin-btn-sm"
            >
              <Icon name="chevronDown" size={11} />
            </button>
          </InlineAction>
          <button
            type="button"
            onClick={() => setEditing(editing === row.id ? null : row.id)}
            className="admin-btn admin-btn-sm"
          >
            {editing === row.id ? "Close" : "Edit"}
          </button>
          <InlineAction action={deleteNavItem} hidden={{ _csrf: csrf, id: row.id }}>
            <ConfirmSubmit className="admin-btn-sm" message={`Remove the link “${row.labelEn}”?`}>
              <Icon name="trash" size={11} />
              <span className="sr-only">Remove</span>
            </ConfirmSubmit>
          </InlineAction>
        </div>
      </div>

      {editing === row.id ? (
        <div className="mt-3 border-t border-[var(--admin-line)] pt-3">
          <NavForm csrf={csrf} row={row} menu={menu} parents={parents} />
        </div>
      ) : null}
    </div>
  );
}

function NavForm({
  csrf,
  row,
  menu,
  parents,
}: {
  csrf: string;
  row: NavRow | null;
  menu: string;
  parents: Array<{ id: number; label: string }>;
}) {
  const key = row?.id ?? `new-${menu}`;
  return (
    <AdminForm action={saveNavItem} successMessage={row ? "Link saved." : "Link added."}>
      <input type="hidden" name="_csrf" value={csrf} />
      <input type="hidden" name="menu" value={menu} />
      {row ? <input type="hidden" name="id" value={row.id} /> : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Label (English)" name={`labelEn-${key}`}>
          <input id={`labelEn-${key}`} name="labelEn" defaultValue={row?.labelEn ?? ""} required className="admin-input" />
        </Field>
        <Field label="Label (العربية)" name={`labelAr-${key}`}>
          <input id={`labelAr-${key}`} name="labelAr" defaultValue={row?.labelAr ?? ""} dir="rtl" className="admin-input" />
        </Field>
        <Field label="Link" name={`href-${key}`} hint="A site path such as /services, or a full https:// address.">
          <input id={`href-${key}`} name="href" defaultValue={row?.href ?? ""} required dir="ltr" className="admin-input" />
        </Field>
        {menu === "header" ? (
          <Field label="Sits under" name={`parentId-${key}`} hint="Leave empty for a top-level link.">
            <select
              id={`parentId-${key}`}
              name="parentId"
              defaultValue={row?.parentId ? String(row.parentId) : ""}
              className="admin-select"
            >
              <option value="">Top level</option>
              {parents.map((parent) => (
                <option key={parent.id} value={parent.id}>
                  {parent.label}
                </option>
              ))}
            </select>
          </Field>
        ) : (
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
        )}
      </div>

      <label className="mt-3 flex cursor-pointer items-center gap-2 text-[0.82rem]">
        <input
          type="checkbox"
          name="isPublished"
          defaultChecked={row?.isPublished ?? true}
          className="size-4 accent-[var(--color-orange)]"
        />
        Visible on the site
      </label>

      <div className="mt-4">
        <SubmitButton className="admin-btn-sm">{row ? "Save link" : "Add link"}</SubmitButton>
      </div>
    </AdminForm>
  );
}
