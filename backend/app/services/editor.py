"""Редактор офферов в потоках кампании.

Логика повторяет существующую обёртку:
- Fetch streams from KT — забираем потоки; потоки без офферов показываем
  только заголовком, их содержимое не разбираем.
- Add / Remove / Bring back — меняют только локальный черновик, веса
  пересчитываются, поток становится «жёлтым» (есть неопубликованные изменения).
- Push to KT — отправляет черновик в Keitaro. Cancel — откатывает черновик:
  добавленные привязки удаляются, остальные возвращаются к опубликованному.
- Офферы, исчезнувшие из Keitaro, при следующем fetch попадают в removed
  (серые, 0%) — их можно вернуть кнопкой Bring back.
- Закреплённые (pinned) веса не пересчитываются; остаток до 100% делится
  поровну между незакреплёнными активными офферами.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AppError
from app.keitaro import KeitaroClient, KeitaroError
from app.models import Campaign, Stream, StreamOffer
from app.schemas import CampaignStreamsOut, StreamOfferOut, StreamOut
from app.services import audit
from app.services.naming import distribute_evenly
from app.services.offers import offer_names, sync_offers

ACTIVE = "active"
REMOVED = "removed"


# ---------------------------------------------------------------- helpers
def ordered_offers(stream: Stream) -> list[StreamOffer]:
    """Активные сверху (в порядке добавления), удалённые внизу."""
    return sorted(stream.offers, key=lambda o: (o.status != ACTIVE, o.sort_order, o.id or 0))


def recalculate(stream: Stream) -> None:
    active = [o for o in ordered_offers(stream) if o.status == ACTIVE]
    pinned_total = sum(o.share for o in active if o.pinned)
    free = [o for o in active if not o.pinned]
    for offer, share in zip(free, distribute_evenly(len(free), max(0, 100 - pinned_total))):
        offer.share = share
    for offer in stream.offers:
        if offer.status != ACTIVE:
            offer.share = 0
            offer.pinned = False


def is_dirty(stream: Stream) -> bool:
    return any(o.is_dirty for o in stream.offers)


def share_total(stream: Stream) -> int:
    return sum(o.share for o in stream.offers if o.status == ACTIVE)


def _names(db: Session, client: KeitaroClient, needed: set[int]) -> dict[int, str]:
    names = offer_names(db)
    if needed - names.keys():
        sync_offers(db, client)
        names = offer_names(db)
    return names


def _apply_kt_offers(stream: Stream, kt_offers: list[dict[str, Any]], names: dict[int, str]) -> None:
    """Приводит привязки к состоянию Keitaro (и черновик, и опубликованное)."""
    by_offer = {o.offer_id: o for o in stream.offers}
    next_order = max((o.sort_order for o in stream.offers), default=0) + 1
    in_kt: set[int] = set()

    for item in kt_offers:
        offer_id = int(item["offer_id"])
        share = int(item.get("share") or 0)
        in_kt.add(offer_id)
        link = by_offer.get(offer_id)
        if link is None:
            link = StreamOffer(offer_id=offer_id, sort_order=next_order, pinned=False)
            next_order += 1
            stream.offers.append(link)
        link.offer_name = names.get(offer_id) or link.offer_name or f"Offer #{offer_id}"
        link.status = ACTIVE
        link.share = share
        link.published_status = ACTIVE
        link.published_share = share

    for link in list(stream.offers):
        if link.offer_id in in_kt:
            continue
        if link.published_status is None:
            # Неопубликованная привязка — Keitaro о ней не знает, выбрасываем
            stream.offers.remove(link)
        else:
            # Была в Keitaro, а теперь нет -> removed (можно вернуть)
            link.status = REMOVED
            link.share = 0
            link.pinned = False
            link.published_status = REMOVED
            link.published_share = 0


def _get_stream(db: Session, stream_id: int) -> Stream:
    stream = db.get(Stream, stream_id)
    if stream is None:
        raise AppError(f"Поток #{stream_id} не найден — сделайте Fetch streams", 404)
    if not stream.has_offers:
        raise AppError("В этом потоке нет офферов — он не редактируется", 400)
    return stream


def _get_link(stream: Stream, offer_id: int) -> StreamOffer:
    for link in stream.offers:
        if link.offer_id == offer_id:
            return link
    raise AppError(f"Оффера #{offer_id} нет в потоке #{stream.id}", 404)


# ---------------------------------------------------------------- fetch
def fetch_campaign(db: Session, client: KeitaroClient, campaign_id: int) -> Campaign:
    kt_campaign = client.get_campaign(campaign_id)
    kt_streams = client.list_streams(campaign_id)

    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        campaign = Campaign(id=campaign_id, name=kt_campaign["name"], created_by_app=False)
        db.add(campaign)
    campaign.name = kt_campaign["name"]
    campaign.alias = kt_campaign.get("alias")
    campaign.state = kt_campaign.get("state")
    campaign.domain_id = kt_campaign.get("domain_id")
    campaign.group_id = kt_campaign.get("group_id")
    campaign.traffic_source_id = kt_campaign.get("traffic_source_id")

    needed = {int(o["offer_id"]) for s in kt_streams for o in (s.get("offers") or [])}
    names = _names(db, client, needed)

    existing = {s.id: s for s in campaign.streams}
    seen: set[int] = set()
    for item in kt_streams:
        stream = existing.get(item["id"])
        if stream is None:
            stream = Stream(id=item["id"])
            campaign.streams.append(stream)
        seen.add(stream.id)
        stream.name = item.get("name") or f"Stream #{item['id']}"
        stream.position = item.get("position") or 0
        stream.type = item.get("type")
        stream.stream_schema = item.get("schema")
        kt_offers = item.get("offers") or []
        stream.has_offers = bool(kt_offers) or bool(stream.offers) or item.get("schema") == "landings"
        if stream.has_offers:
            _apply_kt_offers(stream, kt_offers, names)

    for stream in list(campaign.streams):
        if stream.id not in seen:
            campaign.streams.remove(stream)

    campaign.fetched_at = datetime.now(timezone.utc)
    audit.log(db, "fetch", campaign_id=campaign_id, streams=len(kt_streams))
    db.commit()
    db.refresh(campaign)
    return campaign


def get_or_fetch(db: Session, client: KeitaroClient, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.fetched_at is None:
        return fetch_campaign(db, client, campaign_id)
    return campaign


# ---------------------------------------------------------------- draft ops
def add_offer(db: Session, client: KeitaroClient, stream_id: int, offer_id: int) -> Stream:
    stream = _get_stream(db, stream_id)
    for link in stream.offers:
        if link.offer_id == offer_id:
            if link.status == ACTIVE:
                raise AppError(f"Оффер #{offer_id} уже есть в потоке", 409)
            return restore_offer(db, stream_id, offer_id)

    name = offer_names(db).get(offer_id)
    if name is None:
        try:
            name = client.get_offer(offer_id).get("name")
        except KeitaroError as exc:
            if exc.status_code == 404:
                raise AppError(f"Оффер #{offer_id} не найден в Keitaro", 404) from exc
            raise
    next_order = max((o.sort_order for o in stream.offers), default=0) + 1
    stream.offers.append(
        StreamOffer(
            offer_id=offer_id,
            offer_name=name or f"Offer #{offer_id}",
            sort_order=next_order,
            status=ACTIVE,
            share=0,
            pinned=False,
            published_status=None,
            published_share=None,
        )
    )
    recalculate(stream)
    audit.log(db, "add", campaign_id=stream.campaign_id, stream_id=stream.id, offer_id=offer_id)
    db.commit()
    return stream


def remove_offer(db: Session, stream_id: int, offer_id: int) -> Stream:
    stream = _get_stream(db, stream_id)
    link = _get_link(stream, offer_id)
    if link.status != ACTIVE:
        raise AppError("Оффер уже удалён", 409)
    link.status = REMOVED
    link.pinned = False
    recalculate(stream)
    audit.log(db, "remove", campaign_id=stream.campaign_id, stream_id=stream.id, offer_id=offer_id)
    db.commit()
    return stream


def restore_offer(db: Session, stream_id: int, offer_id: int) -> Stream:
    stream = _get_stream(db, stream_id)
    link = _get_link(stream, offer_id)
    if link.status == ACTIVE:
        raise AppError("Оффер и так активен", 409)
    link.status = ACTIVE
    recalculate(stream)
    audit.log(db, "restore", campaign_id=stream.campaign_id, stream_id=stream.id, offer_id=offer_id)
    db.commit()
    return stream


def pin_offer(db: Session, stream_id: int, offer_id: int, pinned: bool, share: int | None) -> Stream:
    stream = _get_stream(db, stream_id)
    link = _get_link(stream, offer_id)
    if link.status != ACTIVE:
        raise AppError("Закрепить можно только активный оффер", 409)

    if pinned:
        value = link.share if share is None else share
        other_pinned = sum(
            o.share for o in stream.offers if o.status == ACTIVE and o.pinned and o is not link
        )
        if other_pinned + value > 100:
            raise AppError(
                f"Сумма закреплённых весов превысит 100% ({other_pinned + value}%)", 400
            )
        link.share = value
    link.pinned = pinned
    recalculate(stream)
    audit.log(
        db,
        "pin" if pinned else "unpin",
        campaign_id=stream.campaign_id,
        stream_id=stream.id,
        offer_id=offer_id,
        share=link.share,
    )
    db.commit()
    return stream


def cancel(db: Session, stream_id: int) -> Stream:
    stream = _get_stream(db, stream_id)
    for link in list(stream.offers):
        if link.published_status is None:
            stream.offers.remove(link)  # привязка удаляется, оффер остаётся в справочнике
        else:
            link.status = link.published_status
            link.share = link.published_share or 0
            if link.status != ACTIVE:
                link.pinned = False
    audit.log(db, "cancel", campaign_id=stream.campaign_id, stream_id=stream.id)
    db.commit()
    return stream


def push(db: Session, client: KeitaroClient, stream_id: int) -> Stream:
    stream = _get_stream(db, stream_id)
    if not is_dirty(stream):
        return stream
    active = [o for o in ordered_offers(stream) if o.status == ACTIVE]
    total = sum(o.share for o in active)
    if active and total != 100:
        raise AppError(f"Сумма весов должна быть 100%, сейчас {total}%", 400)

    payload = {
        "offers": [{"offer_id": o.offer_id, "share": o.share, "state": "active"} for o in active]
    }
    kt_stream = client.update_stream(stream.id, payload)
    names = {o.offer_id: o.offer_name for o in stream.offers}
    _apply_kt_offers(stream, kt_stream.get("offers") or [], names)
    audit.log(db, "push", campaign_id=stream.campaign_id, stream_id=stream.id, offers=payload["offers"])
    db.commit()
    return stream


# ---------------------------------------------------------------- view
def keitaro_link(settings: Settings, campaign_id: int) -> str | None:
    if settings.keitaro_mock or not settings.keitaro_url:
        return None
    base = settings.keitaro_url.rstrip("/")
    base = base.removesuffix("/admin_api/v1")
    return f"{base}/admin/#!/campaign/{campaign_id}"


def stream_view(stream: Stream) -> StreamOut:
    offers = ordered_offers(stream) if stream.has_offers else []
    return StreamOut(
        id=stream.id,
        name=stream.name,
        position=stream.position,
        type=stream.type,
        has_offers=stream.has_offers,
        dirty=is_dirty(stream),
        share_total=share_total(stream),
        offers=[
            StreamOfferOut(
                offer_id=o.offer_id,
                name=o.offer_name,
                status=o.status,
                share=o.share,
                pinned=o.pinned,
                published_status=o.published_status,
                published_share=o.published_share,
                dirty=o.is_dirty,
            )
            for o in offers
        ],
    )


def campaign_view(campaign: Campaign, settings: Settings) -> CampaignStreamsOut:
    streams = sorted(campaign.streams, key=lambda s: (not s.has_offers, s.position, s.id))
    return CampaignStreamsOut(
        id=campaign.id,
        name=campaign.name,
        alias=campaign.alias,
        state=campaign.state,
        fetched_at=campaign.fetched_at,
        keitaro_link=keitaro_link(settings, campaign.id),
        streams=[stream_view(s) for s in streams],
    )
