import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type JournalAccounts, type JournalReport, type JournalWages, type User } from "../api";
import PersonFilter from "../components/PersonFilter";
import InactiveToggle from "../components/InactiveToggle";
import LoadingNote from "../components/LoadingNote";
import ReportToolbar, { ExportButtons } from "../components/ReportToolbar";
import { formatHours, signedHours } from "../labels";
import { effectiveUserIds, monthLabel, parseUserIds, rememberMonth, sessionMonth, visibleUsers } from "../reportPeriod";

function formatDays(value: number | null | undefined, signed = false) {
  if (value === null || value === undefined) return "—";
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${String(value).replace(".", ",")}`;
}

function hm(value: number | null | undefined) {
  if (value === null || value === undefined) return "";
  return formatHours(value);
}

function wageCell(value: number | null | undefined) {
  if (!value) return "";
  return formatHours(value);
}

function WageFooter({ wages }: { wages: JournalWages }) {
  const lines = [
    ["1  20–24 Uhr", wages.hours_20_24],
    ["2  0–4 Uhr", wages.hours_0_4],
    ["3  4–6 Uhr", wages.hours_4_6],
    ["Summe 1 und 3", wages.hours_1_plus_3],
  ] as const;
  return (
    <div className="overflow-x-auto rounded-xl border border-line print:border-0">
      <table className="w-max text-left text-xs">
        <thead className="bg-card text-muted">
          <tr>
            <th className="px-2 py-1.5 font-medium">Lohnart</th>
            <th className="px-2 py-1.5 text-right font-medium">Stunden</th>
          </tr>
        </thead>
        <tbody>
          {lines.map(([label, value], index) => (
            <tr key={label} className={`border-t border-line bg-card ${index === lines.length - 1 ? "font-semibold" : ""}`}>
              <td className="px-2 py-1">{label}</td>
              <td className="px-2 py-1 text-right tabular-nums">{formatHours(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AccountFooter({ accounts }: { accounts: JournalAccounts }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line print:border-0">
      <table className="w-max text-left text-xs">
        <thead className="bg-card text-muted">
          <tr>
            <th className="px-2 py-1.5 font-medium">Salden</th>
            <th className="px-2 py-1.5 text-right font-medium">Vormonat</th>
            <th className="px-2 py-1.5 text-right font-medium">Aktuell</th>
            <th className="px-2 py-1.5 text-right font-medium">Geplant</th>
            <th className="px-2 py-1.5 text-right font-medium">Rest / Neu</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-line bg-card">
            <td className="px-2 py-1 font-medium">Zeitkonto</td>
            <td className="px-2 py-1 text-right tabular-nums">{signedHours(accounts.flex_prev)}</td>
            <td className="px-2 py-1 text-right tabular-nums">{signedHours(accounts.flex_month)}</td>
            <td className="px-2 py-1 text-right tabular-nums">—</td>
            <td className="px-2 py-1 text-right tabular-nums">{signedHours(accounts.flex_total)}</td>
          </tr>
          <tr className="border-t border-line bg-card">
            <td className="px-2 py-1 font-medium">Urlaubskonto</td>
            <td className="px-2 py-1 text-right tabular-nums">{formatDays(accounts.vacation_remaining_prev)}</td>
            <td className="px-2 py-1 text-right tabular-nums">{formatDays(-accounts.vacation_month, true)}</td>
            <td className="px-2 py-1 text-right tabular-nums">{formatDays(accounts.vacation_planned)}</td>
            <td className="px-2 py-1 text-right tabular-nums">{formatDays(accounts.vacation_remaining)}</td>
          </tr>
        </tbody>
      </table>
      <p className="max-w-xs px-2 py-1 text-[11px] text-muted">
        Resturlaub = Jahresanspruch - genommen - geplant + manuelle Buchungen. Ohne Anspruch am Stammsatz bleibt Resturlaub leer.
      </p>
    </div>
  );
}

export default function ReportJournal() {
  const [params, setParams] = useSearchParams();
  const month = params.get("month") || sessionMonth();
  const userIdsKey = params.get("user_ids");
  const selectedIds = parseUserIds(userIdsKey);
  const showInactive = params.get("inaktive") === "1";
  const [users, setUsers] = useState<User[] | null>(null);
  const shownUsers = visibleUsers(users ?? [], showInactive);
  const effectiveIds = effectiveUserIds(users, showInactive, selectedIds);
  const [journals, setJournals] = useState<JournalReport[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [pdfChoice, setPdfChoice] = useState(false);
  const [mailBusy, setMailBusy] = useState(false);
  const [mailMsg, setMailMsg] = useState("");

  useEffect(() => {
    api.users().then(setUsers).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    rememberMonth(month);
    if (!params.get("month")) {
      const next: Record<string, string> = { month };
      if (userIdsKey !== null) next.user_ids = userIdsKey;
      if (showInactive) next.inaktive = "1";
      setParams(next, { replace: true });
    }
  }, [month, params, setParams, showInactive, userIdsKey]);

  useEffect(() => {
    if (selectedIds === null && !showInactive && users === null) return;
    let cancel = false;
    setLoading(true);
    api
      .journals(month, effectiveIds)
      .then((r) => {
        if (cancel) return;
        setJournals(r.people);
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
  }, [month, userIdsKey, showInactive, users]);

  function idsWithoutEmail() {
    const allowed = effectiveIds === null ? null : new Set(effectiveIds);
    return shownUsers.filter((u) => (allowed === null || allowed.has(u.id)) && !(u.email ?? "").trim()).map((u) => u.id);
  }

  function downloadPdf(onlyWithoutEmail: boolean) {
    setPdfChoice(false);
    if (!onlyWithoutEmail) {
      void api.downloadJournalPdf(month, effectiveIds);
      return;
    }
    const ids = idsWithoutEmail();
    if (ids.length === 0) {
      setError("Keine Person ohne E-Mail in dieser Auswahl.");
      return;
    }
    setError("");
    void api.downloadJournalPdf(month, ids);
  }

  async function sendMails() {
    setMailBusy(true);
    setMailMsg("");
    setError("");
    try {
      const result = await api.sendJournalMails(month, effectiveIds);
      const parts = [`${result.sent} ${result.sent === 1 ? "Journal" : "Journale"} gesendet`];
      if (result.skipped_no_flag) parts.push(`${result.skipped_no_flag} ohne Haken`);
      if (result.skipped_no_email) parts.push(`${result.skipped_no_email} ohne E-Mail`);
      if (result.failed.length) parts.push(`${result.failed.length} fehlgeschlagen`);
      setMailMsg(parts.join(", ") + ".");
    } catch (err) {
      setMailMsg(err instanceof Error ? err.message : "Versand fehlgeschlagen");
    } finally {
      setMailBusy(false);
    }
  }

  function setFilter(nextMonth: string, ids: number[] | null, inactive = showInactive) {
    const query: Record<string, string> = { month: nextMonth };
    if (ids !== null) query.user_ids = ids.join(",");
    if (inactive) query.inaktive = "1";
    setParams(query);
  }

  return (
    <div className="pt-2">
      <Link to="/auswertungen" className="print:hidden text-sm text-muted">
        ← Auswertungen
      </Link>
      <div className="print:hidden">
        <ReportToolbar
          title="Journale"
          actions={
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                disabled={journals.length === 0 || mailBusy}
                className="rounded-lg border border-line bg-card px-3 py-1 text-sm disabled:opacity-40"
                onClick={() => void sendMails()}
              >
                Per E-Mail
              </button>
              <ExportButtons pdfDisabled={journals.length === 0} onPdf={() => setPdfChoice(true)} />
            </div>
          }
        >
          <input
            type="month"
            value={month}
            onChange={(e) => setFilter(e.target.value, selectedIds)}
            className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
          />
          <PersonFilter users={shownUsers} selectedIds={selectedIds} onChange={(ids) => setFilter(month, ids)} />
          <InactiveToggle checked={showInactive} onChange={(next) => setFilter(month, selectedIds, next)} />
        </ReportToolbar>
      </div>
      <p className="mt-2 text-sm text-muted print:hidden">
        {monthLabel(month)}. Jede Stempelung steht in einer eigenen Zeile. Die Lohnarten nutzen Raster, Schichtkorridor
        und die automatische Pause wie die Auswertung.
      </p>
      {mailMsg ? <p className="mt-3 text-sm text-muted">{mailMsg}</p> : null}
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      {pdfChoice ? (
        <div className="fixed inset-0 z-20 flex items-end justify-center bg-black/40 p-4 sm:items-center">
          <div className="w-full max-w-lg rounded-2xl bg-card p-5 shadow-xl" role="dialog" aria-labelledby="journal-pdf-title">
            <p id="journal-pdf-title" className="text-lg font-medium">
              PDF herunterladen
            </p>
            <p className="mt-1 text-sm text-muted">
              Alle Journale der aktuellen Auswahl, oder nur die Personen ohne E-Mail-Adresse? Ohne Adresse geht das Journal nicht per Mail raus und kann ausgedruckt werden.
            </p>
            <div className="mt-4 flex flex-col gap-2 sm:flex-row">
              <button type="button" className="flex-1 rounded-xl border border-line py-2" onClick={() => setPdfChoice(false)}>
                Abbrechen
              </button>
              <button type="button" className="flex-1 rounded-xl border border-line py-2" onClick={() => downloadPdf(true)}>
                Nur ohne E-Mail
              </button>
              <button type="button" className="flex-1 rounded-xl bg-present py-2 text-white" onClick={() => downloadPdf(false)}>
                Alle
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {loading ? (
        <LoadingNote />
      ) : journals.length === 0 && !error ? (
        <p className="mt-8 text-sm text-muted">Keine Personen für diesen Monat.</p>
      ) : null}
      {!loading
        ? journals.map((journal) => (
        <section key={journal.user_id} className="mt-6 break-after-page">
          <h2 className="text-lg font-medium">{journal.display_name}</h2>
          <p className="text-sm text-muted">{journal.month_label}</p>
          <div className="mt-2 inline-block max-w-full">
          <div className="overflow-x-auto rounded-xl border border-line print:border-0">
            <table className="w-max text-left text-xs">
              <thead className="bg-nav text-[10px] text-white">
                <tr>
                  <th className="px-1.5 py-1" rowSpan={2}>Datum</th>
                  <th className="px-1.5 py-1 text-center" colSpan={3}>Arbeitszeit</th>
                  <th className="px-1.5 py-1 text-right" rowSpan={2}>Pause</th>
                  <th className="px-1.5 py-1 text-center" colSpan={3}>Tag</th>
                  <th className="px-1.5 py-1" rowSpan={2}>Schicht</th>
                  <th className="px-1.5 py-1 text-center" colSpan={3}>Lohnarten</th>
                  <th className="px-1.5 py-1" rowSpan={2}>Bemerkung</th>
                </tr>
                <tr>
                  <th className="px-1.5 py-1 text-right font-medium">Beginn</th>
                  <th className="px-1.5 py-1 text-right font-medium">Ende</th>
                  <th className="px-1.5 py-1 text-right font-medium">Zeit</th>
                  <th className="px-1.5 py-1 text-right font-medium">Ist</th>
                  <th className="px-1.5 py-1 text-right font-medium">Soll</th>
                  <th className="px-1.5 py-1 text-right font-medium">Saldo</th>
                  <th className="px-1.5 py-1 text-right font-medium">20–24</th>
                  <th className="px-1.5 py-1 text-right font-medium">0–4</th>
                  <th className="px-1.5 py-1 text-right font-medium">4–6</th>
                </tr>
              </thead>
              <tbody>
                {journal.rows.map((row, index) => {
                  const summary =
                    row.type === "month"
                      ? "bg-navy font-semibold text-white"
                      : row.type === "week"
                        ? "bg-line font-semibold"
                        : "bg-card";
                  return (
                    <tr
                      key={`${journal.user_id}-${row.type}-${row.label}-${index}`}
                      className={`border-t border-line ${summary}`}
                    >
                      <td className="whitespace-nowrap px-1.5 py-0.5">{row.label}</td>
                      <td className="px-1.5 py-0.5 text-right tabular-nums">{row.start}</td>
                      <td className="px-1.5 py-0.5 text-right tabular-nums">{row.end}</td>
                      <td className="px-1.5 py-0.5 text-right tabular-nums">{hm(row.segment_hours)}</td>
                      <td className="px-1.5 py-0.5 text-right tabular-nums">{wageCell(row.pause_hours)}</td>
                      <td className="px-1.5 py-0.5 text-right tabular-nums">{hm(row.work_hours)}</td>
                      <td className="px-1.5 py-0.5 text-right tabular-nums">{hm(row.soll_hours)}</td>
                      <td className="px-1.5 py-0.5 text-right tabular-nums">
                        {row.delta_hours === null ? "" : signedHours(row.delta_hours)}
                      </td>
                      <td className="px-1.5 py-0.5">{row.shift}</td>
                      <td className="px-1.5 py-0.5 text-right tabular-nums">{wageCell(row.hours_20_24)}</td>
                      <td className="px-1.5 py-0.5 text-right tabular-nums">{wageCell(row.hours_0_4)}</td>
                      <td className="px-1.5 py-0.5 text-right tabular-nums">{wageCell(row.hours_4_6)}</td>
                      <td className="px-1.5 py-0.5">{row.remark}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-2 grid w-max max-w-full items-start gap-2 md:grid-cols-2">
            {journal.wages ? <WageFooter wages={journal.wages} /> : null}
            {journal.accounts ? <AccountFooter accounts={journal.accounts} /> : null}
          </div>
          </div>
        </section>
      ))
        : null}
    </div>
  );
}
