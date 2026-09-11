import { Icon } from "@/components/ui/icon";

/**
 * Rendered only when an owner has switched WhatsApp on *and* entered a number —
 * `whatsappLink()` returns null otherwise, so there is never a button that
 * opens an empty chat.
 */
export function WhatsappFloat({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={label}
      className="no-print group fixed bottom-5 z-40 flex size-13 items-center justify-center rounded-full bg-[#25d366] text-[#07321a] shadow-[0_14px_34px_-10px_rgba(37,211,102,0.6)] transition-transform duration-300 hover:scale-105 focus-visible:scale-105"
      style={{ insetInlineEnd: "1.25rem" }}
    >
      <span
        aria-hidden
        className="absolute inset-0 rounded-full bg-[#25d366] opacity-0 motion-safe:animate-[eod-pulse-ring_2.6s_ease-out_infinite] group-hover:opacity-100"
        style={{ animationPlayState: "running" }}
      />
      <Icon name="whatsapp" size={26} strokeWidth={1.6} className="relative" />
    </a>
  );
}
