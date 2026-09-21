import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  Clock, CreditCard, Gift, Radio, Share2, TrendingUp, Users as UsersIcon,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { endpoints, type DailyPoint } from "@/lib/api";
import { dayLabel, fmtCompactInt, fmtNum, fmtRub } from "@/lib/format";
import { useEventStream } from "@/lib/ws";
import { StatCard } from "@/components/StatCard";
import { LivePaymentTicker } from "@/components/LivePaymentTicker";
import { AnimatedNum } from "@/components/AnimatedNum";
import { cn } from "@/lib/cn";

const DAY_OPTIONS = [7, 30, 90, 180] as const;
const HOUR_DAY_OPTIONS = [1, 7, 30] as const;

// Chart colours are the theme's semantic tokens: money is jade wherever it
// appears, so the line and the hero figure read as the same quantity.
const METRICS = [
  { key: "revenue", label: "Доход", color: "#17876B", fmt: fmtRub },
  { key: "new_users", label: "Люди", color: "#6B4BC7", fmt: fmtNum },
  { key: "payments", label: "Платежи", color: "#1857D6", fmt: fmtNum },
  { key: "new_paid_subs", label: "Подписки", color: "#B8791C", fmt: fmtNum },
] as const;
type MetricKey = (typeof METRICS)[number]["key"];

const AXIS = { fontSize: 11, fill: "#7C8CA0" } as const;
const GRID = "#E9EEF4";
const TOOLTIP = {
  borderRadius: 12,
  border: "1px solid #DCE3EC",
  fontSize: 12,
  boxShadow: "0 6px 20px -10px rgba(18,32,46,0.22)",
} as const;

function SegPill<T extends string | number>({
  options, value, onChange, render,
}: { options: readonly T[]; value: T; onChange: (v: T) => void; render: (v: T) => string }) {
  return (
    <div className="pill-tabs">
      {options.map((o) => (
        <button
          key={String(o)}
          onClick={() => onChange(o)}
          className={cn("pill-tab", o === value && "pill-tab-active")}
        >
          {render(o)}
        </button>
      ))}
    </div>
  );
}

