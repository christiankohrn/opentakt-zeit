import { Link } from "react-router-dom";

const REPORTS = [
  {
    to: "/auswertungen/krankheit",
    title: "Krankheitstage",
    text: "Krankheitstage je Person im gewählten Zeitraum, Standard ganzes Jahr und alle Mitarbeitenden.",
  },
  {
    to: "/auswertungen/salden",
    title: "Monatssalden",
    text: "Ist, Soll, Diff, Vortrag, Gesamt, Krankheit, Urlaub genommen und geplant — mit Stichtag.",
  },
  {
    to: "/auswertungen/jubilaeen",
    title: "Jubiläen",
    text: "Geburtstage, Eintrittstage und 10/25/40-Jahr-Jubiläen im Halbjahr.",
  },
  {
    to: "/auswertungen/nacht",
    title: "Nachtstunden",
    text: "Arbeitszeit in den Fenstern 20–24, 0–4 und 4–6 Uhr aus Stempelintervallen.",
  },
  {
    to: "/auswertungen/journal",
    title: "Journal",
    text: "Monatliche Stempel- und Abwesenheitsliste einer Person, mit Wochen- und Monatssummen, als PDF.",
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
