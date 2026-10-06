import { useEffect, useRef, useState } from "react";
import type { User } from "../api";
import { IconChevron } from "./Icons";
import SearchField, { matchesQuery } from "./SearchField";

export default function PersonSwitcher({
  users,
  currentId,
  onPick,
}: {
  users: User[];
  currentId: number;
  onPick: (id: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const index = users.findIndex((u) => u.id === currentId);
  const current = index >= 0 ? users[index] : null;
  const shown = users.filter((u) => matchesQuery(query, [u.display_name, u.username, u.department_name]));

  useEffect(() => {
    function close(event: MouseEvent) {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open ]);

  useEffect(() => {
    setOpen(false);
  }, [currentId]);

  function pick(id: number) {
    setOpen(false);
    if (id !== currentId) onPick(id);
  }

  return (
    <div className="flex shrink-0 items-center gap-1">
      <button
        type="button"
        aria-label="Vorherige Person"
        disabled={index <= 0}
        onClick={() => index > 0 && pick(users[index - 1].id)}
        className="rounded-lg border border-line bg-card p-2 disabled:opacity-40"
      >
        <IconChevron className="h-4 w-4 rotate-180" />
      </button>
      <div className="relative" ref={box}>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-haspopup="listbox"
          aria-expanded={open}
          className="h-11 max-w-72 truncate rounded-lg border border-line bg-card px-3 py-1 text-left text-xl font-medium"
        >
          {current?.display_name ?? (users.length === 0 ? "…" : "Person wählen")}
        </button>
        {open ? (
          <div className="absolute left-0 z-20 mt-1 max-h-80 w-72 overflow-y-auto rounded-xl border border-line bg-card p-2 shadow-lg">
            <SearchField
              fill
              autoFocus
              className="mb-2"
              value={query}
              onChange={setQuery}
              placeholder="Name suchen"
            />
            {shown.length === 0 ? (
              <p className="px-1 py-2 text-sm text-muted">Keine Personen in dieser Auswahl.</p>
            ) : null}
            <ul role="listbox">
              {shown.map((u) => (
                <li key={u.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={u.id === currentId}
                    onClick={() => pick(u.id)}
                    className={`w-full truncate rounded-lg px-2 py-1.5 text-left text-sm hover:bg-bg ${
                      u.id === currentId ? "font-medium text-present" : ""
                    }`}
                  >
                    {u.display_name}
                    {u.active ? "" : " · inaktiv"}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
      <button
        type="button"
        aria-label="Nächste Person"
        disabled={index < 0 || index >= users.length - 1}
        onClick={() => index >= 0 && index < users.length - 1 && pick(users[index + 1].id)}
        className="rounded-lg border border-line bg-card p-2 disabled:opacity-40"
      >
        <IconChevron className="h-4 w-4" />
      </button>
    </div>
  );
}
