export type NamedItem = { id: number; name: string };

export type Dictionaries = {
  domains: NamedItem[];
  groups: NamedItem[];
  traffic_sources: NamedItem[];
  defaults: { domain_id: number | null; group_id: number | null; traffic_source_id: number | null };
  campaign_prefix: string;
  geo_redirect_url: string;
  keitaro_url: string | null;
  mock: boolean;
};

export type Offer = { id: number; name: string; state: string | null };

export type CreatedCampaign = {
  id: number;
  name: string;
  alias: string | null;
  url: string | null;
  geo: string[] | null;
  initial_offer_id: number | null;
  created_at: string;
};

export type CampaignListItem = { id: number; name: string; alias: string | null; state: string | null };

export type StreamOffer = {
  offer_id: number;
  name: string;
  status: "active" | "removed";
  share: number;
  pinned: boolean;
  published_status: string | null;
  published_share: number | null;
  dirty: boolean;
};

export type Stream = {
  id: number;
  name: string;
  position: number;
  type: string | null;
  has_offers: boolean;
  dirty: boolean;
  share_total: number;
  offers: StreamOffer[];
};

export type CampaignStreams = {
  id: number;
  name: string;
  alias: string | null;
  state: string | null;
  fetched_at: string | null;
  keitaro_link: string | null;
  streams: Stream[];
};

export type AuditEntry = {
  id: number;
  stream_id: number | null;
  action: string;
  offer_id: number | null;
  details: Record<string, unknown> | null;
  created_at: string;
};

export class ApiError extends Error {}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(formatDetail(data?.detail) || `HTTP ${res.status}`);
  }
  return data as T;
}

function formatDetail(detail: unknown): string {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // ошибки валидации FastAPI
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "";
        const msg = String(d.msg ?? "").replace(/^Value error, /, "");
        return field ? `${field}: ${msg}` : msg;
      })
      .join("; ");
  }
  return JSON.stringify(detail);
}

export const api = {
  dictionaries: () => request<Dictionaries>("GET", "/api/dictionaries"),
  offers: (q: string) => request<Offer[]>("GET", `/api/offers?q=${encodeURIComponent(q)}&limit=20`),
  createCampaign: (body: {
    name: string;
    geo: string;
    offer_id: number;
    domain_id: number | null;
    group_id: number | null;
    traffic_source_id: number | null;
  }) => request<CreatedCampaign>("POST", "/api/campaigns", body),
  createdCampaigns: () => request<CreatedCampaign[]>("GET", "/api/campaigns/created"),

  campaigns: (q: string, onlyMine: boolean) =>
    request<CampaignListItem[]>(
      "GET",
      `/api/campaigns?q=${encodeURIComponent(q)}&only_mine=${onlyMine}`,
    ),
  streams: (id: number) => request<CampaignStreams>("GET", `/api/campaigns/${id}/streams`),
  fetchStreams: (id: number) => request<CampaignStreams>("POST", `/api/campaigns/${id}/fetch`),
  addOffer: (streamId: number, offerId: number) =>
    request<CampaignStreams>("POST", `/api/streams/${streamId}/offers`, { offer_id: offerId }),
  removeOffer: (streamId: number, offerId: number) =>
    request<CampaignStreams>("POST", `/api/streams/${streamId}/offers/${offerId}/remove`),
  restoreOffer: (streamId: number, offerId: number) =>
    request<CampaignStreams>("POST", `/api/streams/${streamId}/offers/${offerId}/restore`),
  pinOffer: (streamId: number, offerId: number, pinned: boolean, share?: number) =>
    request<CampaignStreams>("POST", `/api/streams/${streamId}/offers/${offerId}/pin`, {
      pinned,
      share: share ?? null,
    }),
  push: (streamId: number) => request<CampaignStreams>("POST", `/api/streams/${streamId}/push`),
  cancel: (streamId: number) => request<CampaignStreams>("POST", `/api/streams/${streamId}/cancel`),
  log: (id: number) => request<AuditEntry[]>("GET", `/api/campaigns/${id}/log`),
};
