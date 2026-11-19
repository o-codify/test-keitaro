from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.services.naming import parse_geo


def _as_utc(value: datetime | None) -> datetime | None:
    # SQLite теряет tzinfo — время всегда пишется в UTC
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]


class NamedItem(BaseModel):
    id: int
    name: str


class Defaults(BaseModel):
    domain_id: int | None
    group_id: int | None
    traffic_source_id: int | None


class Dictionaries(BaseModel):
    domains: list[NamedItem]
    groups: list[NamedItem]
    traffic_sources: list[NamedItem]
    defaults: Defaults
    campaign_prefix: str
    geo_redirect_url: str
    keitaro_url: str | None
    mock: bool


class OfferItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    state: str | None = None


# --- создаватор ---
class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geo: list[str]
    offer_id: int = Field(gt=0)
    domain_id: int | None = None
    group_id: int | None = None
    traffic_source_id: int | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Название не может быть пустым")
        return value

    @field_validator("geo", mode="before")
    @classmethod
    def _parse_geo(cls, value: Any) -> list[str]:
        return parse_geo(value)


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    alias: str | None
    state: str | None
    url: str | None
    domain_id: int | None
    group_id: int | None
    traffic_source_id: int | None
    created_by_app: bool
    geo: list[str] | None
    initial_offer_id: int | None
    created_at: UtcDatetime


# --- редактор ---
class CampaignListItem(BaseModel):
    id: int
    name: str
    alias: str | None = None
    state: str | None = None


class StreamOfferOut(BaseModel):
    offer_id: int
    name: str
    status: str  # active | removed
    share: int
    pinned: bool
    published_status: str | None
    published_share: int | None
    dirty: bool


class StreamOut(BaseModel):
    id: int
    name: str
    position: int
    type: str | None
    has_offers: bool
    dirty: bool
    share_total: int
    offers: list[StreamOfferOut]


class CampaignStreamsOut(BaseModel):
    id: int
    name: str
    alias: str | None
    state: str | None
    fetched_at: UtcDatetime | None
    keitaro_link: str | None
    streams: list[StreamOut]


class AddOffer(BaseModel):
    offer_id: int = Field(gt=0)


class PinOffer(BaseModel):
    pinned: bool
    share: int | None = Field(default=None, ge=0, le=100)


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int | None
    stream_id: int | None
    action: str
    offer_id: int | None
    details: dict[str, Any] | None
    created_at: UtcDatetime
