import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type MonthBalanceRow } from "../api";
import { formatHours, signedHours } from "../labels";
import { payrollMonth } from "../reportPeriod";

export default function ReportBalances() {
  const [params, setParams] = useSearchParams();
  const month = params.get("month") || payrollMonth();
  const [people, setPeople] = useState<MonthBalanceRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!params.get("month")) {
      setParams({ month }, { replace: true });
    }
  }, [month, params, setParams]);

  useEffect(() => {
    api
      .monthBalances(month)
      .then((r) => {
        setPeople(r.people);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [month]);

  return (
    <div className="pt-2">
      <Link to="/auswertungen" className="text-sm text-muted">
        ← Auswertungen
      </Link>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-medium">Monatssalden</h1>
        <div className="flex items-center gap-2">
          <input
            type="month"
            value={month}
            onChange={(e) => setParams({ month: e.target.value })}
            className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
          />
          <button type="button" className="text-sm text-present" onClick={() => void api.downloadMonthBalancesCsv(month)}>
            CSV
          </button>
        </div>
      </div>
      <p className="mt-2 text-sm text-muted">
        Stunden bis heute, Krankheit und Urlaub für den ganzen Monat (auch zukünftige Buchungen).
      </p>
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      <ul className="mt-4 space-y-2 md:hidden">
        {people.map((row) => (
          <li key={row.user_id} className="rounded-2xl border border-line bg-card px-4 py-3">
            <Link to={`/personal/${row.user_id}?month=${month}`} className="font-medium text-present">
              {row.display_name}
            </Link>
            <p className="mt-1 text-sm tabular-nums">
              Ist {formatHours(row.work_hours)} · Soll {formatHours(row.soll_hours)} · {signedHours(row.delta_hours)}
            </p>
            <p className="text-xs text-muted">
              Krank {row.sick_days} · Urlaub {row.vacation_days}
            </p>
          </li>
        ))}
      </ul>
      <div className="mt-4 hidden overflow-x-auto rounded-2xl border border-line md:block">
        <table className="w-full text-left text-sm">
          <thead className="bg-card text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium text-right">Ist</th>
              <th className="px-4 py-3 font-medium text-right">Soll</th>
              <th className="px-4 py-3 font-medium text-right">Konto Monat</th>
              <th className="px-4 py-3 font-medium text-right">Krank</th>
              <th className="px-4 py-3 font-medium text-right">Urlaub</th>
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
                <td className="px-4 py-2.5 text-right tabular-nums">{formatHours(row.work_hours)}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{formatHours(row.soll_hours)}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{signedHours(row.delta_hours)}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{row.sick_days}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{row.vacation_days}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
