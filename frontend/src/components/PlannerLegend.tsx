const ENTRIES: { label: string; swatch: string; title?: string }[] = [
  { label: "Urlaub", swatch: "bg-vacation/70" },
  { label: "Krankheit", swatch: "bg-sick/70" },
  { label: "Abwesend", swatch: "bg-away/50" },
  {
    label: "Feiertag",
    swatch: "bg-holiday/15",
    title: "Gesetzlich oder eingetragen. Ein persönlicher Brückentag erscheint kräftig.",
  },
  { label: "Betriebsfrei", swatch: "bg-off/15" },
  { label: "Samstag", swatch: "bg-sat/15" },
  { label: "Sonntag", swatch: "bg-sun/15" },
];

export default function PlannerLegend() {
  return (
    <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted">
      {ENTRIES.map((entry) => (
        <span key={entry.label} className="inline-flex items-center gap-1.5" title={entry.title}>
          <span className={`inline-block h-2.5 w-2.5 rounded-sm ${entry.swatch}`} />
          {entry.label}
        </span>
      ))}
    </p>
  );
}
