"use client";

import Link from "next/link";

import { InlineAction } from "@/components/admin/form";
import { Icon } from "@/components/ui/icon";
import { moveCategory } from "./actions";

type Row = {
  id: number;
  slug: string;
  titleEn: string;
  taglineEn: string;
  icon: string;
  isPublished: boolean;
  serviceCount: number;
};

export function CategoryRows({ csrf, rows }: { csrf: string; rows: Row[] }) {
  return (
    <div className="admin-card overflow-x-auto">
      <table className="admin-table">
        <thead>
          <tr>
            <th>Category</th>
            <th>Address</th>
            <th>Services</th>
            <th>State</th>
            <th>Order</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.id}>
              <td>
                <span className="flex items-center gap-2.5">
                  <Icon name={row.icon} size={16} className="opacity-70" />
                  <span>
                    <Link
                      href={`/admin/categories/${row.id}`}
                      className="font-semibold text-strong hover:text-[var(--color-peach)]"
                    >
                      {row.titleEn}
                    </Link>
                    <span className="block text-[0.74rem] text-muted">{row.taglineEn}</span>
                  </span>
                </span>
              </td>
              <td className="text-muted" dir="ltr">
                /services/{row.slug}
              </td>
              <td>
                <Link
                  href={`/admin/services?category=${row.id}`}
                  className="text-muted hover:text-strong"
                >
                  {row.serviceCount}
                </Link>
              </td>
              <td>
                <span className="admin-badge" style={{ color: row.isPublished ? "#63c98c" : "#9aa2b5" }}>
                  {row.isPublished ? "Published" : "Hidden"}
                </span>
              </td>
              <td>
                <span className="flex gap-1">
                  <InlineAction
                    action={moveCategory}
                    hidden={{ _csrf: csrf, id: row.id, direction: "up" }}
                    className="contents"
                  >
                    <button
                      type="submit"
                      disabled={index === 0}
                      aria-label="Move up"
                      className="admin-btn admin-btn-sm"
                    >
                      <Icon name="chevronDown" size={11} className="rotate-180" />
                    </button>
                  </InlineAction>
                  <InlineAction
                    action={moveCategory}
                    hidden={{ _csrf: csrf, id: row.id, direction: "down" }}
                    className="contents"
                  >
                    <button
                      type="submit"
                      disabled={index === rows.length - 1}
                      aria-label="Move down"
                      className="admin-btn admin-btn-sm"
                    >
                      <Icon name="chevronDown" size={11} />
                    </button>
                  </InlineAction>
                </span>
              </td>
              <td className="text-end">
                <Link href={`/admin/categories/${row.id}`} className="admin-btn admin-btn-sm">
                  Edit
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
