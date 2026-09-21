import { Sidebar } from "./Sidebar";
import { MobileNav } from "./MobileNav";
import { LiveIndicator } from "./LiveIndicator";
import { RouteTransition } from "./RouteTransition";

export function Layout() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-x-hidden pb-24 lg:pb-0">
        <div
          className="mx-auto w-full max-w-7xl px-4 py-6 md:px-8 md:py-8"
          style={{
            paddingTop: "max(1.5rem, env(safe-area-inset-top))",
            paddingLeft: "max(1rem, env(safe-area-inset-left))",
            paddingRight: "max(1rem, env(safe-area-inset-right))",
          }}
        >
          <RouteTransition />
        </div>
      </main>
      <MobileNav />
      <LiveIndicator />
    </div>
  );
}
