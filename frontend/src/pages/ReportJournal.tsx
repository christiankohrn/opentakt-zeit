import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type JournalAccounts, type JournalReport, type User } from "../api";
import PersonFilter from "../components/PersonFilter";
import ReportToolbar, { ExportButtons } from "../components/ReportToolbar";
import { formatHours, signedHours } from "../labels";
import { monthLabel, parseUserIds, payrollMonth } from "../reportPeriod";

function formatDays(value: number | null | undefined, signed = false) {
  if (value === null || value === undefined) return "—";
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${String(value).replace(".", ",")}`;
}

function AccountFooter({ accounts }: { accounts: JournalAccounts }) {
  return (
    <div className="mt-4 overflow-x-auto rounded-2xl border border-line print:border-0">
      <table className="w-full text-left text-sm">
        <thead className="bg-card text-xs uppercase tracking-wider text-muted">
          <tr>
            <th className="px-4 py-3 font-medium">Salden</th>
            <th className="px-4 py-3 font-medium text-right">Vormonat</th>
            <th className="px-4 py-3 font-medium text-right">Aktuell</th>
            <th className="px-4 py-3 font-medium text-right">Verplant</th>
            <th className="px-4 py-3 font-medium text-right">Rest / Neu</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-line bg-card">
            <td className="px-4 py-2.5 font-medium">Zeitkonto</td>
            <td className="px-4 py-2.5 text-right tabular-nums">{signedHours(accounts.flex_prev)}</td>
            <td className="px-4 py-2.5 text-right tabular-nums">{signedHours(accounts.flex_month)}</td>
            <td className="px-4 py-2.5 text-right tabular-nums">—</td>
            <td className="px-4 py-2.5 text-right tabular-nums">{signedHours(accounts.flex_total)}</td>
          </tr>
          <tr className="border-t border-line bg-card">
            <td className="px-4 py-2.5 font-medium">Urlaubskonto</td>
            <td className="px-4 py-2.5 text-right tabular-nums">{formatDays(accounts.vacation_remaining_prev)}</td>
            <td className="px-4 py-2.5 text-right tabular-nums">{formatDays(-accounts.vacation_month, true)}</td>
            <td className="px-4 py-2.5 text-right tabular-nums">{formatDays(accounts.vacation_planned)}</td>
            <td className="px-4 py-2.5 text-right tabular-nums">{formatDays(accounts.vacation_remaining)}</td>
          </tr>
        </tbody>
      </table>
      <p className="px-4 py-2 text-xs text-muted">
        Resturlaub = Jahresanspruch - genommen - verplant. Ohne Anspruch am Stammsatz bleibt Resturlaub leer.
      </p>
    </div>
  );
}

export default function ReportJournal() {
  const [params, setParams] = useSearchParams();
  const month = params.get("month") || payrollMonth();
  const userIdsKey = params.get("user_ids");
  const selectedIds = parseUserIds(userIdsKey);
  const [users, setUsers] = useState<User[]>([]);
  const [journals, setJournals] = useState<JournalReport[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.users().then(setUsers).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!params.get("month")) {
      const next: Record<string, string> = { month };
      if (userIdsKey !== null) next.user_ids = userIdsKey;
      setParams(next, { replace: true });
    }
  }, [month, params, setParams, userIdsKey]);

  useEffect(() => {
    api
      .journals(month, parseUserIds(userIdsKey))
      .then((r) => {
        setJournals(r.people);
        setError("");
      })
      .catch((err: Error) => setError(err.message));
  }, [month, userIdsKey]);

  function setFilter(nextMonth: string, ids: number[] | null) {
    const query: Record<string, string> = { month: nextMonth };
    if (ids !== null) query.user_ids = ids.join(",");
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
            <ExportButtons
              pdfDisabled={journals.length === 0}
              onPdf={() => void api.downloadJournalPdf(month, selectedIds)}
            />
          }
        >
          <input
            type="month"
            value={month}
            onChange={(e) => setFilter(e.target.value, selectedIds)}
            className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
          />
          <PersonFilter users={users} selectedIds={selectedIds} onChange={(ids) => setFilter(month, ids)} />
        </ReportToolbar>
      </div>
      <p className="mt-2 text-sm text-muted print:hidden">
        {monthLabel(month)}. PDF für alle ausgewählten Personen auf einmal, je Person eine Seite zur Aushändigung.
      </p>
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      {journals.length === 0 && !error ? (
        <p className="mt-8 text-sm text-muted">Keine Personen für diesen Monat.</p>
      ) : null}
      {journals.map((journal) => (
        <section key={journal.user_id} className="mt-6 break-after-page">
          <h2 className="text-lg font-medium">{journal.display_name}</h2>
          <p className="text-sm text-muted">{journal.month_label}</p>
          <div className="mt-3 overflow-x-auto rounded-2xl border border-line print:border-0">
            <table className="w-full text-left text-sm">
              <thead className="bg-card text-xs uppercase tracking-wider text-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Tag</th>
                  <th className="px-4 py-3 font-medium">Buchung</th>
                  <th className="px-4 py-3 font-medium text-right">Ist</th>
                  <th className="px-4 py-3 font-medium text-right">Soll</th>
                  <th className="px-4 py-3 font-medium text-right">Konto</th>
                </tr>
              </thead>
              <tbody>
                {journal.rows.map((row, index) => {
                  const strong = row.type !== "day";
                  return (
                    <tr
                      key={`${journal.user_id}-${row.type}-${row.label}-${index}`}
                      className={`border-t border-line ${strong ? "bg-bg font-medium" : "bg-card"}`}
                    >
                      <td className="px-4 py-2.5 whitespace-nowrap">{row.label}</td>
                      <td className="px-4 py-2.5">{row.booking}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">
                        {row.type === "day" && !row.work_hours ? "—" : formatHours(row.work_hours, 2)}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{formatHours(row.soll_hours, 2)}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums">{signedHours(row.delta_hours, 2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {journal.accounts ? <AccountFooter accounts={journal.accounts} /> : null}
        </section>
      ))}
    </div>
  );
}
