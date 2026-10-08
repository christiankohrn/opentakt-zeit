export const PUNCH_LABELS: Record<string, string> = {
  in: "Kommen",
  out: "Gehen",
  break_start: "Pause Beginn",
  break_end: "Pause Ende",
};

export const WARNING_LABELS: Record<string, string> = {
  checkout_missing: "Gehen fehlt",
  break_short: "Pause unter 30 Min.",
  break_short_9h: "Pause unter 45 Min. (ab 9 Std.)",
  break_long: "Pause über 90 Min.",
  over_10h: "Mehr als 10 Stunden",
  missing_day: "Keine Buchung (Werktag)",
  overnight: "Schicht über Mitternacht",
  accepted: "In der Prüfung ignoriert",
};

export const ABSENCE_LABELS: Record<string, string> = {
  vacation: "Urlaub",
  sick: "Krankheit",
  school: "Schule",
  special_leave: "Sonderurlaub",
  comp_time: "Zeitausgleich",
  holiday: "Feiertag",
  company_off: "Betriebsfrei",
  other: "Abwesend",
};

export function punchLabel(kind: string) {
  return PUNCH_LABELS[kind] ?? kind;
}

export function warnLabel(code: string) {
  const custom = code.match(/^break_short:(\d+):(\d+(?:\.\d+)?)$/);
  if (custom) return `Pause unter ${custom[1]} Min. (ab ${custom[2].replace(".", ",")} Std.)`;
  return WARNING_LABELS[code] ?? code;
}

export function formatDecimal(value: number, digits = 1) {
  return value.toFixed(digits).replace(".", ",");
}

export function parseHours(value: string): number | null {
  const text = value.trim().replace(/\s/g, "");
  const clock = text.match(/^([+-])?(\d+):(\d{1,2})$/);
  if (clock) {
    const mins = Number(clock[3]);
    if (mins > 59) return null;
    const sign = clock[1] === "-" ? -1 : 1;
    return (sign * (Number(clock[2]) * 60 + mins)) / 60;
  }
  const hours = Number(text.replace(",", "."));
  return Number.isFinite(hours) ? hours : null;
}

export function formatHm(hours: number, signed = false) {
  if (!Number.isFinite(hours)) return "0:00";
  const negative = hours < 0;
  const total = Math.round(Math.abs(hours) * 60);
  const whole = Math.floor(total / 60);
  const mins = total % 60;
  const body = `${whole}:${String(mins).padStart(2, "0")}`;
  if (negative) return `-${body}`;
  if (signed && total > 0) return `+${body}`;
  return body;
}

export function formatHours(hours: number, _digits = 1) {
  return formatHm(hours, false);
}

export function signedHours(hours: number, _digits = 1) {
  return formatHm(hours, true);
}

