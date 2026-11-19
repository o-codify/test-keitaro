from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.keitaro import KeitaroClient, get_keitaro_client
from app.keitaro.mock_client import MockKeitaroClient
from app.errors import AppError
from app.models import AuditLog, Campaign
from app.schemas import (
    AddOffer,
    AuditOut,
    CampaignCreate,
    CampaignListItem,
    CampaignOut,
    CampaignStreamsOut,
    Defaults,
    Dictionaries,
    NamedItem,
    OfferItem,
    PinOffer,
)
from app.services import campaign_builder, editor
from app.services.offers import ensure_fresh, search_offers, sync_offers

router = APIRouter(prefix="/api")

Db = Depends(get_db)
Client = Depends(get_keitaro_client)
Conf = Depends(get_settings)


def _named(items: list[dict]) -> list[NamedItem]:
    return [NamedItem(id=i["id"], name=str(i.get("name") or i["id"])) for i in items]


# ------------------------------------------------------------ справочники
@router.get("/dictionaries", response_model=Dictionaries)
def dictionaries(client: KeitaroClient = Client, settings: Settings = Conf):
    return Dictionaries(
        domains=_named(client.list_domains()),
        groups=_named(client.list_campaign_groups()),
        traffic_sources=_named(campaign_builder.available_traffic_sources(client)),
        defaults=Defaults(
            domain_id=settings.default_domain_id,
            group_id=settings.default_group_id,
            traffic_source_id=settings.default_traffic_source_id,
        ),
        campaign_prefix=settings.campaign_prefix,
        geo_redirect_url=settings.geo_redirect_url,
        keitaro_url=None if settings.keitaro_mock else settings.keitaro_url or None,
        mock=settings.keitaro_mock,
    )


@router.get("/offers", response_model=list[OfferItem])
def offers(
    q: str = "",
    limit: int = Query(20, ge=1, le=100),
    db: Session = Db,
    client: KeitaroClient = Client,
    settings: Settings = Conf,
):
    ensure_fresh(db, client, settings.offer_cache_ttl_seconds)
    return search_offers(db, q, limit)


@router.post("/offers/sync")
def offers_sync(db: Session = Db, client: KeitaroClient = Client):
    return {"synced": sync_offers(db, client)}


# ------------------------------------------------------------ создаватор
@router.post("/campaigns", response_model=CampaignOut, status_code=201)
def create_campaign(
    data: CampaignCreate,
    db: Session = Db,
    client: KeitaroClient = Client,
    settings: Settings = Conf,
):
    return campaign_builder.create_campaign(db, client, settings, data)


@router.get("/campaigns/created", response_model=list[CampaignOut])
def created_campaigns(db: Session = Db):
    stmt = (
        select(Campaign)
        .where(Campaign.created_by_app.is_(True))
        .order_by(Campaign.created_at.desc())
        .limit(50)
    )
    return list(db.scalars(stmt))


# ------------------------------------------------------------ редактор
@router.get("/campaigns", response_model=list[CampaignListItem])
def list_campaigns(
    q: str = "",
    only_mine: bool = True,
    client: KeitaroClient = Client,
    settings: Settings = Conf,
):
    prefix = settings.campaign_prefix.lower()
    query = q.strip().lower()
    result = []
    for item in client.list_campaigns():
        name = str(item.get("name") or "")
        if item.get("state") == "deleted":
            continue
        if only_mine and prefix and not name.lower().startswith(prefix):
            continue
        if query and query not in name.lower() and query != str(item["id"]):
            continue
        result.append(
            CampaignListItem(id=item["id"], name=name, alias=item.get("alias"), state=item.get("state"))
        )
    return sorted(result, key=lambda c: c.id, reverse=True)


@router.get("/campaigns/{campaign_id}/streams", response_model=CampaignStreamsOut)
def campaign_streams(
    campaign_id: int, db: Session = Db, client: KeitaroClient = Client, settings: Settings = Conf
):
    return editor.campaign_view(editor.get_or_fetch(db, client, campaign_id), settings)


