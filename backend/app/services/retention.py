"""Account deletion / data retention policy (design §privacy_law).

Principle (한국 개인정보보호법): on withdrawal, personal data is purged
immediately — EXCEPT records with a legal/operational retention basis, which are
kept (pseudonymised) and purged after their retention period. The two are kept
strictly separate so the policy is never self-contradictory.

For PlanForge:
  - PURGE NOW: account PII (email, password), the user's project content (idea +
    generated sections) via soft delete, and subscriptions.
  - RETAIN (pseudonymised, user_id only): usage_logs (billing basis) and
    audit_logs (security/operational trail). These reference user_id but carry
    no email/credentials after purge.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Project, Subscription, User
from app.services import audit


def purge_user(db: Session, user: User) -> dict:
    """Apply the withdrawal policy. Returns a summary of purged vs retained."""
    now = datetime.now(timezone.utc)

    # 1) Immediately purge personal identifiers (irreversible anonymisation).
    user.email = f"deleted-user-{user.id}@deleted.invalid"
    user.password_hash = ""  # credentials destroyed
    user.status = "disabled"

    # 2) Soft-delete the user's project content (idea + sections) — recoverable
    #    window for accidental withdrawal, then hard-purged by a scheduled job.
    projects = db.scalars(
        select(Project).where(Project.user_id == user.id, Project.deleted_at.is_(None))
    ).all()
    for p in projects:
        p.deleted_at = now

    # 3) Cancel + soft-delete subscriptions.
    db.execute(
        update(Subscription)
        .where(Subscription.user_id == user.id, Subscription.deleted_at.is_(None))
        .values(status="canceled", deleted_at=now)
    )

    db.commit()

    summary = {
        "purged": ["account_pii(email,password)", f"projects({len(projects)}) soft-deleted", "subscriptions"],
        "retained": [
            "usage_logs (billing basis, pseudonymised)",
            "audit_logs (security/operational, pseudonymised)",
        ],
    }
    # 4) Record the withdrawal itself (this entry is part of the retained trail).
    audit.record(
        db,
        actor_user_id=user.id,
        action="account.delete",
        target_type="user",
        target_id=user.id,
        detail=summary,
    )
    return summary
