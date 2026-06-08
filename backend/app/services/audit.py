"""Append-only audit logging helper. Every sensitive action (signup, generation
dispatch, job outcome) records who/what/when for a tamper-evident trail."""

import json

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    actor_user_id: int | None,
    action: str,
    target_type: str,
    target_id: str | int,
    detail: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            detail=json.dumps(detail, ensure_ascii=False) if detail else None,
        )
    )
    db.commit()