function Figure({
  term, value, loading,
}: { term: string; value: string; loading?: boolean }) {
  return (
    <div className="border-border-subtle py-3 pr-4 sm:border-l sm:pl-4 sm:first:border-l-0 sm:first:pl-0">
      <dt className="text-[13px] text-fg-subtle">{term}</dt>
      <dd className="mt-1 text-xl font-semibold text-fg">
        {loading ? <span className="skeleton block h-6 w-20" /> : value}
      </dd>
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [days, setDays] = useState<number>(30);
  const [metric, setMetric] = useState<MetricKey>("revenue");
  const [hourDays, setHourDays] = useState<number>(7);
  const [hourMetric, setHourMetric] = useState<MetricKey>("new_users");
  const events = useEventStream();

  const ov = useQuery({
    queryKey: ["stats", "overview"], queryFn: endpoints.overview, refetchInterval: 60_000,
  });
  const daily = useQuery({
    queryKey: ["stats", "daily", days], queryFn: () => endpoints.daily(days),
    refetchInterval: 5 * 60_000, staleTime: 60_000,
  });
  const hourly = useQuery({
    queryKey: ["stats", "hourly", hourDays], queryFn: () => endpoints.hourly(hourDays),
    refetchInterval: 5 * 60_000, staleTime: 60_000,
  });
  const providers = useQuery({
    queryKey: ["stats", "providers"], queryFn: () => endpoints.providers(),
    refetchInterval: 5 * 60_000,
  });
  const segs = useQuery({
    queryKey: ["broadcasts", "segments"], queryFn: endpoints.segments,
    refetchInterval: 5 * 60_000,
  });

  const u = ov.data?.users;
  const h = ov.data?.health;
  const activeMetric = METRICS.find((m) => m.key === metric)!;
  const hourlyMetric = METRICS.find((m) => m.key === hourMetric)!;
  const series = daily.data?.series ?? [];
  const conv = u && u.users_total ? (u.buyers / u.users_total) * 100 : 0;
  const revWindow = series.reduce((acc, d) => acc + (d.revenue ?? 0), 0);

  return (
    <div className="stagger-children space-y-6">
      {/* The question this screen answers before any other: идут ли деньги.
          The figure, the trend under it and the supporting numbers are one
          sentence, so they are set as one block rather than four tiles. */}
      <header className="relative">
        <div className="hero-glow pointer-events-none absolute -top-24 left-1/4 h-52 w-52 rounded-full" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="label">Пришло сегодня</p>
            <div className="stat-hero mt-1 text-success">
              {ov.isLoading ? (
                <span className="skeleton block h-[0.9em] w-64" />
              ) : (
                <AnimatedNum value={u?.revenue_today ?? 0} fmt={fmtRub} />
              )}
            </div>
          </div>
          <Link to="/broadcasts/new" className="btn-primary">
            <Radio className="h-4 w-4" /> Новая рассылка
          </Link>
        </div>

        {/* Thirty days of revenue, drawn straight under the figure instead of
            boxed into its own card — it is the same sentence continuing. */}
        <div className="mt-4 h-16" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="spark" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#17876B" stopOpacity={0.26} />
                  <stop offset="100%" stopColor="#17876B" stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone" dataKey="revenue" stroke="#17876B" strokeWidth={1.75}
                fill="url(#spark)" dot={false} isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <dl className="mt-1 grid grid-cols-2 border-y border-border-subtle sm:grid-cols-4">
          <Figure term={`За ${days} дней`} value={fmtRub(revWindow)} loading={daily.isLoading} />
          <Figure term="Активные подписки" value={fmtNum(h?.active_total)} loading={ov.isLoading} />
          <Figure term="Платящие" value={fmtNum(u?.buyers)} loading={ov.isLoading} />
          <Figure term="Пользователи" value={fmtNum(u?.users_total)} loading={ov.isLoading} />
        </dl>
      </header>

      <LivePaymentTicker />

      {/* Daily dynamics */}
      <div className="card card-pad">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-fg-subtle" />
            <h2 className="font-semibold">Динамика</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SegPill
              options={METRICS.map((m) => m.key)} value={metric}
              onChange={(v) => setMetric(v as MetricKey)}
              render={(k) => METRICS.find((m) => m.key === k)!.label}
            />
            <SegPill options={DAY_OPTIONS} value={days} onChange={setDays} render={(d) => `${d}д`} />
          </div>
        </div>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ left: -12, right: 6, top: 4 }}>
              <defs>
                <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={activeMetric.color} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={activeMetric.color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
              <XAxis
                dataKey="day" tickFormatter={dayLabel} tick={AXIS}
                axisLine={false} tickLine={false} minTickGap={24}
              />
              <YAxis
                tickFormatter={(v) => fmtCompactInt(metric === "revenue" ? v / 100 : v)}
                tick={AXIS} axisLine={false} tickLine={false} width={48}
              />
              <Tooltip
                contentStyle={TOOLTIP}
                labelFormatter={(l) => dayLabel(String(l))}
                formatter={(v: number) => [activeMetric.fmt(v), activeMetric.label]}
              />
              <Area
                type="monotone" dataKey={metric as keyof DailyPoint}
                stroke={activeMetric.color} strokeWidth={2} fill="url(#grad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Hourly activity (Moscow time) */}
      <div className="card card-pad">
        <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-fg-subtle" />
            <h2 className="font-semibold">Активность по часам, МСК</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SegPill
              options={["new_users", "payments", "revenue"] as MetricKey[]} value={hourMetric}
              onChange={(v) => setHourMetric(v)}
              render={(k) => METRICS.find((m) => m.key === k)!.label}
            />
            <SegPill options={HOUR_DAY_OPTIONS} value={hourDays} onChange={setHourDays} render={(d) => `${d}д`} />
          </div>
        </div>
        <p className="mb-3 text-xs text-fg-muted">
          В какие часы приходят пользователи и платежи — видно пики и провалы.
        </p>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={hourly.data?.series ?? []} margin={{ left: -14, right: 6, top: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
              <XAxis
                dataKey="hour" tickFormatter={(x) => `${x}`} tick={{ ...AXIS, fontSize: 10 }}
                axisLine={false} tickLine={false} interval={1}
              />
              <YAxis
                tickFormatter={(v) => fmtCompactInt(hourMetric === "revenue" ? v / 100 : v)}
                tick={AXIS} axisLine={false} tickLine={false} width={44}
              />
              <Tooltip
                cursor={{ fill: "rgba(24,87,214,.06)" }}
                contentStyle={TOOLTIP}
                labelFormatter={(l) => `${l}:00–${Number(l) + 1}:00 МСК`}
                formatter={(v: number) => [hourlyMetric.fmt(v), hourlyMetric.label]}
              />
              <Bar dataKey={hourMetric} radius={[5, 5, 0, 0]} fill={hourlyMetric.color} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Subscription health */}
      <div>
        <h2 className="mb-3 font-semibold">Здоровье подписок</h2>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="Активные" value={fmtNum(h?.active_total)} loading={ov.isLoading} />
          <StatCard label="Платные активные" value={fmtNum(h?.active_paid)} tone="success" loading={ov.isLoading} />
          <StatCard label="Триалы активные" value={fmtNum(h?.active_trial)} tone="info" loading={ov.isLoading} />
          <StatCard
            label="Конверсия в покупку" value={conv.toFixed(1) + "%"} loading={ov.isLoading}
            hint={`${fmtNum(u?.buyers)} из ${fmtNum(u?.users_total)}`}
          />
        </div>
      </div>

      {/* Providers + segments */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="card card-pad">
          <h2 className="mb-3 font-semibold">Провайдеры (30 дней)</h2>
          <div className="space-y-2">
            {(providers.data ?? []).map((p) => (
              <div
                key={p.provider}
                className="row-hover flex items-center justify-between rounded-xl bg-bg-subtle px-3 py-2 text-sm"
              >
                <span className="font-medium capitalize">{p.provider}</span>
                <span className="text-fg-muted">
                  {fmtNum(p.payments)} · {fmtRub(p.revenue)}
                </span>
              </div>
            ))}
            {providers.data && providers.data.length === 0 && (
              <div className="py-6 text-center text-sm text-fg-subtle">Пока нет оплат</div>
            )}
          </div>
        </div>

        <div className="card card-pad">
          <h2 className="mb-3 font-semibold">Сегменты для рассылок</h2>
          <div className="flex flex-wrap gap-2">
            {(segs.data ?? []).slice(0, 14).map((s) => (
              <button
                key={s.key}
                onClick={() => navigate(`/broadcasts/new?segment=${s.key}`)}
                className="badge-muted transition-colors hover:bg-bg-elevated"
              >
                {s.label} <span className="ml-1 font-semibold text-fg">{fmtNum(s.count)}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Live event stream */}
      <div className="card card-pad">
        <div className="mb-3 flex items-center gap-2">
          <span className="pulse-live" />
          <h2 className="font-semibold">Живой поток событий</h2>
        </div>
        <div className="divide-y divide-border-subtle">
          {events.length === 0 && (
            <div className="py-6 text-center text-sm text-fg-subtle">Ожидание событий…</div>
          )}
          {events.map((e, i) => (
            <div key={i} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span className="font-mono text-xs text-accent">{e.type}</span>
              <span className="truncate text-fg-muted">
                {"telegram_id" in e ? `id ${String(e.telegram_id)}` : ""}
                {"amount_kopecks" in e ? ` ${fmtRub(Number(e.amount_kopecks))}` : ""}
                {"segment" in e ? ` ${String(e.segment)}` : ""}
                {"sent" in e ? ` ✓${String(e.sent)}` : ""}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { to: "/referrals", label: "Рефералы", icon: Share2 },
          { to: "/gifts", label: "Гифты", icon: Gift },
          { to: "/payments", label: "Платежи", icon: CreditCard },
          { to: "/users", label: "Пользователи", icon: UsersIcon },
        ].map((l) => (
          <Link
            key={l.to}
            to={l.to}
            className="card card-pad card-hover hover-lift flex items-center gap-2 text-sm font-medium"
          >
            <l.icon className="h-4 w-4 text-accent" /> {l.label}
          </Link>
        ))}
      </div>
    </div>
  );
}
