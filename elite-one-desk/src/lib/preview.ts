import "server-only";

import { getSession } from "@/lib/auth/session";
import { getPage, getPagePreview, type RenderedPage } from "@/lib/queries/content";

/**
 * Resolves a page for rendering, in draft form when an authorised editor asks
 * for it with `?preview=1`.
 *
 * The flag alone grants nothing: the session is checked on every request, so a
 * visitor who guesses the parameter gets the published page. Using the real
 * public route for preview — rather than a separate renderer — is what makes
 * the preview trustworthy: it is the site, with the same layout, fonts and
 * scripts, reading different values.
 */
export async function resolvePageForRender(
  slug: string,
  searchParams?: Record<string, string | string[] | undefined>,
): Promise<{ page: RenderedPage | null; isPreview: boolean }> {
  const wants = searchParams?.preview === "1" || searchParams?.preview === "true";
  if (!wants) return { page: await getPage(slug), isPreview: false };

  const session = await getSession();
  if (!session?.permissions.has("content.view")) {
    return { page: await getPage(slug), isPreview: false };
  }
  return { page: await getPagePreview(slug), isPreview: true };
}
