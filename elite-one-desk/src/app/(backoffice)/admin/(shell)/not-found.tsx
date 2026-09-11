import Link from "next/link";

export default function AdminNotFound() {
  return (
    <div className="admin-card flex flex-col items-start gap-3 p-8">
      <h1>That screen does not exist</h1>
      <p className="text-[0.85rem] text-muted">
        The address may have changed, or the record may have been deleted.
      </p>
      <Link href="/admin" className="admin-btn admin-btn-primary">
        Back to the dashboard
      </Link>
    </div>
  );
}
