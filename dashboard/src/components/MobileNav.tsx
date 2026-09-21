import { useEffect, useState } from "react";
import { NavLink, useLocation, useResolvedPath } from "react-router-dom";
import { LogOut, MoreHorizontal, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { logout } from "@/lib/auth";
import { mobileMore, mobilePrimary, type NavItem } from "@/lib/nav";

/** Absolute pathname a relative nav entry resolves to, so "is one of the
 *  sheet's routes open?" can be answered without hard-coding the basename. */
function useItemPaths(items: NavItem[]): string[] {
  const base = useResolvedPath("").pathname;
  return items.map((it) =>
    it.to ? `${base.replace(/\/$/, "")}/${it.to}` : base,
  );
}

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const morePaths = useItemPaths(mobileMore);

  // Any navigation closes the sheet.
  useEffect(() => setOpen(false), [location.pathname]);

  // Freeze the page behind the sheet so iOS doesn't rubber-band it.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const inMore = morePaths.some(
    (p) => location.pathname === p || location.pathname.startsWith(p + "/"),
  );

  return (
    <>
      <nav
        className="fixed inset-x-2 z-30 flex justify-around rounded-2xl border border-border bg-bg-card/90 px-2 py-1.5 backdrop-blur-md lg:hidden"
        style={{ bottom: "max(0.5rem, env(safe-area-inset-bottom))" }}
      >
        {mobilePrimary.map((it) => (
          <NavLink
            key={it.to || "index"}
            to={it.to}
            end={it.to === ""}
            className={({ isActive }) =>
              cn(
                "flex flex-1 flex-col items-center gap-0.5 rounded-xl px-2 py-1.5 text-[10px] font-medium transition-all duration-200",
                isActive
                  ? "bg-accent text-bg font-semibold shadow-glow-sm"
                  : "text-fg-subtle hover:text-fg",
              )
            }
          >
            <it.icon className="h-4 w-4" strokeWidth={2.25} />
            {it.label}
          </NavLink>
        ))}
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={cn(
            "flex flex-1 flex-col items-center gap-0.5 rounded-xl px-2 py-1.5 text-[10px] font-medium transition-all duration-200",
            inMore
              ? "bg-accent text-bg font-semibold shadow-glow-sm"
              : "text-fg-subtle hover:text-fg",
          )}
        >
          <MoreHorizontal className="h-4 w-4" strokeWidth={2.25} />
          Ещё
        </button>
      </nav>

      {open && (
        <div
          className="fixed inset-0 z-40 flex items-end bg-fg/40 backdrop-blur-sm animate-fade-in lg:hidden"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full rounded-t-3xl border-x border-t border-border bg-bg-subtle shadow-matte animate-slide-up"
            style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-border" />
            <div className="flex items-center justify-between px-5 pb-2 pt-3">
              <div>
                <div className="text-[10px] font-medium uppercase tracking-[0.15em] text-fg-subtle">
                  Меню
                </div>
                <h3 className="text-base font-semibold text-fg">Все разделы</h3>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Закрыть меню"
                className="grid h-9 w-9 place-items-center rounded-xl bg-bg-elevated text-fg-muted ring-1 ring-border"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2 px-5 py-3">
              {mobileMore.map((it) => (
                <NavLink
                  key={it.to || "index"}
                  to={it.to}
                  end={it.to === ""}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-xl border px-3 py-3 text-sm font-medium transition-colors",
                      isActive
                        ? "border-accent/40 bg-accent/10 text-accent"
                        : "border-border bg-bg-card text-fg hover:border-fg-subtle",
                    )
                  }
                >
                  <it.icon className="h-4 w-4 shrink-0" strokeWidth={2} />
                  <span className="truncate">{it.label}</span>
                </NavLink>
              ))}
            </div>

            <div className="px-5 pb-4 pt-2">
              <button
                type="button"
                onClick={logout}
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm font-medium text-danger transition-colors hover:bg-danger/15"
              >
                <LogOut className="h-4 w-4" />
                Выйти
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
