import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import AuthScreen from "../components/AuthScreen";

export default function ForgotPassword() {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.forgotPassword(value);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthScreen
      title="Passwort zurücksetzen."
      lead="Wenn ein Konto mit Web-Anmeldung und E-Mail existiert, schicken wir einen Link."
    >
      {done ? (
        <div className="space-y-4">
          <p className="rounded-2xl border border-line bg-card px-4 py-3 text-sm">
            Falls ein Konto existiert, ist die Mail unterwegs. Der Link gilt eine Stunde.
          </p>
          <Link to="/login" className="block text-center text-sm text-present">
            Zur Anmeldung
          </Link>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-muted">Benutzer oder E-Mail</span>
            <input
              autoComplete="username"
              className="mt-1 w-full rounded-xl border border-line bg-card px-4 py-3 outline-none focus:border-present"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              required
            />
          </label>
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-xl bg-present py-3.5 font-medium text-white disabled:opacity-60"
          >
            {busy ? "Senden …" : "Link senden"}
          </button>
          <p className="text-center text-sm">
            <Link to="/login" className="text-muted">
              Zur Anmeldung
            </Link>
          </p>
        </form>
      )}
    </AuthScreen>
  );
}
