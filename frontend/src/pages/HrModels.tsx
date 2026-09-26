import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type WorkModel } from "../api";
import LoadingNote from "../components/LoadingNote";
import SearchField, { matchesQuery } from "../components/SearchField";
import { formatDecimal } from "../labels";

export default function HrModels() {
  const [models, setModels] = useState<WorkModel[]>([]);
  const [name, setName] = useState("Teilzeit 20h");
  const [kind, setKind] = useState("flextime");
  const [hours, setHours] = useState("4,4,4,4,4,0,0");
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const visible = models.filter((m) => matchesQuery(query, [m.name, m.kind === "shift" ? "Schicht" : "Gleitzeit"]));

  async function load() {
    setModels(await api.models());
  }

  useEffect(() => {
    void load().finally(() => setLoading(false));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const parts = hours.split(",").map((x) => Number(x.trim().replace(",", ".")));
    const [mo, di, mi, don, fr, sa, so] = [...parts, 0, 0, 0, 0, 0, 0, 0];
    await api.createModel({
      name,
      kind,
      hours_mon: mo,
      hours_tue: di,
      hours_wed: mi,
      hours_thu: don,
      hours_fri: fr,
      hours_sat: sa,
      hours_sun: so,
    });
    setName("");
    await load();
  }

  return (
    <div className="pt-2">
      <Link to="/personal" className="text-sm text-muted">
        ← Personal
      </Link>
      <h1 className="mt-2 text-xl font-medium">Arbeitszeitmodelle</h1>
      <SearchField className="mt-3" value={query} onChange={setQuery} placeholder="Modell suchen" />
      {loading ? <LoadingNote /> : null}
      {!loading && visible.length === 0 ? (
        <p className="mt-8 text-sm text-muted">{query.trim() ? "Kein Modell in dieser Auswahl." : "Noch kein Modell."}</p>
      ) : null}
      {!loading && visible.length > 0 ? <ul className="mt-4 grid gap-2 md:grid-cols-2">
        {visible.map((m) => (
          <li key={m.id} className="rounded-2xl border border-line bg-card px-4 py-3">
            <p className="font-medium">{m.name}</p>
            <p className="text-xs text-muted">
              {m.kind === "shift" ? "Schicht" : "Gleitzeit"} · Mo–Fr {formatDecimal(m.hours_mon)}/
              {formatDecimal(m.hours_tue)}/{formatDecimal(m.hours_wed)}/{formatDecimal(m.hours_thu)}/
              {formatDecimal(m.hours_fri)} · Sa {formatDecimal(m.hours_sat)} · So {formatDecimal(m.hours_sun)}
            </p>
          </li>
        ))}
      </ul>
      : null}
      <form onSubmit={onSubmit} className="mt-6 space-y-3 rounded-2xl border border-line bg-card p-4">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Name"
          className="w-full rounded-lg border border-line bg-bg px-3 py-2"
          required
        />
        <select
          className="w-full rounded-lg border border-line bg-bg px-3 py-2"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="flextime">Gleitzeit</option>
          <option value="shift">Schicht</option>
        </select>
        <input
          value={hours}
          onChange={(e) => setHours(e.target.value)}
          placeholder="Stunden Mo–So, kommagetrennt"
          className="w-full rounded-lg border border-line bg-bg px-3 py-2"
        />
        <button type="submit" className="w-full rounded-xl bg-present py-2 text-white">
          Modell anlegen
        </button>
      </form>
    </div>
  );
}
