import Link from "next/link";

import { Icon } from "@/components/ui/icon";
import { getDictionary } from "@/lib/i18n/dictionary";

/**
 * Rendered inside the public layout, so a lost visitor keeps the header, the
 * menu and the language switch. Copy is English here because `not-found` cannot
 * read route params — the links still resolve correctly for both editions.
 */
export default function NotFound() {
  const dict = getDictionary("en");
  const links = [
    { href: "/services", label: "All services" },
    { href: "/services/business-setup", label: "Business setup" },
    { href: "/packages", label: "Travel packages" },
    { href: "/contact", label: "Contact us" },
  ];

  return (
    <div className="shell flex min-h-[70vh] flex-col justify-center py-[clamp(5rem,10vw,9rem)]">
      <p className="eyebrow">404</p>
      <h1 className="mt-5 max-w-2xl text-[length:var(--text-h1)]">{dict.errors.notFoundTitle}</h1>
      <p className="lede mt-4 max-w-xl">{dict.errors.notFoundBody}</p>

      <ul className="mt-9 flex flex-wrap gap-2">
        {links.map((link) => (
          <li key={link.href}>
            <Link href={link.href} className="btn btn-ghost btn-sm">
              {link.label}
            </Link>
          </li>
        ))}
      </ul>

      <div className="mt-8">
        <Link href="/" className="link-underline">
          {dict.errors.goHome}
          <Icon name="arrowRight" size={15} className="flip-rtl" />
        </Link>
      </div>
    </div>
  );
}
