import { useEffect, useState } from "react";
import { useEventStream } from "@/lib/ws";

/** Nothing has arrived for this long -> the stream is probably not alive. */
const QUIET_MS = 10 * 60_000;

/**
 * Corner badge telling the admin whether the live event stream is delivering.
 *
 * The freshness comes from the event's own timestamp rather than from a clock
 * reading taken when it arrived, so there is no derived state to keep in sync —
 * only the ticking "now" that decides when quiet becomes suspicious.
 */
export function LiveIndicator() {
  const events = useEventStream(1);
  const lastTs = events[0]?.ts; // seconds, stamped by the bot

  // Lazy initialiser: Date.now() must not run on every render.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 5000);
    return () => window.clearInterval(t);
  }, []);

  // The bot is idle most of the time, so "no events yet" is not "offline".
  const status: "waiting" | "live" | "quiet" =
    lastTs === undefined ? "waiting" : now - lastTs * 1000 > QUIET_MS ? "quiet" : "live";

  const dot =
    status === "live"
      ? "bg-success animate-breathe"
      : status === "quiet"
      ? "bg-warning"
      : "bg-fg-subtle";

  return (
    <div
      className="pointer-events-none fixed right-3 z-40 flex items-center gap-2 rounded-full border border-border bg-bg-card/85 px-3 py-1.5 text-[11px] font-medium backdrop-blur"
      style={{ bottom: "max(80px, calc(env(safe-area-inset-bottom) + 88px))" }}
      title={
        status === "live"
          ? "События приходят"
          : status === "quiet"
          ? "Давно не было событий"
          : "Ожидание событий"
      }
    >
      <span className={"h-1.5 w-1.5 rounded-full " + dot} />
      <span className={status === "live" ? "text-success" : "text-fg-muted"}>
        {status === "live" ? "Live" : status === "quiet" ? "Тихо" : "…"}
      </span>
    </div>
  );
}
