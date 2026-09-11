import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import ConfirmDialog from "./ConfirmDialog";
import { IconAlert, IconCalendar, IconClock, IconGear, IconMoon, IconSun, IconUsers } from "./Icons";
import { useTheme } from "../theme";

function bottomClass(active: boolean) {
  return `flex flex-1 flex-col items-center gap-0.5 rounded-xl px-1 py-2.5 text-[11px] font-semibold tracking-wide ${
    active ? "bg-present text-white shadow-sm" : "text-white/75"
  }`;
}

function sideClass(active: boolean) {
  return `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium ${
    active ? "bg-present text-white" : "text-white/80 hover:bg-white/10"
  }`;
}

export default function Layout() {
  const { user, setUser, orgName } = useAuth();
  const nav = useNavigate();
  const hr = user && ["hr", "admin", "supervisor"].includes(user.role);
  const admin = user?.role === "admin";
  const { dark, cycle, theme } = useTheme();
  const [logoutConfirm, setLogoutConfirm] = useState(false);
  const [logoutBusy, setLogoutBusy] = useState(false);

  async function logout() {
    setLogoutBusy(true);
    try {
      await api.logout();
      setUser(null);
      nav("/login");
    } finally {
      setLogoutBusy(false);
      setLogoutConfirm(false);
    }
  }

  const links = (variant: "bottom" | "side") => {
    const cls = variant === "bottom" ? bottomClass : sideClass;
    const icon = variant === "side" ? "h-5 w-5 shrink-0" : "h-6 w-6";
    return (
      <>
        <NavLink to="/" end className={({ isActive }) => cls(isActive)}>
          <IconClock className={icon} />
          Stempeln
        </NavLink>
        <NavLink to="/zeiten" className={({ isActive }) => cls(isActive)}>
          <IconCalendar className={icon} />
          Zeiten
        </NavLink>
        {hr ? (
          <>
            <NavLink to="/pruefung" className={({ isActive }) => cls(isActive)}>
              <IconAlert className={icon} />
              Prüfung
            </NavLink>
            <NavLink to="/personal" className={({ isActive }) => cls(isActive)}>
              <IconUsers className={icon} />
              Personal
            </NavLink>
          </>
        ) : null}
        {admin && variant === "side" ? (
          <NavLink to="/einstellungen" className={({ isActive }) => cls(isActive)}>
            <IconGear className={icon} />
            Einstellungen
          </NavLink>
        ) : null}
      </>
    );
  };

  return (
    <div className="min-h-dvh lg:flex">
      <aside className="hidden lg:sticky lg:top-0 lg:flex lg:h-dvh lg:w-56 lg:shrink-0 lg:flex-col lg:self-start bg-nav text-white">
        <div className="px-4 pt-6 pb-4">
          <p className="text-sm font-medium leading-tight">{orgName}</p>
          <p className="mt-1 text-sm font-medium">{user?.display_name}</p>
        </div>
        <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-3">{links("side")}</nav>
        <div className="mt-auto shrink-0">
          <div className="flex items-center gap-2 px-4 py-4">
            <button
              type="button"
              onClick={cycle}
              className="rounded-full border border-white/20 p-2 text-white/80 hover:bg-white/10"
              title={theme === "system" ? "System" : theme === "light" ? "Hell" : "Dunkel"}
            >
              {dark ? <IconSun className="h-5 w-5" /> : <IconMoon className="h-5 w-5" />}
            </button>
            <button type="button" onClick={() => setLogoutConfirm(true)} className="text-sm text-white/70 hover:text-white">
              Abmelden
            </button>
          </div>
          <NavLink to="/konto" className="block px-4 pb-4 text-xs text-white/50 hover:text-white">
            Passwort ändern
          </NavLink>
        </div>
      </aside>
      <div className="mx-auto flex min-h-dvh w-full min-w-0 max-w-lg flex-col pb-[env(safe-area-inset-bottom)] sm:max-w-none lg:mx-0 lg:min-h-0 lg:flex-1">
        <header className="flex items-center justify-between gap-3 px-5 pt-[max(1.25rem,env(safe-area-inset-top))] pb-2 lg:hidden">
          <div className="min-w-0">
            <p className="text-[11px] font-medium text-muted">{orgName}</p>
            <p className="truncate text-sm text-ink">{user?.display_name}</p>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <button
              type="button"
              onClick={cycle}
              className="rounded-full border border-line p-2 text-present"
              title={theme === "system" ? "System" : theme === "light" ? "Hell" : "Dunkel"}
            >
              {dark ? <IconSun className="h-5 w-5" /> : <IconMoon className="h-5 w-5" />}
            </button>
            <button type="button" onClick={() => setLogoutConfirm(true)} className="text-sm text-muted">
              Abmelden
            </button>
            <NavLink to="/konto" className="text-sm text-muted">
              Konto
            </NavLink>
            {admin ? (
              <NavLink to="/einstellungen" className="text-sm text-muted">
                Einstellungen
              </NavLink>
            ) : null}
          </div>
        </header>
        <main className="min-w-0 flex-1 px-5 pb-28 lg:px-8 lg:py-6 lg:pb-8 xl:px-10">
          <Outlet />
        </main>
        <nav className="fixed inset-x-0 bottom-0 bg-nav text-white shadow-[0_-12px_28px_rgba(0,34,70,0.35)] lg:hidden">
          <div className="mx-auto flex w-full max-w-3xl gap-1 px-2 pb-[max(0.6rem,env(safe-area-inset-bottom))] pt-2">
            {links("bottom")}
          </div>
        </nav>
      </div>
      {logoutConfirm ? (
        <ConfirmDialog
          title="Wirklich abmelden?"
          body="Die Sitzung auf diesem Gerät wird beendet. Zum Stempeln musst du dich danach neu anmelden."
          confirmLabel={logoutBusy ? "Abmelden …" : "Abmelden"}
          busy={logoutBusy}
          onCancel={() => setLogoutConfirm(false)}
          onConfirm={() => void logout()}
        />
      ) : null}
    </div>
  );
}
