import { FormEvent, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, type DaySummary, type User, type WorkModel, type WorkModelAssignment } from "../api";
import { useAuth } from "../auth";
import DayLegend from "../components/DayLegend";
import ConfirmDialog from "../components/ConfirmDialog";
import { IconChevron, IconTrash } from "../components/Icons";
import PasswordField from "../components/PasswordField";
import { bookingText, dayRowClass, daySurfaceClass, formatDayLabel, formatHours, hoursTone, signedHours, warnLabel } from "../labels";
import { generatePassword } from "../password";

function payrollMonth() {
  const d = new Date();
  if (d.getDate() <= 15) {
    d.setDate(1);
    d.setMonth(d.getMonth() - 1);
  }
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function isoToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const ROLE: Record<string, string> = {
  employee: "Mitarbeiter",
  supervisor: "Vorgesetzt",
  hr: "Personal",
  admin: "Admin",
};

export default function HrUserMonth() {
  const { user: me } = useAuth();
  const isAdmin = me?.role === "admin";
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const userId = Number(id);
  const month = params.get("month") || payrollMonth();
  const from = params.get("from");
  const [user, setUser] = useState<User | null>(null);
  const [days, setDays] = useState<DaySummary[]>([]);
  const [monthFlex, setMonthFlex] = useState(0);
  const [totalFlex, setTotalFlex] = useState(0);
  const [models, setModels] = useState<WorkModel[]>([]);
  const [assignments, setAssignments] = useState<WorkModelAssignment[]>([]);
  const [modelId, setModelId] = useState("");
  const [modelFrom, setModelFrom] = useState(isoToday);
  const [modelConfirm, setModelConfirm] = useState(false);
  const [modelDelete, setModelDelete] = useState<WorkModelAssignment | null>(null);
  const [modelMsg, setModelMsg] = useState("");
  const [absKind, setAbsKind] = useState("vacation");
  const [absStart, setAbsStart] = useState(`${month}-01`);
  const [absEnd, setAbsEnd] = useState(`${month}-01`);
  const [absNote, setAbsNote] = useState("");
  const [absMsg, setAbsMsg] = useState("");
  const [absConfirm, setAbsConfirm] = useState(false);
  const [transponder, setTransponder] = useState("");
  const [webLogin, setWebLogin] = useState(true);
  const [accessMsg, setAccessMsg] = useState("");
  const [account, setAccount] = useState({
    display_name: "",
    username: "",
    email: "",
    role: "employee",
    active: true,
    password: "",
    hired_on: "",
    left_on: "",
  });
  const [accountMsg, setAccountMsg] = useState("");
  const [generatedPassword, setGeneratedPassword] = useState("");
  const [exportMsg, setExportMsg] = useState("");
  const [inviteMsg, setInviteMsg] = useState("");
  const [inviteBusy, setInviteBusy] = useState(false);

  async function reload() {
    if (!userId) return;
    const [r, m, a] = await Promise.all([api.userDays(userId, month), api.models(), api.userModels(userId)]);
    setUser(r.user);
    setDays(r.days);
    setMonthFlex(r.month_flex ?? 0);
    setTotalFlex(r.total_flex ?? 0);
    setModels(m);
    setAssignments(a);
    setModelId((cur) => cur || String(r.user.work_model_id ?? m[0]?.id ?? ""));
    setTransponder(r.user.transponder_id ?? "");
    setWebLogin(r.user.web_login !== false);
    setAccount((cur) => ({
      display_name: r.user.display_name,
      username: r.user.username,
      email: r.user.email ?? "",
      role: r.user.role,
      active: r.user.active,
      password: cur.username === r.user.username ? cur.password : "",
      hired_on: r.user.hired_on ?? "",
      left_on: r.user.left_on ?? "",
    }));
  }

  function setMonth(next: string) {
    const nextParams: Record<string, string> = { month: next };
    if (from) nextParams.from = from;
    setParams(nextParams);
  }

  useEffect(() => {
    if (!params.get("month")) {
      const nextParams: Record<string, string> = { month };
      if (from) nextParams.from = from;
      setParams(nextParams, { replace: true });
    }
  }, [from, month, params, setParams]);

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, month]);

  const visibleDays = days;
  const chosenModel = models.find((m) => String(m.id) === modelId);
  const totals = days
    .filter((d) => d.date <= isoToday())
    .reduce(
      (acc, d) => ({
        work: acc.work + d.work_hours,
        soll: acc.soll + d.soll_hours,
      }),
      { work: 0, soll: 0 },
    );

  const settings = (
    <>
      {user ? (
        <form
          className="space-y-2 rounded-2xl border border-line bg-card p-4"
          onSubmit={async (e: FormEvent) => {
            e.preventDefault();
            setAccountMsg("");
            try {
              const body: {
                username: string;
                display_name: string;
                email: string | null;
                role?: string;
                active?: boolean;
                password?: string;
                hired_on: string | null;
                left_on: string | null;
              } = {
                username: account.username,
                display_name: account.display_name,
                email: account.email.trim() || null,
                hired_on: account.hired_on || null,
                left_on: account.left_on || null,
              };
              if (isAdmin) {
                body.role = account.role;
                body.active = account.active;
                if (account.password.trim()) body.password = account.password.trim();
              }
              const next = await api.patchUserAccount(userId, body);
              setUser(next);
              setGeneratedPassword("");
              setAccount({
                ...account,
                password: "",
                display_name: next.display_name,
                username: next.username,
                email: next.email ?? "",
                role: next.role,
                active: next.active,
                hired_on: next.hired_on ?? "",
                left_on: next.left_on ?? "",
              });
              setAccountMsg("Benutzer gespeichert.");
              await reload();
            } catch (err) {
              setAccountMsg(err instanceof Error ? err.message : "Fehler");
            }
          }}
        >
          <p className="text-sm font-medium">Benutzer</p>
          <label className="block text-xs text-muted">
            Anzeigename
            <input
              className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
              value={account.display_name}
              onChange={(e) => setAccount({ ...account, display_name: e.target.value })}
              required
            />
          </label>
          <label className="block text-xs text-muted">
            Benutzername
            <input
              className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
              value={account.username}
              onChange={(e) => setAccount({ ...account, username: e.target.value })}
              autoCapitalize="none"
              required
            />
          </label>
          <label className="block text-xs text-muted">
            E-Mail
            <input
              type="email"
              className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
              value={account.email}
              onChange={(e) => setAccount({ ...account, email: e.target.value })}
              autoCapitalize="none"
            />
          </label>
          <label className="block text-xs text-muted">
            Rolle
            <select
              className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink disabled:opacity-70"
              value={account.role}
              disabled={!isAdmin}
              onChange={(e) => setAccount({ ...account, role: e.target.value })}
            >
              <option value="employee">Mitarbeiter</option>
              <option value="supervisor">Vorgesetzt</option>
              <option value="hr">Personal</option>
              <option value="admin">Admin</option>
            </select>
            {!isAdmin ? <span className="mt-1 block">Nur Administrator darf die Rolle ändern.</span> : null}
          </label>
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={account.active}
              disabled={!isAdmin}
              onChange={(e) => setAccount({ ...account, active: e.target.checked })}
            />
            <span>
              Aktiv
              {!isAdmin ? <span className="mt-0.5 block text-xs text-muted">Nur Administrator darf Konten deaktivieren.</span> : null}
            </span>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block min-w-0 overflow-hidden text-xs text-muted">
              Eintritt
              <input
                type="date"
                className="mt-1 h-10 w-full rounded-lg border border-line bg-bg px-2 text-sm text-ink"
                value={account.hired_on}
                onChange={(e) => setAccount({ ...account, hired_on: e.target.value })}
                required
              />
            </label>
            <div className="min-w-0 overflow-hidden text-xs text-muted">
              <div className="flex items-baseline justify-between gap-2">
                <label htmlFor="account-left-on">Austritt</label>
                {account.left_on ? (
                  <button
                    type="button"
                    className="text-present"
                    onClick={() => setAccount({ ...account, left_on: "" })}
                  >
                    Leeren
                  </button>
                ) : null}
              </div>
              <input
                id="account-left-on"
                key={account.left_on ? "left-set" : "left-empty"}
                type="date"
                className="mt-1 h-10 w-full rounded-lg border border-line bg-bg px-2 text-sm text-ink"
                value={account.left_on}
                onChange={(e) => setAccount({ ...account, left_on: e.target.value })}
              />
            </div>
          </div>
          {isAdmin ? (
            <>
              <label className="block text-xs text-muted">
                Neues Passwort (leer lassen zum Behalten)
                <PasswordField
                  autoComplete="new-password"
                  minLength={8}
                  className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
                  value={account.password}
                  onChange={(e) => {
                    setAccount({ ...account, password: e.target.value });
                    setGeneratedPassword("");
                  }}
                  placeholder="mind. 8 Zeichen"
                />
              </label>
              <button
                type="button"
                className="text-sm text-present"
                onClick={() => {
                  const next = generatePassword();
                  setAccount((cur) => ({ ...cur, password: next }));
                  setGeneratedPassword(next);
                }}
              >
                Passwort erzeugen
              </button>
              {generatedPassword ? (
                <p className="rounded-lg bg-bg px-3 py-2 font-mono text-sm text-ink">
                  Bitte notieren: {generatedPassword}
                </p>
              ) : null}
            </>
          ) : null}
          {accountMsg ? (
            <p className={`text-sm ${accountMsg === "Benutzer gespeichert." ? "text-present" : "text-danger"}`}>
              {accountMsg}
            </p>
          ) : null}
          <button type="submit" className="w-full rounded-xl bg-navy py-2 text-sm text-white">
            Benutzer speichern
          </button>
        </form>
      ) : null}
      {user && user.web_login && user.auth_source === "local" ? (
        <div className="space-y-2 rounded-2xl border border-line bg-card p-4">
          <p className="text-sm font-medium">Zugang per Mail</p>
          <p className="text-xs text-muted">
            Sendet einen Link, mit dem {user.display_name} das Passwort selbst setzt. Dafür braucht es eine
            E-Mail-Adresse und einen eingerichteten Mailserver.
          </p>
          {inviteMsg ? (
            <p className={`text-sm ${inviteMsg.startsWith("Mail") ? "text-present" : "text-danger"}`}>{inviteMsg}</p>
          ) : null}
          <button
            type="button"
            disabled={inviteBusy || !account.email.trim()}
            className="w-full rounded-xl bg-present py-2 text-sm text-white disabled:opacity-60"
            onClick={async () => {
              setInviteMsg("");
              setInviteBusy(true);
              try {
                if (account.email.trim() && account.email.trim() !== (user.email ?? "")) {
                  await api.patchUserAccount(userId, { email: account.email.trim() });
                }
                await api.sendAccessMail(userId);
                setInviteMsg("Mail ist unterwegs.");
              } catch (err) {
                setInviteMsg(err instanceof Error ? err.message : "Fehler");
              } finally {
                setInviteBusy(false);
              }
            }}
          >
            {inviteBusy ? "Senden …" : "Zugangsdaten senden"}
          </button>
        </div>
      ) : null}
      {user ? (
        <label className="flex items-start gap-3 rounded-2xl border border-line bg-card px-4 py-3 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={Boolean(user.auto_break)}
            onChange={async (e) => {
              const next = await api.patchUserSettings(userId, { auto_break: e.target.checked });
              setUser(next);
              await reload();
            }}
          />
          <span>
            <span className="font-medium">Pausenautomatik</span>
            <span className="mt-0.5 block text-xs text-muted">
              Wenn keine Pause gestempelt wurde: 30 Min. ab 6 Std., 45 Min. ab 9 Std. Arbeitszeit.
            </span>
          </span>
        </label>
      ) : null}
      {user ? (
        <form
          className="space-y-2 rounded-2xl border border-line bg-card p-4"
          onSubmit={async (e: FormEvent) => {
            e.preventDefault();
            setAccessMsg("");
            try {
              const next = await api.patchUserSettings(userId, {
                transponder_id: transponder.trim() || null,
                ...(isAdmin ? { web_login: webLogin } : {}),
              });
              setUser(next);
              setTransponder(next.transponder_id ?? "");
              setWebLogin(next.web_login);
              setAccessMsg("Zugang gespeichert.");
            } catch (err) {
              setAccessMsg(err instanceof Error ? err.message : "Fehler");
            }
          }}
        >
          <p className="text-sm font-medium">Terminal und Webseite</p>
          <label className="block text-xs text-muted">
            Transpondernummer
            <input
              className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 font-mono text-sm text-ink"
              value={transponder}
              onChange={(e) => setTransponder(e.target.value)}
              placeholder="wie am Gerät angezeigt"
            />
          </label>
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={webLogin}
              disabled={!isAdmin || ["hr", "admin", "supervisor"].includes(user.role)}
              onChange={(e) => setWebLogin(e.target.checked)}
            />
            <span>
              Anmeldung auf der Webseite aktivieren
              {!isAdmin ? (
                <span className="mt-0.5 block text-xs text-muted">Nur Administrator darf den Web-Zugang ändern.</span>
              ) : null}
            </span>
          </label>
          {accessMsg ? (
            <p className={`text-sm ${accessMsg === "Zugang gespeichert." ? "text-present" : "text-danger"}`}>{accessMsg}</p>
          ) : null}
          <button type="submit" className="w-full rounded-xl bg-navy py-2 text-sm text-white">
            Zugang speichern
          </button>
        </form>
      ) : null}
      <form
        className="space-y-2 rounded-2xl border border-line bg-card p-4"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          setModelMsg("");
          setModelConfirm(true);
        }}
      >
        <p className="text-sm font-medium">Arbeitszeitmodell</p>
        <p className="text-xs text-muted">Aktuell: {user?.work_model_name ?? "keins"}</p>
        <select
          className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm"
          value={modelId}
          onChange={(e) => setModelId(e.target.value)}
          required
        >
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
        <label className="block min-w-0 overflow-hidden text-xs text-muted">
          Gültig ab
          <input
            type="date"
            className="mt-1 h-10 w-full rounded-lg border border-line bg-bg px-2 text-sm text-ink"
            value={modelFrom}
            onChange={(e) => setModelFrom(e.target.value)}
            required
          />
        </label>
        {modelMsg ? <p className="text-sm text-present">{modelMsg}</p> : null}
        <button type="submit" className="w-full rounded-xl bg-navy py-2 text-sm text-white">
          Modell setzen
        </button>
        {assignments.length ? (
          <ul className="mt-2 space-y-1 text-xs text-muted">
            {assignments.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2">
                <span>
                  {a.work_model_name} ab{" "}
                  {new Date(a.valid_from + "T12:00:00").toLocaleDateString("de-DE")}
                </span>
                <button
                  type="button"
                  className="rounded-lg p-1 text-danger"
                  title="Löschen"
                  aria-label="Löschen"
                  onClick={() => {
                    setModelMsg("");
                    setModelDelete(a);
                  }}
                >
                  <IconTrash className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </form>
      <form
        className="space-y-2 rounded-2xl border border-line bg-card p-4"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          setAbsMsg("");
          setAbsConfirm(true);
        }}
      >
        <p className="text-sm font-medium">Urlaub und Krankheit</p>
        <div className="grid grid-cols-2 gap-2">
          <select
            className="col-span-2 min-w-0 rounded-lg border border-line bg-bg px-3 py-2 text-sm"
            value={absKind}
            onChange={(e) => setAbsKind(e.target.value)}
          >
            <option value="vacation">Urlaub</option>
            <option value="sick">Krankheit</option>
            <option value="holiday">Brückentag (nur diese Person)</option>
          </select>
          <label className="block min-w-0 overflow-hidden text-xs text-muted">
            Von
            <input
              type="date"
              className="mt-1 h-10 w-full rounded-lg border border-line bg-bg px-2 text-sm text-ink"
              value={absStart}
              onChange={(e) => setAbsStart(e.target.value)}
              required
            />
          </label>
          <label className="block min-w-0 overflow-hidden text-xs text-muted">
            Bis
            <input
              type="date"
              className="mt-1 h-10 w-full rounded-lg border border-line bg-bg px-2 text-sm text-ink"
              value={absEnd}
              onChange={(e) => setAbsEnd(e.target.value)}
              required
            />
          </label>
        </div>
        <input
          placeholder="Notiz, optional"
          className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm"
          value={absNote}
          onChange={(e) => setAbsNote(e.target.value)}
        />
        {absMsg ? <p className="text-sm text-present">{absMsg}</p> : null}
        <button type="submit" className="w-full rounded-xl bg-present py-2 text-sm text-white">
          Eintragen
        </button>
      </form>
    </>
  );

  return (
    <div className="pt-2">
      <Link to={from === "pruefung" ? `/pruefung?month=${month}&user=${userId}` : "/personal"} className="text-sm text-muted">
        ← {from === "pruefung" ? "Prüfung" : "Personal"}
      </Link>
      <div className="mt-2 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-medium">{user?.display_name ?? "…"}</h1>
          <p className="text-xs text-muted">
            {user ? ROLE[user.role] ?? user.role : ""}
            {user?.work_model_name ? ` · ${user.work_model_name}` : ""}
          </p>
          {days.length ? (
            <p className="mt-1 text-sm text-muted">
              Ist {formatHours(totals.work)} · Soll {formatHours(totals.soll)} · Monat{" "}
              <span className={hoursTone(monthFlex)}>{signedHours(monthFlex)}</span>
              {" · "}
              Gesamt <span className={hoursTone(totalFlex)}>{signedHours(totalFlex)}</span>
            </p>
          ) : null}
        </div>
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
        />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
        <button
          type="button"
          className="text-present"
          onClick={async () => {
            setExportMsg("");
            try {
              await api.downloadExportCsv(month, userId);
            } catch (err) {
              setExportMsg(err instanceof Error ? err.message : "CSV-Export fehlgeschlagen.");
            }
          }}
        >
          CSV exportieren
        </button>
        {from === "pruefung" ? (
          <Link to="/personal" className="text-muted">
            Zur Personalliste
          </Link>
        ) : (
          <Link to={`/pruefung?month=${month}&user=${userId}`} className="text-muted">
            Zur Prüfung
          </Link>
        )}
        <Link to="/modelle" className="text-muted">
          Modelle
        </Link>
        <Link to="/feiertage" className="text-muted">
          Feiertage
        </Link>
      </div>
      {exportMsg ? <p className="mt-2 text-sm text-danger">{exportMsg}</p> : null}
      <div className="mt-4 flex flex-col gap-3 xl:grid xl:grid-cols-[minmax(0,1fr)_22rem] xl:items-start xl:gap-6">
        <div className="order-2 xl:order-1">
          <DayLegend />
          <ul className="mt-3 space-y-2 xl:hidden">
            {visibleDays.map((d) => {
              const issues = d.warnings.filter((w) => w !== "overnight");
              const overnight = d.warnings.includes("overnight");
              return (
                <li key={d.date}>
                  <Link
                    to={`/personal/${userId}/tag/${d.date}?from=${from === "pruefung" ? "pruefung" : "personal"}&month=${month}`}
                    className={`block rounded-2xl border px-4 py-3 ${
                      issues.length ? `${daySurfaceClass(d)} ring-1 ring-danger/40` : daySurfaceClass(d)
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium">{formatDayLabel(d.date, "long")}</p>
                        <p className="mt-1 text-xs text-muted">{bookingText(d, "Keine Buchung")}</p>
                        {overnight && !issues.length ? (
                          <p className="mt-1 text-xs text-muted">{warnLabel("overnight")}</p>
                        ) : null}
                        {issues.length ? (
                          <p className="mt-1 text-xs text-danger">{issues.map(warnLabel).join(" · ")}</p>
                        ) : null}
                        {d.accepted ? <p className="mt-1 text-xs text-present">Akzeptiert</p> : null}
                        {d.auto_break_minutes ? (
                          <p className="mt-1 text-xs text-muted">Pause auto. {d.auto_break_minutes} Min.</p>
                        ) : null}
                      </div>
                      <div className="flex shrink-0 items-center gap-1 text-right text-sm">
                        <div>
                          <p className="whitespace-nowrap text-present">
                            {d.calendar || d.absence || !d.work_hours ? "" : formatHours(d.work_hours)}
                          </p>
                          {d.calendar || d.absence || (!d.work_hours && !d.soll_hours) ? null : (
                            <p className={`whitespace-nowrap text-xs ${hoursTone(d.delta_hours)}`}>
                              {signedHours(d.delta_hours)}
                            </p>
                          )}
                        </div>
                        <IconChevron className="h-5 w-5 text-muted" />
                      </div>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
          <div className="mt-3 hidden overflow-x-auto rounded-2xl border border-line xl:block">
            <table className="w-full min-w-[36rem] text-left text-sm">
              <thead className="bg-card text-xs uppercase tracking-wider text-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Datum</th>
                  <th className="px-4 py-3 font-medium">Buchungen</th>
                  <th className="px-4 py-3 font-medium text-right">Ist</th>
                  <th className="px-4 py-3 font-medium text-right">Soll</th>
                  <th className="px-4 py-3 font-medium text-right">Konto</th>
                  <th className="px-4 py-3 font-medium">Hinweise</th>
                </tr>
              </thead>
              <tbody>
                {visibleDays.map((d) => {
                  const issues = d.warnings.filter((w) => w !== "overnight");
                  return (
                    <tr
                      key={d.date}
                      className={`border-t border-line ${dayRowClass(d)} ${issues.length ? "outline outline-1 -outline-offset-1 outline-danger/40" : ""}`}
                    >
                      <td className="whitespace-nowrap px-4 py-2.5">
                        <Link
                          className="font-medium text-present"
                          to={`/personal/${userId}/tag/${d.date}?from=${from === "pruefung" ? "pruefung" : "personal"}&month=${month}`}
                        >
                          {formatDayLabel(d.date, "short")}
                        </Link>
                      </td>
                      <td className="px-4 py-2.5 text-muted">{bookingText(d)}</td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right tabular-nums">
                        {(d.calendar || d.absence) && !d.work_hours ? "—" : formatHours(d.work_hours)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right tabular-nums text-muted">
                        {formatHours(d.soll_hours)}
                      </td>
                      <td
                        className={`whitespace-nowrap px-4 py-2.5 text-right tabular-nums ${hoursTone(
                          d.delta_hours,
                          Boolean(d.calendar || d.absence),
                        )}`}
                      >
                        {d.calendar || d.absence ? "—" : signedHours(d.delta_hours)}
                      </td>
                      <td className={`px-4 py-2.5 text-xs ${issues.length ? "text-danger" : "text-muted"}`}>
                        {d.warnings.map(warnLabel).join(" · ") || (d.accepted ? "Akzeptiert" : "—")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        <div className="order-1 space-y-3 xl:order-2 xl:sticky xl:top-6">{settings}</div>
      </div>
      {modelConfirm ? (
        <div className="fixed inset-0 z-20 flex items-end justify-center bg-black/40 p-4 sm:items-center">
          <div className="w-full max-w-lg rounded-2xl bg-card p-5 shadow-xl">
            <p className="text-lg font-medium">Modell ändern?</p>
            <p className="mt-1 text-sm text-muted">
              {chosenModel?.name ?? "Modell"} gilt ab{" "}
              {new Date(modelFrom + "T12:00:00").toLocaleDateString("de-DE")}. Tage davor behalten das bisherige
              Modell, ab diesem Datum gilt das neue Soll.
            </p>
            <div className="mt-4 flex gap-2">
              <button type="button" className="flex-1 rounded-xl border border-line py-2" onClick={() => setModelConfirm(false)}>
                Zurück
              </button>
              <button
                type="button"
                className="flex-1 rounded-xl bg-navy py-2 text-white"
                onClick={async () => {
                  try {
                    await api.assignUserModel(userId, { work_model_id: Number(modelId), valid_from: modelFrom });
                    setModelConfirm(false);
                    setModelMsg("Modell gesetzt.");
                    await reload();
                  } catch (err) {
                    setModelConfirm(false);
                    setModelMsg(err instanceof Error ? err.message : "Fehler");
                  }
                }}
              >
                Übernehmen
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {modelDelete ? (
        <ConfirmDialog
          title="Modellzuordnung löschen?"
          body={`${modelDelete.work_model_name} ab ${new Date(modelDelete.valid_from + "T12:00:00").toLocaleDateString("de-DE")} wird entfernt. Das Soll richtet sich dann nach der vorherigen Zuordnung.`}
          confirmLabel="Löschen"
          danger
          onCancel={() => setModelDelete(null)}
          onConfirm={() => {
            const assignment = modelDelete;
            void (async () => {
              try {
                await api.deleteUserModel(userId, assignment.id);
                setModelDelete(null);
                setModelMsg("Modellzuordnung gelöscht.");
                await reload();
              } catch (err) {
                setModelDelete(null);
                setModelMsg(err instanceof Error ? err.message : "Fehler");
              }
            })();
          }}
        />
      ) : null}
      {absConfirm ? (
        <div className="fixed inset-0 z-20 flex items-end justify-center bg-black/40 p-4 sm:items-center">
          <div className="w-full max-w-lg rounded-2xl bg-card p-5 shadow-xl">
            <p className="text-lg font-medium">
              {absKind === "vacation"
                ? "Urlaub eintragen?"
                : absKind === "sick"
                  ? "Krankheitstage eintragen?"
                  : "Abwesenheit eintragen?"}
            </p>
            <p className="mt-1 text-sm text-muted">
              {absStart === absEnd
                ? `${new Date(absStart + "T12:00:00").toLocaleDateString("de-DE")} gilt dann als abwesend und fällt aus der Prüfung.`
                : `${new Date(absStart + "T12:00:00").toLocaleDateString("de-DE")} bis ${new Date(absEnd + "T12:00:00").toLocaleDateString("de-DE")} gelten als abwesend und fallen aus der Prüfung.`}
            </p>
            <div className="mt-4 flex gap-2">
              <button type="button" className="flex-1 rounded-xl border border-line py-2" onClick={() => setAbsConfirm(false)}>
                Zurück
              </button>
              <button
                type="button"
                className="flex-1 rounded-xl bg-present py-2 text-white"
                onClick={async () => {
                  try {
                    await api.createAbsences(userId, {
                      kind: absKind,
                      start: absStart,
                      end: absEnd,
                      note: absNote || undefined,
                    });
                    setAbsNote("");
                    setAbsConfirm(false);
                    setAbsMsg("Abwesenheit eingetragen.");
                    await reload();
                  } catch (err) {
                    setAbsConfirm(false);
                    setAbsMsg(err instanceof Error ? err.message : "Fehler");
                  }
                }}
              >
                Eintragen
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
