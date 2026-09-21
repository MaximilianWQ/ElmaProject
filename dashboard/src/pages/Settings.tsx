import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Bell, BellOff, Fingerprint, KeyRound, LogOut, Plus, Trash2, Wrench,
} from "lucide-react";
import { ApiError, endpoints } from "@/lib/api";
import { fmtDate, fmtNum } from "@/lib/format";
import { logout } from "@/lib/auth";
import { registerPasskey } from "@/lib/passkey";
import { disablePush, enablePush, pushSubscribed, pushSupported } from "@/lib/push";
import { PageLoader, Spinner } from "@/components/Spinner";
import { ConfirmButton } from "@/components/ConfirmButton";
import { PageHeader } from "@/components/StatCard";
import { toast } from "@/store/toast";
import { ErrorNote } from "@/components/ErrorNote";

/**
 * What the service *is*. Anything that runs an operation against live data
 * (panel reconciliation, the bypass migration) lives on the Сервис page.
 */
export default function Settings() {
  const qc = useQueryClient();
  const s = useQuery({ queryKey: ["settings"], queryFn: endpoints.settings });
  const pk = useQuery({ queryKey: ["passkey-available"], queryFn: endpoints.passkeyAvailable });

  const addKey = useMutation({
    mutationFn: () => registerPasskey("Passkey"),
    onSuccess: () => {
      toast.success("Passkey добавлен");
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["passkey-available"] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.detail : "Не удалось добавить ключ"),
  });
  const delKey = useMutation({
    mutationFn: (id: string) => endpoints.passkeyDelete(id),
    onSuccess: () => {
      toast.success("Ключ удалён");
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: () => toast.error("Не удалось удалить"),
  });

  if (s.isLoading) return <PageLoader />;
  // Without this branch a failed request left the page on its spinner for ever:
  // isLoading is already false, data is still undefined.
  if (!s.data) {
    return (
      <div className="max-w-2xl space-y-5">
        <PageHeader title="Настройки" />
        <ErrorNote
          what="настройки"
          error={s.error}
          onRetry={() => s.refetch()}
          retrying={s.isFetching}
        />
      </div>
    );
  }
  const d = s.data;

  return (
    <div className="stagger-children max-w-2xl space-y-5">
      <PageHeader
        title="Настройки"
        subtitle="Конфигурация бота, тарифы и ключи входа."
        actions={
          <Link to="/service" className="btn-secondary">
            <Wrench className="h-4 w-4" /> Сервис
          </Link>
        }
      />

      <div className="card card-pad space-y-3">
        <div className="label">Сервис</div>
        <Row k="Бренд" v={d.brand} />
        <Row k="Триал" v={`${d.trial_days} дн.`} />
        <Row k="Лимит устройств" v={fmtNum(d.device_limit)} />
        <Row k="Реф. бонус" v={`${d.referral_bonus_days} дн.`} />
        <Row k="Приём платежей" v={d.payments_enabled ? "включён" : "выключен"} />
      </div>

      <PushCard />

      <div className="card card-pad">
        <div className="label mb-2">Тарифы · Premium</div>
        <div className="divide-y divide-border-subtle text-sm">
          {d.tariffs.map((t) => (
            <div key={t.code} className="flex items-center justify-between gap-3 py-2">
              <span className="font-medium">{t.title}</span>
              <span className="text-fg-muted">
                {fmtNum(t.price_rub)} ₽ · {t.days} дн.
                {t.save_label ? <span className="ml-1 text-success">{t.save_label}</span> : null}
              </span>
            </div>
          ))}
        </div>
        <p className="mt-2 text-xs text-fg-subtle">
          Один план в четырёх периодах. Пакеты ГБ обхода продаются отдельно.
        </p>
      </div>

      <div className="card card-pad">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-fg-subtle" />
            <div className="label">Passkey / WebAuthn</div>
          </div>
          {pk.data?.available && (
            <button
              className="btn-info px-3 py-1.5 text-xs"
              disabled={addKey.isPending}
              onClick={() => addKey.mutate()}
            >
              {addKey.isPending ? <Spinner className="h-4 w-4 text-white" /> : <Plus className="h-4 w-4" />}
              Добавить
            </button>
          )}
        </div>

        {!pk.data?.available ? (
          <p className="text-sm text-fg-muted">
            WebAuthn недоступен на сервере. Используйте пароль (сброс — командой{" "}
            <span className="font-mono">/dashboard</span> в боте).
          </p>
        ) : d.passkeys.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-fg-muted">
            <Fingerprint className="h-4 w-4" /> Ключей нет — добавьте Passkey для быстрого входа.
          </p>
        ) : (
          <div className="divide-y divide-border-subtle text-sm">
            {d.passkeys.map((p) => (
              <div key={p.credential_id} className="flex items-center justify-between py-2">
                <div>
                  <div className="font-medium">{p.label ?? "Passkey"}</div>
                  <div className="text-xs text-fg-subtle">добавлен {fmtDate(p.created_at)}</div>
                </div>
                <ConfirmButton
                  variant="secondary"
                  className="px-2 text-danger"
                  icon={Trash2}
                  idleLabel=""
                  confirmLabel="Удалить?"
                  pending={delKey.isPending && delKey.variables === p.credential_id}
                  onConfirm={() => delKey.mutate(p.credential_id)}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <button onClick={logout} className="btn-secondary w-full">
        <LogOut className="h-4 w-4" /> Выйти из консоли
      </button>
    </div>
  );
}

function PushCard() {
  const key = useQuery({ queryKey: ["push", "key"], queryFn: endpoints.pushKey });
  const sub = useQuery({
    queryKey: ["push", "subscribed"],
    queryFn: pushSubscribed,
    enabled: pushSupported(),
  });
  const on = useMutation({
    mutationFn: () => enablePush(),
    onSuccess: () => {
      toast.success("Push включён на этом устройстве");
      sub.refetch();
      key.refetch();
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Ошибка"),
  });
  const off = useMutation({
    mutationFn: () => disablePush(),
    onSuccess: () => {
      toast.success("Push выключён");
      sub.refetch();
      key.refetch();
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Ошибка"),
  });

  const serverOff = key.data && !key.data.enabled;
  const isSub = !!sub.data;

  return (
    <div className="card card-pad space-y-3">
      <div className="flex items-center gap-2">
        <Bell className="h-4 w-4 text-fg-subtle" />
        <div className="label">Push-уведомления</div>
      </div>
      <p className="text-sm text-fg-muted">
        Пуш в это приложение при достижении дневного дохода (5к/10к/…/40к ₽ по МСК)
        и по завершении рассылки. Работает после установки дашборда как приложения (PWA).
      </p>
      {!pushSupported() ? (
        <div className="text-xs text-fg-muted">Браузер не поддерживает push.</div>
      ) : serverOff ? (
        <div className="text-xs text-fg-muted">
          Выключено на сервере — задайте <code>VAPID_PUBLIC_KEY</code> /{" "}
          <code>VAPID_PRIVATE_KEY</code>.
        </div>
      ) : isSub ? (
        <button className="btn-secondary" disabled={off.isPending} onClick={() => off.mutate()}>
          {off.isPending ? <Spinner className="h-4 w-4" /> : <BellOff className="h-4 w-4" />}
          Выключить на этом устройстве
        </button>
      ) : (
        <button className="btn-primary" disabled={on.isPending} onClick={() => on.mutate()}>
          {on.isPending ? <Spinner className="h-4 w-4" /> : <Bell className="h-4 w-4" />}
          Включить на этом устройстве
        </button>
      )}
      {key.data?.enabled && (
        <div className="text-xs text-fg-subtle">Активных подписок: {fmtNum(key.data.count)}</div>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-fg-muted">{k}</span>
      <span className="font-medium">{v}</span>
    </div>
  );
}
