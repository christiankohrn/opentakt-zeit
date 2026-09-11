import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type FlexBalance, type User, type WorkModel } from "../api";
import { useAuth } from "../auth";
import FieldError from "../components/FieldError";
import PasswordField from "../components/PasswordField";
import UnsavedChangesDialog from "../components/UnsavedChangesDialog";
import { hoursTone, isoDate, signedHours } from "../labels";
import { generatePassword } from "../password";
import { useUnsavedGuard } from "../unsaved";
import { firstUserFieldError, inputClass, validateUserAccount, type UserFieldErrors } from "../userForm";

type UserForm = {
  username: string;
  display_name: string;
  email: string;
  password: string;
  role: string;
  work_model_id: string;
  transponder_id: string;
  web_login: boolean;
  hired_on: string;
  left_on: string;
  send_access_mail: boolean;
};

function emptyUserForm(workModelId: string): UserForm {
  return {
    username: "",
    display_name: "",
    email: "",
    password: "",
    role: "employee",
    work_model_id: workModelId,
    transponder_id: "",
    web_login: true,
    hired_on: isoDate(),
    left_on: "",
    send_access_mail: true,
  };
}

function SecurityBadges({ u, compact = false }: { u: User; compact?: boolean }) {
  const totp = Boolean(u.totp_enabled);
  const keys = u.passkey_count ?? 0;
  if (!totp && keys === 0) {
    return <span className="text-muted">{compact ? "keine 2FA" : "—"}</span>;
  }
  return (
    <span className="inline-flex flex-wrap gap-1">
      {totp ? (
        <span className="rounded border border-present px-1.5 py-0.5 text-xs text-present">2FA</span>
      ) : null}
      {keys > 0 ? (
        <span className="rounded border border-ok px-1.5 py-0.5 text-xs text-ok">
          {keys > 1 ? `${keys} Passkeys` : "Passkey"}
        </span>
      ) : null}
    </span>
  );
}

