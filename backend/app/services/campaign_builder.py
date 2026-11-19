"""Создаватор кампаний: кампания + 2 потока (гео -> Google, остальные -> оффер)."""

import logging
import re
import secrets

from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AppError
from app.keitaro import KeitaroClient, KeitaroError
from app.models import Campaign
from app.schemas import CampaignCreate
from app.services import audit
from app.services.editor import fetch_campaign
from app.services.naming import apply_prefix

logger = logging.getLogger(__name__)


def make_alias(name: str) -> str:
    """Keitaro требует alias (часть URL кампании): test_ivanov_x -> test-ivanov-x-3f9a1c."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "campaign"
    return f"{slug}-{secrets.token_hex(3)}"


def campaign_payload(name: str, domain_id: int, group_id: int, source_id: int | None) -> dict:
    payload = {
        "name": name,
        "alias": make_alias(name),
        "type": "position",  # ротация потоков «по позиции»
        "state": "active",
        "domain_id": domain_id,
        "group_id": group_id,
        "cost_type": "CPC",
        "cost_value": 0,
        "cost_currency": "USD",
        "cost_auto": True,  # стоимость «из параметра cost»
    }
    if source_id:
        payload["traffic_source_id"] = source_id
    return payload


def available_traffic_sources(client: KeitaroClient) -> list[dict]:
    """Источники, которые видит API-ключ. Без прав на TrafficSources Keitaro
    отдаёт пустой список (или 403) — тогда кампания создаётся без источника."""
    try:
        return client.list_traffic_sources() or []
    except KeitaroError as exc:
        if exc.status_code in (401, 403):
            return []
        raise


def geo_stream_payload(campaign_id: int, geo: list[str], redirect_url: str) -> dict:
    return {
        "campaign_id": campaign_id,
        "type": "regular",
        "name": f"Geo {','.join(geo)} -> Google",
        "position": 1,
        "state": "active",
        "schema": "redirect",
        "action_type": "http",
        "action_payload": redirect_url,
        "collect_clicks": True,
        "filter_or": False,
        "filters": [{"name": "country", "mode": "accept", "payload": geo}],
    }


def offer_stream_payload(campaign_id: int, offer_id: int) -> dict:
    return {
        "campaign_id": campaign_id,
        # «Запасной» поток: получает всех, кто не попал в обычные потоки
        "type": "default",
        "name": "Offers",
        "position": 2,
        "state": "active",
        "schema": "landings",
        "action_type": "http",
        "collect_clicks": True,
        "filters": [],
        "landings": [],
        "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
    }


def _campaign_url(client: KeitaroClient, domain_id: int, kt_campaign: dict) -> str | None:
    alias = kt_campaign.get("alias")
    if not alias:
        return None
    # Keitaro сам отдаёт адрес домена кампании: "domain": "https://example.com/"
    if kt_campaign.get("domain"):
        return f"{str(kt_campaign['domain']).rstrip('/')}/{alias}"
    for domain in client.list_domains():
        if domain["id"] == domain_id:
            host = str(domain["name"]).strip().rstrip("/")
            if not host.startswith(("http://", "https://")):
                host = f"https://{host}"
            return f"{host}/{alias}"
    return None


def create_campaign(
    db: Session, client: KeitaroClient, settings: Settings, data: CampaignCreate
) -> Campaign:
    domain_id = data.domain_id or settings.default_domain_id
    group_id = data.group_id or settings.default_group_id
    source_id = data.traffic_source_id or settings.default_traffic_source_id
    source_required = not source_id and bool(available_traffic_sources(client))
    missing = [
        label
        for label, value in (("домен", domain_id), ("группу", group_id))
        if not value
    ]
    if source_required:
        missing.append("источник")
    if missing:
        raise AppError(f"Выберите {', '.join(missing)}", status_code=422)

    try:
        name = apply_prefix(data.name, settings.campaign_prefix)
    except ValueError as exc:
        raise AppError(str(exc), status_code=422) from exc

    try:
        client.get_offer(data.offer_id)
    except KeitaroError as exc:
        if exc.status_code == 404:
            raise AppError(f"Оффер #{data.offer_id} не найден в Keitaro", 422) from exc
        raise

    kt_campaign = client.create_campaign(campaign_payload(name, domain_id, group_id, source_id))
    campaign_id = kt_campaign["id"]
    try:
        client.create_stream(geo_stream_payload(campaign_id, data.geo, settings.geo_redirect_url))
        client.create_stream(offer_stream_payload(campaign_id, data.offer_id))
    except Exception:
        # Не оставляем в трекере полусобранную кампанию
        try:
            client.delete_campaign(campaign_id)
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось откатить кампанию %s", campaign_id)
        raise

    campaign = db.get(Campaign, campaign_id) or Campaign(id=campaign_id, name=name)
    campaign.created_by_app = True
    campaign.geo = data.geo
    campaign.initial_offer_id = data.offer_id
    campaign.url = _campaign_url(client, domain_id, kt_campaign)
    db.add(campaign)
    audit.log(db, "create", campaign_id=campaign_id, offer_id=data.offer_id, geo=data.geo, name=name)
    db.flush()

    # Сразу подтягиваем потоки — кампания готова к редактированию
    return fetch_campaign(db, client, campaign_id)
