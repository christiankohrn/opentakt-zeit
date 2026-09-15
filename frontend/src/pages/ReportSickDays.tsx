import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type SickDaysRow } from "../api";
import { payrollYear } from "../reportPeriod";

export default function ReportSickDays() {
  const [params, setParams] = useSearchParams();
  const year = Number(params.get("year") || payrollYear());
  const [people, setPeople] = useState<SickDaysRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!params.get("year")) {
      setParams({ year: String(year) }, { replace: true });
    }
  }, [params, setParams, year]);

  useEffect(() => {
    api
      .sickDays(year)
      .then((r) => {
        setPeople(r.people);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [year]);

  const total = people.reduce((sum, row) => sum + row.sick_days, 0);

  return (
    <div className="pt-2">
      <Link to="/auswertungen" className="text-sm text-muted">
        ← Auswertungen
      </Link>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-medium">Krankheitstage</h1>
        <div className="flex items-center gap-2">
          <input
            type="number"
            min={1990}
            max={2100}
            value={year}
            onChange={(e) => setParams({ year: e.target.value })}
            className="w-24 rounded-lg border border-line bg-card px-2 py-1 text-sm"
          />
          <button type="button" className="text-sm text-present" onClick={() => void api.downloadSickDaysCsv(year)}>
            CSV
          </button>
        </div>
      </div>
      <p className="mt-2 text-sm text-muted">
        Kalenderjahr {year}. {people.length} Personen, {total} Krankheitstage insgesamt. Auch 0 Tage.
      </p>
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      <ul className="mt-4 space-y-2 md:hidden">
        {people.map((row) => (
          <li key={row.user_id} className="rounded-2xl border border-line bg-card px-4 py-3">
            <Link to={`/personal/${row.user_id}`} className="font-medium text-present">
              {row.display_name}
            </Link>
            <p className="text-sm tabular-nums">{row.sick_days} Tage</p>
          </li>
        ))}
      </ul>
      <div className="mt-4 hidden overflow-x-auto rounded-2xl border border-line md:block">
        <table className="w-full text-left text-sm">
          <thead className="bg-card text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium text-right">Krankheitstage</th>
            </tr>
          </thead>
          <tbody>
            {people.map((row) => (
              <tr key={row.user_id} className="border-t border-line bg-card">
                <td className="px-4 py-2.5">
                  <Link to={`/personal/${row.user_id}`} className="font-medium text-present">
                    {row.display_name}
                  </Link>
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums">{row.sick_days}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
