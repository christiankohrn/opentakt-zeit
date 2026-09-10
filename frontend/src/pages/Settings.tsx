import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type SecurityPolicyValue, type SmtpSettings } from "../api";
import PasswordField from "../components/PasswordField";

const ROLE_LABELS: Record<string, string> = {
  employee: "Mitarbeiter",
  supervisor: "Vorgesetzt",
  hr: "Personal",
  admin: "Admin",
};

const POLICY_LABELS: Record<SecurityPolicyValue, string> = {
  off: "Aus",
  totp: "2FA per App erforderlich",
  passkey: "Passkey erforderlich",
  any: "2FA oder Passkey erforderlich",
};

function SecurityPolicyCard() {
  const [policies, setPolicies] = useState<Record<string, SecurityPolicyValue>>({});
  const [roles, setRoles] = useState<string[]>([]);
  const [values, setValues] = useState<SecurityPolicyValue[]>([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api
      .securityPolicy()
      .then((p) => {
        setPolicies(p.policies);
        setRoles(p.roles);
        setValues(p.values);
      })
      .catch(() => setErr("Sicherheitsrichtlinie konnte nicht geladen werden."));
  }, []);

  async function save() {
    setMsg("");
    setErr("");
    setBusy(true);
    try {
      const next = await api.patchSecurityPolicy(policies);
      setPolicies(next.policies);
      setMsg("Sicherheitsrichtlinie gespeichert.");
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-4 space-y-3 rounded-2xl border border-line bg-card p-4">
      <p className="text-sm font-medium">Anmelde-Sicherheit erzwingen</p>
      <p className="text-xs text-muted">
        Pro Benutzergruppe festlegen, ob eine zweite Stufe Pflicht ist. Betroffene Personen werden beim nächsten Login
        aufgefordert, 2FA bzw. einen Passkey einzurichten, bevor sie weiterkommen.
      </p>
      {roles.map((role) => (
        <label key={role} className="flex items-center justify-between gap-3 text-sm">
          <span>{ROLE_LABELS[role] ?? role}</span>
          <select
            className="rounded-lg border border-line bg-bg px-3 py-2 text-sm"
            value={policies[role] ?? "off"}
            onChange={(e) => setPolicies({ ...policies, [role]: e.target.value as SecurityPolicyValue })}
          >
            {values.map((v) => (
              <option key={v} value={v}>
                {POLICY_LABELS[v] ?? v}
              </option>
            ))}
          </select>
        </label>
      ))}
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {msg ? <p className="text-sm text-present">{msg}</p> : null}
      <button
        type="button"
        disabled={busy}
        onClick={() => void save()}
        className="w-full rounded-xl bg-navy py-2 text-sm text-white disabled:opacity-60"
      >
        {busy ? "…" : "Richtlinie speichern"}
      </button>
    </div>
  );
}

const empty: SmtpSettings = {
  enabled: false,
  host: "",
  port: 587,
  username: "",
  from_addr: "",
  use_tls: true,
  use_ssl: false,
  password_set: false,
  source: "config",
  ready: false,
};

export default function Settings() {
  const [form, setForm] = useState<SmtpSettings>(empty);
  const [password, setPassword] = useState("");
  const [testTo, setTestTo] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const smtp = await api.smtpSettings();
    setForm(smtp);
  }

  useEffect(() => {
    void load();
  }, []);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setMsg("");
    setErr("");
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        enabled: form.enabled,
        host: form.host,
        port: Number(form.port) || 587,
        username: form.username,
        from_addr: form.from_addr,
        use_tls: form.use_tls,
        use_ssl: form.use_ssl,
      };
      if (password.trim()) body.password = password.trim();
      const next = await api.patchSmtpSettings(body);
      setForm(next);
      setPassword("");
      setMsg("Mailserver gespeichert.");
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  async function onTest() {
    setMsg("");
    setErr("");
    setBusy(true);
    try {
      await api.testSmtp(testTo.trim() || undefined);
      setMsg("Testmail ist unterwegs.");
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pt-2 md:max-w-xl">
      <Link to="/personal" className="text-sm text-muted">
        ← Personal
      </Link>
      <h1 className="mt-2 text-xl font-medium">Einstellungen</h1>

      <SecurityPolicyCard />

      <p className="mt-6 text-sm text-muted">
        Mailserver für Zugangsdaten, Passwort-Reset und die Erinnerung zum Ausstempeln.
      </p>
      <form onSubmit={onSave} className="mt-4 space-y-3 rounded-2xl border border-line bg-card p-4">
        <p className="text-sm font-medium">Mailserver</p>
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={form.enabled}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
          />
          <span>Mailversand aktiv</span>
        </label>
        <label className="block text-xs text-muted">
          Host
          <input
            className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
            value={form.host}
            onChange={(e) => setForm({ ...form, host: e.target.value })}
            placeholder="mail.firma.de"
            autoCapitalize="none"
          />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="block text-xs text-muted">
            Port
            <input
              type="number"
              min={1}
              max={65535}
              className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
              value={form.port}
              onChange={(e) => setForm({ ...form, port: Number(e.target.value) })}
            />
          </label>
          <label className="block text-xs text-muted">
            Benutzer
            <input
              className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              autoCapitalize="none"
            />
          </label>
        </div>
        <label className="block text-xs text-muted">
          Passwort {form.password_set ? "(gesetzt, leer lassen zum Behalten)" : ""}
          <PasswordField
            autoComplete="new-password"
            className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={form.password_set ? "unverändert" : "SMTP-Passwort"}
          />
        </label>
        <label className="block text-xs text-muted">
          Absender
          <input
            type="email"
            className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
            value={form.from_addr}
            onChange={(e) => setForm({ ...form, from_addr: e.target.value })}
            placeholder="zeit@firma.de"
          />
        </label>
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={form.use_tls}
            onChange={(e) => setForm({ ...form, use_tls: e.target.checked })}
          />
          <span>STARTTLS (typisch Port 587)</span>
        </label>
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={form.use_ssl}
            onChange={(e) => setForm({ ...form, use_ssl: e.target.checked })}
          />
          <span>SSL (typisch Port 465)</span>
        </label>
        <p className="text-xs text-muted">
          {form.ready ? "Versand ist bereit." : "Zum Versand braucht es Host, Absender und den Haken „aktiv“."}
          {form.source === "config" ? " Aktuell gelten die Werte aus der Server-Config, bis du hier speicherst." : ""}
        </p>
        {err ? <p className="text-sm text-danger">{err}</p> : null}
        {msg ? <p className="text-sm text-present">{msg}</p> : null}
        <button type="submit" disabled={busy} className="w-full rounded-xl bg-navy py-2 text-sm text-white disabled:opacity-60">
          {busy ? "…" : "Mailserver speichern"}
        </button>
      </form>
      <div className="mt-3 space-y-3 rounded-2xl border border-line bg-card p-4">
        <p className="text-sm font-medium">Testmail</p>
        <label className="block text-xs text-muted">
          Empfänger (leer = deine Adresse)
          <input
            type="email"
            className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
            value={testTo}
            onChange={(e) => setTestTo(e.target.value)}
            placeholder="du@firma.de"
          />
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={() => void onTest()}
          className="w-full rounded-xl border border-line py-2 text-sm disabled:opacity-60"
        >
          Testmail senden
        </button>
      </div>
    </div>
  );
}
