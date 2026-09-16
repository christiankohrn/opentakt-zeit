import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type MonthBalanceRow } from "../api";
import { formatHours, signedHours } from "../labels";
import { defaultStichtag, formatDeDate, monthLabel, payrollMonth } from "../reportPeriod";

export default function ReportBalances() {
  const [params, setParams] = useSearchParams();
  const month = params.get("month") || payrollMonth();
  const asOf = params.get("as_of") || defaultStichtag(month);
  const [people, setPeople] = useState<MonthBalanceRow[]>([]);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!params.get("month") || !params.get("as_of")) {
      setParams({ month, as_of: asOf }, { replace: true });
    }
  }, [asOf, month, params, setParams]);

  useEffect(() => {
    api
      .monthBalances(month, asOf)
      .then((r) => {
        setPeople(r.people);
        setNote(r.note);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [asOf, month]);

  function setMonth(next: string) {
    setParams({ month: next, as_of: defaultStichtag(next) });
  }

  return (
    <div className="pt-2">
      <Link to="/auswertungen" className="text-sm text-muted">
        ← Auswertungen
      </Link>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-medium">Monatssalden</h1>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
          />
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted">Stichtag</span>
            <input
              type="date"
              value={asOf}
              onChange={(e) => setParams({ month, as_of: e.target.value })}
              className="rounded-lg border border-line bg-card px-2 py-1 text-sm"
            />
          </label>
          <button
            type="button"
            className="rounded-lg border border-line bg-card px-3 py-1 text-sm"
            onClick={() => void api.downloadMonthBalancesCsv(month, asOf)}
          >
            CSV
          </button>
          <button
            type="button"
            className="rounded-lg border border-present bg-present px-3 py-1 text-sm text-white"
            onClick={() => void api.downloadMonthBalancesPdf(month, asOf)}
          >
            PDF
          </button>
        </div>
      </div>
      <p className="mt-2 text-sm text-muted">
        {monthLabel(month)}, Stichtag {formatDeDate(asOf)}. Stunden bis zum früheren von Stichtag und heute. {note}
      </p>
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      <ul className="mt-4 space-y-2 md:hidden">
        {people.map((row) => (
          <li key={row.user_id} className="rounded-2xl border border-line bg-card px-4 py-3">
            <Link to={`/personal/${row.user_id}?month=${month}`} className="font-medium text-present">
              {row.display_name}
            </Link>
            <p className="mt-1 text-sm tabular-nums">
              Ist {formatHours(row.work_hours)} · Soll {formatHours(row.soll_hours)} · Diff {signedHours(row.delta_hours)}
            </p>
            <p className="text-xs text-muted">
              Vortrag {signedHours(row.carry_hours)} · Gesamt {signedHours(row.total_hours)}
            </p>
            <p className="text-xs text-muted">
              Krank {row.sick_days} · Urlaub {row.vacation_days} · geplant {row.vacation_planned_days}
            </p>
          </li>
        ))}
      </ul>
      <div className="mt-4 hidden overflow-x-auto rounded-2xl border border-line md:block">
        <table className="w-full min-w-[52rem] text-left text-sm">
          <thead className="bg-card text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium text-right">Ist</th>
              <th className="px-4 py-3 font-medium text-right">Soll</th>
              <th className="px-4 py-3 font-medium text-right">Diff</th>
              <th className="px-4 py-3 font-medium text-right">Vortrag</th>
              <th className="px-4 py-3 font-medium text-right">Gesamt</th>
              <th className="px-4 py-3 font-medium text-right">Krank</th>
              <th className="px-4 py-3 font-medium text-right">Urlaub</th>
              <th className="px-4 py-3 font-medium text-right">Urlaub geplant</th>
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
                <td className="px-4 py-2.5 text-right tabular-nums">{signedHours(row.carry_hours)}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{signedHours(row.total_hours)}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{row.sick_days}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{row.vacation_days}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{row.vacation_planned_days}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