export function isoDate(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function formatDayLabel(iso: string, weekday: "short" | "long" = "short") {
  const d = new Date(iso + "T12:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const wd = d.toLocaleDateString("de-DE", { weekday }).replace(/\.$/, "");
  return `${dd}.${mm}. ${wd}`;
}

export function formatDayTitle(iso: string) {
  const d = new Date(iso + "T12:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  const date = d.toLocaleDateString("de-DE", { day: "numeric", month: "long", year: "numeric" });
  const wd = d.toLocaleDateString("de-DE", { weekday: "long" });
  return `${date} ${wd}`;
}

export function hoursTone(hours: number, off = false) {
  if (off) return "text-muted";
  return hours < 0 ? "text-danger" : "text-present";
}

export function absenceLabel(kind: string) {
  return ABSENCE_LABELS[kind] ?? kind;
}

export function punchOrigin(punch: { source?: string; terminal_name?: string }) {
  if (punch.source === "import") return "Import";
  return (punch.terminal_name || "").trim();
}

export function formatPunchLine(
  punches: { kind: string; time: string; voided: boolean; source?: string; terminal_name?: string }[],
) {
  return punches
    .filter((p) => !p.voided)
    .map((p) => {
      const place = punchOrigin(p);
      return place ? `${punchLabel(p.kind)} ${p.time} (${place})` : `${punchLabel(p.kind)} ${p.time}`;
    })
    .join("  ·  ");
}

export function daySurfaceClass(d: {
  date: string;
  weekday?: number;
  calendar?: { kind: string } | null;
  absence?: { kind: string } | null;
}) {
  const kind =
    d.calendar?.kind ||
    (d.absence?.kind === "holiday" || d.absence?.kind === "company_off" ? d.absence.kind : "");
  if (kind === "holiday") return "border-holiday/35 bg-holiday/15";
  if (kind === "company_off") return "border-off/35 bg-off/15";
  const wd = d.weekday ?? new Date(d.date + "T12:00:00").getDay();
  // API weekday: 0=Mo … 6=So. JS getDay: 0=So.
  const sunday = d.weekday !== undefined ? wd === 6 : wd === 0;
  const saturday = d.weekday !== undefined ? wd === 5 : wd === 6;
  if (sunday) return "border-sun/35 bg-sun/15";
  if (saturday) return "border-sat/35 bg-sat/15";
  return "border-line bg-card";
}

export function dayRowClass(d: {
  date: string;
  weekday?: number;
  calendar?: { kind: string } | null;
  absence?: { kind: string } | null;
}) {
  const kind =
    d.calendar?.kind ||
    (d.absence?.kind === "holiday" || d.absence?.kind === "company_off" ? d.absence.kind : "");
  if (kind === "holiday") return "bg-holiday/15";
  if (kind === "company_off") return "bg-off/15";
  const wd = d.weekday ?? new Date(d.date + "T12:00:00").getDay();
  const sunday = d.weekday !== undefined ? wd === 6 : wd === 0;
  const saturday = d.weekday !== undefined ? wd === 5 : wd === 6;
  if (sunday) return "bg-sun/15";
  if (saturday) return "bg-sat/15";
  return "bg-card";
}

/**
 * Zellfarbe für den Urlaubsplaner. Persönliche Abwesenheiten sind kräftig,
 * Kalender (Feiertag/betriebsfrei) und Wochenende nur zart hinterlegt.
 * weekday wie Date.getDay() (0 = Sonntag).
 */
export function plannerCellClass(
  absenceKind: string | null,
  calendarKind: string | null,
  weekday: number,
): string {
  if (absenceKind === "vacation") return "bg-vacation/70";
  if (absenceKind === "sick") return "bg-sick/70";
  if (absenceKind === "holiday") return "bg-holiday/70";
  if (absenceKind) return "bg-away/50";
  if (calendarKind === "holiday") return "bg-holiday/15";
  if (calendarKind === "company_off") return "bg-off/15";
  if (weekday === 0) return "bg-sun/15";
  if (weekday === 6) return "bg-sat/15";
  return "bg-card";
}

export function dayKindLabel(d: {
  calendar?: { kind: string; name: string } | null;
  absence?: { kind: string; note: string | null } | null;
}) {
  if (d.calendar?.name) return d.calendar.name;
  if (d.absence) return d.absence.note || absenceLabel(d.absence.kind);
  return "";
}

export function bookingText(
  d: {
    calendar?: { kind: string; name: string } | null;
    absence?: { kind: string; note: string | null } | null;
    punches: { kind: string; time: string; voided: boolean }[];
    span_punches?: { kind: string; time: string; voided: boolean }[];
    first_in: string | null;
    last_out: string | null;
    open: boolean;
  },
  empty = "—",
) {
  const punches = formatPunchLine(d.span_punches ?? d.punches);
  const label = dayKindLabel(d);
  if (label && punches) return `${label} · ${punches}`;
  if (label) return label;
  if (punches) return punches;
  if (d.first_in) return `${d.first_in} – ${d.last_out ?? (d.open ? "offen" : "—")}`;
  return empty;
}
