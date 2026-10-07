import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api, type PlannerPerson, type User, type VacationPlanner } from "../api";
import { useClosedMonth } from "../closedMonth";
import ConfirmDialog from "../components/ConfirmDialog";
import { IconAlert } from "../components/Icons";
import InactiveToggle from "../components/InactiveToggle";
import LoadingNote from "../components/LoadingNote";
import MonthStepper from "../components/MonthStepper";
import PersonFilter from "../components/PersonFilter";
import PlannerLegend from "../components/PlannerLegend";
import ReportToolbar, { ExportButtons } from "../components/ReportToolbar";
import { absenceLabel, formatDayTitle, isoDate, plannerCellClass } from "../labels";
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

type Pending = Record<number, Record<string, "add" | "remove">>;

type Preview = { taken: number; planned: number; remaining: number | null };

type Deficit = { user_id: number; display_name: string; remaining: number; deficit: number };

const COMPENSATION_REASON = "Ausgleich Urlaubskonto (Urlaubsplaner)";

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

function quotaText(taken: number, planned: number, allowance: number | null, remaining: number | null): string {
  const parts = [`${taken} gen.`, `${planned} gepl.`];
  if (allowance != null && remaining != null) {
    parts.push(`Rest ${remaining} von ${allowance}`);
  }
  return parts.join(" · ");
}

/** Näherung der Backend-Quote: Wochenende und Feiertage/betriebsfrei zählen nicht. */
function consumesQuota(day: string, calMap: Map<string, { kind: string }>): boolean {
  const weekday = new Date(`${day}T12:00:00`).getDay();
  if (weekday === 0 || weekday === 6) return false;
  const cal = calMap.get(day);
  return !cal || (cal.kind !== "holiday" && cal.kind !== "company_off");
}

