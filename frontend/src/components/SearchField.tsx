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
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <input
      type="search"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`w-full max-w-xs rounded-lg border border-line bg-card px-3 py-1 text-sm ${className}`}
    />
  );
}
