import { useEffect, useState } from "react";
import { api, CampaignListItem } from "../api";

export default function CampaignList({ prefix }: { prefix: string }) {
  const [q, setQ] = useState("");
  const [onlyMine, setOnlyMine] = useState(true);
  const [items, setItems] = useState<CampaignListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    const timer = setTimeout(() => {
      api
        .campaigns(q, onlyMine)
        .then((res) => {
          setItems(res);
          setError("");
        })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(timer);
  }, [q, onlyMine]);

  return (
    <section className="card">
      <div className="breadcrumbs">Campaigns</div>
      <div className="toolbar">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Поиск по названию или ID" />
        <label className="checkbox">
          <input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} />
          только <code>{prefix || "…"}*</code>
        </label>
      </div>
      {error && <div className="alert error">{error}</div>}
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 80 }}>ID</th>
            <th>Название</th>
            <th style={{ width: 120 }}>Alias</th>
            <th style={{ width: 100 }}>Статус</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.id} className="clickable" onClick={() => (window.location.hash = `#/campaigns/${c.id}`)}>
              <td>{c.id}</td>
              <td>
                <a href={`#/campaigns/${c.id}`}>{c.name}</a>
              </td>
              <td className="muted">{c.alias}</td>
              <td>{c.state}</td>
            </tr>
          ))}
          {loading && items.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                Загрузка из Keitaro…
              </td>
            </tr>
          )}
          {!loading && items.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                Кампаний не найдено
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
