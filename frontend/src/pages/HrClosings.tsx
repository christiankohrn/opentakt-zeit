import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type ClosingJob } from "../api";
import LoadingNote from "../components/LoadingNote";
import { hoursTone, signedHours } from "../labels";

type MonthRow = { year: number; month: number; people: number; closed_at: string | null };
type PersonRow = {
  user_id: number;
  display_name: string;
  flex_hours: number;
  opening_balance_hours: number;
  opening_balance_on: string | null;
};

const MONTHS = [
  "Januar",
  "Februar",
  "März",
  "April",
  "Mai",
  "Juni",
  "Juli",
  "August",
  "September",
  "Oktober",
  "November",
  "Dezember",
];

function previousMonthValue() {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function label(year: number, month: number) {
  return `${MONTHS[month - 1] ?? month} ${year}`;
}

export default function HrClosings() {
  const [months, setMonths] = useState<MonthRow[]>([]);
  const [ready, setReady] = useState(false);
  const [target, setTarget] = useState(previousMonthValue);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [people, setPeople] = useState<PersonRow[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const data = await api.closings();
    setMonths(data.months);
  }

  useEffect(() => {
    void load()
      .catch(() => setMsg("Abschlüsse konnten nicht geladen werden."))
      .finally(() => setReady(true));
  }, []);

  async function openMonth(row: MonthRow) {
    const key = `${row.year}-${row.month}`;
    if (openKey === key) {
      setOpenKey(null);
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const detail = await api.closingDetail(row.year, row.month);
      setPeople(detail.people);
      setOpenKey(key);
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Fehler");
    } finally {
      setBusy(false);
    }
  }

  function progressText(job: ClosingJob) {
    const name = job.kind === "recalculate" ? "Neuberechnung" : "Abschluss";
    const when = job.year && job.month ? ` ${label(job.year, job.month)}` : "";
    if (!job.total) return `${name}${when} läuft …`;
    return `${name}${when}: ${job.done} von ${job.total} Personen. Die Seite kann offen bleiben.`;
  }

  async function followJob(job: ClosingJob) {
    let current = job;
    while (current.running) {
      setMsg(progressText(current));
      await new Promise((resolve) => setTimeout(resolve, 2000));
      current = await api.closingJob();
    }
    if (current.error) {
      setMsg(current.error);
      return;
    }
    await load();
    if (current.kind === "recalculate") {
      if (openKey === `${current.year}-${current.month}`) {
        const detail = await api.closingDetail(current.year, current.month);
        setPeople(detail.people);
      }
      setMsg(`${label(current.year, current.month)} neu gerechnet (${current.rows} Personen).`);
      return;
    }
    if (current.year && current.month) {
      setMsg(
        current.rows
          ? `${label(current.year, current.month)} abgeschlossen (${current.rows} Salden).`
          : `${label(current.year, current.month)} war schon abgeschlossen.`,
      );
    }
  }

  useEffect(() => {
    let cancel = false;
    void api
      .closingJob()
      .then((job) => {
        if (cancel || !job.running) return;
        setBusy(true);
        return followJob(job).finally(() => setBusy(false));
      })
      .catch(() => undefined);
    return () => {
      cancel = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function closeThrough(e: FormEvent) {
    e.preventDefault();
    const [yearText, monthText] = target.split("-");
    const year = Number(yearText);
    const month = Number(monthText);
    if (!year || !month) return;
    setBusy(true);
    setMsg("");
    try {
      await followJob(await api.closeMonth(year, month));
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Abschluss fehlgeschlagen");
    } finally {
      setBusy(false);
    }
  }

  async function recalculate(row: MonthRow) {
    setBusy(true);
    setMsg("");
    try {
      await followJob(await api.recalculateClosing(row.year, row.month));
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Neuberechnung fehlgeschlagen");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pt-2">
      <h1 className="text-xl font-medium">Abschlüsse</h1>
      <p className="mt-1 text-sm text-muted">
        Der Saldo wird am Monatsende festgehalten. Spätere Auswertungen rechnen nur noch die Tage danach. Der erste
        Abschluss über viele Monate kann einen Moment dauern.
      </p>
      <form onSubmit={(e) => void closeThrough(e)} className="mt-4 flex flex-wrap items-end gap-2">
        <label className="text-sm">
          Abschließen bis
          <input
            type="month"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className="mt-1 block rounded-lg border border-line bg-card px-2 py-1"
          />
        </label>
        <button type="submit" disabled={busy} className="rounded-xl bg-navy px-3 py-2 text-sm text-white">
          {busy ? "…" : "Monat abschließen"}
        </button>
      </form>
      {msg ? <p className="mt-3 text-sm">{msg}</p> : null}
      {!ready ? <LoadingNote /> : null}
      {ready && months.length === 0 ? <p className="mt-4 text-sm text-muted">Noch kein Monat abgeschlossen.</p> : null}
      <div className="mt-4 space-y-2">
        {months.map((row) => {
          const key = `${row.year}-${row.month}`;
          const open = openKey === key;
          return (
            <section key={key} className="rounded-2xl border border-line bg-card">
              <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                <button type="button" className="text-left text-sm font-medium" onClick={() => void openMonth(row)}>
                  {label(row.year, row.month)}
                  <span className="ml-2 font-normal text-muted">{row.people} Personen</span>
                </button>
                <button
                  type="button"
                  disabled={busy}
                  className="text-sm text-present"
                  onClick={() => void recalculate(row)}
                >
                  Neu rechnen
                </button>
              </div>
              {open ? (
                <ul className="border-t border-line">
                  {people.map((person) => (
                    <li key={person.user_id} className="flex items-center justify-between gap-3 px-4 py-2 text-sm">
                      <Link to={`/personal/${person.user_id}`} className="text-present">
                        {person.display_name}
                      </Link>
                      <span className="text-right">
                        <span className={hoursTone(person.flex_hours)}>{signedHours(person.flex_hours)}</span>
                        {person.opening_balance_on ? (
                          <span className="mt-0.5 block text-xs text-muted">
                            Start {signedHours(person.opening_balance_hours)} ab{" "}
                            {new Date(person.opening_balance_on + "T12:00:00").toLocaleDateString("de-DE")}
                          </span>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>
          );
        })}
      </div>
    </div>
  );
}
