import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, type DaySummary, type PunchKind, type User } from "../api";
import UnsavedChangesDialog from "../components/UnsavedChangesDialog";
import { IconTrash } from "../components/Icons";
import { absenceLabel, formatDayTitle, punchLabel, warnLabel } from "../labels";
import { useUnsavedGuard } from "../unsaved";

const KINDS: PunchKind[] = ["in", "out", "break_start", "break_end"];
const ISSUE_KEYS = new Set(["missing_day", "checkout_missing", "break_short", "break_short_9h", "break_long", "over_10h"]);

type Row = { kind: PunchKind; time: string };
type PendingAbsence = "vacation" | "sick" | "clear" | null;

function rowsKey(rows: Row[]) {
  return JSON.stringify(rows.map((r) => ({ kind: r.kind, time: r.time })));
}

function cloneRows(rows: Row[]) {
  return rows.map((r) => ({ ...r }));
}

export default function HrDay() {
  const { id, date } = useParams();
  const [search] = useSearchParams();
  const nav = useNavigate();
  const userId = Number(id);
  const day = date ?? "";
  const from = search.get("from");
  const month = search.get("month") || day.slice(0, 7);
  const backTo = from === "pruefung" ? `/pruefung?month=${month}&user=${userId}` : `/personal/${userId}?month=${month}`;
  const employeeTo =
    from === "pruefung"
      ? `/personal/${userId}?from=pruefung&month=${month}`
      : `/personal/${userId}?month=${month}`;
  const pruefungTo = `/pruefung?month=${month}&user=${userId}`;

  const [user, setUser] = useState<User | null>(null);
  const [summary, setSummary] = useState<DaySummary | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [baselineRows, setBaselineRows] = useState<Row[]>([]);
  const [pendingAbsence, setPendingAbsence] = useState<PendingAbsence>(null);
  const [pendingAccept, setPendingAccept] = useState(false);
  const [reasonOpen, setReasonOpen] = useState(false);
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const punchesDirty = rowsKey(rows) !== rowsKey(baselineRows);
  const dirty = punchesDirty || pendingAbsence !== null || pendingAccept;
  const blocker = useUnsavedGuard(dirty);
  const issues = (summary?.warnings ?? []).filter((w) => ISSUE_KEYS.has(w));

  async function load() {
    const r = await api.userDays(userId, month || day.slice(0, 7));
    setUser(r.user);
    const found = r.days.find((d) => d.date === day) ?? null;
    setSummary(found);
    const next = (found?.punches.filter((p) => !p.voided) ?? []).map((p) => ({
      kind: p.kind as PunchKind,
      time: p.time,
    }));
    setRows(next);
    setBaselineRows(cloneRows(next));
    setPendingAbsence(null);
    setPendingAccept(false);
    setMsg("");
  }

  useEffect(() => {
    if (userId && day) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, day]);

  function discardLocal() {
    setRows(cloneRows(baselineRows));
    setPendingAbsence(null);
    setPendingAccept(false);
    setMsg("");
  }

  function onCancel() {
    if (dirty) {
      discardLocal();
      return;
    }
    nav(backTo);
  }

  function addRow() {
    setRows((cur) => [...cur, { kind: "in", time: "08:00" }]);
  }

  async function applyPending(acceptReason?: string) {
    if (pendingAbsence === "clear") {
      await api.deleteAbsence(userId, day);
    } else if (pendingAbsence === "vacation" || pendingAbsence === "sick") {
      await api.createAbsences(userId, { kind: pendingAbsence, start: day, end: day });
    }
    if (pendingAccept && acceptReason) {
      await api.acceptDay(userId, day, acceptReason);
    }
  }

  function onSaveClick() {
    if (punchesDirty) {
      setReasonOpen(true);
      return;
    }
    if (pendingAccept) {
      setAcceptOpen(true);
      return;
    }
    void saveWithoutPunchReason();
  }

  async function saveWithoutPunchReason() {
    setBusy(true);
    setMsg("");
    try {
      await applyPending();
      await load();
      setMsg("Gespeichert.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Speichern fehlgeschlagen");
    } finally {
      setBusy(false);
    }
  }

  async function savePunches(e: FormEvent) {
    e.preventDefault();
    if (!reason.trim() || reason.trim().length < 3) return;
    setBusy(true);
    setMsg("");
    try {
      await api.replaceDay(userId, day, {
        reason: reason.trim(),
        punches: rows.map((r) => ({ kind: r.kind, time: r.time })),
      });
      await applyPending(pendingAccept ? reason.trim() : undefined);
      setReasonOpen(false);
      setReason("");
      await load();
      setMsg("Korrektur gespeichert und protokolliert.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Speichern fehlgeschlagen");
    } finally {
      setBusy(false);
    }
  }

  async function saveAccept(e: FormEvent) {
    e.preventDefault();
    if (!reason.trim() || reason.trim().length < 3) return;
    setBusy(true);
    setMsg("");
    try {
      await applyPending(reason.trim());
      setAcceptOpen(false);
      setReason("");
      await load();
      setMsg("Tag als akzeptiert markiert. Er erscheint nicht mehr in der Prüfung.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Akzeptieren fehlgeschlagen");
    } finally {
      setBusy(false);
    }
  }

  const pendingNotes: string[] = [];
  if (pendingAbsence === "vacation") pendingNotes.push("Wird als Urlaub gespeichert.");
  if (pendingAbsence === "sick") pendingNotes.push("Wird als Krankheitstag gespeichert.");
  if (pendingAbsence === "clear") pendingNotes.push("Abwesenheit wird entfernt.");
  if (pendingAccept) pendingNotes.push("Wird als akzeptiert gespeichert.");

  const title = day ? formatDayTitle(day) : "";
  const backLabel = from === "pruefung" ? "Prüfung" : (user?.display_name ?? "Personal");

  return (
    <div className="pt-2">
      <Link to={backTo} className="text-sm text-muted">
        ← {backLabel}
      </Link>
      <p className="mt-1 text-sm">
        {from === "pruefung" ? (
          <Link to={employeeTo} className="text-present">
            Zum Mitarbeiter
          </Link>
        ) : (
          <Link to={pruefungTo} className="text-present">
            Zur Prüfung
          </Link>
        )}
      </p>
      <h1 className="mt-2 text-xl font-medium">{title}</h1>
      <p className="mt-1 text-sm text-muted">
        Zeiten ändern, dann speichern. Der Originalstand bleibt im Protokoll. Nachtschicht: Gehen am Folgetag eintragen.
      </p>
      {summary?.calendar ? (
        <div
          className={`mt-3 rounded-2xl border px-4 py-3 ${
            summary.calendar.kind === "company_off" ? "border-off/35 bg-off/15" : "border-holiday/35 bg-holiday/15"
          }`}
        >
          <p className="text-sm font-medium">
            {summary.calendar.kind === "company_off" ? "Betriebsfrei" : "Feiertag"}
          </p>
          <p className="mt-0.5 text-xs text-muted">
            {summary.calendar.name}
            {summary.calendar.source === "law" ? " · gesetzlich" : " · Kalender"}
          </p>
        </div>
      ) : null}
      {summary?.absence && pendingAbsence !== "clear" ? (
        <p className="mt-2 text-sm text-present">
          {absenceLabel(summary.absence.kind)}
          {summary.absence.note ? ` · ${summary.absence.note}` : ""}
        </p>
      ) : null}
      {summary?.auto_break_minutes ? (
        <p className="mt-2 text-sm text-muted">Pause automatisch {summary.auto_break_minutes} Min. abgezogen.</p>
      ) : null}
      {issues.length ? (
        <p className="mt-2 text-sm text-danger">{issues.map(warnLabel).join(" · ")}</p>
      ) : null}
      {summary?.accepted && !pendingAccept ? (
        <p className="mt-2 text-sm text-present">Akzeptiert: {summary.accepted.reason}</p>
      ) : null}
      {pendingNotes.length ? (
        <p className="mt-3 rounded-2xl border border-present/30 bg-present/10 px-4 py-3 text-sm text-present">
          {pendingNotes.join(" ")} Noch nicht gespeichert.
        </p>
      ) : null}
      <div className="mt-4 space-y-2 md:grid md:grid-cols-2 md:gap-2 md:space-y-0">
        {rows.map((row, i) => (
          <div key={i} className="flex gap-2 rounded-2xl border border-line bg-card p-3">
            <select
              className="flex-1 rounded-lg border border-line bg-bg px-2 py-2 text-sm"
              value={row.kind}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, kind: e.target.value as PunchKind };
                setRows(next);
              }}
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {punchLabel(k)}
                </option>
              ))}
            </select>
            <input
              type="time"
              required
              className="w-28 rounded-lg border border-line bg-bg px-2 py-2 text-sm"
              value={row.time}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...row, time: e.target.value };
                setRows(next);
              }}
            />
            <button
              type="button"
              className="rounded-lg p-2 text-danger"
              title="Löschen"
              aria-label="Löschen"
              onClick={() => setRows(rows.filter((_, j) => j !== i))}
            >
              <IconTrash className="h-5 w-5" />
            </button>
          </div>
        ))}
      </div>
      <button type="button" onClick={addRow} className="mt-3 text-sm text-present">
        + Buchung hinzufügen
      </button>
      <div className="mt-4 flex flex-wrap gap-2 text-sm">
        {summary?.absence && pendingAbsence !== "clear" ? (
          <button type="button" className="text-danger" onClick={() => setPendingAbsence("clear")} disabled={busy}>
            Abwesenheit entfernen
          </button>
        ) : (
          <>
            <button type="button" className="text-present" onClick={() => setPendingAbsence("vacation")}>
              Als Urlaub
            </button>
            <button type="button" className="text-present" onClick={() => setPendingAbsence("sick")}>
              Als Krankheit
            </button>
          </>
        )}
        {pendingAbsence ? (
          <button type="button" className="text-muted" onClick={() => setPendingAbsence(null)}>
            Abwesenheitsänderung zurücknehmen
          </button>
        ) : null}
        {issues.length && !summary?.accepted && !pendingAccept ? (
          <button type="button" className="text-present" onClick={() => setPendingAccept(true)}>
            Trotzdem akzeptieren
          </button>
        ) : null}
        {pendingAccept ? (
          <button type="button" className="text-muted" onClick={() => setPendingAccept(false)}>
            Akzeptieren zurücknehmen
          </button>
        ) : null}
        {summary?.accepted ? (
          <button
            type="button"
            className="text-muted"
            onClick={() => void api.revokeAccept(userId, day).then(() => load())}
          >
            Akzeptierung zurücknehmen
          </button>
        ) : null}
      </div>
      {summary?.punches.some((p) => p.voided) ? (
        <div className="mt-6">
          <p className="text-xs uppercase tracking-wider text-muted">Stornierte Originale</p>
          <ul className="mt-2 space-y-1 text-sm text-muted">
            {summary.punches
              .filter((p) => p.voided)
              .map((p) => (
                <li key={p.id}>
                  {punchLabel(p.kind)} {p.time}
                </li>
              ))}
          </ul>
        </div>
      ) : null}
      {msg ? <p className="mt-4 text-sm text-present">{msg}</p> : null}
      <div className="mt-6 flex gap-2">
        <button type="button" onClick={onCancel} className="flex-1 rounded-xl border border-line py-3 font-medium">
          Abbrechen
        </button>
        <button
          type="button"
          onClick={onSaveClick}
          disabled={!dirty || busy}
          className="flex-1 rounded-xl bg-navy py-3 font-medium text-white disabled:opacity-40"
        >
          Speichern
        </button>
      </div>
      {reasonOpen ? (
        <div className="fixed inset-0 z-20 flex items-end justify-center bg-black/40 p-4 sm:items-center">
          <form onSubmit={savePunches} className="w-full max-w-lg rounded-2xl bg-card p-5 shadow-xl">
            <p className="text-lg font-medium">Korrekturgrund</p>
            <p className="mt-1 text-sm text-muted">Wird unveränderlich im Audit gespeichert.</p>
            <textarea
              required
              minLength={3}
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="mt-3 w-full rounded-xl border border-line bg-bg px-3 py-2"
              placeholder="z. B. vergessen auszustempeln, mit Mitarbeiter abgestimmt"
            />
            <div className="mt-4 flex gap-2">
              <button type="button" className="flex-1 rounded-xl border border-line py-2" onClick={() => setReasonOpen(false)}>
                Zurück
              </button>
              <button type="submit" disabled={busy} className="flex-1 rounded-xl bg-present py-2 text-white">
                {busy ? "…" : "Übernehmen"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
      {acceptOpen ? (
        <div className="fixed inset-0 z-20 flex items-end justify-center bg-black/40 p-4 sm:items-center">
          <form onSubmit={saveAccept} className="w-full max-w-lg rounded-2xl bg-card p-5 shadow-xl">
            <p className="text-lg font-medium">Unplausibel akzeptieren?</p>
            <p className="mt-1 text-sm text-muted">
              Die Hinweise bleiben sichtbar, der Tag erscheint aber nicht mehr in der Prüfung.
            </p>
            <textarea
              required
              minLength={3}
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="mt-3 w-full rounded-xl border border-line bg-bg px-3 py-2"
              placeholder="z. B. mit Mitarbeiter geklärt, Ausnahme genehmigt"
            />
            <div className="mt-4 flex gap-2">
              <button type="button" className="flex-1 rounded-xl border border-line py-2" onClick={() => setAcceptOpen(false)}>
                Zurück
              </button>
              <button type="submit" disabled={busy} className="flex-1 rounded-xl bg-navy py-2 text-white">
                {busy ? "…" : "Ja, akzeptieren"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
      {blocker.state === "blocked" ? (
        <UnsavedChangesDialog onStay={() => blocker.reset()} onDiscard={() => blocker.proceed()} />
      ) : null}
    </div>
  );
}
