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
  accepted: "Unplausibel, akzeptiert",
};

export const ABSENCE_LABELS: Record<string, string> = {
  vacation: "Urlaub",
  sick: "Krankheit",
  holiday: "Feiertag",
  company_off: "Betriebsfrei",
  other: "Abwesend",
};

export function punchLabel(kind: string) {
  return PUNCH_LABELS[kind] ?? kind;
}

export function warnLabel(code: string) {
  return WARNING_LABELS[code] ?? code;
}

export function formatDecimal(value: number, digits = 1) {
  return value.toFixed(digits).replace(".", ",");
}

export function formatHours(hours: number, digits = 1) {
  return `${formatDecimal(hours, digits)}\u00a0h`;
}

export function signedHours(hours: number, digits = 1) {
  const sign = hours > 0 ? "+" : "";
  return `${sign}${formatHours(hours, digits)}`;
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

export function formatPunchLine(punches: { kind: string; time: string; voided: boolean }[]) {
  return punches
    .filter((p) => !p.voided)
    .map((p) => `${punchLabel(p.kind)} ${p.time}`)
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
    first_in: string | null;
    last_out: string | null;
    open: boolean;
  },
  empty = "—",
) {
  const punches = formatPunchLine(d.punches);
  const label = dayKindLabel(d);
  if (label && punches) return `${label} · ${punches}`;
  if (label) return label;
  if (punches) return punches;
  if (d.first_in) return `${d.first_in} – ${d.last_out ?? (d.open ? "offen" : "—")}`;
  return empty;
}