@router.post("/campaigns/{campaign_id}/fetch", response_model=CampaignStreamsOut)
def fetch_streams(
    campaign_id: int, db: Session = Db, client: KeitaroClient = Client, settings: Settings = Conf
):
    return editor.campaign_view(editor.fetch_campaign(db, client, campaign_id), settings)


def _view(db: Session, settings: Settings, campaign_id: int) -> CampaignStreamsOut:
    campaign = db.get(Campaign, campaign_id)
    db.refresh(campaign)
    return editor.campaign_view(campaign, settings)


@router.post("/streams/{stream_id}/offers", response_model=CampaignStreamsOut)
def add_offer(
    stream_id: int,
    data: AddOffer,
    db: Session = Db,
    client: KeitaroClient = Client,
    settings: Settings = Conf,
):
    stream = editor.add_offer(db, client, stream_id, data.offer_id)
    return _view(db, settings, stream.campaign_id)


@router.post("/streams/{stream_id}/offers/{offer_id}/remove", response_model=CampaignStreamsOut)
def remove_offer(stream_id: int, offer_id: int, db: Session = Db, settings: Settings = Conf):
    stream = editor.remove_offer(db, stream_id, offer_id)
    return _view(db, settings, stream.campaign_id)


@router.post("/streams/{stream_id}/offers/{offer_id}/restore", response_model=CampaignStreamsOut)
def restore_offer(stream_id: int, offer_id: int, db: Session = Db, settings: Settings = Conf):
    stream = editor.restore_offer(db, stream_id, offer_id)
    return _view(db, settings, stream.campaign_id)


@router.post("/streams/{stream_id}/offers/{offer_id}/pin", response_model=CampaignStreamsOut)
def pin_offer(
    stream_id: int, offer_id: int, data: PinOffer, db: Session = Db, settings: Settings = Conf
):
    stream = editor.pin_offer(db, stream_id, offer_id, data.pinned, data.share)
    return _view(db, settings, stream.campaign_id)


@router.post("/streams/{stream_id}/push", response_model=CampaignStreamsOut)
def push_stream(
    stream_id: int, db: Session = Db, client: KeitaroClient = Client, settings: Settings = Conf
):
    stream = editor.push(db, client, stream_id)
    return _view(db, settings, stream.campaign_id)


@router.post("/streams/{stream_id}/cancel", response_model=CampaignStreamsOut)
def cancel_stream(stream_id: int, db: Session = Db, settings: Settings = Conf):
    stream = editor.cancel(db, stream_id)
    return _view(db, settings, stream.campaign_id)


@router.get("/campaigns/{campaign_id}/log", response_model=list[AuditOut])
def campaign_log(campaign_id: int, db: Session = Db):
    stmt = (
        select(AuditLog)
        .where(AuditLog.campaign_id == campaign_id)
        .order_by(AuditLog.id.desc())
        .limit(100)
    )
    return list(db.scalars(stmt))


# ------------------------------------------------------------ mock-only
@router.post("/mock/streams/{stream_id}/offers/{offer_id}/delete")
def mock_delete_in_keitaro(stream_id: int, offer_id: int, client: KeitaroClient = Client):
    """Имитирует удаление оффера из потока прямо в интерфейсе Keitaro (только mock)."""
    if not isinstance(client, MockKeitaroClient):
        raise AppError("Доступно только в режиме KEITARO_MOCK=true", 404)
    stream = client.get_stream(stream_id)
    offers = [
        {"offer_id": o["offer_id"], "share": o["share"], "state": o["state"]}
        for o in stream["offers"]
        if o["offer_id"] != offer_id
    ]
    client.update_stream(stream_id, {"offers": offers})
    return {"ok": True, "offers_left": len(offers)}
