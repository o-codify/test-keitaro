import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, CreatedCampaign, Dictionaries, NamedItem, Offer } from "../api";
import OfferAutocomplete from "./OfferAutocomplete";

const GEO_RE = /^[A-Z]{2}$/;

function parseGeo(raw: string) {
  const codes = raw
    .split(/[\s,;]+/)
    .map((c) => c.trim().toUpperCase())
    .filter(Boolean);
  const unique = Array.from(new Set(codes));
  return { valid: unique.filter((c) => GEO_RE.test(c)), invalid: unique.filter((c) => !GEO_RE.test(c)) };
}

function withPrefix(name: string, prefix: string) {
  const trimmed = name.trim();
  if (!trimmed) return "";
  if (prefix && trimmed.toLowerCase().startsWith(prefix.toLowerCase())) {
    return prefix + trimmed.slice(prefix.length);
  }
  return prefix + trimmed;
}

export default function CreateCampaign({ dicts }: { dicts: Dictionaries | null }) {
  const [name, setName] = useState("");
  const [geo, setGeo] = useState("");
  const [offer, setOffer] = useState<Offer | null>(null);
  const [domainId, setDomainId] = useState<number | "">("");
  const [groupId, setGroupId] = useState<number | "">("");
  const [sourceId, setSourceId] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<CreatedCampaign | null>(null);
  const [history, setHistory] = useState<CreatedCampaign[]>([]);

  useEffect(() => {
    if (!dicts) return;
    setDomainId((v) => v || dicts.defaults.domain_id || dicts.domains[0]?.id || "");
    setGroupId((v) => v || dicts.defaults.group_id || dicts.groups[0]?.id || "");
    setSourceId((v) => v || dicts.defaults.traffic_source_id || dicts.traffic_sources[0]?.id || "");
  }, [dicts]);

  useEffect(() => {
    api.createdCampaigns().then(setHistory).catch(() => undefined);
  }, [created]);

  // Ключ без прав на источники трафика получает пустой список — тогда источник не обязателен
  const sourceItems = useMemo(() => {
    const items = dicts?.traffic_sources ?? [];
    const def = dicts?.defaults.traffic_source_id;
    return def && !items.some((i) => i.id === def) ? [...items, { id: def, name: `#${def} (из .env)` }] : items;
  }, [dicts]);
  const sourceOptional = !!dicts && sourceItems.length === 0;

  const prefix = dicts?.campaign_prefix ?? "";
  const finalName = withPrefix(name, prefix);
  const geoParsed = useMemo(() => parseGeo(geo), [geo]);
  const canSubmit =
    !busy && finalName && geoParsed.valid.length > 0 && geoParsed.invalid.length === 0 && offer && domainId && groupId && (sourceId || sourceOptional);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit || !offer) return;
    setBusy(true);
    setError("");
    setCreated(null);
    try {
      const result = await api.createCampaign({
        name,
        geo: geoParsed.valid.join(","),
        offer_id: offer.id,
        domain_id: domainId || null,
        group_id: groupId || null,
        traffic_source_id: sourceId || null,
      });
      setCreated(result);
      setName("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid-2">
      <section className="card">
        <h2>New campaign</h2>
        <form onSubmit={submit} className="form">
          <label>
            <span>Name</span>
            <div className="input-addon">
              <span className="addon">{prefix}</span>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="campaign1" />
            </div>
            {finalName && (
              <small className="muted">
                В Keitaro: <b>{finalName}</b>
              </small>
            )}
          </label>

          <label>
            <span>Geo</span>
            <input value={geo} onChange={(e) => setGeo(e.target.value)} placeholder="MX,AU,RO" />
            <div className="chips">
              {geoParsed.valid.map((c) => (
                <span key={c} className="chip">
                  {c}
                </span>
              ))}
              {geoParsed.invalid.map((c) => (
                <span key={c} className="chip bad" title="Нужен двухбуквенный код ISO 3166-1">
                  {c}
                </span>
              ))}
            </div>
          </label>

          <label>
            <span>Offer</span>
            <OfferAutocomplete value={offer} onChange={setOffer} />
          </label>

          <div className="row-3">
            <Select label="Домен" items={dicts?.domains} value={domainId} onChange={setDomainId} />
            <Select label="Группа" items={dicts?.groups} value={groupId} onChange={setGroupId} />
            <Select
              label="Источник"
              items={sourceItems}
              value={sourceId}
              onChange={setSourceId}
              emptyLabel={sourceOptional ? "нет доступных" : "—"}
            />
          </div>
          {sourceOptional && (
            <small className="muted">
              API-ключ не видит источники трафика (нет прав на TrafficSources) — кампания будет создана без
              источника. ID можно задать в <code>DEFAULT_TRAFFIC_SOURCE_ID</code>.
            </small>
          )}

          <div className="hint">
            Будут созданы 2 потока: <b>#1</b> — страны {geoParsed.valid.join(", ") || "…"} →{" "}
            {dicts?.geo_redirect_url ?? "Google"}; <b>#2</b> — все остальные → оффер{" "}
            {offer ? `#${offer.id}` : "…"} (100%).
          </div>

          {error && <div className="alert error">{error}</div>}

          <button className="btn primary wide" disabled={!canSubmit}>
            {busy ? "Создаём…" : "Create"}
          </button>
        </form>

        {created && (
          <div className="alert success">
            Кампания <b>{created.name}</b> создана (ID {created.id}).
            {created.url && (
              <div>
                Ссылка:{" "}
                <a href={created.url} target="_blank" rel="noreferrer">
                  {created.url}
                </a>
              </div>
            )}
            <div>
              <a href={`#/campaigns/${created.id}`}>Открыть в редакторе →</a>
            </div>
          </div>
        )}
      </section>

      <section className="card">
        <h2>Созданные кампании</h2>
        {history.length === 0 && <p className="muted">Пока ничего не создано.</p>}
        <table className="table compact">
          <tbody>
            {history.map((c) => (
              <tr key={c.id}>
                <td>
                  <a href={`#/campaigns/${c.id}`}>{c.name}</a>
                  <div className="muted small">
                    ID {c.id} · {c.geo?.join(", ")} · оффер #{c.initial_offer_id}
                  </div>
                </td>
                <td className="muted small nowrap">{new Date(c.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function Select({
  label,
  items,
  value,
  onChange,
  emptyLabel = "—",
}: {
  label: string;
  items?: NamedItem[];
  value: number | "";
  onChange: (v: number | "") => void;
  emptyLabel?: string;
}) {
  return (
    <label>
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")}>
        <option value="">{emptyLabel}</option>
        {items?.map((i) => (
          <option key={i.id} value={i.id}>
            {i.name}
          </option>
        ))}
      </select>
    </label>
  );
}
