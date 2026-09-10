import { startAuthentication } from "@simplewebauthn/browser";
import { FormEvent, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api, ApiError, isMfaChallenge } from "../api";
import { useAuth } from "../auth";
import AuthScreen from "../components/AuthScreen";
import PasswordField from "../components/PasswordField";

export default function Login() {
  const { user, setUser, loading } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(() => sessionStorage.getItem("ze-auth-reason") || "");
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<"password" | "mfa">("password");
  const [code, setCode] = useState("");
  const [backupHint, setBackupHint] = useState(false);

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
      const result = await api.login(username, password);
      if (isMfaChallenge(result)) {
        setBackupHint(result.methods.includes("backup_code"));
        setStep("mfa");
        setCode("");
      } else {
        setUser(result);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Anmeldung fehlgeschlagen");
    } finally {
      setBusy(false);
    }
  }

  async function onVerifyMfa(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const u = await api.verifyMfa(code.trim());
      setUser(u);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Code ungültig");
    } finally {
      setBusy(false);
    }
  }

  async function onPasskey() {
    setError("");
    setBusy(true);
    try {
      const options = await api.passkeyLoginOptions(username.trim() || undefined);
      const credential = await startAuthentication({ optionsJSON: options });
      const u = await api.passkeyLoginVerify(credential);
      setUser(u);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else if (err instanceof Error && err.name === "NotAllowedError") setError("Passkey-Anmeldung abgebrochen.");
      else setError("Passkey-Anmeldung nicht möglich.");
    } finally {
      setBusy(false);
    }
  }

  if (step === "mfa") {
    return (
      <AuthScreen title="Bestätigen." lead="Gib den 6-stelligen Code aus deiner Authenticator-App ein.">
        <form onSubmit={onVerifyMfa} className="space-y-4">
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-muted">Code</span>
            <input
              autoFocus
              inputMode="numeric"
              autoComplete="one-time-code"
              className="mt-1 w-full rounded-xl border border-line bg-card px-4 py-3 text-center text-lg tracking-[0.4em] outline-none focus:border-present"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="000000"
              required
            />
          </label>
          {backupHint ? (
            <p className="text-xs text-muted">Kein Zugriff auf die App? Gib einen deiner Backup-Codes ein.</p>
          ) : null}
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-xl bg-present py-3.5 font-medium text-white disabled:opacity-60"
          >
            {busy ? "Prüfen …" : "Bestätigen"}
          </button>
          <button
            type="button"
            onClick={() => {
              setStep("password");
              setError("");
              setPassword("");
            }}
            className="w-full text-center text-sm text-muted"
          >
            Abbrechen
          </button>
        </form>
      </AuthScreen>
    );
  }

  return (
    <AuthScreen title="Einstempeln reicht." lead="Kein Portal-Dschungel. Kommen, Pause, Gehen — auf dem Handy oder am Schreibtisch.">
      <form onSubmit={onSubmit} className="space-y-4">
        <label className="block">
          <span className="text-xs uppercase tracking-wider text-muted">Benutzer</span>
          <input
            autoComplete="username webauthn"
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
        <div className="flex items-center gap-3 text-xs text-muted">
          <span className="h-px flex-1 bg-line" />
          oder
          <span className="h-px flex-1 bg-line" />
        </div>
        <button
          type="button"
          onClick={() => void onPasskey()}
          disabled={busy}
          className="w-full rounded-xl border border-line bg-card py-3.5 font-medium text-ink disabled:opacity-60"
        >
          Mit Passkey anmelden
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