function payrollMonth() {
  const d = new Date();
  if (d.getDate() <= 15) {
    d.setDate(1);
    d.setMonth(d.getMonth() - 1);
  }
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function HrUsers() {
  const { user: me } = useAuth();
  const isAdmin = me?.role === "admin";
  const [params, setParams] = useSearchParams();
  const month = params.get("month") || payrollMonth();
  const [users, setUsers] = useState<User[]>([]);
  const [models, setModels] = useState<WorkModel[]>([]);
  const [balances, setBalances] = useState<Record<number, FlexBalance>>({});
  const [open, setOpen] = useState(false);
  const [closeConfirm, setCloseConfirm] = useState(false);
  const [form, setForm] = useState<UserForm>(() => emptyUserForm(""));
  const [fieldErrors, setFieldErrors] = useState<UserFieldErrors>({});
  const [error, setError] = useState("");
  const [generatedPassword, setGeneratedPassword] = useState("");
  const [mailReady, setMailReady] = useState(false);
  const [info, setInfo] = useState("");
  const dirty = open && JSON.stringify(form) !== JSON.stringify(emptyUserForm(form.work_model_id));
  const blocker = useUnsavedGuard(dirty);
  const sendingMail = Boolean(isAdmin && form.send_access_mail && form.web_login && mailReady);
  const passwordRequired = Boolean(isAdmin && form.web_login && !sendingMail);

  async function load() {
    const [u, m, b, mail] = await Promise.all([api.users(), api.models(), api.balances(month), api.mailStatus().catch(() => ({ ready: false }))]);
    setUsers(u);
    setModels(m);
    setBalances(Object.fromEntries(b.people.map((row) => [row.user_id, row])));
    setMailReady(mail.ready);
    if (m[0] && !form.work_model_id) setForm((f) => ({ ...f, work_model_id: String(m[0].id) }));
  }

  useEffect(() => {
    if (!params.get("month")) {
      setParams({ month }, { replace: true });
    }
  }, [month, params, setParams]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month]);

  function patchForm(patch: Partial<UserForm>) {
    setForm((cur) => ({ ...cur, ...patch }));
    setFieldErrors((cur) => {
      const next = { ...cur };
      for (const key of Object.keys(patch) as (keyof UserFieldErrors)[]) {
        delete next[key];
      }
      return next;
    });
  }

  function resetAndClose() {
    setForm(emptyUserForm(form.work_model_id));
    setGeneratedPassword("");
    setFieldErrors({});
    setError("");
    setCloseConfirm(false);
    setOpen(false);
  }

  function requestClose() {
    if (dirty) setCloseConfirm(true);
    else resetAndClose();
  }

  function onStay() {
    if (blocker.state === "blocked") blocker.reset();
    setCloseConfirm(false);
  }

  function onDiscard() {
    if (blocker.state === "blocked") {
      blocker.proceed();
      return;
    }
    resetAndClose();
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setInfo("");
    const nextErrors = validateUserAccount({
      display_name: form.display_name,
      username: form.username,
      email: form.email,
      emailRequired: sendingMail,
      password: form.password,
      passwordRequired,
      hired_on: form.hired_on,
      left_on: form.left_on,
    });
    setFieldErrors(nextErrors);
    if (firstUserFieldError(nextErrors)) {
      setError("Bitte die markierten Felder ausfüllen.");
      requestAnimationFrame(() => {
        document.querySelector<HTMLElement>("#new-user-form [aria-invalid='true']")?.focus();
      });
      return;
    }
    try {
      const created = await api.createUser({
        ...form,
        email: form.email.trim() || null,
        work_model_id: form.work_model_id ? Number(form.work_model_id) : null,
        transponder_id: form.transponder_id.trim() || null,
        role: isAdmin ? form.role : "employee",
        web_login: isAdmin ? form.web_login : false,
        password: isAdmin ? form.password || null : null,
        hired_on: form.hired_on || null,
        left_on: form.left_on || null,
        send_access_mail: sendingMail,
      });
      setGeneratedPassword("");
      setFieldErrors({});
      setForm(emptyUserForm(form.work_model_id));
      setOpen(false);
      if (created.mail_sent) setInfo(`Zugang per Mail an ${created.email} gesendet.`);
      else if (created.mail_error) setError(`Benutzer angelegt, Mail fehlgeschlagen: ${created.mail_error}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fehler");
    }
  }

  return (
    <div className="pt-2">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-medium">Personal</h1>
        <input
          type="month"
          value={month}
          onChange={(e) => setParams({ month: e.target.value })}
          className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
        />
      </div>
      <div className="mt-2 flex flex-wrap gap-3 text-sm">
        <Link to="/pruefung" className="text-present">
          Prüfung
        </Link>
        <Link to="/modelle" className="text-muted">
          Modelle
        </Link>
        <Link to="/feiertage" className="text-muted">
          Feiertage
        </Link>
        {me?.role === "admin" ? (
          <Link to="/einstellungen" className="text-muted">
            Mail
          </Link>
        ) : null}
        <button type="button" className="text-present" onClick={() => (open ? requestClose() : setOpen(true))}>
          {open ? "Schließen" : "Neu"}
        </button>
      </div>
      {info ? <p className="mt-2 text-sm text-present">{info}</p> : null}
      {!open && error ? <p className="mt-2 text-sm text-danger">{error}</p> : null}
      {open ? (
        <form id="new-user-form" noValidate onSubmit={onSubmit} className="mt-4 space-y-3 rounded-2xl border border-line bg-card p-4">
          <label className="block text-xs text-muted">
            Anzeigename
            <input
              placeholder="z. B. Erika Mustermann"
              className={`mt-1 w-full px-3 py-2 ${inputClass(fieldErrors.display_name)}`}
              value={form.display_name}
              onChange={(e) => patchForm({ display_name: e.target.value })}
              aria-invalid={Boolean(fieldErrors.display_name)}
              aria-describedby={fieldErrors.display_name ? "err-display-name" : undefined}
            />
            <FieldError id="err-display-name">{fieldErrors.display_name}</FieldError>
          </label>
          <label className="block text-xs text-muted">
            Benutzername
            <input
              placeholder="zum Anmelden"
              className={`mt-1 w-full px-3 py-2 ${inputClass(fieldErrors.username)}`}
              value={form.username}
              onChange={(e) => patchForm({ username: e.target.value })}
              autoCapitalize="none"
              aria-invalid={Boolean(fieldErrors.username)}
              aria-describedby={fieldErrors.username ? "err-username" : undefined}
            />
            <FieldError id="err-username">{fieldErrors.username}</FieldError>
          </label>
          <label className="block text-xs text-muted">
            E-Mail{sendingMail ? "" : " (optional)"}
            <input
              type="email"
              placeholder={sendingMail ? "für den Zugangslink" : "optional"}
              className={`mt-1 w-full px-3 py-2 ${inputClass(fieldErrors.email)}`}
              value={form.email}
              onChange={(e) => patchForm({ email: e.target.value })}
              autoCapitalize="none"
              aria-invalid={Boolean(fieldErrors.email)}
              aria-describedby={fieldErrors.email ? "err-email" : undefined}
            />
            <FieldError id="err-email">{fieldErrors.email}</FieldError>
          </label>
          {isAdmin ? (
            <>
              <label className="block text-xs text-muted">
                {passwordRequired ? "Passwort" : "Passwort (optional)"}
                <PasswordField
                  placeholder={passwordRequired ? "mind. 8 Zeichen" : "leer lassen, wenn Mail den Zugang setzt"}
                  autoComplete="new-password"
                  className={`mt-1 w-full px-3 py-2 ${inputClass(fieldErrors.password)}`}
                  value={form.password}
                  onChange={(e) => {
                    patchForm({ password: e.target.value });
                    setGeneratedPassword("");
                  }}
                  aria-invalid={Boolean(fieldErrors.password)}
                  aria-describedby={fieldErrors.password ? "err-password" : undefined}
                />
                <FieldError id="err-password">{fieldErrors.password}</FieldError>
              </label>
              <button
                type="button"
                className="text-sm text-present"
                onClick={() => {
                  const next = generatePassword();
                  patchForm({ password: next });
                  setGeneratedPassword(next);
                }}
              >
                Passwort erzeugen
              </button>
              {generatedPassword ? (
                <p className="rounded-lg bg-bg px-3 py-2 font-mono text-sm">
                  Bitte notieren: {generatedPassword}
                </p>
              ) : null}
            </>
          ) : null}
          <div className="grid grid-cols-2 gap-2">
            <label className="block min-w-0 overflow-hidden text-xs text-muted">
              Eintritt
              <input
                type="date"
                className={`mt-1 h-10 w-full px-2 text-sm ${inputClass(fieldErrors.hired_on)}`}
                value={form.hired_on}
                onChange={(e) => patchForm({ hired_on: e.target.value })}
                aria-invalid={Boolean(fieldErrors.hired_on)}
                aria-describedby={fieldErrors.hired_on ? "err-hired-on" : undefined}
              />
              <FieldError id="err-hired-on">{fieldErrors.hired_on}</FieldError>
            </label>
            <div className="min-w-0 overflow-hidden text-xs text-muted">
              <div className="flex items-baseline justify-between gap-2">
                <label htmlFor="new-left-on">Austritt</label>
                {form.left_on ? (
                  <button type="button" className="text-present" onClick={() => patchForm({ left_on: "" })}>
                    Leeren
                  </button>
                ) : null}
              </div>
              <input
                id="new-left-on"
                key={form.left_on ? "left-set" : "left-empty"}
                type="date"
                className={`mt-1 h-10 w-full px-2 text-sm ${inputClass(fieldErrors.left_on)}`}
                value={form.left_on}
                onChange={(e) => patchForm({ left_on: e.target.value })}
                aria-invalid={Boolean(fieldErrors.left_on)}
                aria-describedby={fieldErrors.left_on ? "err-left-on" : undefined}
              />
              <FieldError id="err-left-on">{fieldErrors.left_on}</FieldError>
            </div>
          </div>
          <label className="block text-xs text-muted">
            Transpondernummer (optional)
            <input
              placeholder="wie am Gerät angezeigt"
              className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2"
              value={form.transponder_id}
              onChange={(e) => patchForm({ transponder_id: e.target.value })}
            />
          </label>
          {isAdmin ? (
            <>
              <label className="flex items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={form.web_login}
                  onChange={(e) => patchForm({ web_login: e.target.checked })}
                  disabled={form.role === "hr" || form.role === "admin" || form.role === "supervisor"}
                />
                <span>Anmeldung auf der Webseite aktivieren</span>
              </label>
              <label className="flex items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={form.send_access_mail && form.web_login && mailReady}
                  disabled={!form.web_login || !mailReady}
                  onChange={(e) => patchForm({ send_access_mail: e.target.checked })}
                />
                <span>
                  Zugangsdaten per E-Mail senden
                  {!mailReady ? (
                    <span className="mt-0.5 block text-xs text-muted">
                      Mailserver ist noch nicht eingerichtet (Einstellungen).
                    </span>
                  ) : null}
                </span>
              </label>
              <select
                className="w-full rounded-lg border border-line bg-bg px-3 py-2"
                value={form.role}
                onChange={(e) => {
                  const role = e.target.value;
                  const forceWeb = role === "hr" || role === "admin" || role === "supervisor";
                  patchForm({ role, web_login: forceWeb ? true : form.web_login });
                }}
              >
                <option value="employee">Mitarbeiter</option>
                <option value="supervisor">Vorgesetzt</option>
                <option value="hr">Personal</option>
                <option value="admin">Admin</option>
              </select>
            </>
          ) : (
            <p className="text-xs text-muted">Neue Personen werden als Mitarbeiter ohne Web-Anmeldung angelegt. Rolle, Passwort und Web-Zugang setzt nur ein Administrator.</p>
          )}
          <select
            className="w-full rounded-lg border border-line bg-bg px-3 py-2"
            value={form.work_model_id}
            onChange={(e) => patchForm({ work_model_id: e.target.value })}
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          {info ? <p className="text-sm text-present">{info}</p> : null}
          <button type="submit" className="w-full rounded-xl bg-present py-2 text-white">
            Anlegen
          </button>
        </form>
      ) : null}
      <ul className="mt-4 space-y-2 md:hidden">
        {users.map((u) => {
          const flex = balances[u.id];
          return (
            <li key={u.id}>
              <Link to={`/personal/${u.id}?month=${month}`} className="block rounded-2xl border border-line bg-card px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium">{u.display_name}</p>
                    <p className="text-xs text-muted">
                      {u.username} ·{" "}
                      {{ employee: "Mitarbeiter", supervisor: "Vorgesetzt", hr: "Personal", admin: "Admin" }[u.role] ??
                        u.role}
                      {u.work_model_name ? ` · ${u.work_model_name}` : ""}
                      {u.transponder_id ? " · Terminal" : ""}
                      {u.web_login ? "" : " · nur Terminal"}
                      {u.active ? "" : " · inaktiv"}
                    </p>
                    <div className="mt-1">
                      <SecurityBadges u={u} compact />
                    </div>
                  </div>
                  {flex ? (
                    <div className="shrink-0 text-right text-sm tabular-nums">
                      <p className={hoursTone(flex.delta_hours)}>{signedHours(flex.delta_hours)}</p>
                      <p className={`text-xs ${hoursTone(flex.total_delta_hours)}`}>
                        {signedHours(flex.total_delta_hours)} gesamt
                      </p>
                    </div>
                  ) : null}
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="mt-4 hidden overflow-x-auto rounded-2xl border border-line md:block">
        <table className="w-full text-left text-sm">
          <thead className="bg-card text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Benutzer</th>
              <th className="px-4 py-3 font-medium">Rolle</th>
              <th className="px-4 py-3 font-medium">Modell</th>
              <th className="px-4 py-3 font-medium">Transponder</th>
              <th className="px-4 py-3 font-medium text-right">Monat</th>
              <th className="px-4 py-3 font-medium text-right">Gesamt</th>
              <th className="px-4 py-3 font-medium">Sicherheit</th>
              <th className="px-4 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const flex = balances[u.id];
              return (
                <tr key={u.id} className="border-t border-line bg-card">
                  <td className="px-4 py-2.5">
                    <Link to={`/personal/${u.id}?month=${month}`} className="font-medium text-present">
                      {u.display_name}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5 text-muted">{u.username}</td>
                  <td className="px-4 py-2.5">
                    {{ employee: "Mitarbeiter", supervisor: "Vorgesetzt", hr: "Personal", admin: "Admin" }[u.role] ??
                      u.role}
                  </td>
                  <td className="px-4 py-2.5 text-muted">{u.work_model_name ?? "—"}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-muted">{u.transponder_id ?? "—"}</td>
                  <td
                    className={`px-4 py-2.5 text-right tabular-nums ${flex ? hoursTone(flex.delta_hours) : "text-muted"}`}
                  >
                    {flex ? signedHours(flex.delta_hours) : "—"}
                  </td>
                  <td
                    className={`px-4 py-2.5 text-right tabular-nums ${flex ? hoursTone(flex.total_delta_hours) : "text-muted"}`}
                  >
                    {flex ? signedHours(flex.total_delta_hours) : "—"}
                  </td>
                  <td className="px-4 py-2.5">
                    <SecurityBadges u={u} />
                  </td>
                  <td className="px-4 py-2.5 text-muted">
                    {u.active ? "aktiv" : "inaktiv"}
                    {u.web_login ? "" : " · nur Terminal"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {closeConfirm || blocker.state === "blocked" ? (
        <UnsavedChangesDialog onStay={onStay} onDiscard={onDiscard} />
      ) : null}
    </div>
  );
}
