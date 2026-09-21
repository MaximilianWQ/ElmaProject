import { cn } from "@/lib/cn";

/**
 * The ELMA mark.
 *
 * Three left-aligned bars: an abstract Э that also reads as a signal climbing.
 * It carries the product's actual subject (a connection that holds) instead of
 * a stock shield or lightning bolt, and stays legible down to 16px because it
 * is three shapes and nothing else.
 */
export function ElmaMark({
  className,
  tone = "solid",
}: {
  className?: string;
  /** solid: azure tile, white bars. plain: bars only, inherits currentColor. */
  tone?: "solid" | "plain";
}) {
  if (tone === "plain") {
    return (
      <svg viewBox="0 0 24 24" className={className} aria-hidden="true" fill="currentColor">
        <rect x="5" y="6" width="8" height="3" rx="1.5" />
        <rect x="5" y="10.5" width="14" height="3" rx="1.5" />
        <rect x="5" y="15" width="11" height="3" rx="1.5" />
      </svg>
    );
  }
  return (
    <svg
      viewBox="0 0 24 24"
      className={cn("shrink-0", className)}
      aria-hidden="true"
    >
      <rect width="24" height="24" rx="7" fill="#1857D6" />
      <g fill="#fff">
        <rect x="5" y="6" width="8" height="3" rx="1.5" />
        <rect x="5" y="10.5" width="14" height="3" rx="1.5" />
        <rect x="5" y="15" width="11" height="3" rx="1.5" />
      </g>
    </svg>
  );
}

/** Mark plus wordmark, as it appears in the sidebar and on the auth screens. */
export function ElmaLogo({ subtitle = "Консоль" }: { subtitle?: string }) {
  return (
    <div className="flex items-center gap-3">
      <ElmaMark className="h-9 w-9" />
      <div className="min-w-0 leading-tight">
        <div className="text-[15px] font-semibold tracking-[-0.02em] text-fg">ELMA</div>
        <div className="text-xs text-fg-subtle">{subtitle}</div>
      </div>
    </div>
  );
}
