"use client";

import { useState } from "react";

import { AdminForm, ConfirmSubmit, Field, InlineAction, SubmitButton } from "@/components/admin/form";
import { Icon } from "@/components/ui/icon";
import { createUser, deleteUser, resetUserPassword, saveRolePermissions, updateUser } from "./actions";

export type UserRow = {
  id: number;
  email: string;
  name: string;
  roleId: number;
  roleKey: string;
  roleName: string;
  isActive: boolean;
  mustChangePassword: boolean;
  lastLoginAt: string | null;
};

export type RoleRow = {
  id: number;
  key: string;
  name: string;
  description: string;
  permissions: string[];
};

export type PermissionRow = { key: string; label: string; group: string };

export function UsersClient({
  csrf,
  users,
  roles,
  permissions,
  currentUserId,
  isOwner,
  canManageRoles,
}: {
  csrf: string;
  users: UserRow[];
  roles: RoleRow[];
  permissions: PermissionRow[];
  currentUserId: number;
  isOwner: boolean;
  canManageRoles: boolean;
}) {
  const [tab, setTab] = useState<"people" | "roles">("people");
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const assignable = isOwner ? roles : roles.filter((role) => role.key !== "owner");

  return (
    <>
      <nav aria-label="Sections" className="mb-4 flex gap-1.5">
        <button
          type="button"
          onClick={() => setTab("people")}
          className="admin-btn admin-btn-sm"
          style={tab === "people" ? { borderColor: "var(--color-orange)" } : undefined}
        >
          People ({users.length})
        </button>
        {canManageRoles ? (
          <button
            type="button"
            onClick={() => setTab("roles")}
            className="admin-btn admin-btn-sm"
            style={tab === "roles" ? { borderColor: "var(--color-orange)" } : undefined}
          >
            Roles &amp; permissions
          </button>
        ) : null}
      </nav>

      {tab === "people" ? (
        <div className="space-y-5">
          <div className="admin-card p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2>{editing === "new" ? "Add someone" : "People"}</h2>
                <p className="mt-0.5 text-[0.78rem] text-muted">
                  Each account has one role. A role decides what its holder can open and change.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setEditing(editing === "new" ? null : "new")}
                className="admin-btn admin-btn-sm"
              >
                {editing === "new" ? "Cancel" : "Add person"}
              </button>
            </div>

            {editing === "new" ? (
              <AdminForm action={createUser} successMessage="Account created.">
                <input type="hidden" name="_csrf" value={csrf} />
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Name" name="new-name">
                    <input id="new-name" name="name" required className="admin-input" />
                  </Field>
                  <Field label="Email address" name="new-email">
                    <input id="new-email" name="email" type="email" required dir="ltr" className="admin-input" />
                  </Field>
                  <Field label="Role" name="new-roleId">
                    <select id="new-roleId" name="roleId" className="admin-select" defaultValue="">
                      <option value="" disabled>
                        Choose a role…
                      </option>
                      {assignable.map((role) => (
                        <option key={role.id} value={role.id}>
                          {role.name} — {role.description}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field
                    label="Temporary password"
                    name="new-password"
                    hint="At least 12 characters with upper case, lower case and a digit."
                  >
                    <input
                      id="new-password"
                      name="password"
                      type="text"
                      required
                      autoComplete="new-password"
                      dir="ltr"
                      className="admin-input"
                    />
                  </Field>
                </div>
                <div className="mt-4">
                  <SubmitButton>Create account</SubmitButton>
                </div>
              </AdminForm>
            ) : null}
          </div>

          <ul className="space-y-2.5">
            {users.map((user) => (
              <li key={user.id} className="admin-card p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-strong">{user.name}</span>
                  <span className="text-[0.78rem] text-muted" dir="ltr">
                    {user.email}
                  </span>
                  <span className="admin-badge" style={{ color: "var(--color-peach)" }}>
                    {user.roleName}
                  </span>
                  {!user.isActive ? (
                    <span className="admin-badge" style={{ color: "#ff8a80" }}>
                      Deactivated
                    </span>
                  ) : null}
                  {user.id === currentUserId ? (
                    <span className="admin-badge" style={{ color: "var(--text-muted)" }}>
                      You
                    </span>
                  ) : null}
                  <span className="ms-auto flex gap-1.5">
                    <button
                      type="button"
                      onClick={() => setEditing(editing === user.id ? null : user.id)}
                      className="admin-btn admin-btn-sm"
                    >
                      {editing === user.id ? "Close" : "Manage"}
                    </button>
                    {user.id !== currentUserId ? (
                      <InlineAction action={deleteUser} hidden={{ _csrf: csrf, id: user.id }}>
                        <ConfirmSubmit
                          className="admin-btn-sm"
                          message={`Delete the account for ${user.email}? Their activity-log entries are kept.`}
                        >
                          <Icon name="trash" size={11} />
                          <span className="sr-only">Delete</span>
                        </ConfirmSubmit>
                      </InlineAction>
                    ) : null}
                  </span>
                </div>

                <p className="mt-1 text-[0.74rem] text-muted">
                  {user.lastLoginAt
                    ? `Last signed in ${new Date(user.lastLoginAt).toLocaleString("en-GB", {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })}`
                    : "Has never signed in"}
                </p>

                {editing === user.id ? (
                  <div className="mt-4 grid gap-4 border-t border-[var(--admin-line)] pt-4 lg:grid-cols-2">
                    <AdminForm action={updateUser} successMessage="Account updated.">
                      <input type="hidden" name="_csrf" value={csrf} />
                      <input type="hidden" name="id" value={user.id} />
                      <div className="space-y-3">
                        <Field label="Name" name={`name-${user.id}`}>
                          <input
                            id={`name-${user.id}`}
                            name="name"
                            defaultValue={user.name}
                            required
                            className="admin-input"
                          />
                        </Field>
                        <Field label="Role" name={`roleId-${user.id}`}>
                          <select
                            id={`roleId-${user.id}`}
                            name="roleId"
                            defaultValue={String(user.roleId)}
                            className="admin-select"
                          >
                            {assignable.map((role) => (
                              <option key={role.id} value={role.id}>
                                {role.name}
                              </option>
                            ))}
                          </select>
                        </Field>
                        <label className="flex cursor-pointer items-center gap-2 text-[0.82rem]">
                          <input
                            type="checkbox"
                            name="isActive"
                            defaultChecked={user.isActive}
                            disabled={user.id === currentUserId}
                            className="size-4 accent-[var(--color-orange)]"
                          />
                          Active — can sign in
                        </label>
                        <SubmitButton className="admin-btn-sm">Save</SubmitButton>
                      </div>
                    </AdminForm>

                    <AdminForm action={resetUserPassword} successMessage="Password reset.">
                      <input type="hidden" name="_csrf" value={csrf} />
                      <input type="hidden" name="id" value={user.id} />
                      <Field
                        label="Set a new password"
                        name={`password-${user.id}`}
                        hint="Signs every session for this account out, including on other devices."
                      >
                        <input
                          id={`password-${user.id}`}
                          name="password"
                          type="text"
                          autoComplete="new-password"
                          dir="ltr"
                          className="admin-input"
                        />
                      </Field>
                      <div className="mt-3">
                        <SubmitButton className="admin-btn-sm" variant="ghost">
                          Reset password
                        </SubmitButton>
                      </div>
                    </AdminForm>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {tab === "roles" && canManageRoles ? (
        <div className="space-y-5">
          {roles.map((role) => (
            <section key={role.id} className="admin-card p-5">
              <h2 className="mb-1">{role.name}</h2>
              <p className="mb-4 text-[0.8rem] text-muted">{role.description}</p>

              {role.key === "owner" ? (
                <p className="text-[0.82rem] text-muted">
                  The owner role always holds every permission — it is the way back in if another
                  role is narrowed too far.
                </p>
              ) : (
                <AdminForm action={saveRolePermissions} successMessage="Permissions saved.">
                  <input type="hidden" name="_csrf" value={csrf} />
                  <input type="hidden" name="roleId" value={role.id} />
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {Array.from(new Set(permissions.map((p) => p.group))).map((group) => (
                      <div key={group}>
                        <p className="admin-label">{group}</p>
                        <div className="space-y-1.5">
                          {permissions
                            .filter((p) => p.group === group)
                            .map((permission) => (
                              <label
                                key={permission.key}
                                className="flex cursor-pointer items-start gap-2 text-[0.8rem]"
                              >
                                <input
                                  type="checkbox"
                                  name={`perm:${permission.key}`}
                                  defaultChecked={role.permissions.includes(permission.key)}
                                  className="mt-0.5 size-3.5 accent-[var(--color-orange)]"
                                />
                                {permission.label}
                              </label>
                            ))}
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-5">
                    <SubmitButton className="admin-btn-sm">Save {role.name} permissions</SubmitButton>
                  </div>
                </AdminForm>
              )}
            </section>
          ))}
        </div>
      ) : null}
    </>
  );
}
