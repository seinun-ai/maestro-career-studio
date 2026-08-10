from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.application import Application
from app.models.referral import Referral
from app.schemas.referral import ReferralCreate, ReferralPatch, ReferralRead


router = APIRouter(prefix="/api/referrals", tags=["referrals"])


def _to_read(referral: Referral, applications_count: int) -> ReferralRead:
    return ReferralRead(
        id=referral.id,
        company=referral.company,
        careers_url=referral.careers_url,
        contact_name=referral.contact_name,
        notes=referral.notes,
        applications_count=applications_count,
        created_at=referral.created_at,
        updated_at=referral.updated_at,
    )


def _count_for(referral_id: UUID, db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(Application).where(Application.referral_id == referral_id)
    ) or 0


@router.get("", response_model=list[ReferralRead])
def list_referrals(db: Annotated[Session, Depends(get_db)]):
    rows = db.scalars(select(Referral).order_by(Referral.company)).all()
    counts = dict(
        db.execute(
            select(Application.referral_id, func.count())
            .where(Application.referral_id.is_not(None))
            .group_by(Application.referral_id)
        ).all()
    )
    return [_to_read(r, counts.get(r.id, 0)) for r in rows]


@router.post("", response_model=ReferralRead)
def create_referral(payload: ReferralCreate, db: Annotated[Session, Depends(get_db)]):
    referral = Referral(
        company=payload.company,
        careers_url=str(payload.careers_url),
        contact_name=payload.contact_name,
        notes=payload.notes,
    )
    db.add(referral)
    db.commit()
    db.refresh(referral)
    return _to_read(referral, 0)


@router.put("/{referral_id}", response_model=ReferralRead)
def update_referral(
    referral_id: UUID,
    payload: ReferralPatch,
    db: Annotated[Session, Depends(get_db)],
):
    referral = db.get(Referral, referral_id)
    if referral is None:
        raise HTTPException(status_code=404, detail="Referral not found")
    data = payload.model_dump(exclude_unset=True)
    if "careers_url" in data and data["careers_url"] is not None:
        data["careers_url"] = str(data["careers_url"])
    for key, value in data.items():
        setattr(referral, key, value)
    db.commit()
    db.refresh(referral)
    return _to_read(referral, _count_for(referral.id, db))


@router.delete("/{referral_id}", status_code=204)
def delete_referral(referral_id: UUID, db: Annotated[Session, Depends(get_db)]):
    referral = db.get(Referral, referral_id)
    if referral is None:
        raise HTTPException(status_code=404, detail="Referral not found")
    db.delete(referral)
    db.commit()
    return Response(status_code=204)
