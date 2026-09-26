import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Department } from "../api";
import LoadingNote from "../components/LoadingNote";
import SearchField, { matchesQuery } from "../components/SearchField";

export default function HrDepartments() {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const visible = departments.filter((dept) => matchesQuery(query, [dept.name]));

  async function load() {
    setDepartments(await api.departments());
  }

  useEffect(() => {
    void load()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.createDepartment({ name });
      setName("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fehler");
    }
  }

  async function saveName(id: number) {
    setError("");
    try {
      await api.patchDepartment(id, { name: editName });
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fehler");
    }
  }

  async function remove(id: number) {
    setError("");
    try {
      await api.deleteDepartment(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fehler");
    }
  }

  return (
    <div className="pt-2">
      <Link to="/personal" className="text-sm text-muted">
        ← Personal
      </Link>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-medium">Abteilungen</h1>
        <SearchField value={query} onChange={setQuery} placeholder="Abteilung suchen" />
      </div>
      <p className="mt-2 text-sm text-muted">
        Mitarbeitende einer Abteilung zuordnen. In Auswertungen reicht dann ein Haken auf die Abteilung.
      </p>
      {error ? <p className="mt-3 text-sm text-danger">{error}</p> : null}
      <ul className="mt-4 grid gap-2 md:grid-cols-2">
        {visible.map((dept) => (
          <li key={dept.id} className="rounded-2xl border border-line bg-card px-4 py-3">
            {editing === dept.id ? (
              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void saveName(dept.id);
                }}
              >
                <input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="min-w-0 flex-1 rounded-lg border border-line bg-bg px-3 py-1.5 text-sm"
                  autoFocus
                />
                <button type="submit" className="text-sm text-present">
                  Speichern
                </button>
                <button type="button" className="text-sm text-muted" onClick={() => setEditing(null)}>
                  Abbrechen
                </button>
              </form>
            ) : (
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{dept.name}</p>
                  <p className="text-xs text-muted">
                    {dept.user_count === 1 ? "1 Person" : `${dept.user_count} Personen`}
                  </p>
                </div>
                <div className="flex gap-3 text-sm">
                  <button
                    type="button"
                    className="text-present"
                    onClick={() => {
                      setEditing(dept.id);
                      setEditName(dept.name);
                    }}
                  >
                    Umbenennen
                  </button>
                  <button type="button" className="text-muted" onClick={() => void remove(dept.id)}>
                    Löschen
                  </button>
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>
      {loading ? <LoadingNote className="mt-4" /> : null}
      {!loading && visible.length === 0 ? (
        <p className="mt-4 text-sm text-muted">
          {query.trim() ? "Keine Abteilung in dieser Auswahl." : "Noch keine Abteilungen."}
        </p>
      ) : null}
      <form onSubmit={onSubmit} className="mt-6 space-y-3 rounded-2xl border border-line bg-card p-4">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="z. B. Produktion"
          className="w-full rounded-lg border border-line bg-bg px-3 py-2"
          required
        />
        <button type="submit" className="w-full rounded-xl bg-present py-2 text-white">
          Abteilung anlegen
        </button>
      </form>
    </div>
  );
}
