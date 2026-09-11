import { redirect } from "next/navigation";

import { Logo } from "@/components/ui/logo";
import { getSession } from "@/lib/auth/session";
import { LoginForm } from "./login-form";

export const metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  // Already signed in? There is nothing to do on this page.
  if (await getSession()) redirect("/admin");

  const { next } = await searchParams;
  const target = next && next.startsWith("/admin") && !next.startsWith("//") ? next : "/admin";

  return (
    <div className="flex min-h-dvh items-center justify-center p-5">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <Logo height={44} priority />
        </div>

        <div className="admin-card p-7">
          <h1 className="mb-1">Sign in</h1>
          <p className="mb-6 text-[0.82rem] text-muted">
            Elite One Desk administration.
          </p>
          <LoginForm next={target} />
        </div>

        <p className="mt-6 text-center text-[0.75rem] text-muted">
          Access is limited to authorised staff. Sign-in attempts are recorded.
        </p>
      </div>
    </div>
  );
}
