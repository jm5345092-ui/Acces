import { useEffect } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import ToolStatusBanner from "./ToolStatusBanner";

/** Real session check against the portal — Apache's rewrite-based gate
 * only catches the admin cookie being entirely absent; this catches a
 * present-but-logged-out session too, and (via the pageshow listener)
 * catches the browser restoring this page from bfcache after Salir,
 * where the back button shows a frozen page with no new network request
 * for Apache's gate to ever see. */
function useSessionGuard() {
  useEffect(() => {
    const check = () => {
      fetch("/webserver-session.php", { credentials: "same-origin", cache: "no-store" })
        .then((r) => r.json())
        .then((data) => {
          if (!data.authenticated) window.location.replace("/login.php");
        })
        .catch(() => {
          // Network hiccup — fail open rather than bounce the user on a
          // transient error; the next check (or Apache's gate) will catch
          // a truly dead session.
        });
    };

    check();
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) check();
    };
    window.addEventListener("pageshow", onPageShow);
    return () => window.removeEventListener("pageshow", onPageShow);
  }, []);
}

export default function AppShell({ children }: { children: ReactNode }) {
  useSessionGuard();

  return (
    <div className="app-shell">
      <div className="bg-decor" aria-hidden="true">
        <div className="scanlines" />
      </div>
      <div className="app-ambient-light" aria-hidden="true" />
      <div
        className="app-watermark"
        aria-hidden="true"
        style={{ backgroundImage: `url(${import.meta.env.BASE_URL}brand/logo-watermark.png)` }}
      />
      <header className="app-topbar">
        <Link to="/" className="app-brand">
          <img src={`${import.meta.env.BASE_URL}brand/logo-access.png`} alt="" className="app-brand-logo" />
          <span className="app-brand-name">
            APK-Lab <span className="app-brand-accent">Server</span>
          </span>
        </Link>
        <nav className="app-portal-nav">
          <a href="/dashboard.php">Dashboard</a>
          <a href="/conectar.php">Conectar</a>
          <a href="/ver.php">Ver</a>
          <a href="/logout.php" className="app-portal-nav__salir">Salir</a>
        </nav>
      </header>
      <ToolStatusBanner />
      <div className="app-content">{children}</div>
    </div>
  );
}
