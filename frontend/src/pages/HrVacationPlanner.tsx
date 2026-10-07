import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type PlannerPerson, type User, type VacationPlanner } from "../api";
import InactiveToggle from "../components/InactiveToggle";
import LoadingNote from "../components/LoadingNote";
import MonthStepper from "../components/MonthStepper";
import PersonFilter from "../components/PersonFilter";
import PlannerLegend from "../components/PlannerLegend";
import ReportToolbar from "../components/ReportToolbar";
import { absenceLabel, formatDayTitle, plannerCellClass } from "../labels";
import {
  effectiveUserIds,
  formatDeDate,
  lastDayOfMonth,
  monthLabel,
  parseUserIds,
  rememberMonth,
  sessionMonth,
  visibleUsers,
  yearRange,
} from "../reportPeriod";

type View = "monat" | "jahr";

type Group = { key: string; name: string; people: PlannerPerson[] };

function groupPeople(people: PlannerPerson[]): Group[] {
  const map = new Map<string, Group>();
  for (const person of people) {
    const key = person.department_id != null ? `d-${person.department_id}` : "none";
    const name = person.department_name || "Ohne Abteilung";
    const group = map.get(key) ?? { key, name, people: [] };
    group.people.push(person);
    map.set(key, group);
  }
  return [...map.values()].sort((a, b) => {
    if (a.key === "none") return 1;
    if (b.key === "none") return -1;
    return a.name.localeCompare(b.name, "de");
  });
}

function quotaLine(person: PlannerPerson): string {
  const parts = [`${person.vacation_taken} gen.`, `${person.vacation_planned} gepl.`];
  if (person.vacation_allowance != null && person.vacation_remaining != null) {
    parts.push(`Rest ${person.vacation_remaining} von ${person.vacation_allowance}`);
  }
  return parts.join(" · ");
}

