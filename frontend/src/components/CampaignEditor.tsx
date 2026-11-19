import { useCallback, useEffect, useState } from "react";
import { api, AuditEntry, CampaignStreams, Offer, Stream, StreamOffer } from "../api";
import OfferAutocomplete from "./OfferAutocomplete";

type Run = (key: string, fn: () => Promise<CampaignStreams>) => Promise<void>;

export default function CampaignEditor({ campaignId }: { campaignId: number }) {
  const [data, setData] = useState<CampaignStreams | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [log, setLog] = useState<AuditEntry[] | null>(null);

  const run: Run = useCallback(async (key, fn) => {
    setBusy(key);
    setError("");
    try {
      setData(await fn());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }, []);

  useEffect(() => {
    setData(null);
    run("load", () => api.streams(campaignId));
  }, [campaignId, run]);

  useEffect(() => {
    if (log !== null) api.log(campaignId).then(setLog).catch(() => undefined);
    // обновляем журнал после каждого действия, если он открыт
  }, [data]);

  return (
    <section className="card">
      <div className="breadcrumbs">
        <a href="#/campaigns">Campaigns</a> / <span>{data?.name ?? `#${campaignId}`}</span> / Keitaro Streams
      </div>

      <div className="toolbar">
        <button
          className="btn"
          disabled={busy !== null}
          onClick={() => run("fetch", () => api.fetchStreams(campaignId))}
        >
          {busy === "fetch" ? "Fetching…" : "⟳ Fetch streams from KT"}
        </button>
        {data?.keitaro_link && (
          <a className="btn" href={data.keitaro_link} target="_blank" rel="noreferrer">
            View in KT ↗
          </a>
        )}
        <button
          className="btn ghost"
          onClick={() => (log === null ? api.log(campaignId).then(setLog) : setLog(null))}
        >
          {log === null ? "Журнал действий" : "Скрыть журнал"}
        </button>
        {data?.fetched_at && (
          <span className="muted small push-right">
            Синхронизировано: {new Date(data.fetched_at).toLocaleString()}
          </span>
        )}
      </div>

      {error && <div className="alert error">{error}</div>}
      {busy === "load" && !data && <p className="muted">Загрузка…</p>}

      {data?.streams.map((stream) => (
        <StreamBlock key={stream.id} stream={stream} busy={busy} run={run} />
      ))}
      {data && data.streams.length === 0 && <p className="muted">В кампании нет потоков.</p>}

      {log && <AuditLog entries={log} />}
    </section>
  );
}

function StreamBlock({ stream, busy, run }: { stream: Stream; busy: string | null; run: Run }) {
  const [offer, setOffer] = useState<Offer | null>(null);
  const k = (action: string) => `${stream.id}:${action}`;
  const disabled = busy !== null;
  const activeIds = stream.offers.filter((o) => o.status === "active").map((o) => o.offer_id);

  const header = (
    <div className="stream-header">
      <div>
        <b>Stream: {stream.name}</b> <span className="muted">(#{stream.id})</span>
        <span className="muted small">
          {" "}
          position {stream.position}
          {stream.type ? ` · ${stream.type}` : ""}
        </span>
      </div>
      {stream.dirty && <span className="badge warn">не опубликовано</span>}
    </div>
  );

  if (!stream.has_offers) {
    return <div className="stream plain">{header}</div>;
  }

  return (
    <div className={`stream ${stream.dirty ? "dirty" : ""}`}>
      {header}
      {stream.dirty && (
        <div className="stream-actions">
          <button className="btn primary" disabled={disabled} onClick={() => run(k("push"), () => api.push(stream.id))}>
            {busy === k("push") ? "Pushing…" : "⇪ Push to KT"}
          </button>
          <button className="btn" disabled={disabled} onClick={() => run(k("cancel"), () => api.cancel(stream.id))}>
            ✕ Cancel
          </button>
        </div>
      )}

      <table className="table offers">
        <thead>
          <tr>
            <th>Offer</th>
            <th style={{ width: 150 }}>Share</th>
            <th style={{ width: 130 }}>Keitaro</th>
            <th style={{ width: 130 }} className="right">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {stream.offers.map((o) => (
            <OfferRow key={o.offer_id} streamId={stream.id} offer={o} busy={busy} run={run} />
          ))}
          {stream.offers.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                В потоке нет офферов
              </td>
            </tr>
          )}
        </tbody>
        <tfoot>
          <tr>
            <td className="right muted">Итого активных:</td>
            <td className={stream.share_total === 100 || activeIds.length === 0 ? "" : "error-text"}>
              <b>{stream.share_total}%</b>
              {stream.share_total !== 100 && activeIds.length > 0 && " — должно быть 100%"}
            </td>
            <td colSpan={2} />
          </tr>
        </tfoot>
      </table>

      <div className="add-row">
        <OfferAutocomplete value={offer} onChange={setOffer} excludeIds={activeIds} placeholder="Добавить оффер…" />
        <button
          className="btn"
          disabled={disabled || !offer}
          onClick={() =>
            offer &&
            run(k("add"), async () => {
              const res = await api.addOffer(stream.id, offer.id);
              setOffer(null);
              return res;
            })
          }
        >
          Add
        </button>
      </div>
    </div>
  );
}

function OfferRow({
  streamId,
  offer,
  busy,
  run,
}: {
  streamId: number;
  offer: StreamOffer;
  busy: string | null;
  run: Run;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(String(offer.share));
  const removed = offer.status === "removed";
  const disabled = busy !== null;
  const key = (a: string) => `${streamId}:${offer.offer_id}:${a}`;

  const saveShare = () => {
    const share = Number(value);
    if (!Number.isInteger(share) || share < 0 || share > 100) return;
    setEditing(false);
    run(key("pin"), () => api.pinOffer(streamId, offer.offer_id, true, share));
  };

  let published = "—";
  if (offer.published_status === "active") published = `${offer.published_share}%`;
  else if (offer.published_status === "removed") published = "удалён";
  else if (offer.published_status === null) published = "новый";

  return (
    <tr className={`${removed ? "removed" : ""} ${offer.dirty ? "changed" : ""}`}>
      <td>
        <span className="offer-id">#{offer.offer_id}</span> {offer.name}
        {removed && <span className="muted"> (removed)</span>}
      </td>
      <td>
        {editing ? (
          <span className="share-edit">
            <input
              autoFocus
              type="number"
              min={0}
              max={100}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") saveShare();
                if (e.key === "Escape") setEditing(false);
              }}
            />
            <button className="btn tiny" onClick={saveShare}>
              ✓
            </button>
          </span>
        ) : (
          <>
            <button
              className="link"
              disabled={removed || disabled}
              title="Задать вес вручную (он будет закреплён)"
              onClick={() => {
                setValue(String(offer.share));
                setEditing(true);
              }}
            >
              {offer.share}%
            </button>
            {!removed && (
              <button
                className={`pin ${offer.pinned ? "on" : ""}`}
                disabled={disabled}
                title={offer.pinned ? "Открепить вес" : "Закрепить вес — он не будет пересчитываться"}
                onClick={() => run(key("pin"), () => api.pinOffer(streamId, offer.offer_id, !offer.pinned))}
              >
                📌
              </button>
            )}
          </>
        )}
      </td>
      <td className="muted small">{published}</td>
      <td className="right">
        {removed ? (
          <button
            className="btn small"
            disabled={disabled}
            onClick={() => run(key("restore"), () => api.restoreOffer(streamId, offer.offer_id))}
          >
            ↺ Bring back
          </button>
        ) : (
          <button
            className="btn small danger"
            disabled={disabled}
            onClick={() => run(key("remove"), () => api.removeOffer(streamId, offer.offer_id))}
          >
            🗑 Remove
          </button>
        )}
      </td>
    </tr>
  );
}

const ACTION_LABELS: Record<string, string> = {
  create: "Создание",
  fetch: "Fetch из KT",
  add: "Добавлен оффер",
  remove: "Удалён оффер",
  restore: "Возвращён оффер",
  pin: "Закреплён вес",
  unpin: "Откреплён вес",
  push: "Push в KT",
  cancel: "Отмена изменений",
};

function AuditLog({ entries }: { entries: AuditEntry[] }) {
  return (
    <div className="audit">
      <h3>Журнал действий</h3>
      <table className="table compact">
        <tbody>
          {entries.map((e) => (
            <tr key={e.id}>
              <td className="muted small nowrap">{new Date(e.created_at).toLocaleString()}</td>
              <td>{ACTION_LABELS[e.action] ?? e.action}</td>
              <td className="muted small">
                {e.stream_id ? `stream #${e.stream_id}` : ""}
                {e.offer_id ? ` · offer #${e.offer_id}` : ""}
                {e.action === "pin" && e.details?.share !== undefined ? ` · ${String(e.details.share)}%` : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
