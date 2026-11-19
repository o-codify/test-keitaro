from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(Base):
    """Локальная копия кампании Keitaro. id == id кампании в Keitaro."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str | None] = mapped_column(String(32))
    domain_id: Mapped[int | None] = mapped_column(Integer)
    group_id: Mapped[int | None] = mapped_column(Integer)
    traffic_source_id: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(String(512))

    # Заполнено, только если кампания создана через создаватор
    created_by_app: Mapped[bool] = mapped_column(Boolean, default=False)
    geo: Mapped[list[str] | None] = mapped_column(JSON)
    initial_offer_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    streams: Mapped[list["Stream"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="Stream.position",
    )


class Stream(Base):
    """Поток кампании. id == id потока в Keitaro."""

    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=0)
    type: Mapped[str | None] = mapped_column(String(32))
    stream_schema: Mapped[str | None] = mapped_column("schema", String(32))
    # Поток с офферами (schema=landings) — редактируемый; остальные показываем
    # только заголовком, содержимое не парсим (как в оригинальной обёртке).
    has_offers: Mapped[bool] = mapped_column(Boolean, default=False)

    campaign: Mapped[Campaign] = relationship(back_populates="streams")
    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream",
        cascade="all, delete-orphan",
        order_by="StreamOffer.sort_order",
    )


class StreamOffer(Base):
    """Привязка оффера к потоку.

    status/share — черновик (то, что видит пользователь в обёртке);
    published_status/published_share — то, что сейчас лежит в Keitaro.
    published_status IS NULL — привязка добавлена локально и ещё не запушена.
    Поток «жёлтый» (есть неопубликованные изменения), если хотя бы у одной
    привязки черновик отличается от опубликованного состояния.
    """

    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id", name="uq_stream_offer"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stream_id: Mapped[int] = mapped_column(
        ForeignKey("streams.id", ondelete="CASCADE"), index=True
    )
    offer_id: Mapped[int] = mapped_column(Integer)
    offer_name: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(16), default="active")  # active | removed
    share: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    published_status: Mapped[str | None] = mapped_column(String(16))
    published_share: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    stream: Mapped[Stream] = relationship(back_populates="offers")

    @property
    def is_dirty(self) -> bool:
        if self.status != self.published_status:
            return True
        return self.status == "active" and self.share != self.published_share


class OfferCache(Base):
    """Локальная копия справочника офферов Keitaro — для автокомплита."""

    __tablename__ = "offer_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(255), index=True)
    state: Mapped[str | None] = mapped_column(String(32))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """Журнал действий: create / fetch / add / remove / restore / pin / push / cancel."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int | None] = mapped_column(Integer, index=True)
    stream_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16))
    offer_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
