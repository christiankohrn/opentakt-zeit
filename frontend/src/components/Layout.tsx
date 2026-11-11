import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import ConfirmDialog from "./ConfirmDialog";
import { IconAlert, IconCalendar, IconChart, IconChevron, IconClock, IconGear, IconLock, IconLogout, IconMoon, IconSun, IconUsers } from "./Icons";
import { useTheme } from "../theme";

function initials(name: string | undefined, fallback: string | undefined) {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  const fb = (fallback ?? "").trim();
  return fb ? fb.slice(0, 2).toUpperCase() : "?";
}

function bottomClass(active: boolean) {
  return `flex min-w-[76px] flex-1 flex-col items-center gap-0.5 rounded-xl px-1 py-2.5 text-center text-[11px] font-semibold leading-tight tracking-wide ${
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
  const hrFull = user && ["hr", "admin"].includes(user.role);
  const admin = user?.role === "admin";
  const { dark, cycle, theme } = useTheme();
  const [logoutConfirm, setLogoutConfirm] = useState(false);
  const [logoutBusy, setLogoutBusy] = useState(false);
  const location = useLocation();
  const bottomNavRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  useEffect(() => {
    const el = bottomNavRef.current;
    if (!el) return;
    const update = () => {
      setCanScrollLeft(el.scrollLeft > 4);
      setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      el.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [hr, hrFull, admin]);

  useEffect(() => {
    bottomNavRef.current?.querySelector('[aria-current="page"]')?.scrollIntoView({ inline: "nearest", block: "nearest" });
  }, [location.pathname]);

  function scrollBottomNav(direction: 1 | -1) {
    const el = bottomNavRef.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollBy({ left: direction * el.clientWidth * 0.7, behavior: reduce ? "auto" : "smooth" });
  }

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
    const icon = variant === "side" ? "h-5 w-5 shrink-0" : "h-6 w-6 shrink-0";
    const label = variant === "bottom" ? "max-w-full truncate" : "";
    return (
      <>
        <NavLink to="/" end className={({ isActive }) => cls(isActive)}>
          <IconClock className={icon} />
          <span className={label}>Stempeln</span>
        </NavLink>
        <NavLink to="/zeiten" className={({ isActive }) => cls(isActive)}>
          <IconCalendar className={icon} />
          <span className={label}>Zeiten</span>
        </NavLink>
        {hr ? (
          <>
            <NavLink to="/pruefung" className={({ isActive }) => cls(isActive)}>
              <IconAlert className={icon} />
              <span className={label}>Prüfung</span>
            </NavLink>
            <NavLink to="/personal" className={({ isActive }) => cls(isActive)}>
              <IconUsers className={icon} />
              <span className={label}>Personal</span>
            </NavLink>
            {hrFull ? (
              <>
                <NavLink to="/urlaub" className={({ isActive }) => cls(isActive)}>
                  <IconSun className={icon} />
                  <span className={label}>Urlaub</span>
                </NavLink>
                <NavLink to="/auswertungen" className={({ isActive }) => cls(isActive)}>
                  <IconChart className={icon} />
                  <span className={label}>Auswertungen</span>
                </NavLink>
              </>
            ) : null}
          </>
        ) : null}
        {admin ? (
          <>
            <NavLink to="/abschluesse" className={({ isActive }) => cls(isActive)}>
              <IconLock className={icon} />
              <span className={label}>Abschlüsse</span>
            </NavLink>
            <NavLink to="/einstellungen" className={({ isActive }) => cls(isActive)}>
              <IconGear className={icon} />
              <span className={label}>Einstellungen</span>
            </NavLink>
          </>
        ) : null}
      </>
    );
  };

  return (
    <div className="min-h-dvh lg:flex">
      <aside className="hidden print:hidden lg:sticky lg:top-0 lg:flex lg:h-dvh lg:w-56 lg:shrink-0 lg:flex-col lg:self-start bg-nav text-white">
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
        <header className="flex items-center justify-between gap-3 px-5 pt-[max(1.25rem,env(safe-area-inset-top))] pb-2 print:hidden lg:hidden">
          <div className="min-w-0 flex-1">
            <p className="truncate text-[11px] font-medium text-muted">{orgName}</p>
            <p className="truncate text-sm text-ink">{user?.display_name}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={cycle}
              className="flex h-10 w-10 items-center justify-center rounded-full border border-line text-present"
              title={theme === "system" ? "System" : theme === "light" ? "Hell" : "Dunkel"}
              aria-label="Farbmodus wechseln"
            >
              {dark ? <IconSun className="h-5 w-5" /> : <IconMoon className="h-5 w-5" />}
            </button>
            <NavLink
              to="/konto"
              title="Konto"
              aria-label={`Konto von ${user?.display_name ?? "mir"}`}
              className={({ isActive }) =>
                `flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold ${
                  isActive ? "bg-present text-white outline outline-2 outline-offset-2 outline-present" : "bg-present text-white"
                }`
              }
            >
              {initials(user?.display_name, user?.username)}
            </NavLink>
            <button
              type="button"
              onClick={() => setLogoutConfirm(true)}
              className="flex h-10 w-10 items-center justify-center rounded-full border border-line text-present"
              title="Abmelden"
              aria-label="Abmelden"
            >
              <IconLogout className="h-5 w-5" />
            </button>
          </div>
        </header>
        <main className="min-w-0 flex-1 px-5 pb-28 lg:px-8 lg:py-6 lg:pb-8 xl:px-10 print:px-0 print:pb-0">
          <Outlet />
        </main>
        <nav className="fixed inset-x-0 bottom-0 bg-nav text-white shadow-[0_-12px_28px_rgba(0,34,70,0.35)] print:hidden lg:hidden">
          <div className="relative mx-auto w-full max-w-3xl">
            <div
              ref={bottomNavRef}
              className="flex w-full gap-1 overflow-x-auto px-2 pb-[max(0.6rem,env(safe-area-inset-bottom))] pt-2"
            >
              {links("bottom")}
            </div>
            {canScrollLeft ? (
              <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center bg-gradient-to-r from-nav via-nav/80 to-transparent pl-1 pr-6">
                <button
                  type="button"
                  onClick={() => scrollBottomNav(-1)}
                  aria-label="Menü nach links scrollen"
                  className="pointer-events-auto rounded-full bg-white/15 p-1 text-white"
                >
                  <IconChevron className="h-4 w-4 rotate-180" />
                </button>
              </div>
            ) : null}
            {canScrollRight ? (
              <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center bg-gradient-to-l from-nav via-nav/80 to-transparent pl-6 pr-1">
                <button
                  type="button"
                  onClick={() => scrollBottomNav(1)}
                  aria-label="Menü nach rechts scrollen"
                  className="pointer-events-auto rounded-full bg-white/15 p-1 text-white"
                >
                  <IconChevron className="h-4 w-4" />
                </button>
              </div>
            ) : null}
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
