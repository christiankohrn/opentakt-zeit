import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type JubileeEvent, type User } from "../api";
import PersonFilter from "../components/PersonFilter";
import InactiveToggle from "../components/InactiveToggle";
import LoadingNote from "../components/LoadingNote";
import ReportToolbar, { ExportButtons } from "../components/ReportToolbar";
import { effectiveUserIds, formatDeDate, parseUserIds, payrollHalf, payrollYear, visibleUsers } from "../reportPeriod";

export default function ReportJubilees() {
  const [params, setParams] = useSearchParams();
  const year = Number(params.get("year") || payrollYear());
  const half = Number(params.get("half") || payrollHalf()) === 2 ? 2 : 1;
  const userIdsKey = params.get("user_ids");
  const selectedIds = parseUserIds(userIdsKey);
  const showInactive = params.get("inaktive") === "1";
  const [users, setUsers] = useState<User[] | null>(null);
  const shownUsers = visibleUsers(users ?? [], showInactive);
  const effectiveIds = effectiveUserIds(users, showInactive, selectedIds);
  const [events, setEvents] = useState<JubileeEvent[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.users().then(setUsers).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!params.get("year") || !params.get("half")) {
      const next: Record<string, string> = { year: String(year), half: String(half) };
      if (userIdsKey !== null) next.user_ids = userIdsKey;
      if (showInactive) next.inaktive = "1";
      setParams(next, { replace: true });
    }
  }, [half, params, setParams, showInactive, userIdsKey, year]);

  useEffect(() => {
    if (selectedIds === null && !showInactive && users === null) return;
    let cancel = false;
    setLoading(true);
    api
      .jubilees(year, half, effectiveIds)
      .then((r) => {
        if (cancel) return;
        setEvents(r.events);
        setError("");
      })
      .catch((err: Error) => {
        if (!cancel) setError(err.message);
      })
      .finally(() => {
        if (!cancel) setLoading(false);
      });
    return () => {
      cancel = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [half, userIdsKey, year, showInactive, users]);

  function setFilter(nextYear: number, nextHalf: number, ids: number[] | null, inactive = showInactive) {
    const query: Record<string, string> = { year: String(nextYear), half: String(nextHalf) };
    if (ids !== null) query.user_ids = ids.join(",");
    if (inactive) query.inaktive = "1";
    setParams(query);
  }

  return (
    <div className="pt-2">
      <Link to="/auswertungen" className="text-sm text-muted">
        ← Auswertungen
      </Link>
      <ReportToolbar
        title="Jubiläen"
        actions={
          <ExportButtons
            onCsv={() => void api.downloadJubileesCsv(year, half, effectiveIds)}
            onPdf={() => void api.downloadJubileesPdf(year, half, effectiveIds)}
          />
        }
      >
        <input
          type="number"
          min={1990}
          max={2100}
          value={year}
          onChange={(e) => setFilter(Number(e.target.value), half, selectedIds)}
          className="w-24 shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
        />
        <select
          value={half}
          onChange={(e) => setFilter(year, Number(e.target.value), selectedIds)}
          className="shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
        >
          <option value={1}>1. Halbjahr</option>
          <option value={2}>2. Halbjahr</option>
        </select>
        <PersonFilter users={shownUsers} selectedIds={selectedIds} onChange={(ids) => setFilter(year, half, ids)} />
        <InactiveToggle checked={showInactive} onChange={(next) => setFilter(year, half, selectedIds, next)} />
      </ReportToolbar>
      <p className="mt-2 text-sm text-muted">
        Geburtstage, Eintrittstage und 10/25/40-Jahr-Jubiläen. Ohne Geburtstag erscheinen nur Eintritt und Jubiläen.
      </p>
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      {loading ? (
        <LoadingNote />
      ) : events.length === 0 && !error ? (
        <p className="mt-8 text-sm text-muted">Keine Ereignisse in diesem Halbjahr.</p>
      ) : (
        <>
      <ul className="mt-4 space-y-2 md:hidden">
        {events.map((row) => (
          <li key={`${row.user_id}-${row.kind}-${row.date}`} className="rounded-2xl border border-line bg-card px-4 py-3">
            <p className="text-xs text-muted">{formatDeDate(row.date)}</p>
            <Link to={`/personal/${row.user_id}`} className="font-medium text-present">
              {row.display_name}
            </Link>
            <p className="text-sm">
              {row.label} · {row.years} Jahre
              {row.origin_date ? ` · ${formatDeDate(row.origin_date)}` : ""}
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
              <th className="px-4 py-3 font-medium">Geboren/Eintritt</th>
            </tr>
          </thead>
          <tbody>
            {events.map((row) => (
              <tr key={`${row.user_id}-${row.kind}-${row.date}`} className="border-t border-line bg-card">
                <td className="px-4 py-2.5 tabular-nums">{formatDeDate(row.date)}</td>
                <td className="px-4 py-2.5">
                  <Link to={`/personal/${row.user_id}`} className="font-medium text-present">
                    {row.display_name}
                  </Link>
                </td>
                <td className="px-4 py-2.5">{row.label}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{row.years}</td>
                <td className="px-4 py-2.5 tabular-nums">{row.origin_date ? formatDeDate(row.origin_date) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
        </>
      )}
    </div>
  );
}
