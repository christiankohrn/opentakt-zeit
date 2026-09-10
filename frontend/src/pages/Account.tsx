import { FormEvent, useState } from "react";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import PasswordField from "../components/PasswordField";
import SecuritySettings from "../components/SecuritySettings";

export default function Account() {
  const { user } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const nextOk = next.length >= 8;
  const match = next.length > 0 && next === repeat;
  const nextHint = next.length > 0 && !nextOk ? "Mindestens 8 Zeichen." : "";
  const repeatHint = repeat.length > 0 && next !== repeat ? "Die Passwörter stimmen nicht überein." : "";
  const nextBorder = next.length === 0 ? "border-line" : nextOk ? "border-ok" : "border-danger";
  const repeatBorder = repeat.length === 0 ? "border-line" : match ? "border-ok" : "border-danger";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setMsg("");
    setErr("");
    if (!nextOk) {
      setErr("Mindestens 8 Zeichen.");
      return;
    }
    if (!match) {
      setErr("Die neuen Passwörter stimmen nicht überein.");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setCurrent("");
      setNext("");
      setRepeat("");
      setMsg("Passwort gespeichert.");
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pt-2 md:max-w-md">
      <h1 className="text-xl font-medium">Konto</h1>
      <p className="mt-1 text-sm text-muted">
        {user?.display_name} · {user?.username}
      </p>
      <form onSubmit={onSubmit} className="mt-4 space-y-3 rounded-2xl border border-line bg-card p-4">
        <p className="text-sm font-medium">Passwort ändern</p>
        <label className="block text-xs text-muted">
          Aktuelles Passwort
          <PasswordField
            autoComplete="current-password"
            className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </label>
        <label className="block text-xs text-muted">
          Neues Passwort (mind. 8 Zeichen)
          <PasswordField
            autoComplete="new-password"
            minLength={8}
            className={`mt-1 w-full rounded-lg border bg-bg px-3 py-2 text-sm text-ink ${nextBorder}`}
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
            aria-invalid={Boolean(nextHint)}
          />
          {nextHint ? <span className="mt-1 block text-xs text-danger">{nextHint}</span> : null}
        </label>
        <label className="block text-xs text-muted">
          Neues Passwort wiederholen
          <PasswordField
            autoComplete="new-password"
            minLength={8}
            className={`mt-1 w-full rounded-lg border bg-bg px-3 py-2 text-sm text-ink ${repeatBorder}`}
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            required
            aria-invalid={Boolean(repeatHint)}
          />
          {repeatHint ? <span className="mt-1 block text-xs text-danger">{repeatHint}</span> : null}
        </label>
        {err ? <p className="text-sm text-danger">{err}</p> : null}
        {msg ? <p className="text-sm text-present">{msg}</p> : null}
        <button type="submit" disabled={busy} className="w-full rounded-xl bg-navy py-2 text-sm text-white disabled:opacity-60">
          {busy ? "…" : "Passwort speichern"}
        </button>
      </form>

      <h2 className="mt-6 text-lg font-medium">Sicherheit</h2>
      <p className="mt-1 text-sm text-muted">Zwei-Faktor-Authentisierung und Passkeys für dein Konto.</p>
      <SecuritySettings />
    </div>
  );
}
