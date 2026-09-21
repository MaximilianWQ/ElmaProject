import { RefreshCw } from "lucide-react";
import { ApiError } from "@/lib/api";
import { Spinner } from "./Spinner";

/**
 * Says what could not be loaded and offers the way out.
 *
 * Without this a failed query is indistinguishable from real zeros: the
 * dashboard renders "0 ₽" whether nobody paid today or the backend is down,
 * which on a money screen is the difference between calm and a false alarm.
 */
export function ErrorNote({
  what,
  error,
  onRetry,
  retrying,
}: {
  /** What was being loaded, in the reader's words: "статистику", "платежи". */
  what: string;
  error?: unknown;
  onRetry?: () => void;
  retrying?: boolean;
}) {
  const detail =
    error instanceof ApiError
      ? error.detail
      : error instanceof Error
      ? error.message
      : null;

  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-3 rounded-surface border border-warning/30 bg-warning/10 px-4 py-3 text-sm"
    >
      <span className="text-fg">
        Не удалось получить {what}.
        {detail ? <span className="text-fg-muted"> {detail}</span> : null}
      </span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          disabled={retrying}
          className="btn-secondary ml-auto px-3 py-1.5 text-xs"
        >
          {retrying ? <Spinner className="h-3.5 w-3.5" /> : <RefreshCw className="h-3.5 w-3.5" />}
          Повторить
        </button>
      )}
    </div>
  );
}

/** Placeholder for a figure whose source failed — never a zero. */
export const NO_VALUE = "—";
