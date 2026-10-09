import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, type ShiftCorridor, type WorkModel } from "../api";
import { useAuth } from "../auth";
import LoadingNote from "../components/LoadingNote";
import SearchField, { matchesQuery } from "../components/SearchField";
import { formatDecimal } from "../labels";

const WEEKDAYS: [string, string][] = [
  ["mon", "Montag"],
  ["tue", "Dienstag"],
  ["wed", "Mittwoch"],
  ["thu", "Donnerstag"],
  ["fri", "Freitag"],
  ["sat", "Samstag"],
  ["sun", "Sonntag"],
];

const CLOSED_HINT =
  "Abgeschlossene Monate behalten die bisherige Berechnung. Die Änderung gilt nur für offene Monate.";

type Corridor = Record<string, { start: string; end: string }>;

type ShiftDraft = { name: string; days: Corridor };

type BreakDraft = { after: string; minutes: string };

const SHIFT_NAMES = ["Früh", "Spät", "Nacht", "Schicht 4"];

const DEFAULT_BREAKS: BreakDraft[] = [
  { after: "6:00", minutes: "30" },
  { after: "9:00", minutes: "45" },
];

type Draft = {
  name: string;
  kind: string;
  hours: string;
  round_start_before: string;
  round_start_after: string;
  round_end_before: string;
  round_end_after: string;
  round_first_threshold: string;
  round_first_step: string;
  round_last_threshold: string;
  round_last_step: string;
  corridor: Corridor;
  shifts: ShiftDraft[];
  breaks: BreakDraft[];
  breakMode: "threshold" | "fixed";
  fixedBreaks: Corridor;
};

function emptyCorridor(): Corridor {
  return Object.fromEntries(WEEKDAYS.map(([key]) => [key, { start: "", end: "" }]));
}

function blankDraft(): Draft {
  return {
    name: "",
    kind: "flextime",
    hours: "8,8,8,8,8,0,0",
    round_start_before: "0",
    round_start_after: "0",
    round_end_before: "0",
    round_end_after: "0",
    round_first_threshold: "0",
    round_first_step: "0",
    round_last_threshold: "0",
    round_last_step: "0",
    corridor: emptyCorridor(),
    shifts: [],
    breaks: DEFAULT_BREAKS.map((row) => ({ ...row })),
    breakMode: "threshold",
    fixedBreaks: emptyCorridor(),
  };
}

function formatAfter(hours: number) {
  const total = Math.round(hours * 60);
  const whole = Math.floor(total / 60);
  const mins = total % 60;
  return `${whole}:${String(mins).padStart(2, "0")}`;
}

function parseAfter(value: string) {
  const text = value.trim();
  const clock = text.match(/^(\d{1,2}):(\d{2})$/);
  if (clock) {
    const hour = Number(clock[1]);
    const minute = Number(clock[2]);
    if (hour > 24 || minute > 59 || (hour === 24 && minute > 0)) return Number.NaN;
    return hour + minute / 60;
  }
  return Number(text.replace(",", "."));
}

function resizeShifts(existing: ShiftDraft[], count: number): ShiftDraft[] {
  return Array.from(
    { length: count },
    (_, index) => existing[index] ?? { name: SHIFT_NAMES[index] ?? `Schicht ${index + 1}`, days: emptyCorridor() },
  );
}

function shiftDays(slot: ShiftCorridor): Corridor {
  const days = emptyCorridor();
  for (const [key] of WEEKDAYS) {
    const cell = slot.days?.[key];
    if (cell?.start || cell?.end) days[key] = { start: cell.start || "", end: cell.end || "" };
    else if (!slot.days && (slot.start || slot.end)) days[key] = { start: slot.start || "", end: slot.end || "" };
  }
  return days;
}

