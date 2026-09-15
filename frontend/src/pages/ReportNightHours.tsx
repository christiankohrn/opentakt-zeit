import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type NightHoursRow } from "../api";
import { formatHours } from "../labels";
import { payrollMonth } from "../reportPeriod";

export default function ReportNightHours() {
  const [params, setParams] = useSearchParams();
  const month = params.get("month") || payrollMonth();
  const showCombined = params.get("plus") !== "0";
  const [people, setPeople] = useState<NightHoursRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!params.get("month")) {
      const next: Record<string, string> = { month };
      if (!showCombined) next.plus = "0";
      setParams(next, { replace: true });
    }
  }, [month, params, setParams, showCombined]);

  useEffect(() => {
    api
      .nightHours(month)
      .then((r) => {
        setPeople(r.people);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [month]);

  function setMonth(next: string) {
    const query: Record<string, string> = { month: next };
    if (!showCombined) query.plus = "0";
    setParams(query);
  }

  function setCombined(on: boolean) {
    const query: Record<string, string> = { month };
    if (!on) query.plus = "0";
    setParams(query);
  }

  return (
    <div className="pt-2">
      <Link to="/auswertungen" className="text-sm text-muted">
        ← Auswertungen
      </Link>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-medium">Nachtstunden</h1>
        <div className="flex items-center gap-2">
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
          />
          <button type="button" className="text-sm text-present" onClick={() => void api.downloadNightHoursCsv(month)}>
            CSV
          </button>
        </div>
      </div>
      <p className="mt-2 text-sm text-muted">
        Gestempelte Arbeitsintervalle in den Fenstern 20–24, 0–4 und 4–6 Uhr. Auto-Pause wird nicht abgezogen.
      </p>
      <label className="mt-3 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={showCombined} onChange={(e) => setCombined(e.target.checked)} />
        Spalte 1+3 anzeigen (20–24 plus 4–6)
      </label>
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      <ul className="mt-4 space-y-2 md:hidden">
        {people.map((row) => (
          <li key={row.user_id} className="rounded-2xl border border-line bg-card px-4 py-3">
            <Link to={`/personal/${row.user_id}?month=${month}`} className="font-medium text-present">
              {row.display_name}
            </Link>
            <p className="mt-1 text-sm tabular-nums">
              20–24 {formatHours(row.hours_20_24, 2)} · 0–4 {formatHours(row.hours_0_4, 2)} · 4–6{" "}
              {formatHours(row.hours_4_6, 2)}
              {showCombined ? ` · 1+3 ${formatHours(row.hours_1_plus_3, 2)}` : ""}
            </p>
          </li>
        ))}
      </ul>
      <div className="mt-4 hidden overflow-x-auto rounded-2xl border border-line md:block">
        <table className="w-full text-left text-sm">
          <thead className="bg-card text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium text-right">20–24</th>
              <th className="px-4 py-3 font-medium text-right">0–4</th>
              <th className="px-4 py-3 font-medium text-right">4–6</th>
              {showCombined ? <th className="px-4 py-3 font-medium text-right">1+3</th> : null}
            </tr>
          </thead>
          <tbody>
            {people.map((row) => (
              <tr key={row.user_id} className="border-t border-line bg-card">
                <td className="px-4 py-2.5">
                  <Link to={`/personal/${row.user_id}?month=${month}`} className="font-medium text-present">
                    {row.display_name}
                  </Link>
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums">{formatHours(row.hours_20_24, 2)}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{formatHours(row.hours_0_4, 2)}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{formatHours(row.hours_4_6, 2)}</td>
                {showCombined ? (
                  <td className="px-4 py-2.5 text-right tabular-nums">{formatHours(row.hours_1_plus_3, 2)}</td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
