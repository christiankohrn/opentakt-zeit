import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type SickDaysRow, type User } from "../api";
import PersonFilter from "../components/PersonFilter";
import { formatDeDate, payrollYear, yearRange } from "../reportPeriod";

function parseUserIds(raw: string | null): number[] | null {
  if (raw === null) return null;
  if (raw === "") return [];
  return raw
    .split(",")
    .map((part) => Number(part))
    .filter((id) => Number.isInteger(id) && id > 0);
}

export default function ReportSickDays() {
  const [params, setParams] = useSearchParams();
  const year = Number(params.get("year") || payrollYear());
  const range = yearRange(year);
  const from = params.get("from") || range.from;
  const to = params.get("to") || range.to;
  const userIdsKey = params.get("user_ids");
  const selectedIds = parseUserIds(userIdsKey);
  const [users, setUsers] = useState<User[]>([]);
  const [people, setPeople] = useState<SickDaysRow[]>([]);
  const [error, setError] = useState("");

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
    api
      .sickDays(from, to, parseUserIds(userIdsKey))
      .then((r) => {
        setPeople(r.people);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [from, to, userIdsKey]);

  function setFilter(nextFrom: string, nextTo: string, ids: number[] | null) {
    const query: Record<string, string> = { from: nextFrom, to: nextTo };
    if (ids !== null) query.user_ids = ids.join(",");
    setParams(query);
  }

  const total = people.reduce((sum, row) => sum + row.sick_days, 0);

  return (
    <div className="pt-2">
      <Link to="/auswertungen" className="text-sm text-muted">
        ← Auswertungen
      </Link>
      <div className="mt-2 flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-start lg:justify-between">
        <h1 className="text-xl font-medium">Krankheitstage</h1>
        <div className="flex flex-wrap items-center gap-2">
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
          <button
            type="button"
            className="rounded-lg border border-line bg-card px-3 py-1 text-sm"
            onClick={() => void api.downloadSickDaysCsv(from, to, selectedIds)}
          >
            CSV
          </button>
          <button
            type="button"
            className="rounded-lg border border-present bg-present px-3 py-1 text-sm text-white"
            onClick={() => void api.downloadSickDaysPdf(from, to, selectedIds)}
          >
            PDF
          </button>
        </div>
      </div>
      <p className="mt-2 text-sm text-muted">
        {formatDeDate(from)} – {formatDeDate(to)}. Standard: ganzes Jahr, alle Mitarbeitenden. {people.length} Personen,{" "}
        {total} Krankheitstage insgesamt. Auch 0 Tage.
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
