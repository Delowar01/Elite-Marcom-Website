"use client";

import Link from "next/link";

import { InlineAction } from "@/components/admin/form";
import { Icon } from "@/components/ui/icon";
import { togglePackage } from "./actions";

type Row = {
  id: number;
  slug: string;
  titleEn: string;
  region: string;
  destinationEn: string;
  durationEn: string;
  isPublished: boolean;
  isFeatured: boolean;
};

export function PackageRows({ csrf, rows }: { csrf: string; rows: Row[] }) {
  return (
    <div className="admin-card overflow-x-auto">
      <table className="admin-table">
        <thead>
          <tr>
            <th>Package</th>
            <th>Region</th>
            <th>Destination</th>
            <th>Duration</th>
            <th>State</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>
                <Link
                  href={`/admin/packages/${row.id}`}
                  className="font-semibold text-strong hover:text-[var(--color-peach)]"
                >
                  {row.titleEn}
                </Link>
                {row.isFeatured ? (
                  <span className="ms-2 admin-badge" style={{ color: "var(--color-peach)" }}>
                    Featured
                  </span>
                ) : null}
                <span className="block text-[0.72rem] text-muted" dir="ltr">
                  /packages/{row.slug}
                </span>
              </td>
              <td className="text-muted capitalize">{row.region}</td>
              <td className="text-muted">{row.destinationEn || "—"}</td>
              <td className="text-muted">{row.durationEn || "—"}</td>
              <td>
                <span className="admin-badge" style={{ color: row.isPublished ? "#63c98c" : "#9aa2b5" }}>
                  {row.isPublished ? "Published" : "Hidden"}
                </span>
              </td>
              <td className="text-end">
                <span className="flex justify-end gap-1.5">
                  <InlineAction action={togglePackage} hidden={{ _csrf: csrf, id: row.id }}>
                    <button
                      type="submit"
                      className="admin-btn admin-btn-sm"
                      title={row.isPublished ? "Unpublish" : "Publish"}
                    >
                      <Icon name={row.isPublished ? "eyeOff" : "eye"} size={12} />
                    </button>
                  </InlineAction>
                  <Link href={`/admin/packages/${row.id}`} className="admin-btn admin-btn-sm">
                    Edit
                  </Link>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
