import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type DaySummary } from "../api";
import DayLegend from "../components/DayLegend";
import { useVisiblePoll } from "../live";
import { bookingText, dayKindLabel, dayRowClass, daySurfaceClass, formatDayLabel, formatHours, formatPunchLine, hoursTone, isoDate, signedHours, warnLabel } from "../labels";

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function hoursCell(d: DaySummary) {
  if ((d.calendar || d.absence) && !d.work_hours) return "—";
  return formatHours(d.work_hours, 2);
}

export default function Times() {
  const [month, setMonth] = useState(currentMonth);
  const [days, setDays] = useState<DaySummary[]>([]);
  const [monthFlex, setMonthFlex] = useState(0);
  const [totalFlex, setTotalFlex] = useState(0);

  const load = useCallback(() => {
    api.myDays(month).then((r) => {
      setDays(r.days);
      setMonthFlex(r.month_flex ?? 0);
      setTotalFlex(r.total_flex ?? 0);
    });
  }, [month]);

  useEffect(() => {
    load();
  }, [load]);

  useVisiblePoll(20000, load);

  const totals = useMemo(() => {
    const today = isoDate();
    return days
      .filter((d) => d.date <= today)
      .reduce(
        (acc, d) => ({
          work: acc.work + d.work_hours,
          soll: acc.soll + d.soll_hours,
        }),
        { work: 0, soll: 0 },
      );
  }, [days]);

  return (
    <div className="pt-2">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-medium">Meine Zeiten</h1>
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
        />
      </div>
      <p className="mt-2 text-sm text-muted">
        Ist {formatHours(totals.work)} · Soll {formatHours(totals.soll)} · Monat{" "}
        <span className={hoursTone(monthFlex)}>{signedHours(monthFlex)}</span>
        {" · "}
        Gesamt <span className={hoursTone(totalFlex)}>{signedHours(totalFlex)}</span>
      </p>
      <DayLegend />
      <ul className="mt-4 space-y-2 md:hidden">
        {days.map((d) => {
          const off = Boolean(d.calendar || d.absence);
          return (
            <li key={d.date} className={`rounded-2xl border px-4 py-3 ${daySurfaceClass(d)}`}>
              <div className="flex justify-between text-sm">
                <span>
                  {formatDayLabel(d.date, "short")}
                </span>
                <span className={off ? "text-ink" : d.delta_hours < 0 ? "text-danger" : "text-present"}>
                  {off ? dayKindLabel(d) : formatHours(d.work_hours, 2)}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted">
                {off ? formatPunchLine(d.punches) || "frei" : bookingText(d, "Keine Buchung")}
              </p>
              {d.warnings.length ? (
                <p className={`mt-1 text-xs ${d.warnings.some((w) => w !== "overnight") ? "text-danger" : "text-muted"}`}>
                  {d.warnings.map(warnLabel).join(" · ")}
                </p>
              ) : null}
              {d.auto_break_minutes ? (
                <p className="mt-1 text-xs text-muted">Pause automatisch {d.auto_break_minutes} Min.</p>
              ) : null}
            </li>
          );
        })}
      </ul>
      <div className="mt-4 hidden overflow-x-auto rounded-2xl border border-line md:block">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className="bg-card text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-4 py-3 font-medium">Datum</th>
              <th className="px-4 py-3 font-medium">Buchungen</th>
              <th className="px-4 py-3 font-medium text-right">Ist</th>
              <th className="px-4 py-3 font-medium text-right">Soll</th>
              <th className="px-4 py-3 font-medium text-right">Konto</th>
              <th className="px-4 py-3 font-medium">Hinweise</th>
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d.date} className={`border-t border-line ${dayRowClass(d)}`}>
                <td className="whitespace-nowrap px-4 py-2.5">
                  {formatDayLabel(d.date, "short")}
                </td>
                <td className="px-4 py-2.5 text-muted">{bookingText(d)}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{hoursCell(d)}</td>
                <td className="px-4 py-2.5 text-right tabular-nums text-muted">{formatHours(d.soll_hours)}</td>
                <td
                  className={`px-4 py-2.5 text-right tabular-nums ${
                    d.calendar || d.absence ? "text-muted" : d.delta_hours < 0 ? "text-danger" : "text-present"
                  }`}
                >
                  {d.calendar || d.absence ? "—" : signedHours(d.delta_hours)}
                </td>
                <td className={`px-4 py-2.5 text-xs ${d.warnings.some((w) => w !== "overnight") ? "text-danger" : "text-muted"}`}>
                  {[
                    ...d.warnings.map(warnLabel),
                    d.auto_break_minutes ? `Pause auto. ${d.auto_break_minutes} Min.` : "",
                  ]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
