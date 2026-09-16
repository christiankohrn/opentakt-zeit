import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type MonthBalanceRow } from "../api";
import ReportToolbar, { ExportButtons } from "../components/ReportToolbar";
import { signedHours } from "../labels";
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
      <ReportToolbar
        title="Monatssalden"
        actions={
          <ExportButtons
            onCsv={() => void api.downloadMonthBalancesCsv(month, asOf)}
            onPdf={() => void api.downloadMonthBalancesPdf(month, asOf)}
          />
        }
      >
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
        />
        <label className="flex shrink-0 items-center gap-2 text-sm">
          <span className="whitespace-nowrap text-muted">Stichtag</span>
          <input
            type="date"
            value={asOf}
            onChange={(e) => setParams({ month, as_of: e.target.value })}
            className="date-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
          />
        </label>
      </ReportToolbar>
      <p className="mt-2 text-sm text-muted">
        Stand {formatDeDate(asOf)} · {monthLabel(month)}. Zeitkonto bis zum früheren von Stichtag und heute. {note}
      </p>
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      <ul className="mt-4 space-y-2 md:hidden">
        {people.map((row) => (
          <li key={row.user_id} className="rounded-2xl border border-line bg-card px-4 py-3">
            <Link to={`/personal/${row.user_id}?month=${month}`} className="font-medium text-present">
              {row.display_name}
            </Link>
            <p className="mt-1 text-sm tabular-nums">
              Zeitkonto {signedHours(row.flex_prev)} / {signedHours(row.flex_month)} / {signedHours(row.flex_total)}
            </p>
            <p className="text-xs text-muted">
              Urlaub {row.vacation_prev} / {row.vacation_month} / {row.vacation_total} / inkl. Zukunft{" "}
              {row.vacation_future}
            </p>
            <p className="text-xs text-muted">
              Krankheit {row.sick_prev} / {row.sick_month} / {row.sick_total}
            </p>
          </li>
        ))}
      </ul>
      <div className="mt-4 hidden overflow-x-auto rounded-2xl border border-line md:block">
        <table className="w-full min-w-[58rem] text-left text-sm">
          <thead className="bg-card text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-3 font-medium" rowSpan={2}>
                Name
              </th>
              <th className="px-4 py-3 text-center font-medium" colSpan={3}>
                Zeitkonto
              </th>
              <th className="px-4 py-3 text-center font-medium" colSpan={4}>
                Urlaub
              </th>
              <th className="px-4 py-3 text-center font-medium" colSpan={3}>
                Krankheit
              </th>
            </tr>
            <tr>
              <th className="px-3 py-2 font-medium text-right">Vormonat</th>
              <th className="px-3 py-2 font-medium text-right">Monat</th>
              <th className="px-3 py-2 font-medium text-right">Gesamt</th>
              <th className="px-3 py-2 font-medium text-right">Vormonat</th>
              <th className="px-3 py-2 font-medium text-right">Aktuell</th>
              <th className="px-3 py-2 font-medium text-right">Gesamt</th>
              <th className="px-3 py-2 font-medium text-right">inkl. Zukunft</th>
              <th className="px-3 py-2 font-medium text-right">Vormonat</th>
              <th className="px-3 py-2 font-medium text-right">Aktuell</th>
              <th className="px-3 py-2 font-medium text-right">Gesamt</th>
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
                <td className="px-3 py-2.5 text-right tabular-nums">{signedHours(row.flex_prev)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{signedHours(row.flex_month)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{signedHours(row.flex_total)}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{row.vacation_prev}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{row.vacation_month}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{row.vacation_total}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{row.vacation_future}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{row.sick_prev}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{row.sick_month}</td>
                <td className="px-3 py-2.5 text-right tabular-nums">{row.sick_total}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
