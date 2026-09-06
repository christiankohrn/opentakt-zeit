import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import ConfirmDialog from "../components/ConfirmDialog";
import { IconTrash } from "../components/Icons";
import { absenceLabel, formatDayLabel } from "../labels";

type CalRow = { id: number | null; day: string; kind: string; name: string; source: string };

function currentYear() {
  return new Date().getFullYear();
}

function isoToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function HrCalendar() {
  const { user: me } = useAuth();
  const isAdmin = me?.role === "admin";
  const [year, setYear] = useState(currentYear);
  const [land, setLand] = useState("NW");
  const [states, setStates] = useState<Record<string, string>>({});
  const [rows, setRows] = useState<CalRow[]>([]);
  const [day, setDay] = useState(isoToday);
  const [kind, setKind] = useState("holiday");
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<CalRow | null>(null);

  async function load(nextYear = year) {
    const [settings, cal] = await Promise.all([api.orgSettings(), api.calendar(nextYear)]);
    setLand(settings.bundesland);
    setStates(settings.states);
    setRows(cal);
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  const grouped = useMemo(() => {
    const map = new Map<string, CalRow[]>();
    for (const row of rows) {
      const key = row.day.slice(0, 7);
      const list = map.get(key) ?? [];
      list.push(row);
      map.set(key, list);
    }
    return [...map.entries()];
  }, [rows]);

  async function saveLand(code: string) {
    setBusy(true);
    setMsg("");
    try {
      const next = await api.patchOrgSettings({ bundesland: code });
      setLand(next.bundesland);
      setRows(await api.calendar(year));
      setMsg(`Standort: ${next.bundesland_name}`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg("");
    try {
      await api.upsertCalendar({
        day,
        kind,
        name: name.trim() || (kind === "company_off" ? "Betriebsfrei" : "Feiertag"),
      });
      setName("");
      setRows(await api.calendar(year));
      setMsg("Tag gespeichert.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pt-2">
      <Link to="/personal" className="text-sm text-muted">
        ← Personal
      </Link>
      <div className="mt-2 flex items-center justify-between gap-3">
        <h1 className="text-xl font-medium">Feiertage</h1>
        <input
          type="number"
          min={2020}
          max={2100}
          value={year}
          onChange={(e) => setYear(Number(e.target.value) || currentYear())}
          className="w-24 rounded-lg border border-line bg-card px-2 py-1 text-sm"
        />
      </div>
      <p className="mt-2 text-sm text-muted">
        Gesetzliche Feiertage hängen am Standort (Bundesland). Zusätzlich kannst du eigene Feiertage und
        betriebsfreie Tage eintragen.
      </p>
      <label className="mt-4 block rounded-2xl border border-line bg-card px-4 py-3 text-sm">
        <span className="text-xs text-muted">Standort / Bundesland</span>
        <select
          className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 disabled:opacity-70"
          value={land}
          disabled={busy || !isAdmin}
          onChange={(e) => void saveLand(e.target.value)}
        >
          {Object.entries(states).map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </select>
        {!isAdmin ? (
          <span className="mt-1 block text-xs text-muted">Nur Administrator darf den Standort ändern.</span>
        ) : null}
      </label>
      <form onSubmit={onSubmit} className="mt-3 space-y-2 overflow-x-hidden rounded-2xl border border-line bg-card p-4">
        <p className="text-sm font-medium">Tag eintragen</p>
        <div className="grid grid-cols-2 gap-2">
          <label className="block min-w-0 overflow-hidden text-xs text-muted">
            Datum
            <input
              type="date"
              className="mt-1 h-10 w-full rounded-lg border border-line bg-bg px-2 text-sm text-ink"
              value={day}
              onChange={(e) => setDay(e.target.value)}
              required
            />
          </label>
          <label className="block min-w-0 overflow-hidden text-xs text-muted">
            Art
            <select
              className="mt-1 h-10 w-full rounded-lg border border-line bg-bg px-2 py-2 text-sm text-ink"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              <option value="holiday">Feiertag</option>
              <option value="company_off">Betriebsfrei</option>
            </select>
          </label>
        </div>
        <input
          placeholder={kind === "company_off" ? "z. B. Betriebsruhe, Brückentag" : "Name, z. B. Betriebsfeiertag"}
          className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit" disabled={busy} className="w-full rounded-xl bg-present py-2 text-sm text-white">
          Speichern
        </button>
      </form>
      {msg ? <p className="mt-3 text-sm text-present">{msg}</p> : null}
      <div className="mt-4 space-y-4">
        {grouped.map(([month, items]) => (
          <section key={month}>
            <h2 className="text-xs font-medium uppercase tracking-wider text-muted">
              {new Date(month + "-01T12:00:00").toLocaleDateString("de-DE", { month: "long", year: "numeric" })}
            </h2>
            <ul className="mt-2 divide-y divide-line overflow-hidden rounded-2xl border border-line">
              {items.map((row) => (
                <li
                  key={row.day + row.kind + String(row.id)}
                  className={`flex items-center justify-between gap-3 px-4 py-2.5 ${
                    row.kind === "company_off" ? "bg-off/15" : "bg-holiday/15"
                  }`}
                >
                  <div>
                    <p className="text-sm font-medium">
                      {formatDayLabel(row.day, "short")}{" "}
                      · {row.name}
                    </p>
                    <p className="text-xs text-muted">
                      {absenceLabel(row.kind)}
                      {row.source === "law" ? " · gesetzlich" : " · eingetragen"}
                    </p>
                  </div>
                  {row.id ? (
                    <button
                      type="button"
                      className="rounded-lg p-1 text-danger"
                      title="Löschen"
                      aria-label="Löschen"
                      disabled={busy}
                      onClick={() => setPendingDelete(row)}
                    >
                      <IconTrash className="h-4 w-4" />
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      {pendingDelete ? (
        <ConfirmDialog
          title="Eintrag löschen?"
          body={`${new Date(pendingDelete.day + "T12:00:00").toLocaleDateString("de-DE")} · ${pendingDelete.name} wird aus dem Kalender entfernt.`}
          confirmLabel={busy ? "Löschen …" : "Löschen"}
          danger
          busy={busy}
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => {
            const id = pendingDelete.id;
            if (!id) return;
            setBusy(true);
            void (async () => {
              try {
                await api.deleteCalendar(id);
                setRows(await api.calendar(year));
                setMsg("Eintrag gelöscht.");
              } catch (err) {
                setMsg(err instanceof Error ? err.message : "Fehler");
              } finally {
                setBusy(false);
                setPendingDelete(null);
              }
            })();
          }}
        />
      ) : null}
    </div>
  );
}