function draftFrom(model: WorkModel): Draft {
  const corridor = emptyCorridor();
  for (const [key] of WEEKDAYS) {
    const slot = model.booking_corridor?.[key];
    corridor[key] = { start: slot?.start || "", end: slot?.end || "" };
  }
  return {
    name: model.name,
    kind: model.kind,
    hours: [model.hours_mon, model.hours_tue, model.hours_wed, model.hours_thu, model.hours_fri, model.hours_sat, model.hours_sun].join(","),
    round_start_before: String(model.round_start_before ?? 0),
    round_start_after: String(model.round_start_after ?? 0),
    round_end_before: String(model.round_end_before ?? 0),
    round_end_after: String(model.round_end_after ?? 0),
    round_first_threshold: String(model.round_first_threshold ?? 0),
    round_first_step: String(model.round_first_step ?? 0),
    round_last_threshold: String(model.round_last_threshold ?? 0),
    round_last_step: String(model.round_last_step ?? 0),
    corridor,
    shifts: (model.shifts ?? []).map((slot: ShiftCorridor, index) => ({
      name: slot.name || SHIFT_NAMES[index] || `Schicht ${index + 1}`,
      days: shiftDays(slot),
    })),
    breaks: (model.break_rules ?? []).map((rule) => ({
      after: formatAfter(rule.after_hours),
      minutes: String(rule.minutes),
    })),
    breakMode: model.break_mode === "fixed" ? "fixed" : "threshold",
    fixedBreaks: Object.fromEntries(
      WEEKDAYS.map(([key]) => {
        const slot = model.fixed_breaks?.[key];
        return [key, { start: slot?.start || "", end: slot?.end || "" }];
      }),
    ),
  };
}

function pauseSummary(model: WorkModel) {
  if (model.break_mode === "fixed") {
    const slots = WEEKDAYS.flatMap(([key, label]) => {
      const slot = model.fixed_breaks?.[key];
      return slot?.start && slot.end ? [`${label.slice(0, 2)} ${slot.start}–${slot.end}`] : [];
    });
    return slots.length ? `fest ${slots.join(", ")}` : "feste Pausenzeiten";
  }
  const rules = model.break_rules;
  if (!rules?.length) return "keine Mindestpause";
  return rules.map((rule) => `${rule.minutes} Min. ab ${formatAfter(rule.after_hours)}`).join(", ");
}

function minutes(value: string) {
  const parsed = Number(value.trim().replace(",", "."));
  return Number.isFinite(parsed) ? Math.max(0, Math.round(parsed)) : 0;
}

function previousWeekday(key: string): [string, string] {
  const index = WEEKDAYS.findIndex(([day]) => day === key);
  return WEEKDAYS[(index + WEEKDAYS.length - 1) % WEEKDAYS.length];
}

