import { useQuery } from "@tanstack/react-query";
import { CreditCard } from "lucide-react";
import { endpoints } from "@/lib/api";
import { fmtRelative, fmtRub } from "@/lib/format";

/**
 * Marquee of the most recent settled payments.
 *
 * Driven by the payments endpoint on a short interval rather than purely by the
 * socket: the socket tells us *when* to refetch (ws.ts invalidates the
 * "payments" key on payment:confirmed), while the list itself always comes from
 * the API, so the strip is correct after a reload or a dropped connection too.
 */
export function LivePaymentTicker() {
  const q = useQuery({
    queryKey: ["payments", "ticker"],
    queryFn: () => endpoints.payments(1, 12),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const paid = (q.data?.items ?? []).filter((p) => p.status === "paid");
  if (paid.length === 0) return null;

  // Duplicated once so the -50% keyframe wraps seamlessly.
  const lane = [...paid, ...paid];

  return (
    <div className="card relative overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border-subtle px-4 py-2.5">
        <CreditCard className="h-4 w-4 text-success" />
        <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-fg-subtle">
          Последние оплаты
        </span>
        <span className="pulse-live ml-auto" />
      </div>
      <div className="group relative py-2.5">
        <div className="flex w-max animate-ticker gap-3 group-hover:[animation-play-state:paused]">
          {lane.map((p, i) => (
            <div
              key={`${p.telegram_id}-${p.paid_at ?? p.created_at}-${i}`}
              className="flex shrink-0 items-center gap-2 rounded-xl bg-bg-subtle px-3 py-1.5 text-xs"
            >
              <span className="font-semibold text-success">{fmtRub(p.amount_kopecks)}</span>
              <span className="text-fg-muted">
                {p.username ? "@" + p.username : "id " + p.telegram_id}
              </span>
              <span className="text-fg-subtle">·</span>
              <span className="capitalize text-fg-subtle">{p.provider}</span>
              <span className="text-fg-subtle">{fmtRelative(p.paid_at ?? p.created_at)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