function MonthGrid({
  month,
  groups,
  showGroups,
  calendar,
  editing,
  busy,
  pending,
  previews,
  negatives,
  onToggle,
}: {
  month: string;
  groups: Group[];
  showGroups: boolean;
  calendar: VacationPlanner["calendar"];
  editing: boolean;
  busy: boolean;
  pending: Pending;
  previews: Map<number, Preview>;
  negatives: Set<number>;
  onToggle: (userId: number, day: string, current: string | null) => void;
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
                const changes = pending[person.user_id] ?? {};
                const preview = editing ? previews.get(person.user_id) : undefined;
                const negative = negatives.has(person.user_id);
                const quota = preview
                  ? quotaText(preview.taken, preview.planned, person.vacation_allowance, preview.remaining)
                  : quotaText(
                      person.vacation_taken,
                      person.vacation_planned,
                      person.vacation_allowance,
                      person.vacation_remaining,
                    );
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
                        {negative ? <IconAlert className="mr-1 inline h-3.5 w-3.5 text-danger" /> : null}
                        {person.display_name}
                      </Link>
                      <span
                        className={`block text-[11px] tabular-nums ${
                          negative ? "font-medium text-danger" : "text-muted"
                        }`}
                      >
                        {quota}
                      </span>
                    </td>
                    {days.map((d) => {
                      const actual = absences?.get(d.day) ?? null;
                      const action = changes[d.day];
                      const effective = action === "add" ? "vacation" : action === "remove" ? null : actual;
                      const cal = calMap.get(d.day) ?? null;
                      const clickable = editing && !busy && (!actual || actual === "vacation");
                      const label = actual
                        ? absenceLabel(actual)
                        : (cal?.name ?? "");
                      const title = action === "add"
                        ? `${formatDayTitle(d.day)} · Urlaub (wird eingetragen)`
                        : action === "remove"
                          ? `${formatDayTitle(d.day)} · Urlaub (wird entfernt)`
                          : clickable && !actual
                            ? `${formatDayTitle(d.day)} · klicken: Urlaub eintragen`
                            : clickable
                              ? `${formatDayTitle(d.day)} · ${label} · klicken: entfernen`
                              : label
                                ? `${formatDayTitle(d.day)} · ${label}`
                                : formatDayTitle(d.day);
                      return (
                        <td
                          key={d.day}
                          title={title}
                          onClick={clickable ? () => onToggle(person.user_id, d.day, actual) : undefined}
                          className={`h-8 min-w-7 border-l border-line/60 p-0 ${plannerCellClass(
                            effective,
                            cal?.kind ?? null,
                            d.weekday,
                          )}${action === "add" ? " ring-2 ring-inset ring-ink" : ""}${
                            action === "remove" ? " ring-2 ring-inset ring-danger" : ""
                          }${clickable && !action ? " cursor-pointer hover:ring-2 hover:ring-inset hover:ring-ink/50" : ""}`}
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

function NegativeDialog({
  deficits,
  busy,
  onCompensate,
  onSaveAnyway,
  onCancel,
}: {
  deficits: Deficit[];
  busy: boolean;
  onCompensate: () => void;
  onSaveAnyway: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  return (
    <div
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/40 p-4 sm:items-center"
      onClick={() => {
        if (!busy) onCancel();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="negative-title"
        className="w-full max-w-md rounded-2xl bg-card p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <p id="negative-title" className="text-lg font-medium">
          Urlaubskonto läuft ins Minus
        </p>
        <div className="mt-1 text-sm text-muted">
          <p>
            Speichern ist möglich, aber es sollte zusätzlicher Urlaub im Urlaubskonto gebucht
            werden:
          </p>
          <ul className="mt-2 space-y-1">
            {deficits.map((d) => (
              <li key={d.user_id} className="flex justify-between gap-3 tabular-nums">
                <span className="truncate">{d.display_name}</span>
                <span className="shrink-0 font-medium text-danger">
                  Rest {d.remaining} · Ausgleich {d.deficit} {d.deficit === 1 ? "Tag" : "Tage"}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div className="mt-4 flex flex-col gap-2">
          <button
            type="button"
            className="rounded-xl bg-present py-2 text-white disabled:opacity-60"
            disabled={busy}
            onClick={onCompensate}
          >
            {busy ? "Speichern …" : "Ausgleichen und speichern"}
          </button>
          <button
            type="button"
            className="rounded-xl border border-danger py-2 text-danger disabled:opacity-60"
            disabled={busy}
            onClick={onSaveAnyway}
          >
            Trotzdem speichern
          </button>
          <button
            type="button"
            className="rounded-xl border border-line py-2 disabled:opacity-60"
            disabled={busy}
            onClick={onCancel}
          >
            Zurück
          </button>
        </div>
      </div>
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
  const closed = useClosedMonth();
  const [users, setUsers] = useState<User[] | null>(null);
  const [data, setData] = useState<VacationPlanner | null>(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState<Pending>({});
  const [busy, setBusy] = useState(false);
  const [negativeOpen, setNegativeOpen] = useState(false);
  const [discardOpen, setDiscardOpen] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
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
  }, [range.from, range.to, params.get("user_ids"), showInactive, users, reloadKey]);

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

  const calMap = useMemo(
    () => new Map((data?.calendar ?? []).map((c) => [c.day, c])),
    [data],
  );
  const previews = useMemo(() => {
    const map = new Map<number, Preview>();
    if (!data) return map;
    for (const person of data.people) {
      let taken = person.vacation_taken;
      let planned = person.vacation_planned;
      let remaining = person.vacation_remaining;
      const changes = pending[person.user_id] ?? {};
      for (const [day, action] of Object.entries(changes)) {
        if (!consumesQuota(day, calMap)) continue;
        const delta = action === "add" ? 1 : -1;
        if (day <= data.as_of) taken += delta;
        else planned += delta;
        if (remaining != null) remaining -= delta;
      }
      map.set(person.user_id, { taken, planned, remaining });
    }
    return map;
  }, [data, pending, calMap]);
  const deficits = useMemo<Deficit[]>(() => {
    if (!data) return [];
    const out: Deficit[] = [];
    for (const person of data.people) {
      const preview = previews.get(person.user_id);
      if (
        person.vacation_allowance != null &&
        preview?.remaining != null &&
        preview.remaining < 0
      ) {
        out.push({
          user_id: person.user_id,
          display_name: person.display_name,
          remaining: preview.remaining,
          deficit: -preview.remaining,
        });
      }
    }
    return out;
  }, [data, previews]);
  const negatives = useMemo(() => new Set(deficits.map((d) => d.user_id)), [deficits]);
  const pendingCount = useMemo(
    () => Object.values(pending).reduce((sum, changes) => sum + Object.keys(changes).length, 0),
    [pending],
  );

  function toggleCell(userId: number, day: string, current: string | null) {
    if (!editing || busy) return;
    if (current && current !== "vacation") return;
    setPending((prev) => {
      const next = { ...prev };
      const changes = { ...(next[userId] ?? {}) };
      if (changes[day]) delete changes[day];
      else changes[day] = current ? "remove" : "add";
      if (Object.keys(changes).length === 0) delete next[userId];
      else next[userId] = changes;
      return next;
    });
  }

  function entryDay(userId: number): string {
    const changes = pending[userId] ?? {};
    const added = Object.keys(changes)
      .filter((day) => changes[day] === "add")
      .sort();
    if (added.length > 0) return added[0];
    const today = isoDate();
    if (data && today.startsWith(String(data.year))) return today;
    return `${data?.year ?? year}-12-31`;
  }

  async function doSave(compensate: boolean) {
    setNegativeOpen(false);
    setBusy(true);
    setMsg("");
    setError("");
    try {
      await closed.attempt(async (confirmClosed) => {
        for (const [uid, changes] of Object.entries(pending)) {
          const userId = Number(uid);
          for (const [day, action] of Object.entries(changes)) {
            if (action === "add") {
              await api.createAbsences(userId, {
                kind: "vacation",
                start: day,
                end: day,
                confirm_closed: confirmClosed,
              });
            } else {
              try {
                await api.deleteAbsence(userId, day, confirmClosed);
              } catch (err) {
                // Bereits gelöscht (z. B. Wiederholung nach Monats-Bestätigung).
                if (!(err instanceof ApiError) || err.status !== 404) throw err;
              }
            }
          }
        }
        if (compensate) {
          for (const deficit of deficits) {
            const day = entryDay(deficit.user_id);
            const ledger = await api.userLedger(deficit.user_id, data?.year ?? year);
            const exists = ledger.vacation_entries.some(
              (entry) =>
                entry.day === day &&
                entry.amount === deficit.deficit &&
                entry.reason === COMPENSATION_REASON,
            );
            if (!exists) {
              await api.createLedgerEntry(deficit.user_id, {
                kind: "vacation",
                day,
                amount: deficit.deficit,
                reason: COMPENSATION_REASON,
                confirm_closed: confirmClosed,
              });
            }
          }
        }
        setPending({});
        setEditing(false);
        setReloadKey((key) => key + 1);
        setMsg(compensate ? "Gespeichert. Ausgleich im Urlaubskonto gebucht." : "Gespeichert.");
      }, setError);
    } finally {
      setBusy(false);
    }
  }

  function requestSave() {
    if (pendingCount === 0 || busy) return;
    if (deficits.length > 0) {
      setNegativeOpen(true);
      return;
    }
    void doSave(false);
  }

  function requestCancel() {
    if (busy) return;
    if (pendingCount > 0) {
      setDiscardOpen(true);
      return;
    }
    setEditing(false);
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
      <ReportToolbar
        title="Urlaubsplaner"
        actions={
          <div className="flex shrink-0 items-center gap-2">
            <ExportButtons
              onCsv={() => void api.downloadVacationPlannerCsv(range.from, range.to, effectiveIds)}
              onPdf={() => void api.downloadVacationPlannerPdf(range.from, range.to, effectiveIds)}
            />
            {editing ? (
              <>
                <button
                  type="button"
                  disabled={busy}
                  onClick={requestCancel}
                  className="rounded-lg border border-line bg-card px-3 py-1 text-sm disabled:opacity-40"
                >
                  Abbrechen
                </button>
                <button
                  type="button"
                  disabled={busy || pendingCount === 0}
                  onClick={requestSave}
                  className="rounded-lg border border-present bg-present px-3 py-1 text-sm text-white disabled:opacity-40"
                >
                  {busy ? "Speichern …" : pendingCount > 0 ? `Speichern (${pendingCount})` : "Speichern"}
                </button>
              </>
            ) : (
              <button
                type="button"
                disabled={busy || loading || !data}
                onClick={() => {
                  setMsg("");
                  setError("");
                  setEditing(true);
                }}
                className="rounded-lg border border-line bg-card px-3 py-1 text-sm disabled:opacity-40"
              >
                Bearbeiten
              </button>
            )}
          </div>
        }
      >
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
          {editing ? " Klick auf einen Tag trägt Urlaub ein oder entfernt ihn." : null}
          {pendingCount > 0 ? ` ${pendingCount} Änderung${pendingCount === 1 ? "" : "en"} offen.` : null}
          {editing && deficits.length > 0
            ? ` ${deficits.length} ${deficits.length === 1 ? "Person" : "Personen"} im Minus (Vorschau).`
            : null}
        </p>
      )}
      {msg ? <p className="mt-3 text-sm text-present">{msg}</p> : null}
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
              <MonthGrid
                month={m}
                groups={groups}
                showGroups={showGroups}
                calendar={data.calendar}
                editing={editing}
                busy={busy}
                pending={pending}
                previews={previews}
                negatives={negatives}
                onToggle={toggleCell}
              />
            </section>
          ))}
        </div>
      ) : null}
      {closed.dialog}
      {negativeOpen ? (
        <NegativeDialog
          deficits={deficits}
          busy={busy}
          onCompensate={() => void doSave(true)}
          onSaveAnyway={() => void doSave(false)}
          onCancel={() => setNegativeOpen(false)}
        />
      ) : null}
      {discardOpen ? (
        <ConfirmDialog
          title="Änderungen verwerfen?"
          body={`${pendingCount} Änderung${pendingCount === 1 ? " wird" : "en werden"} nicht gespeichert.`}
          confirmLabel="Verwerfen"
          danger
          onCancel={() => setDiscardOpen(false)}
          onConfirm={() => {
            setDiscardOpen(false);
            setPending({});
            setEditing(false);
          }}
        />
      ) : null}
    </div>
  );
}
