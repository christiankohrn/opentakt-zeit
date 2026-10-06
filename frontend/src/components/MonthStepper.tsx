import { shiftMonth } from "../reportPeriod";
import { IconChevron } from "./Icons";

export default function MonthStepper({
  value,
  onChange,
  label = "Monat",
}: {
  value: string;
  onChange: (value: string) => void;
  label?: string;
}) {
  const prev = shiftMonth(value, -1);
  const next = shiftMonth(value, 1);
  return (
    <div className="flex shrink-0 items-center gap-1">
      <button
        type="button"
        aria-label="Vorheriger Monat"
        disabled={!prev}
        onClick={() => prev && onChange(prev)}
        className="shrink-0 rounded-lg border border-line bg-card p-1.5 disabled:opacity-40"
      >
        <IconChevron className="h-4 w-4 rotate-180" />
      </button>
      <input
        type="month"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
        className="month-compact shrink-0 rounded-lg border border-line bg-card px-2 py-1 text-sm"
      />
      <button
        type="button"
        aria-label="Nächster Monat"
        disabled={!next}
        onClick={() => next && onChange(next)}
        className="shrink-0 rounded-lg border border-line bg-card p-1.5 disabled:opacity-40"
      >
        <IconChevron className="h-4 w-4" />
      </button>
    </div>
  );
}
