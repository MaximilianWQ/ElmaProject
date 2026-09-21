import { useEffect, useState } from "react";
import { useEventStream } from "@/lib/ws";

/**
 * Corner badge telling the admin whether the live event socket is actually
 * delivering. Our `useEventStream` returns the buffered events rather than
 * taking a callback, so "a beat arrived" is simply the newest event changing.
 */
export function LiveIndicator() {
  const events = useEventStream(1);
  const newest = events[0]?.ts;
  const [lastBeat, setLastBeat] = useState<number | null>(null);

  useEffect(() => {
    if (newest !== undefined) setLastBeat(Date.now());
  }, [newest]);

  // The bot is idle most of the time, so "no events" is not "offline" —
  // only go red once nothing has arrived for a long while after a first beat.
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 5000);
    return () => window.clearInterval(t);
  }, []);

  const status: "waiting" | "live" | "stale" =
    lastBeat === null ? "waiting" : now - lastBeat > 10 * 60_000 ? "stale" : "live";

  const dot =
    status === "live"
      ? "bg-success animate-pulse-live"
      : status === "stale"
      ? "bg-warning"
      : "bg-fg-subtle";

  return (
    <div
      className="pointer-events-none fixed right-3 z-40 flex items-center gap-2 rounded-full border border-border bg-bg-card/80 px-3 py-1.5 text-[11px] font-medium backdrop-blur"
      style={{ bottom: "max(80px, calc(env(safe-area-inset-bottom) + 88px))" }}
      title={
        status === "live"
          ? "События приходят"
          : status === "stale"
          ? "Давно не было событий"
          : "Ожидание событий"
      }
    >
      <span className={"h-1.5 w-1.5 rounded-full " + dot} />
      <span className={status === "live" ? "text-success" : "text-fg-muted"}>
        {status === "live" ? "Live" : status === "stale" ? "Тихо" : "…"}
      </span>
    </div>
  );
}