function MonthGrid({
  month,
  groups,
  showGroups,
  calendar,
}: {
  month: string;
  groups: Group[];
  showGroups: boolean;
  calendar: VacationPlanner["calendar"];
}) {
  const days = useMemo(() => {
    const [year, mon] = month.split("-").map(Number);
    const count = new Date(year, mon, 0).getDate();
    return Array.from({ length: count }, (_, i) => {
      const day = `${month}-${String(i + 1).padStart(2, "0")}`;
      return { day, num: i + 1, weekday: new Date(year, mon - 1, i + 1).getDay() };
    });
  }, [month]);
  const calMap = useMemo(() => new Map(calendar.map((c) => [c.day, c])), [calendar]);
  const dayMaps = useMemo(() => {
    const maps = new Map<number, Map<string, string>>();
    for (const group of groups) {
      for (const person of group.people) {
        maps.set(person.user_id, new Map(person.days.map((d) => [d.day, d.kind])));
      }
    }
    return maps;
  }, [groups]);
  const letters = ["S", "M", "D", "M", "D", "F", "S"];

  return (
    <div className="overflow-x-auto rounded-2xl border border-line">
      <table className="border-collapse text-xs">
        <thead>
          <tr className="bg-card">
            <th className="sticky left-0 z-[1] min-w-44 border-r border-line bg-card px-3 py-2 text-left font-medium">
              Name
            </th>
            {days.map((d) => (
              <th
                key={d.day}
                title={formatDayTitle(d.day)}
                className="min-w-7 px-0 py-1 text-center font-normal text-muted"
              >
                <span className="block text-[10px]">{letters[d.weekday]}</span>
                <span className="block tabular-nums">{d.num}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <Fragment key={group.key}>
              {showGroups ? (
                <tr className="bg-bg">
                  <td
                    colSpan={days.length + 1}
                    className="sticky left-0 border-y border-line px-3 py-1 font-medium"
                  >
                    {group.name} ({group.people.length})
                  </td>
                </tr>
              ) : null}
              {group.people.map((person) => {
                const absences = dayMaps.get(person.user_id);
                return (
                  <tr key={person.user_id} className="border-t border-line">
                    <td
                      className={`sticky left-0 z-[1] border-r border-line bg-card px-3 py-1.5 align-top ${
                        person.active ? "" : "opacity-60"
                      }`}
                    >
                      <Link
                        to={`/personal/${person.user_id}`}
                        className="block max-w-44 truncate font-medium text-present"
                        title={person.display_name}
                      >
                        {person.display_name}
                      </Link>
                      <span className="block text-[11px] tabular-nums text-muted">
                        {quotaLine(person)}
                      </span>
                    </td>
                    {days.map((d) => {
                      const absence = absences?.get(d.day) ?? null;
                      const cal = calMap.get(d.day) ?? null;
                      const label = absence
                        ? absenceLabel(absence)
                        : (cal?.name ?? "");
                      return (
                        <td
                          key={d.day}
                          title={label ? `${formatDayTitle(d.day)} · ${label}` : formatDayTitle(d.day)}
                          className={`h-8 min-w-7 border-l border-line/60 p-0 ${plannerCellClass(
                            absence,
                            cal?.kind ?? null,
                            d.weekday,
                          )}`}
                        />
                      );
                    })}
                  </tr>
                );
              })}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function HrVacationPlanner() {
  const [params, setParams] = useSearchParams();
  const view: View = params.get("view") === "jahr" ? "jahr" : "monat";
  const month = params.get("month") || sessionMonth();
  const year = Number(params.get("year")) || new Date().getFullYear();
  const selectedIds = parseUserIds(params.get("user_ids"));
  const showInactive = params.get("inaktive") === "1";
  const [users, setUsers] = useState<User[] | null>(null);
  const [data, setData] = useState<VacationPlanner | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const shownUsers = visibleUsers(users ?? [], showInactive);
  const effectiveIds = effectiveUserIds(users, showInactive, selectedIds);
  const range = view === "jahr" ? yearRange(year) : { from: `${month}-01`, to: lastDayOfMonth(month) };

  useEffect(() => {
    api.users().then(setUsers).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (view === "monat") rememberMonth(month);
  }, [view, month]);

  useEffect(() => {
    if (selectedIds === null && !showInactive && users === null) return;
    let cancel = false;
    setLoading(true);
    api
      .vacationPlanner(range.from, range.to, effectiveIds)
      .then((r) => {
        if (cancel) return;
        setData(r);
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
  }, [range.from, range.to, params.get("user_ids"), showInactive, users]);

  function setFilter(next: {
    view?: View;
    month?: string;
    year?: number;
    ids?: number[] | null;
    inactive?: boolean;
  }) {
    const query: Record<string, string> = { view: next.view ?? view };
    if ((next.view ?? view) === "jahr") query.year = String(next.year ?? year);
    else query.month = next.month ?? month;
    const ids = next.ids !== undefined ? next.ids : selectedIds;
    if (ids !== null) query.user_ids = ids.join(",");
    if (next.inactive ?? showInactive) query.inaktive = "1";
    setParams(query);
  }

  const groups = useMemo(() => groupPeople(data?.people ?? []), [data]);
  const showGroups = groups.some((g) => g.key !== "none") || groups.length > 1;
  const months = useMemo(
    () =>
      view === "jahr"
        ? Array.from({ length: 12 }, (_, i) => `${year}-${String(i + 1).padStart(2, "0")}`)
        : [month],
    [view, year, month],
  );

  return (
    <div className="pt-2">
      <ReportToolbar title="Urlaubsplaner">
        <div className="flex shrink-0 overflow-hidden rounded-lg border border-line" role="tablist">
          {(["monat", "jahr"] as View[]).map((v) => (
            <button
              key={v}
              type="button"
              role="tab"
              aria-selected={view === v}
              onClick={() => setFilter({ view: v })}
              className={`px-3 py-1 text-sm capitalize ${
                view === v ? "bg-present text-white" : "bg-card"
              }`}
            >
              {v === "monat" ? "Monat" : "Jahr"}
            </button>
          ))}
        </div>
        {view === "monat" ? (
          <MonthStepper value={month} onChange={(m) => setFilter({ month: m })} />
        ) : (
          <input
            type="number"
            min={2020}
            max={2100}
            value={year}
            aria-label="Jahr"
            onChange={(e) => setFilter({ year: Number(e.target.value) || year })}
            className="h-[2.25rem] w-24 shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
          />
        )}
        <PersonFilter users={shownUsers} selectedIds={selectedIds} onChange={(ids) => setFilter({ ids })} />
        <InactiveToggle checked={showInactive} onChange={(next) => setFilter({ inactive: next })} />
      </ReportToolbar>
      <PlannerLegend />
      {loading ? (
        <LoadingNote className="mt-2" />
      ) : (
        <p className="mt-2 text-sm text-muted">
          {formatDeDate(range.from)} – {formatDeDate(range.to)}. {data?.people.length ?? 0} Personen.
          Genommen/geplant zählt Urlaubstage im Jahr {data?.year} (ohne Wochenenden und Feiertage).
        </p>
      )}
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      {!loading && data && data.people.length === 0 ? (
        <p className="mt-8 text-sm text-muted">Keine Personen in dieser Auswahl.</p>
      ) : null}
      {!loading && data && data.people.length > 0 ? (
        <div className="mt-4 space-y-6">
          {months.map((m) => (
            <section key={m}>
              {view === "jahr" ? (
                <h2 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted">
                  {monthLabel(m)}
                </h2>
              ) : null}
              <MonthGrid month={m} groups={groups} showGroups={showGroups} calendar={data.calendar} />
            </section>
          ))}
        </div>
      ) : null}
    </div>
  );
}
