import { useEffect, useRef, useState } from "react";
import type { User } from "../api";

export default function PersonFilter({
  users,
  selectedIds,
  onChange,
}: {
  users: User[];
  selectedIds: number[] | null;
  onChange: (ids: number[] | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const allIds = users.map((u) => u.id);
  const selected = selectedIds ?? allIds;
  const allOn = selectedIds === null || (allIds.length > 0 && selected.length === allIds.length);

  useEffect(() => {
    function close(event: MouseEvent) {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function toggle(id: number) {
    const current = new Set(selectedIds ?? allIds);
    if (current.has(id)) current.delete(id);
    else current.add(id);
    if (current.size === allIds.length) onChange(null);
    else onChange([...current]);
  }

  const label =
    users.length === 0
      ? "Mitarbeitende"
      : allOn
        ? "Alle Mitarbeitenden"
        : selected.length === 0
          ? "Keine Mitarbeitenden"
          : selected.length === 1
            ? users.find((u) => u.id === selected[0])?.display_name || "1 Person"
            : `${selected.length} von ${allIds.length}`;

  return (
    <div className="relative w-[13.5rem] shrink-0" ref={box}>
      <button
        type="button"
        className="w-full truncate rounded-lg border border-line bg-card px-2 py-1 text-left text-sm"
        onClick={() => setOpen((value) => !value)}
      >
        {label}
      </button>
      {open ? (
        <div className="absolute left-0 z-20 mt-1 max-h-64 w-64 overflow-y-auto rounded-xl border border-line bg-card p-2 shadow-lg">
          <div className="mb-2 flex gap-3 px-1 text-xs">
            <button type="button" className="text-present" onClick={() => onChange(null)}>
              Alle
            </button>
            <button type="button" className="text-muted" onClick={() => onChange([])}>
              Keine
            </button>
          </div>
          {users.map((user) => (
            <label key={user.id} className="flex items-center gap-2 rounded-lg px-1 py-1.5 text-sm hover:bg-bg">
              <input type="checkbox" checked={selected.includes(user.id)} onChange={() => toggle(user.id)} />
              <span>{user.display_name}</span>
            </label>
          ))}
        </div>
      ) : null}
    </div>
  );
}
