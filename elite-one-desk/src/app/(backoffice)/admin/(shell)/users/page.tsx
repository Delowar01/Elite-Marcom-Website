import { asc, eq } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { requirePermission } from "@/lib/auth/guard";
import { PERMISSIONS } from "@/lib/auth/permissions";
import { db } from "@/lib/db";
import { permissions as permissionsTable, rolePermissions, roles, users } from "@/lib/db/schema";
import { UsersClient, type RoleRow, type UserRow } from "./users-client";

export const metadata = { title: "Users & roles" };
export const dynamic = "force-dynamic";

export default async function UsersPage() {
  const session = await requirePermission("users.manage", "/admin/users");

  const [userRows, roleRows, grants] = await Promise.all([
    db
      .select({
        id: users.id,
        email: users.email,
        name: users.name,
        roleId: users.roleId,
        roleKey: roles.key,
        roleName: roles.name,
        isActive: users.isActive,
        mustChangePassword: users.mustChangePassword,
        lastLoginAt: users.lastLoginAt,
      })
      .from(users)
      .innerJoin(roles, eq(roles.id, users.roleId))
      .orderBy(asc(roles.id), asc(users.name)),
    db.select().from(roles).orderBy(asc(roles.id)),
    db
      .select({ roleId: rolePermissions.roleId, key: permissionsTable.key })
      .from(rolePermissions)
      .innerJoin(permissionsTable, eq(permissionsTable.id, rolePermissions.permissionId)),
  ]);

  const byRole = new Map<number, string[]>();
  for (const grant of grants) {
    byRole.set(grant.roleId, [...(byRole.get(grant.roleId) ?? []), grant.key]);
  }

  const roleList: RoleRow[] = roleRows.map((role) => ({
    id: role.id,
    key: role.key,
    name: role.name,
    description: role.description,
    permissions: byRole.get(role.id) ?? [],
  }));

  const people: UserRow[] = userRows.map((row) => ({
    ...row,
    lastLoginAt: row.lastLoginAt ? row.lastLoginAt.toISOString() : null,
  }));

  return (
    <>
      <AdminPageHeader
        title="Users & roles"
        description="Permissions are checked on the server for every change, so what a role cannot do, it cannot do — hiding a button is never the control."
      />
      <UsersClient
        csrf={session.csrfToken}
        users={people}
        roles={roleList}
        permissions={PERMISSIONS.map((p) => ({ key: p.key, label: p.label, group: p.group }))}
        currentUserId={session.user.id}
        isOwner={session.user.roleKey === "owner"}
        canManageRoles={session.permissions.has("roles.manage")}
      />
    </>
  );
}
