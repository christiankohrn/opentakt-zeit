import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, type WorkModel } from "../api";
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
  };
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
  };
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
  const visible = models.filter((m) => matchesQuery(query, [m.name, m.kind === "shift" ? "Schicht" : "Gleitzeit"]));

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
    };
  }

  function copyCorridorFromPrevious(key: string) {
    const [previous] = previousWeekday(key);
    setDraft((current) => ({
      ...current,
      corridor: { ...current.corridor, [key]: { ...current.corridor[previous] } },
    }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setNotice("");
    setMsg("");
    setError("");
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
                    {m.kind === "shift" ? "Schicht" : "Gleitzeit"} · Mo–Fr {formatDecimal(m.hours_mon)}/
                    {formatDecimal(m.hours_tue)}/{formatDecimal(m.hours_wed)}/{formatDecimal(m.hours_thu)}/
                    {formatDecimal(m.hours_fri)} · Sa {formatDecimal(m.hours_sat)} · So {formatDecimal(m.hours_sun)}
                  </p>
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
            <legend className="text-sm font-medium">Buchungskorridor</legend>
            <p className="text-xs text-muted">Optional. Kommen vor dem Beginn und Gehen nach dem Ende zählen nur innerhalb des Korridors.</p>
            {WEEKDAYS.map(([key, label]) => {
              const [, previousLabel] = previousWeekday(key);
              return (
                <div key={key} className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="w-28 shrink-0">{label}</span>
                  <input
                    type="time"
                    aria-label={`${label} von`}
                    value={draft.corridor[key].start}
                    onChange={(e) =>
                      setDraft({ ...draft, corridor: { ...draft.corridor, [key]: { ...draft.corridor[key], start: e.target.value } } })
                    }
                    className={`${field} min-w-0 flex-1`}
                  />
                  <input
                    type="time"
                    aria-label={`${label} bis`}
                    value={draft.corridor[key].end}
                    onChange={(e) =>
                      setDraft({ ...draft, corridor: { ...draft.corridor, [key]: { ...draft.corridor[key], end: e.target.value } } })
                    }
                    className={`${field} min-w-0 flex-1`}
                  />
                  <button
                    type="button"
                    className="shrink-0 rounded-lg border border-line px-2 py-1 text-xs"
                    title={`Beginn und Ende von ${previousLabel} übernehmen`}
                    onClick={() => copyCorridorFromPrevious(key)}
                  >
                    wie {previousLabel}
                  </button>
                </div>
              );
            })}
          </fieldset>
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
