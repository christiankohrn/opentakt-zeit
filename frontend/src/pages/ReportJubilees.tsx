import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type JubileeEvent } from "../api";
import { payrollHalf, payrollYear } from "../reportPeriod";

function formatDate(iso: string) {
  const d = new Date(iso + "T12:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export default function ReportJubilees() {
  const [params, setParams] = useSearchParams();
  const year = Number(params.get("year") || payrollYear());
  const half = Number(params.get("half") || payrollHalf()) === 2 ? 2 : 1;
  const [events, setEvents] = useState<JubileeEvent[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!params.get("year") || !params.get("half")) {
      setParams({ year: String(year), half: String(half) }, { replace: true });
    }
  }, [half, params, setParams, year]);

  useEffect(() => {
    api
      .jubilees(year, half)
      .then((r) => {
        setEvents(r.events);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [half, year]);

  function setFilter(nextYear: number, nextHalf: number) {
    setParams({ year: String(nextYear), half: String(nextHalf) });
  }

  return (
    <div className="pt-2">
      <Link to="/auswertungen" className="text-sm text-muted">
        ← Auswertungen
      </Link>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-medium">Jubiläen</h1>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="number"
            min={1990}
            max={2100}
            value={year}
            onChange={(e) => setFilter(Number(e.target.value), half)}
            className="w-24 rounded-lg border border-line bg-card px-2 py-1 text-sm"
          />
          <select
            value={half}
            onChange={(e) => setFilter(year, Number(e.target.value))}
            className="rounded-lg border border-line bg-card px-2 py-1 text-sm"
          >
            <option value={1}>1. Halbjahr</option>
            <option value={2}>2. Halbjahr</option>
          </select>
          <button
            type="button"
            className="rounded-lg border border-line bg-card px-3 py-1 text-sm"
            onClick={() => void api.downloadJubileesCsv(year, half)}
          >
            CSV
          </button>
          <button
            type="button"
            className="rounded-lg border border-present bg-present px-3 py-1 text-sm text-white"
            onClick={() => void api.downloadJubileesPdf(year, half)}
          >
            PDF
          </button>
        </div>
      </div>
      <p className="mt-2 text-sm text-muted">
        Geburtstage, Eintrittstage und 10/25/40-Jahr-Jubiläen. Ohne Geburtstag erscheinen nur Eintritt und Jubiläen.
      </p>
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      {events.length === 0 && !error ? <p className="mt-8 text-sm text-muted">Keine Ereignisse in diesem Halbjahr.</p> : null}
      <ul className="mt-4 space-y-2 md:hidden">
        {events.map((row) => (
          <li key={`${row.user_id}-${row.kind}-${row.date}`} className="rounded-2xl border border-line bg-card px-4 py-3">
            <p className="text-xs text-muted">{formatDate(row.date)}</p>
            <Link to={`/personal/${row.user_id}`} className="font-medium text-present">
              {row.display_name}
            </Link>
            <p className="text-sm">
              {row.label} · {row.years} Jahre
            </p>
          </li>
        ))}
      </ul>
      <div className="mt-4 hidden overflow-x-auto rounded-2xl border border-line md:block">
        <table className="w-full text-left text-sm">
          <thead className="bg-card text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Datum</th>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Art</th>
              <th className="px-4 py-3 font-medium text-right">Jahre</th>
            </tr>
          </thead>
          <tbody>
            {events.map((row) => (
              <tr key={`${row.user_id}-${row.kind}-${row.date}`} className="border-t border-line bg-card">
                <td className="px-4 py-2.5 tabular-nums">{formatDate(row.date)}</td>
                <td className="px-4 py-2.5">
                  <Link to={`/personal/${row.user_id}`} className="font-medium text-present">
                    {row.display_name}
                  </Link>
                </td>
                <td className="px-4 py-2.5">{row.label}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{row.years}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
