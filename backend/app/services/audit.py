from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def log(
    db: Session,
    action: str,
    *,
    campaign_id: int | None = None,
    stream_id: int | None = None,
    offer_id: int | None = None,
    **details: Any,
) -> None:
    db.add(
        AuditLog(
            action=action,
            campaign_id=campaign_id,
            stream_id=stream_id,
            offer_id=offer_id,
            details=details or None,
        )
    )
