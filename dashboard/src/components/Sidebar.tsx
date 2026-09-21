import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { LogOut, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/cn";
import { logout } from "@/lib/auth";
import { endpoints } from "@/lib/api";
import { sections } from "@/lib/nav";

export function Sidebar() {
  const me = useQuery({ queryKey: ["me"], queryFn: endpoints.me, staleTime: Infinity });

  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-bg-subtle/40 px-4 py-6 lg:flex">
      <div className="mb-8 flex items-center gap-3 px-2">
        <div className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-bg shadow-glow-sm">
          <ShieldCheck className="h-[18px] w-[18px]" strokeWidth={2.5} />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold leading-tight text-fg">ELMA</div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-fg-subtle">Admin</div>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-4 overflow-y-auto">
        {sections.map((section, sIdx) => (
          <div key={section.label} className={sIdx === 0 ? "" : "mt-1"}>
            <div className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-[0.15em] text-fg-subtle">
              {section.label}
            </div>
            <div className="flex flex-col gap-0.5">
              {section.items.map((it) => (
                <NavLink
                  key={it.to || "index"}
                  to={it.to}
                  end={it.to === ""}
                  className={({ isActive }) =>
                    cn(
                      "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all",
                      isActive
                        ? "bg-accent text-bg shadow-glow-sm"
                        : "text-fg-muted hover:bg-bg-elevated hover:text-fg",
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      <it.icon
                        className={cn(
                          "h-4 w-4 transition-colors",
                          isActive ? "text-bg" : "text-fg-subtle group-hover:text-fg-muted",
                        )}
                        strokeWidth={isActive ? 2.5 : 2}
                      />
                      <span className={cn("flex-1 truncate", isActive && "font-semibold")}>
                        {it.label}
                      </span>
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="mt-4 border-t border-border-subtle pt-3">
        <div className="px-3 pb-2 text-[11px] text-fg-subtle">
          {me.data?.username ? "@" + me.data.username : "admin"}
        </div>
        <button
          type="button"
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-fg-muted transition-all hover:bg-danger/10 hover:text-danger"
        >
          <LogOut className="h-4 w-4" />
          Выйти
        </button>
      </div>
    </aside>
  );
}
