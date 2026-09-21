import { Suspense, lazy, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { isLoggedIn } from "./lib/auth";
import { Layout } from "./components/Layout";
import { Toaster } from "./components/Toaster";
import { EntryOverlay } from "./components/EntryOverlay";
import { PageLoader } from "./components/Spinner";
import Login from "./pages/Login";
import SetupPassword from "./pages/SetupPassword";

// Signed-in pages load on demand. This console is opened on a phone, and the
// charting library alone is most of the bundle — there is no reason to ship it
// to someone who came to look up one user. Login and the setup link stay eager:
// they are the first paint.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Analytics = lazy(() => import("./pages/Analytics"));
const Users = lazy(() => import("./pages/Users"));
const Payments = lazy(() => import("./pages/Payments"));
const Broadcasts = lazy(() => import("./pages/Broadcasts"));
const BroadcastCreate = lazy(() => import("./pages/BroadcastCreate"));
const Referrals = lazy(() => import("./pages/Referrals"));
const Gifts = lazy(() => import("./pages/Gifts"));
const PromoCodes = lazy(() => import("./pages/PromoCodes"));
const MarketingLinks = lazy(() => import("./pages/MarketingLinks"));
const Automations = lazy(() => import("./pages/Automations"));
const Audit = lazy(() => import("./pages/Audit"));
const Service = lazy(() => import("./pages/Service"));
const Settings = lazy(() => import("./pages/Settings"));

export default function App() {
  const [authed, setAuthed] = useState(isLoggedIn());
  const [entry, setEntry] = useState(false);

  // Play the entrance once per session when opening an already-signed-in panel.
  useEffect(() => {
    if (isLoggedIn() && !sessionStorage.getItem("entry_shown")) setEntry(true);
  }, []);

  const enter = () => { setAuthed(true); setEntry(true); };
  const finishEntry = () => { sessionStorage.setItem("entry_shown", "1"); setEntry(false); };

  return (
    <BrowserRouter basename="/dashboard">
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/setup" element={<SetupPassword onDone={enter} />} />
          {!authed ? (
            <Route path="*" element={<Login onDone={enter} />} />
          ) : (
            <Route element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="analytics" element={<Analytics />} />
              <Route path="users" element={<Users />} />
              <Route path="payments" element={<Payments />} />
              <Route path="broadcasts" element={<Broadcasts />} />
              <Route path="broadcasts/new" element={<BroadcastCreate />} />
              <Route path="referrals" element={<Referrals />} />
              <Route path="gifts" element={<Gifts />} />
              <Route path="promo" element={<PromoCodes />} />
              <Route path="links" element={<MarketingLinks />} />
              <Route path="automations" element={<Automations />} />
              <Route path="service" element={<Service />} />
              <Route path="audit" element={<Audit />} />
              <Route path="settings" element={<Settings />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          )}
        </Routes>
      </Suspense>
      {entry && <EntryOverlay onDone={finishEntry} />}
      <Toaster />
    </BrowserRouter>
  );
}
