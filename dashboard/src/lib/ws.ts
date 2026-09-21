import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getToken } from "./auth";

export interface BotEvent {
  type: string;
  ts?: number;
  [k: string]: unknown;
}

/** Subscribe to the live event stream; keep the last `max` events and
 *  invalidate affected React Query caches as events arrive. */
export function useEventStream(max = 25): BotEvent[] {
  const [events, setEvents] = useState<BotEvent[]>([]);
  const qc = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    // Exponential backoff, capped. A flat 4s retry turns any persistent
    // failure — expired token, server restart, proxy without WS support —
    // into a permanent 15-requests-per-minute drumbeat against the server.
    let delay = 2000;
    const MAX_DELAY = 30_000;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/dashboard/ws?token=${token}`);
      wsRef.current = ws;
      ws.onopen = () => {
        delay = 2000; // a real connection resets the ladder
      };
      ws.onmessage = (m) => {
        try {
          const ev = JSON.parse(m.data) as BotEvent;
          setEvents((prev) => [{ ...ev, ts: ev.ts ?? Date.now() / 1000 }, ...prev].slice(0, max));
          // Only the types the bot actually publishes (app/events.py callers):
          // payment:confirmed, admin:grant|revoke|reissue|discount,
          // broadcast:created|progress|done, bypass_backfill:started|progress|done.
          // The previous list keyed off "user:registered" and a bare "payment"
          // prefix, neither of which is ever emitted — so nothing refreshed.
          if (ev.type === "payment:confirmed") {
            qc.invalidateQueries({ queryKey: ["stats"] });
            qc.invalidateQueries({ queryKey: ["payments"] });
          }
          if (ev.type.startsWith("admin:")) {
            qc.invalidateQueries({ queryKey: ["stats"] });
            qc.invalidateQueries({ queryKey: ["users"] });
          }
          if (ev.type.startsWith("broadcast:")) {
            qc.invalidateQueries({ queryKey: ["broadcasts"] });
          }
          if (ev.type.startsWith("bypass_backfill:")) {
            qc.invalidateQueries({ queryKey: ["bypass"] });
          }
        } catch {
          /* ignore malformed frame */
        }
      };
      ws.onclose = () => {
        if (closed) return;
        retry = setTimeout(connect, delay);
        delay = Math.min(delay * 2, MAX_DELAY);
      };
    };
    connect();

    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      wsRef.current?.close();
    };
  }, [qc, max]);

  return events;
}
