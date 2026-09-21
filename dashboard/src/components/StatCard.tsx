import { type LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { NO_VALUE } from "./ErrorNote";

interface Props {
  label: string;
  /** ReactNode, not string: pages pass <AnimatedNum/> to count the value up. */
  value: React.ReactNode;
  hint?: string;
  /** Small pill to the right of the number, e.g. a delta. */
  pill?: string;
  icon?: LucideIcon;
  tone?: "default" | "success" | "warning" | "danger" | "accent" | "info";
  loading?: boolean;
  /** Source failed: show a dash, never a fabricated zero. */
  error?: boolean;
}

const TONES: Record<NonNullable<Props["tone"]>, string> = {
  default: "from-bg-elevated to-bg-card",
  accent: "from-accent/10 to-bg-card",
  success: "from-success/10 to-bg-card",
  warning: "from-warning/10 to-bg-card",
  danger: "from-danger/10 to-bg-card",
  info: "from-info/10 to-bg-card",
};

const ICON_TONES: Record<NonNullable<Props["tone"]>, string> = {
  default: "text-fg-muted",
  accent: "text-accent",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  info: "text-info",
};

export function StatCard({
  label,
  value,
  hint,
  pill,
  icon: Icon,
  tone = "default",
  loading,
  error,
}: Props) {
  return (
    <div className="card card-hover relative overflow-hidden p-5 animate-fade-in">
      <div
        className={cn(
          "pointer-events-none absolute inset-0 -z-10 bg-gradient-to-br opacity-60",
          TONES[tone],
        )}
      />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-medium text-fg-muted">
            {label}
          </div>
          <div className="mt-2 flex min-w-0 items-baseline gap-2">
            {loading ? (
              <span className="skeleton inline-block h-8 w-28 rounded-md" />
            ) : error ? (
              <span className="stat-num block text-fg-subtle">{NO_VALUE}</span>
            ) : (
              <span className="stat-num block min-w-0 truncate">{value}</span>
            )}
            {pill && !loading && !error && <span className="stat-pill shrink-0">{pill}</span>}
          </div>
          {hint && !error && (
            <div className="mt-1 truncate text-xs text-fg-muted">{hint}</div>
          )}
        </div>
        {Icon && (
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-bg-elevated/80 ring-1 ring-border">
            <Icon className={cn("h-4 w-4", ICON_TONES[tone])} strokeWidth={2} />
          </div>
        )}
      </div>
    </div>
  );
}

/** Consistent page title block — every page opens with one. */
export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-fg md:text-3xl">
          {title}
        </h1>
        {subtitle && <p className="mt-1 text-sm text-fg-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
