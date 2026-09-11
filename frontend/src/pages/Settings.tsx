import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError, type DfcomSettings, type EspTerminalSettings, type SecurityPolicyValue, type SmtpSettings } from "../api";
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

const TABS = [
  { id: "sicherheit", label: "Sicherheit" },
  { id: "mail", label: "Mail" },
  { id: "terminals", label: "Terminals" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function parseTab(value: string | null): TabId {
  if (value === "mail" || value === "terminals" || value === "sicherheit") return value;
  return "sicherheit";
}

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
    <div className="space-y-3 rounded-2xl border border-line bg-card p-4">
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

const emptySmtp: SmtpSettings = {
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

function MailCard() {
  const [form, setForm] = useState<SmtpSettings>(emptySmtp);
  const [password, setPassword] = useState("");
  const [testTo, setTestTo] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api
      .smtpSettings()
      .then(setForm)
      .catch(() => setErr("Mailserver konnte nicht geladen werden."));
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
    <div className="space-y-3">
      <p className="text-sm text-muted">Zugangsmails, Passwort-Reset und Testversand.</p>
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {msg ? <p className="text-sm text-present">{msg}</p> : null}
      <form onSubmit={onSave} className="space-y-3 rounded-2xl border border-line bg-card p-4">
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
      <div className="space-y-3 rounded-2xl border border-line bg-card p-4">
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

const emptyEsp: EspTerminalSettings = {
  secret: "",
  secret_configured: false,
  secret_source: "",
  ok_line1: "{first_name}",
  ok_line2: "{kind} {flex_month}",
  line_max: 21,
  firmware_version: 0,
  firmware_uploaded: false,
  devices: [],
  placeholders: ["first_name", "display_name", "kind", "flex_month", "flex_total"],
};

function previewLine(template: string, max: number) {
  const sample: Record<string, string> = {
    first_name: "Anna",
    display_name: "Anna Schmidt",
    kind: "Kommen",
    flex_month: "+2,5h",
    flex_total: "+12,5h",
  };
  let out = template;
  for (const [key, value] of Object.entries(sample)) out = out.replaceAll(`{${key}}`, value);
  out = out.replace(/\{[a-z_]+\}/g, "").replace(/\s+/g, " ").trim();
  return { text: out.slice(0, max), over: out.length > max, length: out.length };
}

function formatSeen(value: string | null) {
  if (!value) return "noch nicht gesehen";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
}

function EspCard() {
  const [esp, setEsp] = useState<EspTerminalSettings>(emptyEsp);
  const [fwFile, setFwFile] = useState<File | null>(null);
  const [fwVersion, setFwVersion] = useState(2);
  const [devicePass, setDevicePass] = useState<Record<number, string>>({});
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api
      .espTerminalSettings()
      .then((next) => {
        setEsp(next);
        setFwVersion(Math.max(2, (next.firmware_version || 0) + 1));
      })
      .catch(() => setErr("ESP-Terminal konnte nicht geladen werden."));
  }, []);

  async function saveEsp() {
    setMsg("");
    setErr("");
    setBusy(true);
    try {
      const next = await api.patchEspTerminalSettings({
        ok_line1: esp.ok_line1,
        ok_line2: esp.ok_line2,
        secret: esp.secret,
      });
      setEsp(next);
      setMsg("ESP-Terminal gespeichert.");
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  async function generateEspSecret() {
    setMsg("");
    setErr("");
    setBusy(true);
    try {
      const next = await api.generateEspSecret();
      setEsp(next);
      setMsg("Neues Secret erzeugt. Am Gerät BOOT 4 Sekunden halten und eintragen.");
    } catch (ex) {
      setErr(ex instanceof ApiError ? ex.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {msg ? <p className="text-sm text-present">{msg}</p> : null}
      <div className="space-y-3 rounded-2xl border border-line bg-card p-4">
        <p className="text-sm font-medium">ESP-Terminal</p>
        <p className="text-sm text-muted">
          Eigenes Gerät (kein Datafox). Kommen/Gehen entscheidet der Server. Geräte melden sich mit ihrer MAC; hier
          benennen, WLAN vorgeben und Firmware per OTA hochladen. OLED: {esp.line_max} Zeichen je Zeile, längere Texte
          werden abgeschnitten. Platzhalter: {esp.placeholders.map((name) => `{${name}}`).join(", ")}.
        </p>
        <label className="block text-xs text-muted">
          Secret {esp.secret_source === "config" ? "(aus der Server-Config, speichern legt es in der App ab)" : ""}
          <PasswordField
            autoComplete="off"
            className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
            value={esp.secret}
            onChange={(e) => setEsp({ ...esp, secret: e.target.value })}
            placeholder="leer = API aus"
          />
        </label>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => void generateEspSecret()}
            className="flex-1 rounded-xl border border-line py-2 text-sm disabled:opacity-60"
          >
            Neu erzeugen
          </button>
          <button
            type="button"
            disabled={!esp.secret}
            onClick={() => {
              void navigator.clipboard.writeText(esp.secret).then(
                () => setMsg("Secret kopiert."),
                () => setErr("Kopieren nicht möglich."),
              );
            }}
            className="flex-1 rounded-xl border border-line py-2 text-sm disabled:opacity-60"
          >
            Kopieren
          </button>
        </div>
        <p className="text-xs text-muted">
          {esp.secret_configured ? "API ist an." : "Kein Secret — Geräte werden abgewiesen."} Nach einem neuen Secret
          BOOT am Gerät 4 Sekunden halten und das Secret im Portal eintragen.
        </p>
        <label className="block text-xs text-muted">
          Zeile 1
          <input
            className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
            value={esp.ok_line1}
            onChange={(e) => setEsp({ ...esp, ok_line1: e.target.value })}
          />
        </label>
        {(() => {
          const p = previewLine(esp.ok_line1, esp.line_max);
          return (
            <p className={`text-xs ${p.over ? "text-danger" : "text-muted"}`}>
              Vorschau ({p.length} Zeichen): {p.text || "—"}
              {p.over ? ` — länger als ${esp.line_max}, wird abgeschnitten.` : ""}
            </p>
          );
        })()}
        <label className="block text-xs text-muted">
          Zeile 2
          <input
            className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
            value={esp.ok_line2}
            onChange={(e) => setEsp({ ...esp, ok_line2: e.target.value })}
          />
        </label>
        {(() => {
          const p = previewLine(esp.ok_line2, esp.line_max);
          return (
            <p className={`text-xs ${p.over ? "text-danger" : "text-muted"}`}>
              Vorschau ({p.length} Zeichen): {p.text || "—"}
              {p.over ? ` — länger als ${esp.line_max}, wird abgeschnitten.` : ""}
            </p>
          );
        })()}
        <button
          type="button"
          disabled={busy}
          onClick={() => void saveEsp()}
          className="w-full rounded-xl bg-navy py-2 text-sm text-white disabled:opacity-60"
        >
          Secret und Display speichern
        </button>

        <div className="space-y-2 border-t border-line pt-3">
          <p className="text-sm font-medium">Geräte</p>
          {esp.devices.length === 0 ? (
            <p className="text-xs text-muted">Noch keines. Sobald ein Terminal bucht oder sich meldet, erscheint es hier.</p>
          ) : null}
          {esp.devices.map((dev) => (
            <div key={dev.id} className="space-y-2 rounded-xl border border-line px-3 py-2">
              <p className="text-xs text-muted">
                ID {dev.device_id}
                {dev.firmware ? ` · FW ${dev.firmware}` : ""}
                {dev.last_ip ? ` · ${dev.last_ip}` : ""}
                {dev.last_ssid ? ` · WLAN ${dev.last_ssid}` : ""}
                {" · "}
                {formatSeen(dev.last_seen_at)}
              </p>
              <label className="block text-xs text-muted">
                Name
                <input
                  className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
                  value={dev.name}
                  placeholder="z. B. Eingang"
                  onChange={(e) =>
                    setEsp({
                      ...esp,
                      devices: esp.devices.map((d) => (d.id === dev.id ? { ...d, name: e.target.value } : d)),
                    })
                  }
                />
              </label>
              <label className="block text-xs text-muted">
                WLAN vorgeben (SSID, leer = Gerät behält sein WLAN)
                <input
                  className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
                  value={dev.wifi_ssid}
                  onChange={(e) =>
                    setEsp({
                      ...esp,
                      devices: esp.devices.map((d) => (d.id === dev.id ? { ...d, wifi_ssid: e.target.value } : d)),
                    })
                  }
                />
              </label>
              <label className="block text-xs text-muted">
                WLAN-Passwort {dev.wifi_pass_set ? "(gesetzt, leer lassen zum Behalten)" : ""}
                <PasswordField
                  autoComplete="off"
                  className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
                  value={devicePass[dev.id] ?? ""}
                  onChange={(e) => setDevicePass({ ...devicePass, [dev.id]: e.target.value })}
                  placeholder={dev.wifi_pass_set ? "unverändert" : "optional"}
                />
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    void (async () => {
                      setBusy(true);
                      setErr("");
                      try {
                        const body: { name: string; wifi_ssid: string; wifi_pass?: string; clear_wifi?: boolean } = {
                          name: dev.name,
                          wifi_ssid: dev.wifi_ssid,
                        };
                        const pass = (devicePass[dev.id] ?? "").trim();
                        if (pass) body.wifi_pass = pass;
                        if (!dev.wifi_ssid.trim()) body.clear_wifi = true;
                        const next = await api.patchEspDevice(dev.id, body);
                        setEsp({
                          ...esp,
                          devices: esp.devices.map((d) => (d.id === dev.id ? next : d)),
                        });
                        setDevicePass({ ...devicePass, [dev.id]: "" });
                        setMsg("Gerät gespeichert.");
                      } catch (ex) {
                        setErr(ex instanceof ApiError ? ex.message : "Fehler");
                      } finally {
                        setBusy(false);
                      }
                    })();
                  }}
                  className="flex-1 rounded-xl border border-line py-2 text-sm disabled:opacity-60"
                >
                  Gerät speichern
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-2 border-t border-line pt-3">
          <p className="text-sm font-medium">Firmware (OTA)</p>
          <p className="text-xs text-muted">
            Mit PlatformIO oder Arduino IDE bauen, dann die <code className="text-xs">firmware.bin</code> hochladen.
            Geräte mit älterer Versionsnummer holen sie selbst (alle 30&nbsp;s). Aktuell auf dem Server:{" "}
            {esp.firmware_uploaded ? `Version ${esp.firmware_version}` : "keine Datei"}. Die im Gerät eingebaute Version
            ist 2.
          </p>
          <div className="grid grid-cols-3 gap-2">
            <label className="col-span-2 block text-xs text-muted">
              firmware.bin
              <input
                type="file"
                accept=".bin,application/octet-stream"
                className="mt-1 w-full text-sm"
                onChange={(e) => setFwFile(e.target.files?.[0] ?? null)}
              />
            </label>
            <label className="block text-xs text-muted">
              Version
              <input
                type="number"
                min={1}
                className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm text-ink"
                value={fwVersion}
                onChange={(e) => setFwVersion(Number(e.target.value) || 1)}
              />
            </label>
          </div>
          <button
            type="button"
            disabled={busy || !fwFile}
            onClick={() => {
              void (async () => {
                if (!fwFile) return;
                setBusy(true);
                setErr("");
                try {
                  const next = await api.uploadEspFirmware(fwFile, fwVersion);
                  setEsp(next);
                  setFwFile(null);
                  setMsg(`Firmware Version ${next.firmware_version} liegt bereit.`);
                } catch (ex) {
                  setErr(ex instanceof ApiError ? ex.message : "Fehler");
                } finally {
                  setBusy(false);
                }
              })();
            }}
            className="w-full rounded-xl border border-line py-2 text-sm disabled:opacity-60"
          >
            Firmware hochladen
          </button>
        </div>
      </div>
    </div>
  );
}

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

function DfcomCard() {
  const [dfcom, setDfcom] = useState<DfcomSettings>(emptyDfcom);
  const [termName, setTermName] = useState("Halle");
  const [termHost, setTermHost] = useState("");
  const [termPort, setTermPort] = useState(8000);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setDfcom(await api.dfcomSettings());
  }

  useEffect(() => {
    void load().catch(() => setErr("Terminal-Einstellungen konnten nicht geladen werden."));
  }, []);

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
    <div className="space-y-3">
      <p className="text-sm text-muted">Datafox MasterIV per Polling. HTTP-Stempeln bleibt parallel nutzbar.</p>
      {err ? <p className="text-sm text-danger">{err}</p> : null}
      {msg ? <p className="text-sm text-present">{msg}</p> : null}
      <div className="space-y-3 rounded-2xl border border-line bg-card p-4">
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

export default function Settings() {
  const [params, setParams] = useSearchParams();
  const tab = parseTab(params.get("tab"));

  function setTab(next: TabId) {
    setParams({ tab: next }, { replace: true });
  }

  return (
    <div className="pt-2 md:max-w-2xl">
      <Link to="/personal" className="text-sm text-muted">
        ← Personal
      </Link>
      <h1 className="mt-2 text-xl font-medium">Einstellungen</h1>
      <div className="mt-3 flex gap-1 rounded-2xl border border-line bg-card p-1">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`flex-1 rounded-xl px-2 py-2 text-sm font-medium ${
              tab === item.id ? "bg-present text-white" : "text-muted"
            }`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="mt-4">
        <div hidden={tab !== "sicherheit"}>
          <SecurityPolicyCard />
        </div>
        <div hidden={tab !== "mail"}>
          <MailCard />
        </div>
        <div hidden={tab !== "terminals"}>
          <p className="mb-3 text-sm text-muted">
            ESP-Geräte und optionales Datafox-Polling (DFCom). HTTP-Stempeln bleibt parallel nutzbar.
          </p>
          <EspCard />
          <div className="mt-3">
            <DfcomCard />
          </div>
        </div>
      </div>
    </div>
  );
}
