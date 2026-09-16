import { Link } from "react-router-dom";

const REPORTS = [
  {
    to: "/auswertungen/krankheit",
    title: "Krankheitstage",
    text: "Krankheitstage je Person im gewählten Zeitraum und im Kalenderjahr insgesamt.",
  },
  {
    to: "/auswertungen/urlaub",
    title: "Urlaubstage",
    text: "Gebuchte Urlaubstage je Person im gewählten Zeitraum und im Kalenderjahr insgesamt.",
  },
  {
    to: "/auswertungen/salden",
    title: "Monatssalden",
    text: "Saldenstand zum Stichtag: Zeitkonto, Urlaub und Krankheit mit Vormonat, Monat und Gesamt.",
  },
  {
    to: "/auswertungen/jubilaeen",
    title: "Jubiläen",
    text: "Geburtstage, Eintrittstage und 10/25/40-Jahr-Jubiläen im Halbjahr, inkl. Ursprungsdatum.",
  },
  {
    to: "/auswertungen/lohnarten",
    title: "Lohnarten",
    text: "Nachtstunden als Lohnarten 1 (20–24), 2 (0–4) und 3 (4–6), optional Summe aus 1 und 3.",
  },
  {
    to: "/auswertungen/journal",
    title: "Journale",
    text: "Monatliche Stempel- und Abwesenheitslisten für alle oder ausgewählte Personen, als Sammel-PDF.",
  },
];

export default function Reports() {
  return (
    <div className="pt-2">
      <h1 className="text-xl font-medium">Auswertungen</h1>
      <p className="mt-2 text-sm text-muted">Berichte für Personal. CSV- und PDF-Export in jedem Bericht.</p>
      <ul className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {REPORTS.map((r) => (
          <li key={r.to}>
            <Link to={r.to} className="block h-full rounded-2xl border border-line bg-card px-4 py-3 hover:border-present">
              <p className="font-medium text-present">{r.title}</p>
              <p className="mt-1 text-sm text-muted">{r.text}</p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
