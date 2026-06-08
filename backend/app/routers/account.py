"""Account self-service (design §privacy_law). Currently: withdrawal/deletion
with the immediate-purge vs legal-retention policy from services/retention.py."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User
from app.schemas import AccountDeleteRes
from app.services import retention

router = APIRouter(prefix="/api/v1/account", tags=["account"])


@router.delete("", response_model=AccountDeleteRes)
def delete_account(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AccountDeleteRes:
    """Withdraw: purge personal data now, keep legally-retained records."""
    summary = retention.purge_user(db, user)
    return AccountDeleteRes(**summary)
