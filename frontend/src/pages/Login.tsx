import { FormEvent, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import AuthScreen from "../components/AuthScreen";
import PasswordField from "../components/PasswordField";

export default function Login() {
  const { user, setUser, loading } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(() => sessionStorage.getItem("ze-auth-reason") || "");
  const [busy, setBusy] = useState(false);

  if (!loading && user) {
    sessionStorage.removeItem("ze-auth-reason");
    return <Navigate to="/" replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      sessionStorage.removeItem("ze-auth-reason");
      const u = await api.login(username, password);
      setUser(u);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Anmeldung fehlgeschlagen");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthScreen title="Einstempeln reicht." lead="Kein Portal-Dschungel. Kommen, Pause, Gehen — auf dem Handy oder am Schreibtisch.">
      <form onSubmit={onSubmit} className="space-y-4">
        <label className="block">
          <span className="text-xs uppercase tracking-wider text-muted">Benutzer</span>
          <input
            autoComplete="username"
            className="mt-1 w-full rounded-xl border border-line bg-card px-4 py-3 outline-none focus:border-present"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            required
          />
        </label>
        <label className="block">
          <span className="text-xs uppercase tracking-wider text-muted">Passwort</span>
          <PasswordField
            autoComplete="current-password"
            className="mt-1 w-full rounded-xl border border-line bg-card px-4 py-3 outline-none focus:border-present"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-xl bg-present py-3.5 font-medium text-white disabled:opacity-60"
        >
          {busy ? "Prüfen …" : "Anmelden"}
        </button>
        <p className="text-center text-sm">
          <Link to="/passwort-vergessen" className="text-present">
            Passwort vergessen?
          </Link>
        </p>
      </form>
    </AuthScreen>
  );
}
