import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type NightHoursRow, type User } from "../api";
import PersonFilter from "../components/PersonFilter";
import ReportToolbar, { ExportButtons } from "../components/ReportToolbar";
import { formatHours } from "../labels";
import { monthLabel, parseUserIds, payrollMonth } from "../reportPeriod";

export default function ReportNightHours() {
  const [params, setParams] = useSearchParams();
  const month = params.get("month") || payrollMonth();
  const showCombined = params.get("plus") !== "0";
  const userIdsKey = params.get("user_ids");
  const selectedIds = parseUserIds(userIdsKey);
  const [users, setUsers] = useState<User[]>([]);
  const [people, setPeople] = useState<NightHoursRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.users().then(setUsers).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!params.get("month")) {
      const next: Record<string, string> = { month };
      if (!showCombined) next.plus = "0";
      if (userIdsKey !== null) next.user_ids = userIdsKey;
      setParams(next, { replace: true });
    }
  }, [month, params, setParams, showCombined, userIdsKey]);

  useEffect(() => {
    api
      .nightHours(month, parseUserIds(userIdsKey))
      .then((r) => {
        setPeople(r.people);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [month, userIdsKey]);

  function setFilter(nextMonth: string, combined: boolean, ids: number[] | null) {
    const query: Record<string, string> = { month: nextMonth };
    if (!combined) query.plus = "0";
    if (ids !== null) query.user_ids = ids.join(",");
    setParams(query);
  }

  return (
    <div className="pt-2">
      <Link to="/auswertungen" className="text-sm text-muted">
        ← Auswertungen
      </Link>
      <ReportToolbar
        title="Lohnarten"
        actions={
          <ExportButtons
            onCsv={() => void api.downloadNightHoursCsv(month, selectedIds)}
            onPdf={() => void api.downloadNightHoursPdf(month, selectedIds)}
          />
        }
      >
        <input
          type="month"
          value={month}
          onChange={(e) => setFilter(e.target.value, showCombined, selectedIds)}
          className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
        />
        <label className="flex shrink-0 items-center gap-2 text-sm">
          <input type="checkbox" checked={showCombined} onChange={(e) => setFilter(month, e.target.checked, selectedIds)} />
          Summe aus 1 und 3
        </label>
        <PersonFilter users={users} selectedIds={selectedIds} onChange={(ids) => setFilter(month, showCombined, ids)} />
      </ReportToolbar>
      <p className="mt-2 text-sm text-muted">
        {monthLabel(month)}. Lohnarten aus Nachtfenstern: 1 = 20–24, 2 = 0–4, 3 = 4–6 Uhr. Auto-Pause wird nicht
        abgezogen.
      </p>
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      <ul className="mt-4 space-y-2 md:hidden">
        {people.map((row) => (
          <li key={row.user_id} className="rounded-2xl border border-line bg-card px-4 py-3">
            <Link to={`/personal/${row.user_id}?month=${month}`} className="font-medium text-present">
              {row.display_name}
            </Link>
            <p className="mt-1 text-sm tabular-nums">
              1 {formatHours(row.hours_20_24, 2)} · 2 {formatHours(row.hours_0_4, 2)} · 3 {formatHours(row.hours_4_6, 2)}
              {showCombined ? ` · Summe 1+3 ${formatHours(row.hours_1_plus_3, 2)}` : ""}
            </p>
          </li>
        ))}
      </ul>
      <div className="mt-4 hidden overflow-x-auto rounded-2xl border border-line md:block">
        <table className="w-full text-left text-sm">
          <thead className="bg-card text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium text-right">1 (20–24)</th>
              <th className="px-4 py-3 font-medium text-right">2 (0–4)</th>
              <th className="px-4 py-3 font-medium text-right">3 (4–6)</th>
              {showCombined ? <th className="px-4 py-3 font-medium text-right">Summe aus 1 und 3</th> : null}
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
