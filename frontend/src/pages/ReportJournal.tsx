import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type DaySummary, type User } from "../api";
import { bookingText, dayKindLabel, formatDayLabel, formatHours, signedHours } from "../labels";
import { payrollMonth } from "../reportPeriod";

type JournalRow =
  | { type: "day"; day: DaySummary }
  | { type: "week"; key: string; work: number; soll: number; delta: number }
  | { type: "month"; work: number; soll: number; delta: number };

function journalRows(days: DaySummary[]): JournalRow[] {
  const rows: JournalRow[] = [];
  let weekWork = 0;
  let weekSoll = 0;
  let weekDelta = 0;
  let monthWork = 0;
  let monthSoll = 0;
  let monthDelta = 0;
  days.forEach((day, index) => {
    rows.push({ type: "day", day });
    weekWork += day.work_hours;
    weekSoll += day.soll_hours;
    weekDelta += day.delta_hours;
    monthWork += day.work_hours;
    monthSoll += day.soll_hours;
    monthDelta += day.delta_hours;
    const next = days[index + 1];
    if (day.weekday === 6 || !next) {
      rows.push({
        type: "week",
        key: day.date,
        work: weekWork,
        soll: weekSoll,
        delta: weekDelta,
      });
      weekWork = 0;
      weekSoll = 0;
      weekDelta = 0;
    }
  });
  rows.push({ type: "month", work: monthWork, soll: monthSoll, delta: monthDelta });
  return rows;
}

function monthLabel(month: string) {
  const d = new Date(`${month}-01T12:00:00`);
  if (Number.isNaN(d.getTime())) return month;
  return d.toLocaleDateString("de-DE", { month: "long", year: "numeric" });
}

export default function ReportJournal() {
  const [params, setParams] = useSearchParams();
  const month = params.get("month") || payrollMonth();
  const userParam = params.get("user") || "";
  const [users, setUsers] = useState<User[]>([]);
  const [person, setPerson] = useState<User | null>(null);
  const [days, setDays] = useState<DaySummary[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.users().then(setUsers).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!params.get("month")) {
      const next: Record<string, string> = { month };
      if (userParam) next.user = userParam;
      setParams(next, { replace: true });
    }
  }, [month, params, setParams, userParam]);

  useEffect(() => {
    if (!userParam) {
      setPerson(null);
      setDays([]);
      return;
    }
    api
      .userDays(Number(userParam), month)
      .then((r) => {
        setPerson(r.user);
        setDays(r.days);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [month, userParam]);

  const rows = useMemo(() => journalRows(days), [days]);

  function setFilter(nextUser: string, nextMonth: string) {
    const query: Record<string, string> = { month: nextMonth };
    if (nextUser) query.user = nextUser;
    setParams(query);
  }

  return (
    <div className="pt-2">
      <Link to="/auswertungen" className="print:hidden text-sm text-muted">
        ← Auswertungen
      </Link>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3 print:hidden">
        <h1 className="text-xl font-medium">Journal</h1>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={userParam}
            onChange={(e) => setFilter(e.target.value, month)}
            className="max-w-56 rounded-lg border border-line bg-card px-2 py-1 text-sm"
          >
            <option value="">Person wählen</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.display_name}
              </option>
            ))}
          </select>
          <input
            type="month"
            value={month}
            onChange={(e) => setFilter(userParam, e.target.value)}
            className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
          />
          <button
            type="button"
            className="rounded-lg border border-line bg-card px-3 py-1 text-sm"
            onClick={() => window.print()}
          >
            Drucken
          </button>
          <button
            type="button"
            className="rounded-lg border border-present bg-present px-3 py-1 text-sm text-white disabled:opacity-40"
            disabled={!userParam}
            onClick={() => void api.downloadJournalPdf(Number(userParam), month)}
          >
            PDF
          </button>
        </div>
      </div>
      <div className="mt-4 hidden print:block">
        <h1 className="text-xl font-medium">{person?.display_name ?? "Journal"}</h1>
        <p className="text-sm">{monthLabel(month)}</p>
      </div>
      <p className="mt-2 text-sm text-muted print:hidden">
        Stempel, Abwesenheiten, Wochen- und Monatssummen. Zum Ausdrucken die Navigation ausblenden.
      </p>
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      {!userParam ? <p className="mt-8 text-sm text-muted">Bitte eine Person wählen.</p> : null}
      {userParam && days.length === 0 && !error ? <p className="mt-8 text-sm text-muted">Keine Tage in diesem Monat.</p> : null}
      {days.length > 0 ? (
        <div className="mt-4 overflow-x-auto rounded-2xl border border-line print:border-0">
          <table className="w-full text-left text-sm">
            <thead className="bg-card text-xs uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-3 font-medium">Tag</th>
                <th className="px-4 py-3 font-medium">Buchung</th>
                <th className="px-4 py-3 font-medium text-right">Ist</th>
                <th className="px-4 py-3 font-medium text-right">Soll</th>
                <th className="px-4 py-3 font-medium text-right">Konto</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                if (row.type === "day") {
                  const off = Boolean(row.day.calendar || row.day.absence);
                  return (
                    <tr key={row.day.date} className="border-t border-line bg-card">
                      <td className="px-4 py-2.5 whitespace-nowrap">{formatDayLabel(row.day.date)}</td>
                      <td className="px-4 py-2.5">
                        {off ? dayKindLabel(row.day) || bookingText(row.day) : bookingText(row.day)}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">
                        {row.day.work_hours ? formatHours(row.day.work_hours, 2) : "—"}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{formatHours(row.day.soll_hours, 2)}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{signedHours(row.day.delta_hours, 2)}</td>
                    </tr>
                  );
                }
                if (row.type === "week") {
                  return (
                    <tr key={`week-${row.key}`} className="border-t border-line bg-bg font-medium">
                      <td className="px-4 py-2.5" colSpan={2}>
                        Woche
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{formatHours(row.work, 2)}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{formatHours(row.soll, 2)}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{signedHours(row.delta, 2)}</td>
                    </tr>
                  );
                }
                return (
                  <tr key="month" className="border-t-2 border-ink/20 bg-card font-medium">
                    <td className="px-4 py-2.5" colSpan={2}>
                      Monat
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{formatHours(row.work, 2)}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{formatHours(row.soll, 2)}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{signedHours(row.delta, 2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
