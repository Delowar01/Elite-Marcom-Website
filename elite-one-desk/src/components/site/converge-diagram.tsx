import { Icon } from "@/components/ui/icon";
import { Reveal } from "./reveal";

/**
 * "One Desk. Multiple Solutions." — several service paths resolving into one
 * point of contact.
 *
 * The labels are real HTML in a list, so the meaning survives without the
 * picture; the SVG only carries the lines between them, and it mirrors as a
 * whole under RTL because a converging line has no text to flip back.
 */
export function ConvergeDiagram({ paths, deskLabel }: { paths: string[]; deskLabel: string }) {
  const list = paths.slice(0, 6);
  if (!list.length) return null;

  const height = 340;
  const step = height / (list.length + 1);

  return (
    <Reveal variant="fade" className="relative">
      <div className="relative grid items-center gap-6 sm:grid-cols-[minmax(0,1fr)_auto]">
        <svg
          viewBox={`0 0 420 ${height}`}
          className="pointer-events-none absolute inset-0 hidden size-full rtl:-scale-x-100 sm:block"
          aria-hidden="true"
          preserveAspectRatio="none"
        >
          {list.map((_, index) => {
            const y = step * (index + 1);
            return (
              <path
                key={index}
                className="converge-path"
                d={`M8 ${y} C 170 ${y} 210 ${height / 2} 404 ${height / 2}`}
                fill="none"
                stroke="var(--color-warm)"
                strokeOpacity="0.22"
                strokeWidth="1"
                pathLength={1}
                style={{ ["--converge-delay" as string]: `${index * 130}ms` }}
              />
            );
          })}
          {/* One lit trace, so the eye is told which way the paths run. */}
          <path
            className="converge-pulse"
            d={`M8 ${step} C 170 ${step} 210 ${height / 2} 404 ${height / 2}`}
            fill="none"
            stroke="var(--color-orange)"
            strokeWidth="1.5"
            strokeLinecap="round"
            pathLength={1}
          />
        </svg>

        <ul className="relative z-10 flex flex-col gap-3">
          {list.map((label) => (
            <li key={label}>
              <span className="inline-flex items-center gap-2.5 rounded-full border border-line bg-[color-mix(in_oklab,var(--color-ink-700)_75%,transparent)] py-2 ps-3 pe-4 text-small text-body backdrop-blur-sm">
                <span
                  className="size-1.5 rounded-full"
                  style={{ background: "var(--color-peach)" }}
                  aria-hidden
                />
                {label}
              </span>
            </li>
          ))}
        </ul>

        <div className="relative z-10 mx-auto sm:mx-0">
          <div
            className="flex size-28 flex-col items-center justify-center gap-1.5 rounded-full border text-center sm:size-32"
            style={{
              borderColor: "color-mix(in oklab, var(--color-orange) 55%, transparent)",
              background:
                "radial-gradient(circle at 50% 35%, color-mix(in oklab, var(--color-orange) 20%, transparent), color-mix(in oklab, var(--color-ink-700) 92%, transparent))",
            }}
          >
            <Icon name="desk" size={26} style={{ color: "var(--color-peach)" }} />
            <span className="px-3 font-display text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-strong rtl:tracking-normal">
              {deskLabel}
            </span>
          </div>
        </div>
      </div>
    </Reveal>
  );
}
