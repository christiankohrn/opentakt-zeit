import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type FlexBalance, type User, type WorkModel } from "../api";
import { useAuth } from "../auth";
import PasswordField from "../components/PasswordField";
import { hoursTone, isoDate, signedHours } from "../labels";
import { generatePassword } from "../password";

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
  const [form, setForm] = useState({
    username: "",
    display_name: "",
    email: "",
    password: "",
    role: "employee",
    work_model_id: "",
    transponder_id: "",
    web_login: true,
    hired_on: isoDate(),
    left_on: "",
    send_access_mail: true,
  });
  const [error, setError] = useState("");
  const [generatedPassword, setGeneratedPassword] = useState("");
  const [mailReady, setMailReady] = useState(false);
  const [info, setInfo] = useState("");

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

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setInfo("");
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
        send_access_mail: Boolean(isAdmin && form.send_access_mail && form.web_login && mailReady),
      });
      setOpen(false);
      setGeneratedPassword("");
      setForm({
        username: "",
        display_name: "",
        email: "",
        password: "",
        role: "employee",
        work_model_id: form.work_model_id,
        transponder_id: "",
        web_login: true,
        hired_on: isoDate(),
        left_on: "",
        send_access_mail: true,
      });
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
        <button type="button" className="text-present" onClick={() => setOpen((v) => !v)}>
          {open ? "Schließen" : "Neu"}
        </button>
      </div>
      {info ? <p className="mt-2 text-sm text-present">{info}</p> : null}
      {!open && error ? <p className="mt-2 text-sm text-danger">{error}</p> : null}
      {open ? (
        <form onSubmit={onSubmit} className="mt-4 space-y-3 rounded-2xl border border-line bg-card p-4">
          <input
            placeholder="Anzeigename"
            className="w-full rounded-lg border border-line bg-bg px-3 py-2"
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            required
          />
          <input
            placeholder="Benutzername"
            className="w-full rounded-lg border border-line bg-bg px-3 py-2"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            required
          />
          <input
            type="email"
            placeholder="E-Mail"
            className="w-full rounded-lg border border-line bg-bg px-3 py-2"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            required={Boolean(isAdmin && form.send_access_mail && form.web_login)}
          />
          {isAdmin ? (
            <>
              <PasswordField
                placeholder={
                  form.web_login && !(form.send_access_mail && form.email)
                    ? "Passwort"
                    : "Passwort (optional)"
                }
                autoComplete="new-password"
                className="w-full rounded-lg border border-line bg-bg px-3 py-2"
                value={form.password}
                onChange={(e) => {
                  setForm({ ...form, password: e.target.value });
                  setGeneratedPassword("");
                }}
                required={form.web_login && !(form.send_access_mail && form.email.trim())}
              />
              <button
                type="button"
                className="text-sm text-present"
                onClick={() => {
                  const next = generatePassword();
                  setForm((f) => ({ ...f, password: next }));
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
                className="mt-1 h-10 w-full rounded-lg border border-line bg-bg px-2 text-sm text-ink"
                value={form.hired_on}
                onChange={(e) => setForm({ ...form, hired_on: e.target.value })}
                required
              />
            </label>
            <div className="min-w-0 overflow-hidden text-xs text-muted">
              <div className="flex items-baseline justify-between gap-2">
                <label htmlFor="new-left-on">Austritt</label>
                {form.left_on ? (
                  <button
                    type="button"
                    className="text-present"
                    onClick={() => setForm({ ...form, left_on: "" })}
                  >
                    Leeren
                  </button>
                ) : null}
              </div>
              <input
                id="new-left-on"
                key={form.left_on ? "left-set" : "left-empty"}
                type="date"
                className="mt-1 h-10 w-full rounded-lg border border-line bg-bg px-2 text-sm text-ink"
                value={form.left_on}
                onChange={(e) => setForm({ ...form, left_on: e.target.value })}
              />
            </div>
          </div>
          <input
            placeholder="Transpondernummer (Terminal)"
            className="w-full rounded-lg border border-line bg-bg px-3 py-2"
            value={form.transponder_id}
            onChange={(e) => setForm({ ...form, transponder_id: e.target.value })}
          />
          {isAdmin ? (
            <>
              <label className="flex items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={form.web_login}
                  onChange={(e) => setForm({ ...form, web_login: e.target.checked })}
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
                  onChange={(e) => setForm({ ...form, send_access_mail: e.target.checked })}
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
                  setForm({ ...form, role, web_login: forceWeb ? true : form.web_login });
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
            onChange={(e) => setForm({ ...form, work_model_id: e.target.value })}
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
    </div>
  );
}
