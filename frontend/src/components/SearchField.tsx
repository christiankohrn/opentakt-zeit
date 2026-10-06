import { IconSearch } from "./Icons";

export function matchesQuery(query: string, parts: Array<string | number | null | undefined>) {
  const words = query.trim().toLocaleLowerCase("de").split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const hay = parts
    .filter((part) => part != null && String(part) !== "")
    .join(" ")
    .toLocaleLowerCase("de");
  return words.every((word) => hay.includes(word));
}

export default function SearchField({
  value,
  onChange,
  placeholder = "Suchen",
  className = "",
  fill = false,
  autoFocus = false,
  onClear,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  fill?: boolean;
  autoFocus?: boolean;
  onClear?: () => void;
}) {
  return (
    <div className={`relative ${fill ? "w-full" : "shrink-0"} ${className}`}>
      <label className="block">
        <IconSearch className="pointer-events-none absolute top-1/2 left-2 h-4 w-4 -translate-y-1/2 text-muted" />
        <input
          type="search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          aria-label={placeholder}
          autoFocus={autoFocus}
          className={`search-compact ${fill ? "search-fill" : ""} rounded-lg border border-line bg-card py-1 ${onClear && value ? "pr-7" : "pr-2"} pl-8 text-sm ${onClear ? "[&::-webkit-search-cancel-button]:hidden" : ""}`}
        />
      </label>
      {onClear && value ? (
        <button
          type="button"
          aria-label="Suche löschen"
          onClick={onClear}
          className="absolute top-1/2 right-1 -translate-y-1/2 rounded px-1.5 text-lg leading-none text-muted hover:text-ink"
        >
          ×
        </button>
      ) : null}
    </div>
  );
}
