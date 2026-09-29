import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, type DaySummary, type Department, type User, type WorkModel, type WorkModelAssignment } from "../api";
import { useClosedMonth } from "../closedMonth";
import { useAuth } from "../auth";
import AccountBooks from "../components/AccountBooks";
import DayLegend from "../components/DayLegend";
import ConfirmDialog from "../components/ConfirmDialog";
import LoadingNote from "../components/LoadingNote";
import FieldError from "../components/FieldError";
import { IconChevron, IconTrash } from "../components/Icons";
import PasswordField from "../components/PasswordField";
import UnsavedChangesDialog from "../components/UnsavedChangesDialog";
import { bookingText, dayRowClass, daySurfaceClass, formatDayLabel, formatHours, hoursTone, parseHours, signedHours, warnLabel } from "../labels";
import { generatePassword } from "../password";
import { useUnsavedGuard } from "../unsaved";
import { firstUserFieldError, inputClass, validateUserAccount, type UserFieldErrors } from "../userForm";

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
  const canManage = me?.role === "hr" || me?.role === "admin";
  const nav = useNavigate();
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
  const [departments, setDepartments] = useState<Department[]>([]);
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
    first_name: "",
    last_name: "",
    username: "",
    email: "",
    role: "employee",
    active: true,
    password: "",
    hired_on: "",
    left_on: "",
    birthday: "",
    vacation_days_year: "",
    department_id: "",
  });
  const [accountMsg, setAccountMsg] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteAck, setDeleteAck] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [accountErrors, setAccountErrors] = useState<UserFieldErrors>({});
  const [generatedPassword, setGeneratedPassword] = useState("");
  const [exportMsg, setExportMsg] = useState("");
  const [inviteMsg, setInviteMsg] = useState("");
  const [inviteBusy, setInviteBusy] = useState(false);
  const [monthClosed, setMonthClosed] = useState(false);
  const [openingHours, setOpeningHours] = useState("0");
  const [openingOn, setOpeningOn] = useState("");
  const [openingMsg, setOpeningMsg] = useState("");
  const [openingOpen, setOpeningOpen] = useState(false);
  const closed = useClosedMonth();

  async function reload() {
    if (!userId) return;
    const [r, m, a, d] = await Promise.all([api.userDays(userId, month), api.models(), api.userModels(userId), api.departments()]);
    setUser(r.user);
    setMonthClosed(Boolean(r.closed));
    setOpeningHours(signedHours(r.user.opening_balance_hours ?? 0));
    setOpeningOn(r.user.opening_balance_on ?? "");
    setDays(r.days);
    setMonthFlex(r.month_flex ?? 0);
    setTotalFlex(r.total_flex ?? 0);
    setModels(m);
    setDepartments(d);
    setAssignments(a);
    setModelId((cur) => cur || String(r.user.work_model_id ?? m[0]?.id ?? ""));
    setTransponder(r.user.transponder_id ?? "");
    setWebLogin(r.user.web_login !== false);
    setAccount((cur) => ({
      first_name: r.user.first_name ?? "",
      last_name: r.user.last_name ?? "",
      username: r.user.username,
      email: r.user.email ?? "",
      role: r.user.role,
      active: r.user.active,
      password: cur.username === r.user.username ? cur.password : "",
      hired_on: r.user.hired_on ?? "",
      left_on: r.user.left_on ?? "",
      birthday: r.user.birthday ?? "",
      vacation_days_year: r.user.vacation_days_year != null ? String(r.user.vacation_days_year) : "",
      department_id: r.user.department_id != null ? String(r.user.department_id) : "",
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

  const accountDirty = Boolean(
    user &&
      (account.first_name !== (user.first_name ?? "") ||
        account.last_name !== (user.last_name ?? "") ||
        account.username !== user.username ||
        account.email !== (user.email ?? "") ||
        account.role !== user.role ||
        account.active !== user.active ||
        account.hired_on !== (user.hired_on ?? "") ||
        account.left_on !== (user.left_on ?? "") ||
        account.birthday !== (user.birthday ?? "") ||
        account.vacation_days_year !== (user.vacation_days_year != null ? String(user.vacation_days_year) : "") ||
        account.department_id !== (user.department_id != null ? String(user.department_id) : "") ||
        account.password.trim() !== ""),
  );
  const accessDirty = Boolean(
    user && (transponder !== (user.transponder_id ?? "") || webLogin !== (user.web_login !== false)),
  );
  const dirty = accountDirty || accessDirty;
  const blocker = useUnsavedGuard(dirty);

  function patchAccount(patch: Partial<typeof account>) {
    setAccount((cur) => ({ ...cur, ...patch }));
    setAccountErrors((cur) => {
      const next = { ...cur };
      for (const key of Object.keys(patch) as (keyof UserFieldErrors)[]) {
        delete next[key];
      }
      return next;
    });
  }

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
          noValidate
          onSubmit={async (e: FormEvent) => {
            e.preventDefault();
            setAccountMsg("");
            const nextErrors = validateUserAccount({
              first_name: account.first_name,
              last_name: account.last_name,
              username: account.username,
              email: account.email,
              password: account.password,
              hired_on: account.hired_on,
              left_on: account.left_on,
            });
            setAccountErrors(nextErrors);
            if (firstUserFieldError(nextErrors)) {
              setAccountMsg("Bitte die markierten Felder ausfüllen.");
              requestAnimationFrame(() => {
                document.querySelector<HTMLElement>("#user-account-form [aria-invalid='true']")?.focus();
              });
              return;
            }
            const body: {
              username: string;
              first_name: string;
              last_name: string;
              email: string | null;
              role?: string;
              active?: boolean;
              password?: string;
              hired_on: string | null;
              left_on: string | null;
              birthday: string | null;
              vacation_days_year: number | null;
              department_id: number | null;
              confirm_closed?: boolean;
            } = {
              username: account.username,
              first_name: account.first_name,
              last_name: account.last_name,
              email: account.email.trim() || null,
              hired_on: account.hired_on || null,
              left_on: account.left_on || null,
              birthday: account.birthday || null,
              vacation_days_year: account.vacation_days_year.trim() === "" ? null : Number(account.vacation_days_year.replace(",", ".")),
              department_id: account.department_id ? Number(account.department_id) : null,
            };
            if (isAdmin) {
              body.role = account.role;
              body.active = account.active;
              if (account.password.trim()) body.password = account.password.trim();
            }
            await closed.attempt(async (confirmClosed) => {
              const next = await api.patchUserAccount(userId, { ...body, confirm_closed: confirmClosed });
              setUser(next);
              setGeneratedPassword("");
              setAccountErrors({});
              setAccount({
                ...account,
                password: "",
                first_name: next.first_name ?? "",
                last_name: next.last_name ?? "",
                username: next.username,
                email: next.email ?? "",
                role: next.role,
                active: next.active,
                hired_on: next.hired_on ?? "",
                left_on: next.left_on ?? "",
                birthday: next.birthday ?? "",
                vacation_days_year: next.vacation_days_year != null ? String(next.vacation_days_year) : "",
                department_id: next.department_id != null ? String(next.department_id) : "",
              });
              setAccountMsg("Benutzer gespeichert.");
              await reload();
            }, setAccountMsg);
          }}
          id="user-account-form"
        >
          <p className="text-sm font-medium">Benutzer</p>
          <label className="block text-xs text-muted">
            Vorname
            <input
              className={`mt-1 w-full px-3 py-2 text-sm ${inputClass(accountErrors.first_name)}`}
              value={account.first_name}
              onChange={(e) => patchAccount({ first_name: e.target.value })}
              aria-invalid={Boolean(accountErrors.first_name)}
              aria-describedby={accountErrors.first_name ? "err-acc-first" : undefined}
            />
            <FieldError id="err-acc-first">{accountErrors.first_name}</FieldError>
          </label>
          <label className="block text-xs text-muted">
            Nachname
            <input
              placeholder="z. B. PU Berg"
              className={`mt-1 w-full px-3 py-2 text-sm ${inputClass(accountErrors.last_name)}`}
              value={account.last_name}
              onChange={(e) => patchAccount({ last_name: e.target.value })}
              aria-invalid={Boolean(accountErrors.last_name)}
              aria-describedby={accountErrors.last_name ? "err-acc-last" : undefined}
            />
            <FieldError id="err-acc-last">{accountErrors.last_name}</FieldError>
          </label>
          <label className="block text-xs text-muted">
            Benutzername
            <input
              className={`mt-1 w-full px-3 py-2 text-sm ${inputClass(accountErrors.username)}`}
              value={account.username}
              onChange={(e) => patchAccount({ username: e.target.value })}
              autoCapitalize="none"
              aria-invalid={Boolean(accountErrors.username)}
              aria-describedby={accountErrors.username ? "err-acc-username" : undefined}
            />
            <FieldError id="err-acc-username">{accountErrors.username}</FieldError>
          </label>
          <label className="block text-xs text-muted">
            E-Mail
            <input
              type="email"
              className={`mt-1 w-full px-3 py-2 text-sm ${inputClass(accountErrors.email)}`}
              value={account.email}
              onChange={(e) => patchAccount({ email: e.target.value })}
              autoCapitalize="none"
              aria-invalid={Boolean(accountErrors.email)}
              aria-describedby={accountErrors.email ? "err-acc-email" : undefined}
            />
            <FieldError id="err-acc-email">{accountErrors.email}</FieldError>
          </label>
          <label className="block text-xs text-muted">
            Rolle
            <select
              className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink disabled:opacity-70"
              value={account.role}
              disabled={!isAdmin}
              onChange={(e) => patchAccount({ role: e.target.value })}
            >
              <option value="employee">Mitarbeiter</option>
              <option value="supervisor">Vorgesetzt</option>
              <option value="hr">Personal</option>
              <option value="admin">Admin</option>
            </select>
            {!isAdmin ? <span className="mt-1 block">Nur Administrator darf die Rolle ändern.</span> : null}
          </label>
          <label className="block text-xs text-muted">
            Abteilung
            <select
              className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
              value={account.department_id}
              onChange={(e) => patchAccount({ department_id: e.target.value })}
            >
              <option value="">Keine Abteilung</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              className="mt-1"
              checked={account.active}
              disabled={!isAdmin}
              onChange={(e) => patchAccount({ active: e.target.checked })}
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
                className={`mt-1 h-10 w-full px-2 text-sm ${inputClass(accountErrors.hired_on)}`}
                value={account.hired_on}
                onChange={(e) => patchAccount({ hired_on: e.target.value })}
                aria-invalid={Boolean(accountErrors.hired_on)}
                aria-describedby={accountErrors.hired_on ? "err-acc-hired" : undefined}
              />
              <FieldError id="err-acc-hired">{accountErrors.hired_on}</FieldError>
            </label>
            <div className="min-w-0 overflow-hidden text-xs text-muted">
              <div className="flex items-baseline justify-between gap-2">
                <label htmlFor="account-left-on">Austritt</label>
                {account.left_on ? (
                  <button type="button" className="text-present" onClick={() => patchAccount({ left_on: "" })}>
                    Leeren
                  </button>
                ) : null}
              </div>
              <input
                id="account-left-on"
                key={account.left_on ? "left-set" : "left-empty"}
                type="date"
                className={`mt-1 h-10 w-full px-2 text-sm ${inputClass(accountErrors.left_on)}`}
                value={account.left_on}
                onChange={(e) => patchAccount({ left_on: e.target.value })}
                aria-invalid={Boolean(accountErrors.left_on)}
                aria-describedby={accountErrors.left_on ? "err-acc-left" : undefined}
              />
              <FieldError id="err-acc-left">{accountErrors.left_on}</FieldError>
            </div>
          </div>
          <label className="block min-w-0 overflow-hidden text-xs text-muted">
            Geburtstag (optional)
            <input
              type="date"
              className="mt-1 h-10 w-full rounded-lg border border-line bg-bg px-2 text-sm"
              value={account.birthday}
              onChange={(e) => patchAccount({ birthday: e.target.value })}
            />
          </label>
          <label className="block min-w-0 overflow-hidden text-xs text-muted">
            Urlaubstage/Jahr
            <input
              type="number"
              min={0}
              max={366}
              step={0.5}
              className="mt-1 h-10 w-full rounded-lg border border-line bg-bg px-2 text-sm"
              value={account.vacation_days_year}
              onChange={(e) => patchAccount({ vacation_days_year: e.target.value })}
            />
          </label>
          {isAdmin ? (
            <>
              <label className="block text-xs text-muted">
                Neues Passwort (leer lassen zum Behalten)
                <PasswordField
                  autoComplete="new-password"
                  minLength={8}
                  className={`mt-1 w-full px-3 py-2 text-sm ${inputClass(accountErrors.password)}`}
                  value={account.password}
                  onChange={(e) => {
                    patchAccount({ password: e.target.value });
                    setGeneratedPassword("");
                  }}
                  placeholder="mind. 8 Zeichen"
                  aria-invalid={Boolean(accountErrors.password)}
                  aria-describedby={accountErrors.password ? "err-acc-password" : undefined}
                />
                <FieldError id="err-acc-password">{accountErrors.password}</FieldError>
              </label>
              <button
                type="button"
                className="text-sm text-present"
                onClick={() => {
                  const next = generatePassword();
                  setAccount((cur) => ({ ...cur, password: next }));
                  setAccountErrors((cur) => {
                    const nextErr = { ...cur };
                    delete nextErr.password;
                    return nextErr;
                  });
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
              className="mt-0.5 h-4 w-4 shrink-0"
              checked={Boolean(user.auto_break)}
              onChange={async (e) => {
                const next = await api.patchUserSettings(userId, { auto_break: e.target.checked });
                setUser(next);
                await reload();
              }}
            />
            <span>
              Pausenautomatik
              <span className="mt-0.5 block text-xs text-muted">
                Ohne gestempelte Pause: über 6 Stunden nur der Überhang bis 30 Minuten, über 9 Stunden nur der Überhang bis 45 Minuten.
              </span>
            </span>
          </label>
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 shrink-0"
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
      {isAdmin && user && me?.id !== user.id ? (
        <div className="space-y-2 rounded-2xl border border-danger/40 bg-card p-4">
          <p className="text-sm font-medium text-danger">Person löschen</p>
          <p className="text-xs text-muted">
            Entfernt {user.display_name} samt allen Stempeln, Abwesenheiten und dem Konto. Das ist keine
            Deaktivierung und lässt sich nicht rückgängig machen.
          </p>
          <button
            type="button"
            className="w-full rounded-xl border border-danger py-2 text-sm text-danger"
            onClick={() => {
              setDeleteAck(false);
              setDeleteOpen(true);
            }}
          >
            Endgültig löschen
          </button>
        </div>
      ) : null}
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
          {monthClosed ? (
            <p className="mt-2 text-sm">Dieser Monat ist abgeschlossen. Änderungen rechnen die Abschlüsse neu.</p>
          ) : null}
        </div>
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
        />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <button type="button" className="text-sm text-present" onClick={() => setOpeningOpen((open) => !open)}>
          {openingOpen ? "Startkonto schließen" : "Startkonto"}
        </button>
        {user ? (
          <AccountBooks
            userId={userId}
            year={Number(month.slice(0, 4))}
            attempt={closed.attempt}
            onChanged={reload}
          />
        ) : null}
        {openingOpen ? (
          <div className="w-full">
          <form
            className="max-w-lg space-y-2 rounded-2xl border border-line bg-card p-4"
            onSubmit={(e) => {
              e.preventDefault();
              setOpeningMsg("");
              const hours = parseHours(openingHours);
              if (hours == null) {
                setOpeningMsg("Stunden als hh:mm eingeben, zum Beispiel 12:30 oder -4:15.");
                return;
              }
              void closed.attempt(async (confirmClosed) => {
                await api.patchUserAccount(userId, {
                  opening_balance_hours: hours,
                  opening_balance_on: openingOn || null,
                  confirm_closed: confirmClosed,
                });
                setOpeningMsg("Startkonto gespeichert.");
                await reload();
              }, setOpeningMsg);
            }}
          >
            <p className="text-sm font-medium">Startkonto</p>
            <p className="text-xs text-muted">
              Normalerweise setzt das der Import aus dem letzten Abschluss, zusammen mit dem Stichtag unter
              Einstellungen. Hier nur, wenn eine Person einen anderen Anfangsstand braucht. Die Stunden gelten am
              Beginn des Datums. Tage davor zählen nicht. Liegt das Datum vor dem zentralen Stichtag, gilt der
              Stichtag.
            </p>
            <div className="flex flex-wrap gap-3">
              <label className="text-sm">
                Stunden
                <input
                  value={openingHours}
                  onChange={(e) => setOpeningHours(e.target.value)}
                  className="mt-1 block w-28 rounded-lg border border-line bg-bg px-2 py-1"
                />
              </label>
              <label className="text-sm">
                Gültig ab
                <input
                  type="date"
                  value={openingOn}
                  onChange={(e) => setOpeningOn(e.target.value)}
                  className="mt-1 block rounded-lg border border-line bg-bg px-2 py-1"
                />
              </label>
            </div>
            <button type="submit" className="rounded-xl bg-navy px-3 py-2 text-sm text-white">
              Startkonto speichern
            </button>
            {openingMsg ? <p className="text-sm text-muted">{openingMsg}</p> : null}
          </form>
          </div>
        ) : null}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
        {canManage ? (
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
        ) : null}
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
        <Link to="/abteilungen" className="text-muted">
          Abteilungen
        </Link>
        <Link to="/feiertage" className="text-muted">
          Feiertage
        </Link>
      </div>
      {exportMsg ? <p className="mt-2 text-sm text-danger">{exportMsg}</p> : null}
      <div className="mt-4 flex flex-col gap-3 xl:grid xl:grid-cols-[minmax(0,1fr)_22rem] xl:items-start xl:gap-6">
        <div className="order-2 xl:order-1">
          <DayLegend />
          {!user ? <LoadingNote /> : (
          <>
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
                            {d.work_hours ? formatHours(d.work_hours) : ""}
                          </p>
                          {(d.calendar || d.absence ? d.delta_hours !== 0 : Boolean(d.work_hours || d.soll_hours)) ? (
                            <p
                              className={`whitespace-nowrap text-xs ${hoursTone(
                                d.delta_hours,
                                Boolean((d.calendar || d.absence) && !d.delta_hours),
                              )}`}
                            >
                              {signedHours(d.delta_hours)}
                            </p>
                          ) : null}
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
                          Boolean((d.calendar || d.absence) && !d.delta_hours),
                        )}`}
                      >
                        {(d.calendar || d.absence) && !d.delta_hours ? "—" : signedHours(d.delta_hours)}
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
          </>
          )}
        </div>
        {canManage ? (
          <div className="order-1 space-y-3 xl:order-2 xl:sticky xl:top-6">{settings}</div>
        ) : null}
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
                onClick={() => {
                  void closed.attempt(async (confirmClosed) => {
                    await api.assignUserModel(userId, {
                      work_model_id: Number(modelId),
                      valid_from: modelFrom,
                      confirm_closed: confirmClosed,
                    });
                    setModelConfirm(false);
                    setModelMsg("Modell gesetzt.");
                    await reload();
                  }, (message) => {
                    setModelConfirm(false);
                    setModelMsg(message);
                  });
                }}
              >
                Übernehmen
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {deleteOpen && user ? (
        <ConfirmDialog
          title={`${user.display_name} unwiderruflich löschen?`}
          danger
          confirmDisabled={!deleteAck || deleteBusy}
          busy={deleteBusy}
          confirmLabel={deleteBusy ? "Löschen …" : "Endgültig löschen"}
          body={
            <div className="space-y-3">
              <p>
                Alle Stempel, Pausen, Urlaubs- und Krankheitstage, Salden, Modellzuordnungen, Passkeys und
                Einladungen von <span className="font-medium text-ink">{user.display_name}</span> werden gelöscht.
                Auswertungen zeigen die Person danach nicht mehr.
              </p>
              <p>Deaktivieren lässt Konto und Zeiten stehen. Löschen entfernt beides für immer.</p>
              <label className="flex items-start gap-2 text-ink">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={deleteAck}
                  onChange={(e) => setDeleteAck(e.target.checked)}
                />
                <span>Ich lösche {user.display_name} einschließlich aller Zeitdaten.</span>
              </label>
            </div>
          }
          onCancel={() => {
            if (!deleteBusy) setDeleteOpen(false);
          }}
          onConfirm={() => {
            void (async () => {
              setDeleteBusy(true);
              try {
                await api.deleteUser(user.id);
                nav("/personal");
              } catch (err) {
                setDeleteOpen(false);
                setAccountMsg(err instanceof Error ? err.message : "Löschen fehlgeschlagen");
              } finally {
                setDeleteBusy(false);
              }
            })();
          }}
        />
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
            void closed.attempt(async (confirmClosed) => {
              await api.deleteUserModel(userId, assignment.id, confirmClosed);
              setModelDelete(null);
              setModelMsg("Modellzuordnung gelöscht.");
              await reload();
            }, (message) => {
              setModelDelete(null);
              setModelMsg(message);
            });
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
                onClick={() => {
                  void closed.attempt(async (confirmClosed) => {
                    await api.createAbsences(userId, {
                      kind: absKind,
                      start: absStart,
                      end: absEnd,
                      note: absNote || undefined,
                      confirm_closed: confirmClosed,
                    });
                    setAbsNote("");
                    setAbsConfirm(false);
                    setAbsMsg("Abwesenheit eingetragen.");
                    await reload();
                  }, (message) => {
                    setAbsConfirm(false);
                    setAbsMsg(message);
                  });
                }}
              >
                Eintragen
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {closed.dialog}
      {blocker.state === "blocked" ? (
        <UnsavedChangesDialog onStay={() => blocker.reset()} onDiscard={() => blocker.proceed()} />
      ) : null}
    </div>
  );
}
