import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Globe, ShieldAlert, Activity, Server } from "lucide-react";
import { ApiError, endpoints } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import { useEventStream } from "@/lib/ws";
import { Spinner } from "@/components/Spinner";
import { ConfirmButton } from "@/components/ConfirmButton";
import { PageHeader, StatCard } from "@/components/StatCard";
import { toast } from "@/store/toast";
import { ErrorNote } from "@/components/ErrorNote";

/**
 * Operations, kept apart from Settings: Settings is what the service *is*
 * (brand, tariffs, keys), Service is what you *do to it* — a panel↔DB
 * reconciliation and the bypass migration, both long-running and both capable
 * of touching every subscriber.
 */
export default function Service() {
  const s = useQuery({ queryKey: ["settings"], queryFn: endpoints.settings });
  const bypass = useQuery({
    queryKey: ["bypass", "backfill"],
    queryFn: endpoints.bypassPreview,
    refetchInterval: 30_000,
  });

  return (
    <div className="stagger-children space-y-6">
      <PageHeader
        title="Сервис"
        subtitle="Операции над боевыми данными: сверка с панелью и миграция обхода."
      />

      {s.isError && (
        <ErrorNote
          what="состояние сервиса"
          error={s.error}
          onRetry={() => s.refetch()}
          retrying={s.isFetching}
        />
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          label="Приём платежей"
          value={s.data?.payments_enabled ? "включён" : "выключен"}
          tone={s.data?.payments_enabled ? "success" : "warning"}
          icon={Activity}
          loading={s.isLoading}
        />
        <StatCard
          label="Обход"
          value={bypass.data?.enabled ? "включён" : "выключен"}
          tone={bypass.data?.enabled ? "success" : "default"}
          icon={Globe}
          hint={bypass.data?.enabled ? `без профиля: ${fmtNum(bypass.data.eligible)}` : undefined}
          loading={bypass.isLoading}
        />
        <StatCard
          label="Лимит устройств"
          value={fmtNum(s.data?.device_limit)}
          icon={Server}
          hint={`триал ${s.data?.trial_days ?? "—"} дн.`}
          loading={s.isLoading}
        />
      </div>

      <ReconCard />
      <BypassBackfill />
    </div>
  );
}

function ReconCard() {
  const [run, setRun] = useState(false);
  const q = useQuery({
    queryKey: ["reconcile"],
    queryFn: () => endpoints.reconcile(100),
    enabled: run,
    refetchOnWindowFocus: false,
    staleTime: Infinity,
  });
  const cands = q.data?.candidates ?? [];

  return (
    <div className="card card-pad space-y-3">
      <div className="flex items-center gap-2">
        <ShieldAlert className="h-4 w-4 text-fg-subtle" />
        <div className="label">Сверка выдачи (панель ↔ БД)</div>
      </div>
      <p className="text-sm text-fg-muted">
        Сравнивает срок в Remnawave со сроком в базе и находит перевыдачу
        (панель &gt; БД ≥ 1 дня) или отсутствие пользователя в панели. Проверяет
        до 100 активных платных подписок — идёт несколько секунд.
      </p>
      <button
        className="btn-secondary"
        disabled={q.isFetching}
        onClick={() => {
          setRun(true);
          q.refetch();
        }}
      >
        {q.isFetching ? <Spinner className="h-4 w-4" /> : <ShieldAlert className="h-4 w-4" />}
        Проверить
      </button>

      {q.data && (
        <div className="text-sm">
          <div className="text-fg-muted">
            Проверено: {fmtNum(q.data.scanned)} · расхождений:{" "}
            <b className="text-fg">{fmtNum(cands.length)}</b>
          </div>
          {cands.length > 0 ? (
            <div className="mt-2 divide-y divide-border-subtle">
              {cands.slice(0, 50).map((c) => (
                <div key={c.telegram_id} className="flex items-center justify-between py-1.5">
                  <code className="font-mono text-xs">{c.telegram_id}</code>
                  <span className={c.issue === "no_panel" ? "badge-warning" : "badge-danger"}>
                    {c.issue === "no_panel" ? "нет в панели" : `перевыдача +${c.days_over} дн.`}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-1 font-medium text-success">✓ Расхождений не найдено</div>
          )}
        </div>
      )}
    </div>
  );
}

function BypassBackfill() {
  const [gb, setGb] = useState(50);
  const prev = useQuery({
    queryKey: ["bypass", "backfill"],
    queryFn: endpoints.bypassPreview,
    refetchInterval: 30_000,
  });
  const events = useEventStream().filter((e) => e.type.startsWith("bypass_backfill"));
  const last = events[0];

  const run = useMutation({
    mutationFn: () => endpoints.bypassBackfill(gb),
    onSuccess: (r) => toast.success(`Запущено для ${fmtNum(r.total)} пользователей`),
    onError: (e) => toast.error(e instanceof ApiError ? e.detail : "Ошибка"),
  });

  if (prev.data && !prev.data.enabled) {
    return (
      <div className="card card-pad">
        <div className="mb-1 flex items-center gap-2">
          <Globe className="h-4 w-4 text-fg-subtle" />
          <div className="label">Миграция обхода</div>
        </div>
        <p className="text-sm text-fg-muted">
          Обход выключен. Задайте <code className="font-mono">REMNAWAVE_BYPASS_SQUAD_UUID</code>,
          чтобы включить.
        </p>
      </div>
    );
  }

  const eligible = prev.data?.eligible ?? 0;
  const running = (prev.data?.running ?? false) || (!!last && last.type !== "bypass_backfill:done");
  const done = Number(last?.done ?? 0);
  const total = Number(last?.total ?? 0);
  const ok = Number(last?.ok ?? 0);
  const failed = Number(last?.failed ?? 0);
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;

  return (
    <div className="card card-pad space-y-3">
      <div className="flex items-center gap-2">
        <Globe className="h-4 w-4 text-fg-subtle" />
        <div className="label">Миграция обхода</div>
      </div>
      <p className="text-sm text-fg-muted">
        Создаст профиль обхода в нужном сквоте всем активным платным подписчикам,
        у кого его ещё нет. Идемпотентно (повторно не дублирует), с троттлингом
        панели, фоном с прогрессом.
      </p>

      <div className="flex items-center justify-between rounded-xl bg-bg-elevated px-3 py-2 text-sm">
        <span className="text-fg-muted">Подходит сейчас</span>
        <span className="font-semibold">{fmtNum(eligible)}</span>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="number"
          min={1}
          className="input w-28"
          value={gb}
          onChange={(e) => setGb(Math.max(1, Number(e.target.value)))}
        />
        <span className="text-sm text-fg-muted">ГБ начислить каждому</span>
      </div>

      {last && (
        <div className="rounded-xl bg-bg-elevated px-3 py-2 text-sm">
          <div className="flex justify-between">
            <span className="text-fg-muted">
              {last.type === "bypass_backfill:done" ? "Готово" : "Идёт миграция…"}
            </span>
            <span className="font-medium">
              {fmtNum(done)} / {fmtNum(total)}
            </span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-border-subtle">
            <div
              className="h-full rounded-full bg-info transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="mt-1 text-xs text-fg-subtle">
            ✓ {fmtNum(ok)} · ⚠ {fmtNum(failed)}
          </div>
        </div>
      )}

      <ConfirmButton
        className="w-full"
        variant="info"
        icon={Globe}
        idleLabel={`Создать обход всем (${fmtNum(eligible)})`}
        confirmLabel={`Точно запустить для ${fmtNum(eligible)}?`}
        pending={run.isPending || running}
        disabled={eligible === 0}
        onConfirm={() => run.mutate()}
      />
    </div>
  );
}
