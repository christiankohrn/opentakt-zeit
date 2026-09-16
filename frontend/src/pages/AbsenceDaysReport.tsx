import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type AbsenceDaysRow, type User } from "../api";
import PersonFilter from "../components/PersonFilter";
import ReportToolbar, { ExportButtons } from "../components/ReportToolbar";
import { formatDeDate, parseUserIds, payrollYear, yearRange } from "../reportPeriod";

export default function AbsenceDaysReport({
  kind,
  title,
}: {
  kind: "sick" | "vacation";
  title: string;
}) {
  const [params, setParams] = useSearchParams();
  const year = Number(params.get("year") || payrollYear());
  const range = yearRange(year);
  const from = params.get("from") || range.from;
  const to = params.get("to") || range.to;
  const userIdsKey = params.get("user_ids");
  const selectedIds = parseUserIds(userIdsKey);
  const [users, setUsers] = useState<User[]>([]);
  const [people, setPeople] = useState<AbsenceDaysRow[]>([]);
  const [error, setError] = useState("");
  const periodLabel = kind === "sick" ? "Krankheitstage" : "Urlaubstage";
  const load = kind === "sick" ? api.sickDays : api.vacationDays;
  const downloadCsv = kind === "sick" ? api.downloadSickDaysCsv : api.downloadVacationDaysCsv;
  const downloadPdf = kind === "sick" ? api.downloadSickDaysPdf : api.downloadVacationDaysPdf;

  useEffect(() => {
    api.users().then(setUsers).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!params.get("from") || !params.get("to")) {
      const next: Record<string, string> = { from, to };
      const ids = params.get("user_ids");
      if (ids !== null) next.user_ids = ids;
      setParams(next, { replace: true });
    }
  }, [from, params, setParams, to]);

  useEffect(() => {
    load(from, to, parseUserIds(userIdsKey))
      .then((r) => {
        setPeople(r.people);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [from, load, to, userIdsKey]);

  function setFilter(nextFrom: string, nextTo: string, ids: number[] | null) {
    const query: Record<string, string> = { from: nextFrom, to: nextTo };
    if (ids !== null) query.user_ids = ids.join(",");
    setParams(query);
  }

  const periodTotal = people.reduce((sum, row) => sum + row.period_days, 0);
  const yearTotal = people.reduce((sum, row) => sum + row.year_days, 0);

  return (
    <div className="pt-2">
      <Link to="/auswertungen" className="text-sm text-muted">
        ← Auswertungen
      </Link>
      <ReportToolbar
        title={title}
        actions={
          <ExportButtons
            onCsv={() => void downloadCsv(from, to, selectedIds)}
            onPdf={() => void downloadPdf(from, to, selectedIds)}
          />
        }
      >
        <input
          type="date"
          value={from}
          onChange={(e) => setFilter(e.target.value, to, selectedIds)}
          className="date-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
        />
        <span className="text-sm text-muted">bis</span>
        <input
          type="date"
          value={to}
          onChange={(e) => setFilter(from, e.target.value, selectedIds)}
          className="date-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
        />
        <PersonFilter users={users} selectedIds={selectedIds} onChange={(ids) => setFilter(from, to, ids)} />
      </ReportToolbar>
      <p className="mt-2 text-sm text-muted">
        {formatDeDate(from)} – {formatDeDate(to)}. Standard: ganzes Jahr, alle Mitarbeitenden. {people.length} Personen,{" "}
        {periodTotal} Tage im Zeitraum, {yearTotal} im Jahr insgesamt. Auch 0 Tage.
      </p>
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      <ul className="mt-4 space-y-2 md:hidden">
        {people.map((row) => (
          <li key={row.user_id} className="rounded-2xl border border-line bg-card px-4 py-3">
            <Link to={`/personal/${row.user_id}`} className="font-medium text-present">
              {row.display_name}
            </Link>
            <p className="text-sm tabular-nums">
              Zeitraum {row.period_days} · Jahr {row.year_days}
            </p>
          </li>
        ))}
      </ul>
      <div className="mt-4 hidden overflow-x-auto rounded-2xl border border-line md:block">
        <table className="w-full text-left text-sm">
          <thead className="bg-card text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium text-right">{periodLabel} Zeitraum</th>
              <th className="px-4 py-3 font-medium text-right">Jahr insgesamt</th>
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
                <td className="px-4 py-2.5 text-right tabular-nums">{row.period_days}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{row.year_days}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