export default function HrModels() {
  const { user: me } = useAuth();
  const canManage = me?.role === "hr" || me?.role === "admin";
  const [models, setModels] = useState<WorkModel[]>([]);
  const [draft, setDraft] = useState<Draft>(blankDraft);
  const [editing, setEditing] = useState<WorkModel | null>(null);
  const [notice, setNotice] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const visible = models.filter((m) =>
    matchesQuery(query, [m.name, m.kind === "shift" ? "Schicht" : "Gleitzeit", ...(m.shifts ?? []).map((slot) => slot.name)]),
  );

  async function load() {
    setModels(await api.models());
  }

  useEffect(() => {
    void load().finally(() => setLoading(false));
  }, []);

  function payload() {
    const parts = draft.hours.split(",").map((x) => Number(x.trim().replace(",", ".")));
    const [mo, di, mi, don, fr, sa, so] = [...parts, 0, 0, 0, 0, 0, 0, 0];
    const booking_corridor: Record<string, { start: string; end: string }> = {};
    for (const [key] of WEEKDAYS) {
      const slot = draft.corridor[key];
      if (slot.start || slot.end) booking_corridor[key] = { start: slot.start, end: slot.end };
    }
    return {
      name: draft.name,
      kind: draft.kind,
      hours_mon: mo,
      hours_tue: di,
      hours_wed: mi,
      hours_thu: don,
      hours_fri: fr,
      hours_sat: sa,
      hours_sun: so,
      round_start_before: minutes(draft.round_start_before),
      round_start_after: minutes(draft.round_start_after),
      round_end_before: minutes(draft.round_end_before),
      round_end_after: minutes(draft.round_end_after),
      round_first_threshold: minutes(draft.round_first_threshold),
      round_first_step: minutes(draft.round_first_step),
      round_last_threshold: minutes(draft.round_last_threshold),
      round_last_step: minutes(draft.round_last_step),
      booking_corridor,
      shifts:
        draft.kind === "shift"
          ? draft.shifts.map((slot, index) => {
              const days: Record<string, { start: string; end: string }> = {};
              for (const [key] of WEEKDAYS) {
                const cell = slot.days[key];
                if (cell.start || cell.end) days[key] = { start: cell.start, end: cell.end };
              }
              return {
                name: slot.name.trim() || SHIFT_NAMES[index] || `Schicht ${index + 1}`,
                days,
              };
            })
          : [],
      break_rules: draft.breaks.map((row) => ({
        after_hours: parseAfter(row.after),
        minutes: minutes(row.minutes),
      })),
      break_mode: draft.breakMode,
      fixed_breaks: Object.fromEntries(
        WEEKDAYS.flatMap(([key]) => {
          const slot = draft.fixedBreaks[key];
          return slot.start || slot.end ? [[key, { start: slot.start, end: slot.end }]] : [];
        }),
      ),
    };
  }

  function copyCorridorFromPrevious(key: string) {
    const [previous] = previousWeekday(key);
    setDraft((current) => ({
      ...current,
      corridor: { ...current.corridor, [key]: { ...current.corridor[previous] } },
    }));
  }

  function copyShiftDay(index: number, key: string) {
    const [previous] = previousWeekday(key);
    setDraft((current) => ({
      ...current,
      shifts: current.shifts.map((item, itemIndex) =>
        itemIndex === index ? { ...item, days: { ...item.days, [key]: { ...item.days[previous] } } } : item,
      ),
    }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setNotice("");
    setMsg("");
    setError("");
    if (
      draft.kind === "shift" &&
      draft.shifts.some((slot) => WEEKDAYS.some(([key]) => Boolean(slot.days[key].start) !== Boolean(slot.days[key].end)))
    ) {
      setError("Jeder angegebene Korridor braucht Beginn und Ende.");
      return;
    }
    if (
      draft.breakMode === "threshold" &&
      draft.breaks.some((row) => {
        const after = parseAfter(row.after);
        return !row.after.trim() || !row.minutes.trim() || minutes(row.minutes) < 1 || !Number.isFinite(after) || after < 0 || after > 24;
      })
    ) {
      setError("Jede Pausenschwelle braucht eine Zeit wie 9:45 und die Minuten der Pause.");
      return;
    }
    if (
      draft.breakMode === "fixed" &&
      WEEKDAYS.some(([key]) => Boolean(draft.fixedBreaks[key].start) !== Boolean(draft.fixedBreaks[key].end))
    ) {
      setError("Jede hinterlegte Pause braucht Beginn und Ende.");
      return;
    }
    setBusy(true);
    try {
      const body = payload();
      const saved = editing ? await api.updateModel(editing.id, body) : await api.createModel(body);
      setNotice(saved.notice || "");
      setMsg("Gespeichert.");
      if (editing) setEditing(saved);
      else setDraft(blankDraft());
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Speichern fehlgeschlagen");
    } finally {
      setBusy(false);
    }
  }

  const field = "w-full rounded-lg border border-line bg-bg px-3 py-2";
  const hint = editing && editing.closed_months > 0 ? notice || CLOSED_HINT : notice;

  return (
    <div className="pt-2">
      <Link to="/personal" className="text-sm text-muted">
        ← Personal
      </Link>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-medium">Arbeitszeitmodelle</h1>
        <SearchField value={query} onChange={setQuery} placeholder="Modell suchen" />
      </div>
      {loading ? <LoadingNote /> : null}
      {!loading && visible.length === 0 ? (
        <p className="mt-8 text-sm text-muted">{query.trim() ? "Kein Modell in dieser Auswahl." : "Noch kein Modell."}</p>
      ) : null}
      {!loading && visible.length > 0 ? (
        <ul className="mt-4 grid gap-2 md:grid-cols-2">
          {visible.map((m) => (
            <li key={m.id} className="rounded-2xl border border-line bg-card px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{m.name}</p>
                  <p className="text-xs text-muted">
                    {m.kind === "shift"
                      ? m.shifts?.length
                        ? `${m.shifts.length} ${m.shifts.length === 1 ? "Schicht" : "Schichten"}`
                        : "Schicht"
                      : "Gleitzeit"}{" "}
                    · Mo–Fr {formatDecimal(m.hours_mon)}/
                    {formatDecimal(m.hours_tue)}/{formatDecimal(m.hours_wed)}/{formatDecimal(m.hours_thu)}/
                    {formatDecimal(m.hours_fri)} · Sa {formatDecimal(m.hours_sat)} · So {formatDecimal(m.hours_sun)}
                  </p>
                  <p className="text-xs text-muted">Pause {pauseSummary(m)}</p>
                </div>
                {canManage ? (
                  <button
                    type="button"
                    className="shrink-0 text-sm text-muted"
                    onClick={() => {
                      setEditing(m);
                      setDraft(draftFrom(m));
                      setNotice(m.closed_months > 0 ? CLOSED_HINT : "");
                      setMsg("");
                      setError("");
                    }}
                  >
                    Anpassen
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {canManage ? (
        <form onSubmit={onSubmit} className="mt-6 space-y-4 rounded-2xl border border-line bg-card p-4">
          <p className="font-medium">{editing ? `${editing.name} anpassen` : "Modell anlegen"}</p>
          {hint ? <p className="text-sm text-muted">{hint}</p> : null}
          <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Name" className={field} required />
          <select className={field} value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value })}>
            <option value="flextime">Gleitzeit</option>
            <option value="shift">Schicht</option>
          </select>
          <label className="block text-sm">
            Stunden Mo–So
            <input value={draft.hours} onChange={(e) => setDraft({ ...draft, hours: e.target.value })} placeholder="8,8,8,8,8,0,0" className={`${field} mt-1`} />
          </label>
          <fieldset className="space-y-3">
            <legend className="text-sm font-medium">Rundung</legend>
            <p className="text-xs text-muted">
              0 lässt die jeweilige Rundung aus. Die Stempel bleiben sichtbar, nur die angerechnete Zeit ändert sich.
              Die eingetragene Minute rundet noch ab, einschließlich der Sekunden. Erst die nächste volle Minute rundet auf.
            </p>
            <RoundRow
              label="Für Buchungen, die"
              mid="Min. vor oder"
              tail="Min. nach Arbeitsbeginn getätigt werden, gilt der Arbeitsbeginn"
              before={draft.round_start_before}
              after={draft.round_start_after}
              onBefore={(value) => setDraft({ ...draft, round_start_before: value })}
              onAfter={(value) => setDraft({ ...draft, round_start_after: value })}
            />
            <RoundRow
              label="Für Buchungen, die"
              mid="Min. vor oder"
              tail="Min. nach Arbeitsende getätigt werden, gilt das Arbeitsende"
              before={draft.round_end_before}
              after={draft.round_end_after}
              onBefore={(value) => setDraft({ ...draft, round_end_before: value })}
              onAfter={(value) => setDraft({ ...draft, round_end_after: value })}
            />
            <RoundRow
              label="Erste Buchung wird ab"
              mid="Min. auf"
              tail="Min. auf-, sonst abgerundet"
              before={draft.round_first_threshold}
              after={draft.round_first_step}
              onBefore={(value) => setDraft({ ...draft, round_first_threshold: value })}
              onAfter={(value) => setDraft({ ...draft, round_first_step: value })}
            />
            <RoundRow
              label="Letzte Buchung wird ab"
              mid="Min. auf"
              tail="Min. auf-, sonst abgerundet"
              before={draft.round_last_threshold}
              after={draft.round_last_step}
              onBefore={(value) => setDraft({ ...draft, round_last_threshold: value })}
              onAfter={(value) => setDraft({ ...draft, round_last_step: value })}
            />
          </fieldset>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Pausen</legend>
            <label className="block text-sm">
              Regel
              <select
                className={`${field} mt-1`}
                value={draft.breakMode}
                onChange={(e) => setDraft({ ...draft, breakMode: e.target.value === "fixed" ? "fixed" : "threshold" })}
              >
                <option value="threshold">Automatisch ab Schwelle</option>
                <option value="fixed">Feste Pausenzeiten</option>
              </select>
            </label>
            {draft.breakMode === "threshold" ? (
              <p className="text-xs text-muted">
                Mindestpause ab einer Arbeitszeit. Die Zeit steht als Stunden:Minuten, zum Beispiel 9:45. Gestempelte Minuten zählen darauf an. Voreinstellung: 30 Minuten ab 6:00 und 45 Minuten ab 9:00.
              </p>
            ) : (
              <p className="text-xs text-muted">
                Es gilt die hier hinterlegte Uhrzeit. Wer in diesem Fenster arbeitet, verliert diese Minuten. Eine gestempelte Pause daneben bleibt zusätzlich stehen.
              </p>
            )}
            {draft.breakMode === "fixed"
              ? WEEKDAYS.map(([key, label]) => (
                  <div key={key} className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="w-24">{label}</span>
                    <input
                      type="time"
                      aria-label={`${label} Pause von`}
                      value={draft.fixedBreaks[key].start}
                      onChange={(e) => {
                        const value = e.target.value;
                        setDraft((current) => ({
                          ...current,
                          fixedBreaks: { ...current.fixedBreaks, [key]: { ...current.fixedBreaks[key], start: value } },
                        }));
                      }}
                      className="rounded-lg border border-line bg-bg px-2 py-1"
                    />
                    <span>bis</span>
                    <input
                      type="time"
                      aria-label={`${label} Pause bis`}
                      value={draft.fixedBreaks[key].end}
                      onChange={(e) => {
                        const value = e.target.value;
                        setDraft((current) => ({
                          ...current,
                          fixedBreaks: { ...current.fixedBreaks, [key]: { ...current.fixedBreaks[key], end: value } },
                        }));
                      }}
                      className="rounded-lg border border-line bg-bg px-2 py-1"
                    />
                  </div>
                ))
              : null}
            {draft.breakMode === "threshold" ? draft.breaks.map((row, index) => (
              <div key={index} className="flex flex-wrap items-center gap-2 text-sm">
                <span>ab</span>
                <input
                  aria-label={`Pause ${index + 1} ab`}
                  value={row.after}
                  placeholder="9:45"
                  inputMode="text"
                  onChange={(e) => {
                    const value = e.target.value;
                    setDraft((current) => ({
                      ...current,
                      breaks: current.breaks.map((item, itemIndex) => (itemIndex === index ? { ...item, after: value } : item)),
                    }));
                  }}
                  className="w-20 rounded-lg border border-line bg-bg px-2 py-1"
                />
                <input
                  aria-label={`Pause ${index + 1} Minuten`}
                  value={row.minutes}
                  inputMode="numeric"
                  onChange={(e) => {
                    const value = e.target.value;
                    setDraft((current) => ({
                      ...current,
                      breaks: current.breaks.map((item, itemIndex) => (itemIndex === index ? { ...item, minutes: value } : item)),
                    }));
                  }}
                  className="w-20 rounded-lg border border-line bg-bg px-2 py-1"
                />
                <span>Minuten</span>
                <button
                  type="button"
                  className="rounded-lg border border-line px-2 py-1 text-xs"
                  onClick={() =>
                    setDraft((current) => ({ ...current, breaks: current.breaks.filter((_, itemIndex) => itemIndex !== index) }))
                  }
                >
                  Entfernen
                </button>
              </div>
            )) : null}
            {draft.breakMode === "threshold" && draft.breaks.length < 4 ? (
              <button
                type="button"
                className="rounded-lg border border-line px-3 py-1.5 text-sm"
                onClick={() => setDraft((current) => ({ ...current, breaks: [...current.breaks, { after: "", minutes: "" }] }))}
              >
                Schwelle hinzufügen
              </button>
            ) : null}
          </fieldset>
          {draft.kind === "shift" ? (
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Schichten</legend>
              <p className="text-xs text-muted">
                Je Schicht und Wochentag. Die erste Kommen-Zeit wählt unter den Schichten dieses Tages die mit dem nächsten Beginn. Kommen vor diesem Beginn und Gehen nach diesem Ende zählen nicht. Tage ohne Angabe zählen alle Buchungen. Liegt das Ende vor dem Beginn, läuft die Schicht über Mitternacht.
              </p>
              <label className="block text-sm">
                Anzahl
                <select
                  className={`${field} mt-1`}
                  value={draft.shifts.length}
                  onChange={(e) => setDraft({ ...draft, shifts: resizeShifts(draft.shifts, Number(e.target.value)) })}
                >
                  <option value={0}>Keine automatische Erkennung</option>
                  <option value={1}>1 Schicht</option>
                  <option value={2}>2 Schichten</option>
                  <option value={3}>3 Schichten</option>
                </select>
              </label>
              {draft.shifts.map((slot, index) => (
                <div key={index} className="w-fit max-w-full space-y-2 rounded-xl border border-line p-3">
                  <input
                    aria-label={`Schicht ${index + 1} Name`}
                    value={slot.name}
                    onChange={(e) => {
                      const value = e.target.value;
                      setDraft((current) => ({
                        ...current,
                        shifts: current.shifts.map((item, itemIndex) => (itemIndex === index ? { ...item, name: value } : item)),
                      }));
                    }}
                    className="w-40 rounded-lg border border-line bg-bg px-2 py-1 text-sm"
                  />
                  {WEEKDAYS.map(([key, label]) => {
                    const [, previousLabel] = previousWeekday(key);
                    return (
                      <CorridorDayRow
                        key={key}
                        label={label}
                        previousLabel={previousLabel}
                        start={slot.days[key].start}
                        end={slot.days[key].end}
                        startLabel={`${slot.name || "Schicht"} ${label} von`}
                        endLabel={`${slot.name || "Schicht"} ${label} bis`}
                        onStart={(value) =>
                          setDraft((current) => ({
                            ...current,
                            shifts: current.shifts.map((item, itemIndex) =>
                              itemIndex === index
                                ? { ...item, days: { ...item.days, [key]: { ...item.days[key], start: value } } }
                                : item,
                            ),
                          }))
                        }
                        onEnd={(value) =>
                          setDraft((current) => ({
                            ...current,
                            shifts: current.shifts.map((item, itemIndex) =>
                              itemIndex === index
                                ? { ...item, days: { ...item.days, [key]: { ...item.days[key], end: value } } }
                                : item,
                            ),
                          }))
                        }
                        onCopy={() => copyShiftDay(index, key)}
                      />
                    );
                  })}
                </div>
              ))}
            </fieldset>
          ) : null}
          {draft.kind !== "shift" || draft.shifts.length === 0 ? (
          <fieldset className="w-fit max-w-full space-y-2">
            <legend className="text-sm font-medium">Buchungskorridor</legend>
            <p className="text-xs text-muted">Optional. Kommen vor dem Beginn und Gehen nach dem Ende zählen nur innerhalb des Korridors.</p>
            {WEEKDAYS.map(([key, label]) => {
              const [, previousLabel] = previousWeekday(key);
              return (
                <CorridorDayRow
                  key={key}
                  label={label}
                  previousLabel={previousLabel}
                  start={draft.corridor[key].start}
                  end={draft.corridor[key].end}
                  startLabel={`${label} von`}
                  endLabel={`${label} bis`}
                  onStart={(value) =>
                    setDraft({ ...draft, corridor: { ...draft.corridor, [key]: { ...draft.corridor[key], start: value } } })
                  }
                  onEnd={(value) =>
                    setDraft({ ...draft, corridor: { ...draft.corridor, [key]: { ...draft.corridor[key], end: value } } })
                  }
                  onCopy={() => copyCorridorFromPrevious(key)}
                />
              );
            })}
          </fieldset>
          ) : null}
          {msg ? <p className="text-sm text-present">{msg}</p> : null}
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          <div className="flex gap-2">
            <button type="submit" disabled={busy} className="flex-1 rounded-xl bg-present py-2 text-white disabled:opacity-60">
              {busy ? "Speichern …" : editing ? "Speichern" : "Modell anlegen"}
            </button>
            {editing ? (
              <button
                type="button"
                className="rounded-xl border border-line px-4 py-2 text-sm"
                onClick={() => {
                  setEditing(null);
                  setDraft(blankDraft());
                  setNotice("");
                  setMsg("");
                  setError("");
                }}
              >
                Neu
              </button>
            ) : null}
          </div>
        </form>
      ) : null}
    </div>
  );
}

function CorridorDayRow({
  label,
  previousLabel,
  start,
  end,
  startLabel,
  endLabel,
  onStart,
  onEnd,
  onCopy,
}: {
  label: string;
  previousLabel: string;
  start: string;
  end: string;
  startLabel: string;
  endLabel: string;
  onStart: (value: string) => void;
  onEnd: (value: string) => void;
  onCopy: () => void;
}) {
  const time = "w-full min-w-0 rounded-lg border border-line bg-bg px-2 py-1.5";
  return (
    <div className="grid grid-cols-[5.5rem_minmax(0,1fr)_minmax(0,1fr)] items-center gap-2 text-sm sm:grid-cols-[7rem_9.5rem_9.5rem_8.75rem] sm:justify-start">
      <span>{label}</span>
      <input type="time" aria-label={startLabel} value={start} onChange={(e) => onStart(e.target.value)} className={time} />
      <input type="time" aria-label={endLabel} value={end} onChange={(e) => onEnd(e.target.value)} className={time} />
      <button
        type="button"
        className="col-span-3 h-9 rounded-lg border border-line px-2 text-xs sm:col-span-1"
        title={`Beginn und Ende von ${previousLabel} übernehmen`}
        onClick={onCopy}
      >
        wie {previousLabel}
      </button>
    </div>
  );
}

function RoundRow({
  label,
  mid,
  tail,
  before,
  after,
  onBefore,
  onAfter,
}: {
  label: string;
  mid: string;
  tail: string;
  before: string;
  after: string;
  onBefore: (value: string) => void;
  onAfter: (value: string) => void;
}) {
  const box = "w-20 rounded-lg border border-line bg-bg px-2 py-1";
  return (
    <label className="flex flex-wrap items-center gap-2 text-sm">
      <span>{label}</span>
      <input value={before} onChange={(e) => onBefore(e.target.value)} inputMode="numeric" className={box} />
      <span>{mid}</span>
      <input value={after} onChange={(e) => onAfter(e.target.value)} inputMode="numeric" className={box} />
      <span>{tail}</span>
    </label>
  );
}
