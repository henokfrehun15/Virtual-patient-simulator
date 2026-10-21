import uuid

from sqlalchemy.orm import Session as DbSession

from app.models.llm import AuditEvent


def record_audit_event(
    db: DbSession,
    *,
    user_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            meta=metadata,
        )
    )
