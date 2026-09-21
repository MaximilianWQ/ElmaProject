import { Outlet, useLocation } from "react-router-dom";

/**
 * Fade + slide-in on every route change. Keying the wrapper by pathname
 * remounts it, which replays the CSS `route-in` keyframes — no animation
 * library needed.
 */
export function RouteTransition() {
  const { pathname } = useLocation();
  return (
    <div key={pathname} className="route-in">
      <Outlet />
    </div>
  );
}
