"use server";

import { and, eq, gt, lt, sql } from "drizzle-orm";
import { revalidatePath } from "next/cache";

import { logActivity } from "@/lib/activity";
import {
  checkbox, fail, field, numberField, ok, optionalId, runAction, type ActionState,
} from "@/lib/admin/actions";
import { guardAction } from "@/lib/auth/guard";
import { TAGS, revalidate } from "@/lib/cache";
import { sanitizeHref } from "@/lib/cms/sanitize";
import { db } from "@/lib/db";
import { navigationItems } from "@/lib/db/schema";

const MENUS = ["header", "footer_services", "footer_company", "footer_legal"] as const;
type Menu = (typeof MENUS)[number];
const isMenu = (value: string): value is Menu => (MENUS as readonly string[]).includes(value);

const refresh = () => {
  revalidate(TAGS.navigation);
  revalidatePath("/admin/navigation");
};

export async function saveNavItem(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("nav-save", async () => {
    const session = await guardAction("navigation.manage", form);
    const id = Number(form.get("id")) || 0;
    const rawMenu = field(form, "menu", 32);
    const menu: Menu = isMenu(rawMenu) ? rawMenu : "header";
    const labelEn = field(form, "labelEn", 120);
    const href = sanitizeHref(field(form, "href", 255));

    if (!labelEn) return fail("Give the link a label.", { labelEn: "Required." });
    if (!href) {
      return fail("That link is not one we can use.", {
        href: "Use a site path like /services, or a full https:// address.",
      });
    }

    const parentId = optionalId(form, "parentId");
    // A link cannot be its own parent, and sub-menus stop at one level: the
    // header has no room for a third, and the markup would not render it.
    if (parentId && parentId === id) return fail("A link cannot sit under itself.");
    if (parentId) {
      const [parent] = await db
        .select({ parentId: navigationItems.parentId })
        .from(navigationItems)
        .where(eq(navigationItems.id, parentId))
        .limit(1);
      if (parent?.parentId) return fail("Sub-menus only go one level deep.");
    }

    const values = {
      menu,
      parentId,
      labelEn,
      labelAr: field(form, "labelAr", 120),
      href,
      sortOrder: numberField(form, "sortOrder", 0),
      isPublished: checkbox(form, "isPublished"),
    };

    if (id) {
      await db.update(navigationItems).set({ ...values, updatedAt: new Date() }).where(eq(navigationItems.id, id));
    } else {
      const [last] = await db
        .select({ n: sql<number>`coalesce(max(${navigationItems.sortOrder}), -1)::int` })
        .from(navigationItems)
        .where(eq(navigationItems.menu, menu));
      await db.insert(navigationItems).values({ ...values, sortOrder: (last?.n ?? -1) + 1 });
    }

    await logActivity(session, {
      action: id ? "navigation.updated" : "navigation.created",
      entityType: "navigation",
      entityId: id || 0,
      summary: `${id ? "Updated" : "Added"} the link “${labelEn}”`,
    });
    refresh();
    return ok(id ? "Link saved." : "Link added.");
  });
}

export async function deleteNavItem(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("nav-delete", async () => {
    const session = await guardAction("navigation.manage", form);
    const id = Number(form.get("id"));
    const [row] = await db.select().from(navigationItems).where(eq(navigationItems.id, id)).limit(1);
    if (!row) return fail("That link no longer exists.");

    const [{ n }] = await db
      .select({ n: sql<number>`count(*)::int` })
      .from(navigationItems)
      .where(eq(navigationItems.parentId, id));
    if (n) return fail(`Remove the ${n} link${n === 1 ? "" : "s"} underneath it first.`);

    await db.delete(navigationItems).where(eq(navigationItems.id, id));
    await logActivity(session, {
      action: "navigation.deleted",
      entityType: "navigation",
      entityId: id,
      summary: `Removed the link “${row.labelEn}”`,
    });
    refresh();
    return ok("Link removed.");
  });
}

export async function moveNavItem(_prev: ActionState, form: FormData): Promise<ActionState> {
  return runAction("nav-move", async () => {
    await guardAction("navigation.manage", form);
    const id = Number(form.get("id"));
    const up = field(form, "direction", 8) === "up";
    const [row] = await db.select().from(navigationItems).where(eq(navigationItems.id, id)).limit(1);
    if (!row) return fail("That link no longer exists.");

    // Reordering happens within a menu and within a parent, so a sub-menu item
    // never jumps out of its group.
    const sameGroup = and(
      eq(navigationItems.menu, row.menu),
      row.parentId
        ? eq(navigationItems.parentId, row.parentId)
        : sql`${navigationItems.parentId} is null`,
      up ? lt(navigationItems.sortOrder, row.sortOrder) : gt(navigationItems.sortOrder, row.sortOrder),
    );

    const [neighbour] = await db
      .select()
      .from(navigationItems)
      .where(sameGroup)
      .orderBy(up ? sql`sort_order desc` : sql`sort_order asc`)
      .limit(1);
    if (!neighbour) return ok();

    await db.transaction(async (tx) => {
      await tx.update(navigationItems).set({ sortOrder: -1 }).where(eq(navigationItems.id, row.id));
      await tx
        .update(navigationItems)
        .set({ sortOrder: row.sortOrder })
        .where(eq(navigationItems.id, neighbour.id));
      await tx
        .update(navigationItems)
        .set({ sortOrder: neighbour.sortOrder })
        .where(eq(navigationItems.id, row.id));
    });
    refresh();
    return ok();
  });
}
