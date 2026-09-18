import { useEffect, useRef, useState } from "react";
import type { User } from "../api";

type Group = { key: string; name: string; users: User[] };

function groupUsers(users: User[]): Group[] {
  const map = new Map<string, Group>();
  for (const user of users) {
    const key = user.department_id != null ? `d-${user.department_id}` : "none";
    const name = user.department_name || "Ohne Abteilung";
    const group = map.get(key) ?? { key, name, users: [] };
    group.users.push(user);
    map.set(key, group);
  }
  return [...map.values()].sort((a, b) => {
    if (a.key === "none") return 1;
    if (b.key === "none") return -1;
    return a.name.localeCompare(b.name, "de");
  });
}

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
  const selectedSet = new Set(selected);
  const allOn = selectedIds === null || (allIds.length > 0 && selected.length === allIds.length);
  const groups = groupUsers(users);
  const showGroups = groups.some((g) => g.key !== "none") || groups.length > 1;

  useEffect(() => {
    function close(event: MouseEvent) {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  function commit(next: Set<number>) {
    if (next.size === allIds.length) onChange(null);
    else onChange([...next]);
  }

  function toggle(id: number) {
    const current = new Set(selectedIds ?? allIds);
    if (current.has(id)) current.delete(id);
    else current.add(id);
    commit(current);
  }

  function toggleGroup(ids: number[]) {
    const current = new Set(selectedIds ?? allIds);
    const allSelected = ids.length > 0 && ids.every((id) => current.has(id));
    if (allSelected) ids.forEach((id) => current.delete(id));
    else ids.forEach((id) => current.add(id));
    commit(current);
  }

  const selectedGroups = groups.filter((g) => g.users.some((u) => selectedSet.has(u.id)));
  const fullGroups = selectedGroups.filter((g) => g.users.every((u) => selectedSet.has(u.id)));
  const label =
    users.length === 0
      ? "Mitarbeitende"
      : allOn
        ? "Alle Mitarbeitenden"
        : selected.length === 0
          ? "Keine Mitarbeitenden"
          : fullGroups.length === 1 && selected.length === fullGroups[0].users.length
            ? fullGroups[0].name
            : selectedGroups.length === 1 && selected.length === selectedGroups[0].users.filter((u) => selectedSet.has(u.id)).length
              ? `${selectedGroups[0].name} (${selected.length})`
              : selected.length === 1
                ? users.find((u) => u.id === selected[0])?.display_name || "1 Person"
                : `${selected.length} von ${allIds.length}`;

  return (
    <div className="relative w-[14.5rem] shrink-0" ref={box}>
      <button
        type="button"
        className="w-full truncate rounded-lg border border-line bg-card px-2 py-1 text-left text-sm"
        onClick={() => setOpen((value) => !value)}
      >
        {label}
      </button>
      {open ? (
        <div className="absolute left-0 z-20 mt-1 max-h-80 w-72 overflow-y-auto rounded-xl border border-line bg-card p-2 shadow-lg">
          <div className="mb-2 flex gap-3 px-1 text-xs">
            <button type="button" className="text-present" onClick={() => onChange(null)}>
              Alle
            </button>
            <button type="button" className="text-muted" onClick={() => onChange([])}>
              Keine
            </button>
          </div>
          {showGroups
            ? groups.map((group) => {
                const ids = group.users.map((u) => u.id);
                const on = ids.length > 0 && ids.every((id) => selectedSet.has(id));
                const some = !on && ids.some((id) => selectedSet.has(id));
                return (
                  <div key={group.key} className="mb-1">
                    <label className="flex items-center gap-2 rounded-lg px-1 py-1.5 text-sm font-medium hover:bg-bg">
                      <input
                        type="checkbox"
                        checked={on}
                        ref={(el) => {
                          if (el) el.indeterminate = some;
                        }}
                        onChange={() => toggleGroup(ids)}
                      />
                      <span>{group.name}</span>
                      <span className="ml-auto text-xs font-normal text-muted">{ids.length}</span>
                    </label>
                    {group.users.map((user) => (
                      <label key={user.id} className="flex items-center gap-2 rounded-lg py-1 pl-6 pr-1 text-sm hover:bg-bg">
                        <input type="checkbox" checked={selectedSet.has(user.id)} onChange={() => toggle(user.id)} />
                        <span>{user.display_name}</span>
                      </label>
                    ))}
                  </div>
                );
              })
            : users.map((user) => (
                <label key={user.id} className="flex items-center gap-2 rounded-lg px-1 py-1.5 text-sm hover:bg-bg">
                  <input type="checkbox" checked={selectedSet.has(user.id)} onChange={() => toggle(user.id)} />
                  <span>{user.display_name}</span>
                </label>
              ))}
        </div>
      ) : null}
    </div>
  );
}
