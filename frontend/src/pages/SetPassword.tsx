import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import AuthScreen from "../components/AuthScreen";
import PasswordField from "../components/PasswordField";

export default function SetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [info, setInfo] = useState<{ username: string; display_name: string; purpose: string } | null>(null);
  const [loadError, setLoadError] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) {
      setLoadError("Link ist unvollständig.");
      return;
    }
    api
      .passwordTokenInfo(token)
      .then(setInfo)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Link ist ungültig oder abgelaufen"));
  }, [token]);

  const nextOk = password.length >= 8;
  const match = password.length > 0 && password === repeat;
  const invite = info?.purpose === "invite";
  const title = useMemo(() => (invite ? "Zugang einrichten." : "Neues Passwort."), [invite]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!nextOk) {
      setError("Mindestens 8 Zeichen.");
      return;
    }
    if (!match) {
      setError("Die Passwörter stimmen nicht überein.");
      return;
    }
    setBusy(true);
    try {
      await api.setPasswordWithToken(token, password);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <AuthScreen title="Link ungültig." lead="Der Link ist abgelaufen oder wurde schon benutzt. Fordere bei Bedarf einen neuen an.">
        <p className="text-sm text-danger">{loadError}</p>
        <p className="mt-4 text-center text-sm">
          <Link to="/passwort-vergessen" className="text-present">
            Neuen Link anfordern
          </Link>
        </p>
      </AuthScreen>
    );
  }

  if (done) {
    return (
      <AuthScreen title="Passwort gespeichert." lead="Du kannst dich jetzt mit deinem Benutzernamen anmelden.">
        <Link
          to="/login"
          className="block rounded-xl bg-present py-3.5 text-center font-medium text-white"
        >
          Zur Anmeldung
        </Link>
      </AuthScreen>
    );
  }

  return (
    <AuthScreen
      title={info ? title : "Passwort setzen."}
      lead={
        info
          ? `${info.display_name} · ${info.username}`
          : "Wir prüfen den Link."
      }
    >
      {info ? (
        <form onSubmit={onSubmit} className="space-y-4">
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-muted">Neues Passwort (mind. 8 Zeichen)</span>
            <PasswordField
              autoComplete="new-password"
              minLength={8}
              className="mt-1 w-full rounded-xl border border-line bg-card px-4 py-3 outline-none focus:border-present"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-muted">Passwort wiederholen</span>
            <PasswordField
              autoComplete="new-password"
              minLength={8}
              className="mt-1 w-full rounded-xl border border-line bg-card px-4 py-3 outline-none focus:border-present"
              value={repeat}
              onChange={(e) => setRepeat(e.target.value)}
              required
            />
          </label>
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-xl bg-present py-3.5 font-medium text-white disabled:opacity-60"
          >
            {busy ? "Speichern …" : "Passwort speichern"}
          </button>
        </form>
      ) : (
        <p className="text-sm text-muted">Laden …</p>
      )}
    </AuthScreen>
  );
}
