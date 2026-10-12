import { useEffect, useState, type FocusEvent, type KeyboardEvent, type MouseEvent } from "react";
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

export function searchHitId(listId: string, index: number) {
  return `${listId}-opt-${index}`;
}

export function searchHitClass(active: boolean) {
  return active ? "bg-present/10" : "";
}

/** Cursor auf den ersten Treffer, sobald sich die Ergebnisliste ändert. */
export function useSearchCursor(resetKey: string) {
  const [activeIndex, setActiveIndex] = useState(0);
  useEffect(() => {
    setActiveIndex(0);
  }, [resetKey]);
  return [activeIndex, setActiveIndex] as const;
}

function scrollSearchHit(id: string) {
  requestAnimationFrame(() => {
    document.querySelectorAll(`[data-search-hit="${id}"]`).forEach((node) => {
      if (node instanceof HTMLElement && node.getClientRects().length > 0) {
        node.scrollIntoView({ block: "nearest" });
      }
    });
  });
}

export default function SearchField({
  value,
  onChange,
  placeholder = "Suchen",
  className = "",
  fill = false,
  autoFocus = false,
  onClear,
  listId,
  resultCount = 0,
  activeIndex = 0,
  onActiveIndexChange,
  onPickResult,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  fill?: boolean;
  autoFocus?: boolean;
  onClear?: () => void;
  listId?: string;
  resultCount?: number;
  activeIndex?: number;
  onActiveIndexChange?: (index: number) => void;
  onPickResult?: (index: number) => void;
}) {
  const picks = Boolean(onPickResult) && resultCount > 0;
  const current = picks ? Math.min(Math.max(activeIndex, 0), resultCount - 1) : 0;

  function selectAll(input: HTMLInputElement) {
    input.select();
    requestAnimationFrame(() => input.select());
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!picks || !onPickResult) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      const next = Math.min(resultCount - 1, current + 1);
      onActiveIndexChange?.(next);
      if (listId) scrollSearchHit(searchHitId(listId, next));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      const next = Math.max(0, current - 1);
      onActiveIndexChange?.(next);
      if (listId) scrollSearchHit(searchHitId(listId, next));
    } else if (event.key === "Enter") {
      event.preventDefault();
      onPickResult(current);
    }
  }

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
          role={onPickResult ? "combobox" : undefined}
          aria-autocomplete={onPickResult ? "list" : undefined}
          aria-expanded={onPickResult ? picks : undefined}
          aria-controls={picks ? listId : undefined}
          aria-activedescendant={picks && listId ? searchHitId(listId, current) : undefined}
          onFocus={(event: FocusEvent<HTMLInputElement>) => selectAll(event.currentTarget)}
          onClick={(event: MouseEvent<HTMLInputElement>) => selectAll(event.currentTarget)}
          onMouseUp={(event: MouseEvent<HTMLInputElement>) => event.preventDefault()}
          onKeyDown={onKeyDown}
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
