import { Link, useSearchParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "../api";
import { formatDayLabel, warnLabel } from "../labels";

function payrollMonth() {
  const d = new Date();
  if (d.getDate() <= 15) {
    d.setDate(1);
    d.setMonth(d.getMonth() - 1);
  }
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function HrPlausibility() {
  const [params, setParams] = useSearchParams();
  const month = params.get("month") || payrollMonth();
  const userFilter = params.get("user");
  const [people, setPeople] = useState<
    Awaited<ReturnType<typeof api.plausibility>>["people"]
  >([]);

  function setMonth(next: string) {
    const nextParams: Record<string, string> = { month: next };
    if (userFilter) nextParams.user = userFilter;
    setParams(nextParams);
  }

  useEffect(() => {
    if (!params.get("month")) {
      const next: Record<string, string> = { month };
      if (userFilter) next.user = userFilter;
      setParams(next, { replace: true });
    }
  }, [month, params, setParams, userFilter]);

  useEffect(() => {
    api.plausibility(month).then((r) => setPeople(r.people));
  }, [month]);

  const visible = userFilter ? people.filter((p) => String(p.user.id) === userFilter) : people;
  const filteredName = visible[0]?.user.display_name;

  return (
    <div className="pt-2">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-medium">Prüfung</h1>
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
        />
      </div>
      <p className="mt-2 text-sm text-muted">
        Unregelmäßigkeiten im Monat: fehlende Buchungen, Pausen, Überlänge, offene Tage.{" "}
        <Link to="/feiertage" className="text-present">
          Feiertage
        </Link>
      </p>
      {userFilter ? (
        <p className="mt-2 text-sm">
          {filteredName ? `Nur ${filteredName}.` : "Nur diese Person."}{" "}
          <Link to={`/pruefung?month=${month}`} className="text-present">
            Alle anzeigen
          </Link>
        </p>
      ) : null}
      {visible.length === 0 ? (
        <p className="mt-8 text-sm text-muted">
          {userFilter ? "Keine Auffälligkeiten für diese Person in diesem Monat." : "Keine Auffälligkeiten in diesem Monat."}
        </p>
      ) : (
        <ul className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {visible.map((p) => (
            <li key={p.user.id} className="overflow-hidden rounded-2xl border border-danger/25 bg-card">
              <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
                <div className="min-w-0">
                  <Link
                    to={`/personal/${p.user.id}?from=pruefung&month=${month}`}
                    className="block truncate font-medium"
                  >
                    {p.user.display_name}
                  </Link>
                  <p className="mt-0.5 text-xs text-muted">{p.model_name ?? "ohne Modell"}</p>
                </div>
                <div
                  className="shrink-0 rounded-xl bg-danger/10 px-2.5 py-1.5 text-right"
                  title={`${p.issue_count} einzelne Auffälligkeiten an ${p.days_with_issues} Tagen`}
                >
                  <p className="text-sm font-medium leading-none text-danger">
                    {p.issue_count} Hinweis{p.issue_count === 1 ? "" : "e"}
                  </p>
                  <p className="mt-1 text-[11px] text-danger/80">
                    an {p.days_with_issues} Tag{p.days_with_issues === 1 ? "" : "en"}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5 px-4 py-2.5">
                {Object.entries(p.counts)
                  .filter(([, n]) => n > 0)
                  .map(([code, n]) => (
                    <span
                      key={code}
                      className="rounded-full bg-danger/10 px-2 py-0.5 text-[11px] text-danger"
                    >
                      {n}× {warnLabel(code)}
                    </span>
                  ))}
              </div>
              <ul className="divide-y divide-line border-t border-line">
                {p.days.map((d) => (
                  <li key={d.date} className="px-4 py-2.5">
                    <Link
                      className="text-sm font-medium text-present"
                      to={`/personal/${p.user.id}/tag/${d.date}?from=pruefung&month=${month}`}
                    >
                      {formatDayLabel(d.date, "short")}
                    </Link>
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {d.warnings.map((w) => (
                        <span
                          key={w}
                          className="rounded-md bg-bg px-1.5 py-0.5 text-[11px] text-muted ring-1 ring-line"
                        >
                          {warnLabel(w)}
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
