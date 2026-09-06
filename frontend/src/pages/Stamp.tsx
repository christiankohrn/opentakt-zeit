import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type PunchKind, type Status } from "../api";
import { useVisiblePoll } from "../live";
import { enqueue, newEventId, readQueue, writeQueue } from "../offline";
import { bookingText, daySurfaceClass, formatDayLabel, hoursTone, isoDate, signedHours, warnLabel } from "../labels";

const LABELS: Record<PunchKind, string> = {
  in: "Kommen",
  break_start: "Pause",
  break_end: "Pause Ende",
  out: "Gehen",
};

const STATE_COPY: Record<Status["state"], { title: string; hint: string; color: string }> = {
  away: { title: "Abwesend", hint: "Noch nicht eingestempelt", color: "text-away" },
  in: { title: "Anwesend", hint: "Arbeitszeit läuft", color: "text-present" },
  break: { title: "Pause", hint: "Die Uhr für die Arbeit steht", color: "text-pause" },
};

export default function Stamp() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<PunchKind | null>(null);
  const [clock, setClock] = useState(() => new Date());
  const [pending, setPending] = useState(0);

  const refresh = useCallback(async (quiet = false) => {
    try {
      setStatus(await api.status());
      if (!quiet) setError("");
      else setError((cur) => (cur.startsWith("Offline") ? "" : cur));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      setError("Offline — Stempel werden gespeichert und später gesendet.");
    }
  }, []);

  const flush = useCallback(async () => {
    const q = readQueue();
    if (!q.length) {
      setPending(0);
      return;
    }
    const rest: typeof q = [];
    let lastErr = "";
    for (const item of q) {
      try {
        await api.punch(item.kind, item.client_event_id, item.device_time);
      } catch (err) {
        if (err instanceof ApiError && (err.status === 409 || err.status === 422)) {
          lastErr = err.message;
          continue;
        }
        rest.push(item);
        if (err instanceof ApiError && err.status === 401) {
          lastErr = "Sitzung abgelaufen. Stempel bleibt gespeichert.";
        }
      }
    }
    writeQueue(rest);
    setPending(rest.length);
    if (lastErr) setError(lastErr);
    if (rest.length < q.length) await refresh();
  }, [refresh]);

  useEffect(() => {
    void refresh();
    setPending(readQueue().length);
    void flush();
    const t = setInterval(() => setClock(new Date()), 1000);
    const onOnline = () => {
      void flush();
    };
    window.addEventListener("online", onOnline);
    return () => {
      clearInterval(t);
      window.removeEventListener("online", onOnline);
    };
  }, [flush, refresh]);

  const pollStatus = useCallback(() => {
    void refresh(true);
  }, [refresh]);
  useVisiblePoll(4000, pollStatus);

  async function stamp(kind: PunchKind) {
    setBusy(kind);
    setError("");
    const event = {
      kind,
      client_event_id: newEventId(),
      device_time: new Date().toISOString(),
    };
    try {
      if (!navigator.onLine) throw new TypeError("offline");
      await api.punch(kind, event.client_event_id, event.device_time);
      await refresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(err.message);
        await refresh();
        return;
      }
      enqueue(event);
      setPending(readQueue().length);
      if (err instanceof ApiError && err.status === 401) {
        setError("Sitzung abgelaufen. Stempel bleibt gespeichert und wird nach der Anmeldung gesendet.");
      } else {
        setError("Gespeichert auf dem Gerät. Wird gesendet, sobald Netz da ist.");
      }
    } finally {
      setBusy(null);
    }
  }

  const copy = status ? STATE_COPY[status.state] : STATE_COPY.away;
  const time = clock.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const dateLabel = formatDayLabel(isoDate(clock), "long");
  const flex = status?.flex_hours ?? 0;
  const totalFlex = status?.total_flex_hours ?? 0;
  const recent = [...(status?.recent_days ?? [])].reverse();

  return (
    <div className="pt-6 md:mx-auto md:max-w-4xl md:pt-4">
      <div className="md:grid md:grid-cols-[1fr_minmax(16rem,20rem)] md:items-center md:gap-10">
        <div>
          <p className="text-center text-5xl font-light tracking-tight sm:text-6xl md:text-left md:text-7xl">{time}</p>
          <p className="mt-2 text-center text-lg text-muted md:text-left">{dateLabel}</p>
          <div className="mt-8 rounded-3xl border border-line bg-card px-6 py-10 text-center md:mt-6 md:py-8 md:text-left">
            <p className={`text-sm uppercase tracking-[0.25em] ${copy.color}`}>{copy.title}</p>
            <p className="mt-3 text-2xl font-medium">{status?.display_name ?? "…"}</p>
            <p className="mt-2 text-muted">{copy.hint}</p>
            <p className="mt-6 text-xs uppercase tracking-widest text-muted">Stundenkonto</p>
            <div className="mt-2 grid grid-cols-2 gap-4 md:max-w-sm">
              <div>
                <p className={`text-3xl font-medium tabular-nums ${hoursTone(flex)}`}>{signedHours(flex)}</p>
                <p className="mt-1 text-xs text-muted">dieser Monat</p>
              </div>
              <div>
                <p className={`text-3xl font-medium tabular-nums ${hoursTone(totalFlex)}`}>{signedHours(totalFlex)}</p>
                <p className="mt-1 text-xs text-muted">gesamt</p>
              </div>
            </div>
          </div>
        </div>
        <div>
          {error ? <p className="mt-4 text-center text-sm text-pause md:mt-0 md:text-left">{error}</p> : null}
          {pending ? (
            <p className="mt-2 text-center text-sm text-muted md:text-left">{pending} Stempel warten aufs Netz</p>
          ) : null}
          <div className="mt-8 grid grid-cols-1 gap-3 md:mt-0">
            {(status?.allowed ?? ["in"]).map((kind) => (
              <button
                key={kind}
                type="button"
                disabled={busy !== null}
                onClick={() => stamp(kind)}
                className={`min-h-16 rounded-2xl px-4 py-4 text-xl font-medium text-white ${
                  kind === "in" || kind === "break_end"
                    ? "bg-present"
                    : kind === "break_start"
                      ? "bg-pause"
                      : "bg-navy"
                }`}
              >
                {busy === kind ? "…" : LABELS[kind]}
              </button>
            ))}
          </div>
        </div>
      </div>
      {recent.length ? (
        <section className="mt-8">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-sm font-medium">Letzte Tage</h2>
            <Link to="/zeiten" className="text-sm text-present">
              Alle Zeiten
            </Link>
          </div>
          <ul className="mt-3 space-y-2">
            {recent.map((d) => {
              const issues = (d.warnings ?? []).filter((w) => w !== "overnight");
              const off = Boolean(d.calendar || d.absence);
              return (
                <li key={d.date} className={`rounded-2xl border px-4 py-3 ${daySurfaceClass(d)}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{formatDayLabel(d.date, "long")}</p>
                      <p className="mt-1 truncate text-xs text-muted">{bookingText(d, "Keine Buchung")}</p>
                      {issues.length ? (
                        <p className="mt-1 text-xs text-danger">{issues.map(warnLabel).join(" · ")}</p>
                      ) : null}
                    </div>
                    <p
                      className={`shrink-0 text-sm tabular-nums ${
                        off || (!d.work_hours && !d.soll_hours) ? "text-muted" : hoursTone(d.delta_hours)
                      }`}
                    >
                      {off && !d.work_hours
                        ? "—"
                        : !d.work_hours && !d.soll_hours
                          ? "—"
                          : signedHours(d.delta_hours)}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
