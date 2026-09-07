import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type DfcomSettings, type SmtpSettings } from "../api";
import PasswordField from "../components/PasswordField";

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

const emptyDfcom: DfcomSettings = {
  library_ok: false,
  library_path: null,
  poll_enabled: false,
  poll_dry_run: true,
  poll_interval_sec: 20,
  sync_lists: true,
  last_poll: null,
  terminals: [],
};

export default function Settings() {
  const [form, setForm] = useState<SmtpSettings>(empty);
  const [dfcom, setDfcom] = useState<DfcomSettings>(emptyDfcom);
  const [termName, setTermName] = useState("Halle");
  const [termHost, setTermHost] = useState("");
  const [termPort, setTermPort] = useState(8000);
  const [password, setPassword] = useState("");
  const [testTo, setTestTo] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const [smtp, nextDfcom] = await Promise.all([api.smtpSettings(), api.dfcomSettings()]);
    setForm(smtp);
    setDfcom(nextDfcom);
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

  async function saveDfcom() {
    setMsg("");
    setErr("");
    setBusy(true);
    try {
      const next = await api.patchDfcomSettings({
        poll_enabled: dfcom.poll_enabled,
        poll_dry_run: dfcom.poll_dry_run,
        poll_interval_sec: Number(dfcom.poll_interval_sec) || 20,
        sync_lists: dfcom.sync_lists,
      });
      setDfcom(next);
      setMsg("Terminal-Polling gespeichert.");
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  async function addTerminal(e: FormEvent) {
    e.preventDefault();
    setMsg("");
    setErr("");
    setBusy(true);
    try {
      await api.createDfcomTerminal({
        name: termName.trim() || "Terminal",
        host: termHost.trim(),
        port: Number(termPort) || 8000,
      });
      setTermHost("");
      await load();
      setMsg("Terminal eingetragen.");
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  async function pollNow() {
    setMsg("");
    setErr("");
    setBusy(true);
    try {
      const report = await api.pollDfcom();
      await load();
      if (report.error) setErr(report.error);
      else setMsg("Polling ausgeführt.");
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  async function pushListsNow() {
    setMsg("");
    setErr("");
    setBusy(true);
    try {
      const report = await api.pushDfcomLists();
      await load();
      if (report.error) setErr(report.error);
      else setMsg("Personalliste geschrieben.");
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pt-2 md:max-w-2xl">
      <Link to="/personal" className="text-sm text-muted">
        ← Personal
      </Link>
      <h1 className="mt-2 text-xl font-medium">Einstellungen</h1>
      <p className="mt-1 text-sm text-muted">
        Mailserver und optionales Datafox-Polling (DFCom). HTTP-Stempeln bleibt parallel nutzbar.
      </p>
      {err ? <p className="mt-3 text-sm text-danger">{err}</p> : null}
      {msg ? <p className="mt-3 text-sm text-present">{msg}</p> : null}
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

      <div className="mt-3 space-y-3 rounded-2xl border border-line bg-card p-4">
        <p className="text-sm font-medium">Datafox-Polling (DFCom)</p>
        <p className="text-sm text-muted">
          Der Server holt Buchungen per TCP vom Terminal (typisch Port 8000), Tabelle{" "}
          <code className="text-xs">Stempelung</code> (Kommen = Kennzeichen 0, Gehen = 1). Dafür muss die Maschine die
          Geräte erreichen, und <code className="text-xs">libDFCom.so</code> muss lokal gebaut sein.
        </p>
        <p className="text-sm text-muted">
          Im Normalbetrieb bestätigt der Server die Buchung (Datensatz wird gelöscht), setzt die Uhrzeit und schreibt
          die Liste PERSONAL (Name, Zeitkonto, genommene Urlaubstage). Im Testbetrieb wird nur gelesen.
        </p>
        <p className="text-xs text-muted">
          {dfcom.library_ok
            ? `Bibliothek gefunden${dfcom.library_path ? `: ${dfcom.library_path}` : "."}`
            : "libDFCom.so fehlt noch. Auf dem Server: bash /opt/zeiterfassung/deploy/install-dfcom.sh"}
        </p>
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={dfcom.poll_enabled}
            onChange={(e) => setDfcom({ ...dfcom, poll_enabled: e.target.checked })}
          />
          <span>Polling aktiv (im Hintergrund, alle {dfcom.poll_interval_sec} s)</span>
        </label>
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={dfcom.poll_dry_run}
            onChange={(e) => setDfcom({ ...dfcom, poll_dry_run: e.target.checked })}
          />
          <span>Testbetrieb: Buchungen nicht bestätigen (nicht vom Terminal löschen, nicht in Opentakt speichern)</span>
        </label>
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={dfcom.sync_lists}
            onChange={(e) => setDfcom({ ...dfcom, sync_lists: e.target.checked })}
          />
          <span>Personalliste und Konten aufs Terminal schreiben (nur Normalbetrieb, nur wenn sich etwas geändert hat)</span>
        </label>
        <label className="block text-xs text-muted">
          Intervall (Sekunden)
          <input
            type="number"
            min={10}
            max={300}
            className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
            value={dfcom.poll_interval_sec}
            onChange={(e) => setDfcom({ ...dfcom, poll_interval_sec: Number(e.target.value) })}
          />
        </label>
        {dfcom.poll_dry_run ? (
          <p className="text-xs text-muted">
            Im Testbetrieb bleibt der älteste Datensatz auf dem Gerät. Es wird immer nur dieser eine gelesen, bis der
            Haken aus ist.
          </p>
        ) : null}
        <button
          type="button"
          disabled={busy}
          onClick={() => void saveDfcom()}
          className="w-full rounded-xl bg-navy py-2 text-sm text-white disabled:opacity-60"
        >
          Polling speichern
        </button>
        <form onSubmit={(e) => void addTerminal(e)} className="space-y-2 border-t border-line pt-3">
          <p className="text-sm font-medium">Terminals</p>
          {dfcom.terminals.length === 0 ? <p className="text-xs text-muted">Noch kein Gerät.</p> : null}
          <ul className="space-y-2">
            {dfcom.terminals.map((term) => (
              <li key={term.id} className="rounded-xl border border-line px-3 py-2 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">
                      {term.name}{" "}
                      <span className="font-normal text-muted">
                        {term.host}:{term.port}
                      </span>
                    </p>
                    <p className="mt-1 text-xs text-muted">{term.last_summary || "Noch nicht gepollt."}</p>
                  </div>
                  <button
                    type="button"
                    className="text-xs text-danger"
                    disabled={busy}
                    onClick={() => {
                      void (async () => {
                        setBusy(true);
                        setErr("");
                        try {
                          await api.deleteDfcomTerminal(term.id);
                          await load();
                        } catch (ex) {
                          setErr(ex instanceof ApiError ? ex.message : "Fehler");
                        } finally {
                          setBusy(false);
                        }
                      })();
                    }}
                  >
                    Entfernen
                  </button>
                </div>
              </li>
            ))}
          </ul>
          <div className="grid grid-cols-6 gap-2">
            <label className="col-span-2 block text-xs text-muted">
              Name
              <input
                className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
                value={termName}
                onChange={(e) => setTermName(e.target.value)}
              />
            </label>
            <label className="col-span-3 block text-xs text-muted">
              Host / IP
              <input
                className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
                value={termHost}
                onChange={(e) => setTermHost(e.target.value)}
                placeholder="192.168.1.50"
                autoCapitalize="none"
              />
            </label>
            <label className="col-span-1 block text-xs text-muted">
              Port
              <input
                type="number"
                min={1}
                max={65535}
                className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
                value={termPort}
                onChange={(e) => setTermPort(Number(e.target.value))}
              />
            </label>
          </div>
          <button type="submit" disabled={busy} className="w-full rounded-xl border border-line py-2 text-sm disabled:opacity-60">
            Terminal hinzufügen
          </button>
        </form>
        <button
          type="button"
          disabled={busy}
          onClick={() => void pollNow()}
          className="w-full rounded-xl border border-line py-2 text-sm disabled:opacity-60"
        >
          Jetzt pollen
        </button>
        <button
          type="button"
          disabled={busy || dfcom.poll_dry_run}
          onClick={() => void pushListsNow()}
          className="w-full rounded-xl border border-line py-2 text-sm disabled:opacity-60"
        >
          Personalliste jetzt schreiben
        </button>
      </div>
    </div>
  );
}
