import { browserSupportsWebAuthn, startRegistration } from "@simplewebauthn/browser";
import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, type Passkey, type SecurityStatus, type TotpSetup } from "../api";
import ConfirmDialog from "./ConfirmDialog";
import PasswordField from "./PasswordField";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("de-DE");
}

function BackupCodes({ codes, onClose }: { codes: string[]; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mt-3 rounded-xl border border-line bg-bg p-3">
      <p className="text-sm font-medium">Backup-Codes</p>
      <p className="mt-1 text-xs text-muted">
        Bewahre diese Codes sicher auf. Jeder funktioniert einmal, falls du keinen Zugriff auf die App hast.
      </p>
      <div className="mt-2 grid grid-cols-2 gap-2 font-mono text-sm">
        {codes.map((c) => (
          <span key={c} className="rounded-lg bg-card px-2 py-1 text-center">
            {c}
          </span>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          className="flex-1 rounded-lg border border-line py-2 text-sm"
          onClick={() => {
            void navigator.clipboard?.writeText(codes.join("\n")).then(() => setCopied(true));
          }}
        >
          {copied ? "Kopiert ✓" : "Kopieren"}
        </button>
        <button type="button" className="flex-1 rounded-lg bg-navy py-2 text-sm text-white" onClick={onClose}>
          Erledigt
        </button>
      </div>
    </div>
  );
}

type Props = {
  onChanged?: () => void;
  restrict?: "totp" | "passkey" | "any" | null;
};

export default function SecuritySettings({ onChanged, restrict = null }: Props = {}) {
  const showTotp = !restrict || restrict === "totp" || restrict === "any";
  const showPasskey = !restrict || restrict === "passkey" || restrict === "any";
  const [status, setStatus] = useState<SecurityStatus | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  // TOTP setup flow
  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const [enableCode, setEnableCode] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);

  // TOTP disable flow
  const [showDisable, setShowDisable] = useState(false);
  const [disablePassword, setDisablePassword] = useState("");
  const [disableCode, setDisableCode] = useState("");

  // Passkeys
  const [newPasskeyName, setNewPasskeyName] = useState("Mein Gerät");
  const [toDelete, setToDelete] = useState<Passkey | null>(null);
  const webauthnSupported = browserSupportsWebAuthn();

  async function reload() {
    setStatus(await api.securityStatus());
  }

  async function refreshAll() {
    await reload();
    onChanged?.();
  }

  useEffect(() => {
    void reload().catch(() => setErr("Sicherheitsstatus konnte nicht geladen werden."));
  }, []);

  function fail(e: unknown, fallback: string) {
    setErr(e instanceof ApiError ? e.message : fallback);
  }

  async function startSetup() {
    setErr("");
    setMsg("");
    setBusy(true);
    try {
      setSetup(await api.totpSetup());
      setEnableCode("");
    } catch (e) {
      fail(e, "Einrichtung nicht möglich.");
    } finally {
      setBusy(false);
    }
  }

  async function enableTotp(e: FormEvent) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const res = await api.totpEnable(enableCode.trim());
      setBackupCodes(res.backup_codes);
      setSetup(null);
      setMsg("Zwei-Faktor-Authentisierung ist aktiv.");
      await refreshAll();
    } catch (e2) {
      fail(e2, "Code stimmt nicht.");
    } finally {
      setBusy(false);
    }
  }

  async function disableTotp(e: FormEvent) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await api.totpDisable(disablePassword, disableCode.trim());
      setShowDisable(false);
      setDisablePassword("");
      setDisableCode("");
      setMsg("Zwei-Faktor-Authentisierung wurde deaktiviert.");
      await refreshAll();
    } catch (e2) {
      fail(e2, "Deaktivieren fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  async function addPasskey() {
    setErr("");
    setMsg("");
    setBusy(true);
    try {
      const options = await api.passkeyRegisterOptions();
      const credential = await startRegistration({ optionsJSON: options });
      await api.passkeyRegisterVerify(credential, newPasskeyName.trim() || "Passkey");
      setMsg("Passkey gespeichert.");
      await refreshAll();
    } catch (e) {
      if (e instanceof ApiError) setErr(e.message);
      else if (e instanceof Error && e.name === "NotAllowedError") setErr("Passkey-Einrichtung abgebrochen.");
      else setErr("Passkey konnte nicht eingerichtet werden.");
    } finally {
      setBusy(false);
    }
  }

  async function renamePasskey(pk: Passkey) {
    const name = window.prompt("Neuer Name", pk.name);
    if (!name || name.trim() === pk.name) return;
    try {
      await api.renamePasskey(pk.id, name.trim());
      await refreshAll();
    } catch (e) {
      fail(e, "Umbenennen fehlgeschlagen.");
    }
  }

  async function confirmDelete() {
    if (!toDelete) return;
    setBusy(true);
    try {
      await api.deletePasskey(toDelete.id);
      setToDelete(null);
      await refreshAll();
    } catch (e) {
      fail(e, "Löschen fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  if (!status) {
    return <p className="mt-4 text-sm text-muted">Laden …</p>;
  }

  return (
    <div className="mt-4 space-y-4">
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {msg ? <p className="text-sm text-present">{msg}</p> : null}

      {/* Two-factor / authenticator app */}
      {showTotp ? (
      <section className="space-y-3 rounded-2xl border border-line bg-card p-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">Zwei-Faktor per Authenticator-App</p>
          <span className={`text-xs ${status.totp_enabled ? "text-present" : "text-muted"}`}>
            {status.totp_enabled ? "Aktiv" : "Inaktiv"}
          </span>
        </div>

        {backupCodes ? <BackupCodes codes={backupCodes} onClose={() => setBackupCodes(null)} /> : null}

        {!status.totp_enabled && !setup ? (
          <>
            <p className="text-xs text-muted">
              Zusätzlicher Schutz: Beim Anmelden wird zusätzlich ein 6-stelliger Code aus Google Authenticator,
              1Password, Aegis o. ä. abgefragt.
            </p>
            <button
              type="button"
              disabled={busy}
              onClick={() => void startSetup()}
              className="w-full rounded-xl bg-navy py-2 text-sm text-white disabled:opacity-60"
            >
              Einrichten
            </button>
          </>
        ) : null}

        {setup ? (
          <form onSubmit={enableTotp} className="space-y-3">
            <p className="text-xs text-muted">
              1. Scanne den QR-Code mit deiner Authenticator-App (oder gib den Schlüssel manuell ein).
            </p>
            <div className="flex flex-col items-center gap-2">
              <img
                src={setup.qr_svg}
                alt="QR-Code für die Authenticator-App"
                className="h-44 w-44 rounded-lg border border-line bg-white p-2"
              />
              <code className="select-all break-all rounded-lg bg-bg px-2 py-1 text-center text-xs">
                {setup.secret}
              </code>
            </div>
            <label className="block text-xs text-muted">
              2. Bestätige mit dem aktuellen 6-stelligen Code
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-center text-lg tracking-[0.3em] text-ink"
                value={enableCode}
                onChange={(e) => setEnableCode(e.target.value)}
                placeholder="000000"
                required
              />
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                className="flex-1 rounded-xl border border-line py-2 text-sm"
                onClick={() => setSetup(null)}
              >
                Abbrechen
              </button>
              <button
                type="submit"
                disabled={busy}
                className="flex-1 rounded-xl bg-navy py-2 text-sm text-white disabled:opacity-60"
              >
                Aktivieren
              </button>
            </div>
          </form>
        ) : null}

        {status.totp_enabled ? (
          <div className="space-y-2">
            <p className="text-xs text-muted">Noch {status.backup_codes_remaining} Backup-Codes übrig.</p>
            {restrict ? null : !showDisable ? (
              <button
                type="button"
                className="w-full rounded-xl border border-danger py-2 text-sm text-danger"
                onClick={() => setShowDisable(true)}
              >
                Zwei-Faktor deaktivieren
              </button>
            ) : (
              <form onSubmit={disableTotp} className="space-y-2 rounded-xl border border-line bg-bg p-3">
                {status.can_use_password ? (
                  <label className="block text-xs text-muted">
                    Aktuelles Passwort
                    <PasswordField
                      autoComplete="current-password"
                      className="mt-1 w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink"
                      value={disablePassword}
                      onChange={(e) => setDisablePassword(e.target.value)}
                      required
                    />
                  </label>
                ) : null}
                <label className="block text-xs text-muted">
                  Code aus der App oder ein Backup-Code
                  <input
                    className="mt-1 w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink"
                    value={disableCode}
                    onChange={(e) => setDisableCode(e.target.value)}
                    required
                  />
                </label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="flex-1 rounded-lg border border-line py-2 text-sm"
                    onClick={() => setShowDisable(false)}
                  >
                    Abbrechen
                  </button>
                  <button
                    type="submit"
                    disabled={busy}
                    className="flex-1 rounded-lg bg-danger py-2 text-sm text-white disabled:opacity-60"
                  >
                    Deaktivieren
                  </button>
                </div>
              </form>
            )}
          </div>
        ) : null}
      </section>
      ) : null}

      {/* Passkeys */}
      {showPasskey ? (
      <section className="space-y-3 rounded-2xl border border-line bg-card p-4">
        <p className="text-sm font-medium">Passkeys</p>
        <p className="text-xs text-muted">
          Melde dich ohne Passwort an — mit Fingerabdruck, Gesicht, Geräte-PIN oder Sicherheitsschlüssel.
        </p>

        {status.passkeys.length > 0 ? (
          <ul className="divide-y divide-line rounded-xl border border-line">
            {status.passkeys.map((pk) => (
              <li key={pk.id} className="flex items-center justify-between gap-2 px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm">{pk.name}</p>
                  <p className="text-xs text-muted">
                    seit {fmtDate(pk.created_at)} · zuletzt {fmtDate(pk.last_used_at)}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button type="button" className="text-xs text-muted" onClick={() => void renamePasskey(pk)}>
                    Umbenennen
                  </button>
                  <button type="button" className="text-xs text-danger" onClick={() => setToDelete(pk)}>
                    Entfernen
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted">Noch kein Passkey hinterlegt.</p>
        )}

        {webauthnSupported ? (
          <div className="flex gap-2">
            <input
              className="min-w-0 flex-1 rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
              value={newPasskeyName}
              onChange={(e) => setNewPasskeyName(e.target.value)}
              placeholder="Gerätename"
              aria-label="Name für den neuen Passkey"
            />
            <button
              type="button"
              disabled={busy}
              onClick={() => void addPasskey()}
              className="shrink-0 rounded-xl bg-navy px-4 py-2 text-sm text-white disabled:opacity-60"
            >
              Passkey hinzufügen
            </button>
          </div>
        ) : (
          <p className="text-xs text-muted">Dieser Browser unterstützt keine Passkeys.</p>
        )}
      </section>
      ) : null}

      {toDelete ? (
        <ConfirmDialog
          title="Passkey entfernen?"
          body={`„${toDelete.name}“ kann danach nicht mehr zum Anmelden verwendet werden.`}
          confirmLabel="Entfernen"
          danger
          busy={busy}
          onCancel={() => setToDelete(null)}
          onConfirm={() => void confirmDelete()}
        />
      ) : null}
    </div>
  );
}
