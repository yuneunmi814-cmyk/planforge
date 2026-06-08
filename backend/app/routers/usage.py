"""Usage API (design §admin_flow 결제/사용량). A user can see their own usage and
current plan. Payment integration is intentionally out of scope."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Subscription, UsageLog, User
from app.schemas import UsageRes

router = APIRouter(prefix="/api/v1/usage", tags=["usage"])
settings = get_settings()


def current_plan(db: Session, user_id: int) -> str:
    sub = db.scalar(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status == "active",
            Subscription.deleted_at.is_(None),
        )
    )
    return sub.plan if sub else "free"


@router.get("", response_model=UsageRes)
def my_usage(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UsageRes:
    start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    base = select(UsageLog).where(UsageLog.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    today = (
        db.scalar(
            select(func.count())
            .select_from(UsageLog)
            .where(UsageLog.user_id == user.id, UsageLog.created_at >= start_of_day)
        )
        or 0
    )
    by_status = {
        s: int(c)
        for s, c in db.execute(
            select(UsageLog.status, func.count())
            .where(UsageLog.user_id == user.id)
            .group_by(UsageLog.status)
        ).all()
    }
    return UsageRes(
        plan=current_plan(db, user.id),
        limitPerMinute=settings.generate_rate_limit_per_minute,
        today=int(today),
        total=int(total),
        byStatus=by_status,
    )
