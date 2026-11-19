"""In-memory имитация Keitaro Admin API.

Повторяет форму ответов настоящего API настолько, насколько это нужно
приложению. Данные живут в памяти процесса и сбрасываются при перезапуске.
"""

import copy
import secrets
import string
import threading
from datetime import datetime, timezone
from typing import Any

from app.keitaro.base import JSON
from app.keitaro.errors import KeitaroError

_OFFER_SEED = [
    "MX | Casino | Caliente",
    "MX | Betting | Codere",
    "AU | Casino | PlayAmo",
    "AU | Casino | Joe Fortune",
    "RO | Betting | Superbet",
    "RO | Casino | Netbet",
    "BR | Betting | Betano",
    "BR | Casino | Pixbet",
    "DE | Casino | Wildz",
    "PL | Betting | STS",
    "IN | Casino | Parimatch",
    "KZ | Betting | Olimpbet",
    "CA | Casino | Spin Palace",
    "US | Sweepstakes | Chumba",
    "ES | Casino | Codere ES",
    "IT | Betting | Snai",
    "TR | Casino | Mostbet",
    "PH | Casino | Megapari",
    "CL | Betting | Jugabet",
    "PE | Casino | Inkabet",
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _alias() -> str:
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(7))


class MockKeitaroClient:
    def __init__(self, *, campaign_prefix: str, redirect_url: str, seed_demo: bool = True):
        # Префикс и URL редиректа приходят из настроек (.env), чтобы демо-кампания
        # выглядела так же, как созданная через создаватор
        self._campaign_prefix = campaign_prefix
        self._redirect_url = redirect_url
        self._lock = threading.Lock()
        self._seq = {"campaign": 100, "stream": 1000, "stream_offer": 5000}
        self.domains: list[JSON] = [
            {"id": 1, "name": "in.posdk.xyz", "network_status": "active"},
            {"id": 2, "name": "go.trackdemo.net", "network_status": "active"},
        ]
        self.groups: list[JSON] = [
            {"id": 1, "name": "FORTESTS", "type": "campaigns"},
            {"id": 2, "name": "MAIN", "type": "campaigns"},
        ]
        self.traffic_sources: list[JSON] = [
            {"id": 1, "name": "FORTESTS", "state": "active"},
            {"id": 2, "name": "Facebook", "state": "active"},
            {"id": 3, "name": "Google Ads", "state": "active"},
        ]
        self.offers: dict[int, JSON] = {
            i: {"id": i, "name": name, "state": "active", "group_id": None}
            for i, name in enumerate(_OFFER_SEED, start=1)
        }
        self.campaigns: dict[int, JSON] = {}
        self.streams: dict[int, JSON] = {}
        if seed_demo:
            self._seed_demo_campaign()

    # --- служебное ---
    def _next(self, kind: str) -> int:
        self._seq[kind] += 1
        return self._seq[kind]

    def _seed_demo_campaign(self) -> None:
        campaign = self.create_campaign(
            {
                "name": f"{self._campaign_prefix}demo",
                "type": "position",
                "group_id": 1,
                "domain_id": 1,
                "traffic_source_id": 1,
                "cost_type": "CPC",
                "cost_auto": True,
            }
        )
        self.create_stream(
            {
                "campaign_id": campaign["id"],
                "type": "regular",
                "name": "Geo MX → Google",
                "position": 1,
                "schema": "redirect",
                "action_type": "http",
                "action_payload": self._redirect_url,
                "filters": [{"name": "country", "mode": "accept", "payload": ["MX"]}],
            }
        )
        self.create_stream(
            {
                "campaign_id": campaign["id"],
                "type": "default",
                "name": "Offers",
                "position": 2,
                "schema": "landings",
                "action_type": "http",
                "offers": [
                    {"offer_id": 1, "share": 34, "state": "active"},
                    {"offer_id": 2, "share": 33, "state": "active"},
                    {"offer_id": 3, "share": 33, "state": "active"},
                ],
            }
        )

    def _not_found(self, what: str, ident: int) -> KeitaroError:
        return KeitaroError(f"{what} #{ident} not found", status_code=404)

    def _build_offers(self, stream_id: int, offers: list[JSON]) -> list[JSON]:
        result = []
        for item in offers:
            offer_id = int(item["offer_id"])
            if offer_id not in self.offers:
                raise KeitaroError(f"Offer #{offer_id} not found", status_code=422)
            result.append(
                {
                    "id": self._next("stream_offer"),
                    "stream_id": stream_id,
                    "offer_id": offer_id,
                    "state": item.get("state", "active"),
                    "share": int(item.get("share", 100)),
                    "created_at": _now(),
                }
            )
        return result

    # --- справочники ---
    def list_domains(self) -> list[JSON]:
        return copy.deepcopy(self.domains)

    def list_campaign_groups(self) -> list[JSON]:
        return copy.deepcopy(self.groups)

    def list_traffic_sources(self) -> list[JSON]:
        return copy.deepcopy(self.traffic_sources)

    def list_offers(self) -> list[JSON]:
        return copy.deepcopy(list(self.offers.values()))

    def get_offer(self, offer_id: int) -> JSON:
        if offer_id not in self.offers:
            raise self._not_found("Offer", offer_id)
        return copy.deepcopy(self.offers[offer_id])

    # --- кампании ---
    def list_campaigns(self) -> list[JSON]:
        return copy.deepcopy([c for c in self.campaigns.values() if c["state"] != "deleted"])

    def get_campaign(self, campaign_id: int) -> JSON:
        campaign = self.campaigns.get(campaign_id)
        if not campaign or campaign["state"] == "deleted":
            raise self._not_found("Campaign", campaign_id)
        return copy.deepcopy(campaign)

    def create_campaign(self, payload: JSON) -> JSON:
        with self._lock:
            if not payload.get("name"):
                raise KeitaroError("name is required", status_code=422)
            for key, pool in (
                ("domain_id", self.domains),
                ("group_id", self.groups),
                ("traffic_source_id", self.traffic_sources),
            ):
                value = payload.get(key)
                if value is not None and not any(x["id"] == value for x in pool):
                    raise KeitaroError(f"{key}={value} not found", status_code=422)
            campaign_id = self._next("campaign")
            campaign: dict[str, Any] = {
                "id": campaign_id,
                "alias": payload.get("alias") or _alias(),
                "name": payload["name"],
                "type": payload.get("type", "position"),
                "state": payload.get("state", "active"),
                "group_id": payload.get("group_id"),
                "domain_id": payload.get("domain_id"),
                "traffic_source_id": payload.get("traffic_source_id") or 0,
                "cost_type": payload.get("cost_type", "CPC"),
                "cost_value": payload.get("cost_value", 0),
                "cost_currency": payload.get("cost_currency", "USD"),
                "cost_auto": payload.get("cost_auto", False),
                "created_at": _now(),
                "updated_at": _now(),
            }
            self.campaigns[campaign_id] = campaign
            return copy.deepcopy(campaign)

    def delete_campaign(self, campaign_id: int) -> None:
        with self._lock:
            campaign = self.campaigns.get(campaign_id)
            if not campaign:
                raise self._not_found("Campaign", campaign_id)
            campaign["state"] = "deleted"

    # --- потоки ---
    def list_streams(self, campaign_id: int) -> list[JSON]:
        self.get_campaign(campaign_id)
        streams = [s for s in self.streams.values() if s["campaign_id"] == campaign_id]
        return copy.deepcopy(sorted(streams, key=lambda s: s["position"]))

    def get_stream(self, stream_id: int) -> JSON:
        if stream_id not in self.streams:
            raise self._not_found("Stream", stream_id)
        return copy.deepcopy(self.streams[stream_id])

    def create_stream(self, payload: JSON) -> JSON:
        with self._lock:
            campaign_id = payload.get("campaign_id")
            if campaign_id not in self.campaigns:
                raise KeitaroError(f"Campaign #{campaign_id} not found", status_code=422)
            stream_id = self._next("stream")
            stream = {
                "id": stream_id,
                "campaign_id": campaign_id,
                "type": payload.get("type", "regular"),
                "name": payload.get("name", ""),
                "position": payload.get("position", 1),
                "weight": payload.get("weight", 100),
                "state": payload.get("state", "active"),
                "schema": payload.get("schema", "landings"),
                "action_type": payload.get("action_type", "http"),
                "action_payload": payload.get("action_payload"),
                "collect_clicks": payload.get("collect_clicks", True),
                "filter_or": payload.get("filter_or", False),
                "filters": copy.deepcopy(payload.get("filters", [])),
                "landings": [],
                "offers": [],
            }
            stream["offers"] = self._build_offers(stream_id, payload.get("offers", []))
            self.streams[stream_id] = stream
            return copy.deepcopy(stream)

    def update_stream(self, stream_id: int, payload: JSON) -> JSON:
        with self._lock:
            stream = self.streams.get(stream_id)
            if not stream:
                raise self._not_found("Stream", stream_id)
            for key, value in payload.items():
                if key == "offers":
                    stream["offers"] = self._build_offers(stream_id, value)
                elif key not in ("id", "campaign_id"):
                    stream[key] = copy.deepcopy(value)
            return copy.deepcopy(stream)
