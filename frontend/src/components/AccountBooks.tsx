import { FormEvent, useEffect, useState } from "react";
import { api, type UserLedger } from "../api";
import { IconTrash } from "./Icons";
import { isoDate, parseHours, signedHours } from "../labels";

type Attempt = (action: (confirmClosed: boolean) => Promise<void>, fail: (message: string) => void) => Promise<void>;

function deDate(iso: string) {
  const [year, month, day] = iso.split("-");
  return `${day}.${month}.${year}`;
}

function formatDays(value: number, signed = false) {
  const rounded = Math.round(value * 10) / 10;
  const text = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1).replace(".", ",");
  if (signed && rounded > 0) return `+${text}`;
  return text;
}

function parseDays(value: string): number | null {
  const amount = Number(value.trim().replace(",", "."));
  return Number.isFinite(amount) ? amount : null;
}

export default function AccountBooks({
  userId,
  year,
  attempt,
  onChanged,
}: {
  userId: number;
  year: number;
  attempt: Attempt;
  onChanged: () => Promise<void>;
}) {
  const [ledger, setLedger] = useState<UserLedger | null>(null);
  const [timeOpen, setTimeOpen] = useState(false);
  const [vacationOpen, setVacationOpen] = useState(false);
  const [timeDay, setTimeDay] = useState(isoDate);
  const [timeAmount, setTimeAmount] = useState("");
  const [timeReason, setTimeReason] = useState("");
  const [vacDay, setVacDay] = useState(isoDate);
  const [vacAmount, setVacAmount] = useState("");
  const [vacReason, setVacReason] = useState("");
  const [msg, setMsg] = useState("");

  async function load() {
    setLedger(await api.userLedger(userId, year));
  }

  useEffect(() => {
    if (!timeOpen && !vacationOpen) return;
    void load().catch((err: unknown) => setMsg(err instanceof Error ? err.message : "Konto konnte nicht geladen werden."));
  }, [userId, year, timeOpen, vacationOpen]);

  async function book(
    kind: "time" | "vacation",
    day: string,
    amount: number | null,
    reason: string,
    clear: () => void,
  ) {
    setMsg("");
    if (!day || amount === null || amount === 0) {
      setMsg("Tag und Betrag angeben.");
      return;
    }
    if (reason.trim().length < 2) {
      setMsg("Grund angeben.");
      return;
    }
    await attempt(async (confirmClosed) => {
      await api.createLedgerEntry(userId, { kind, day, amount, reason: reason.trim(), confirm_closed: confirmClosed });
      clear();
      await load();
      await onChanged();
      setMsg("Buchung gespeichert.");
    }, setMsg);
  }

  const field = "mt-1 block rounded-lg border border-line bg-bg px-2 py-1 text-sm text-ink";

  return (
    <>
      <button type="button" className="text-sm text-present" onClick={() => setTimeOpen((open) => !open)}>
        {timeOpen ? "Zeitkonto schließen" : "Zeitkonto"}
      </button>
      <button type="button" className="text-sm text-present" onClick={() => setVacationOpen((open) => !open)}>
        {vacationOpen ? "Urlaubskonto schließen" : "Urlaubskonto"}
      </button>
      {timeOpen || vacationOpen || msg ? (
      <div className="w-full space-y-2">
      {timeOpen ? (
      <section className="max-w-lg space-y-3 rounded-2xl border border-line bg-card p-4">
        <p className="text-sm font-medium">Zeitkonto {year}</p>
        <ul className="space-y-1 text-sm">
          {ledger?.opening_balance_on ? (
            <li className="flex justify-between gap-3">
              <span>
                {deDate(ledger.opening_balance_on)} Startsaldo
              </span>
              <span className="tabular-nums">{signedHours(ledger.opening_balance_hours ?? 0)}</span>
            </li>
          ) : null}
          {(ledger?.time_entries ?? []).map((row) => (
            <li key={row.id} className="flex items-start justify-between gap-3">
              <span>
                {deDate(row.day)} {row.reason}
              </span>
              <span className="flex items-center gap-2">
                <span className="tabular-nums">{signedHours(row.amount)}</span>
                <button
                  type="button"
                  className="text-danger"
                  aria-label="Buchung löschen"
                  onClick={() => {
                    setMsg("");
                    void attempt(async (confirmClosed) => {
                      await api.deleteLedgerEntry(userId, row.id, confirmClosed);
                      await load();
                      await onChanged();
                    }, setMsg);
                  }}
                >
                  <IconTrash className="h-4 w-4" />
                </button>
              </span>
            </li>
          ))}
        </ul>
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            void book("time", timeDay, parseHours(timeAmount), timeReason, () => {
              setTimeAmount("");
              setTimeReason("");
            });
          }}
        >
          <label className="text-xs text-muted">
            Datum
            <input type="date" value={timeDay} onChange={(e) => setTimeDay(e.target.value)} className={field} />
          </label>
          <label className="text-xs text-muted">
            Stunden
            <input value={timeAmount} onChange={(e) => setTimeAmount(e.target.value)} placeholder="−35:00" className={`${field} w-28`} />
          </label>
          <label className="min-w-36 flex-1 text-xs text-muted">
            Grund
            <input value={timeReason} onChange={(e) => setTimeReason(e.target.value)} placeholder="Auszahlung" className={`${field} w-full`} />
          </label>
          <button type="submit" className="rounded-xl bg-navy px-3 py-2 text-sm text-white">Buchen</button>
        </form>
      </section>
      ) : null}
      {vacationOpen ? (
      <section className="max-w-lg space-y-3 rounded-2xl border border-line bg-card p-4">
        <p className="text-sm font-medium">Urlaubskonto {year}</p>
        <ul className="space-y-1 text-sm">
          {ledger?.vacation_allowance != null ? (
            <li className="flex justify-between gap-3">
              <span>01.01.{year} Jahresurlaub</span>
              <span className="tabular-nums">{formatDays(ledger.vacation_allowance, true)}</span>
            </li>
          ) : null}
          {(ledger?.vacation_days ?? []).map((row) => (
            <li key={row.day} className="flex justify-between gap-3">
              <span>
                {deDate(row.day)} Urlaub{row.note ? ` · ${row.note}` : ""}
              </span>
              <span className="tabular-nums">−1</span>
            </li>
          ))}
          {(ledger?.vacation_entries ?? []).map((row) => (
            <li key={row.id} className="flex items-start justify-between gap-3">
              <span>
                {deDate(row.day)} {row.reason}
              </span>
              <span className="flex items-center gap-2">
                <span className="tabular-nums">{formatDays(row.amount, true)}</span>
                <button
                  type="button"
                  className="text-danger"
                  aria-label="Buchung löschen"
                  onClick={() => {
                    setMsg("");
                    void attempt(async (confirmClosed) => {
                      await api.deleteLedgerEntry(userId, row.id, confirmClosed);
                      await load();
                      await onChanged();
                    }, setMsg);
                  }}
                >
                  <IconTrash className="h-4 w-4" />
                </button>
              </span>
            </li>
          ))}
          {ledger?.vacation_remaining != null ? (
            <li className="flex justify-between gap-3 font-medium">
              <span>Rest</span>
              <span className="tabular-nums">{formatDays(ledger.vacation_remaining)}</span>
            </li>
          ) : null}
        </ul>
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            void book("vacation", vacDay, parseDays(vacAmount), vacReason, () => {
              setVacAmount("");
              setVacReason("");
            });
          }}
        >
          <label className="text-xs text-muted">
            Datum
            <input type="date" value={vacDay} onChange={(e) => setVacDay(e.target.value)} className={field} />
          </label>
          <label className="text-xs text-muted">
            Tage
            <input value={vacAmount} onChange={(e) => setVacAmount(e.target.value)} placeholder="−2" className={`${field} w-24`} />
          </label>
          <label className="min-w-36 flex-1 text-xs text-muted">
            Grund
            <input value={vacReason} onChange={(e) => setVacReason(e.target.value)} placeholder="Korrektur" className={`${field} w-full`} />
          </label>
          <button type="submit" className="rounded-xl bg-navy px-3 py-2 text-sm text-white">Buchen</button>
        </form>
      </section>
      ) : null}
      {msg ? <p className="max-w-lg text-sm text-muted">{msg}</p> : null}
      </div>
      ) : null}
    </>
  );
}
