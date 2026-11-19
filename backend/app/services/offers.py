from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.keitaro import KeitaroClient
from app.models import OfferCache


def sync_offers(db: Session, client: KeitaroClient) -> int:
    """Полностью перезаливает кэш офферов из Keitaro."""
    offers = client.list_offers()
    now = datetime.now(timezone.utc)
    ids = []
    for offer in offers:
        ids.append(offer["id"])
        db.merge(
            OfferCache(
                id=offer["id"],
                name=offer.get("name") or f"Offer #{offer['id']}",
                state=offer.get("state"),
                synced_at=now,
            )
        )
    stale = delete(OfferCache)
    if ids:
        stale = stale.where(OfferCache.id.not_in(ids))
    db.execute(stale)
    db.commit()
    return len(ids)


def ensure_fresh(db: Session, client: KeitaroClient, ttl_seconds: int) -> None:
    last = db.scalar(select(func.max(OfferCache.synced_at)))
    if last is not None and last.tzinfo is None:  # SQLite отдаёт naive datetime
        last = last.replace(tzinfo=timezone.utc)
    if last is None or datetime.now(timezone.utc) - last > timedelta(seconds=ttl_seconds):
        sync_offers(db, client)


def search_offers(db: Session, query: str, limit: int = 20) -> list[OfferCache]:
    stmt = select(OfferCache).where(OfferCache.state.is_distinct_from("deleted"))
    query = query.strip()
    if query:
        conditions = [OfferCache.name.ilike(f"%{query}%")]
        if query.isdigit():
            conditions.append(OfferCache.id == int(query))
        stmt = stmt.where(or_(*conditions))
    stmt = stmt.order_by(OfferCache.name).limit(limit)
    return list(db.scalars(stmt))


def offer_names(db: Session) -> dict[int, str]:
    return {row.id: row.name for row in db.scalars(select(OfferCache))}
