import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()

DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


@router.get("/", response_model=List[schemas.NotificationSchema])
def read_notifications(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    pov: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    category: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)
    stmt = select(models.Notification).where(models.Notification.organization_id == organization_id)

    # Strict role-scoped filtering (pov: admin, owner, client) at database query level
    raw_pov = "all"
    normalized_pov = "all"
    if pov and pov.lower() != "all":
        raw_pov = pov.lower().strip()
        normalized_pov = raw_pov
        if raw_pov in ("tenant", "client_pov"):
            normalized_pov = "client"
        elif raw_pov in ("property_owner", "investor"):
            normalized_pov = "owner"
        elif raw_pov in ("pm", "property_manager"):
            normalized_pov = "admin"

        stmt = stmt.where(or_(
            models.Notification.pov == normalized_pov,
            models.Notification.pov == raw_pov,
            models.Notification.pov == "all"
        ))

    if status_filter:
        stmt = stmt.where(models.Notification.status.ilike(f"%{status_filter}%"))
    if category:
        stmt = stmt.where(models.Notification.category.ilike(f"%{category}%"))

    notifications = list(db.scalars(stmt.order_by(models.Notification.created_at.desc())).all())

    # Fallback seed if DB is empty
    if not notifications:
        default_notifs = [
            models.Notification(
                id=uuid.uuid4(),
                organization_id=organization_id,
                pov="admin",
                category="maintenance",
                status="unread",
                is_read=False,
                title="Tenant Reported Unit Maintenance Issue",
                description="Tenant Maria Santos (Sunrise Residences • Unit 101) submitted a service request: 'AC Unit Leaking Water'.",
                property="Sunrise Residences • Unit 101",
                tag="Ticket TCK-2026-001",
                urgent=True
            ),
            models.Notification(
                id=uuid.uuid4(),
                organization_id=organization_id,
                pov="client",
                category="payment",
                status="unread",
                is_read=False,
                title="New Electricity Bill (Meralco) Issued",
                description="Your monthly electricity bill of ₱2,368.75 has been posted to your ledger.",
                property="Sunrise Residences • Unit 101",
                tag="Status: UNPAID",
                urgent=False
            ),
            models.Notification(
                id=uuid.uuid4(),
                organization_id=organization_id,
                pov="owner",
                category="asset",
                status="unread",
                is_read=False,
                title="Monthly Owner Statement Ready",
                description="Your equity disbursement statement for Sunrise Residences has been generated.",
                property="Sunrise Residences",
                tag="Statement: August 2026",
                urgent=False
            )
        ]
        db.add_all(default_notifs)
        db.commit()
        
        # Re-run query with role filter applied
        stmt = select(models.Notification).where(models.Notification.organization_id == organization_id)
        if pov and pov.lower() != "all":
            stmt = stmt.where(or_(
                models.Notification.pov == normalized_pov,
                models.Notification.pov == raw_pov,
                models.Notification.pov == "all"
            ))
        notifications = list(db.scalars(stmt.order_by(models.Notification.created_at.desc())).all())

    return notifications


@router.post("/", response_model=schemas.NotificationSchema, status_code=status.HTTP_201_CREATED)
def create_notification(
    notif_in: schemas.NotificationCreate,
    db: Session = Depends(get_db)
):
    org_id = getattr(notif_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    notif_data = notif_in.model_dump(exclude_unset=True) if hasattr(notif_in, "model_dump") else notif_in.dict(exclude_unset=True)
    
    if "id" not in notif_data or not notif_data["id"]:
        notif_data["id"] = uuid.uuid4()
    notif_data["organization_id"] = org_id

    db_notif = models.Notification(**notif_data)
    db.add(db_notif)
    db.commit()
    db.refresh(db_notif)
    return db_notif


@router.put("/{notification_id}/read", response_model=schemas.NotificationSchema)
def mark_notification_read(
    notification_id: uuid.UUID,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    stmt = select(models.Notification).where(
        models.Notification.id == notification_id,
        models.Notification.organization_id == organization_id
    )
    db_notif = db.scalar(stmt)
    if not db_notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")

    db_notif.status = "read"
    db_notif.is_read = True
    db.commit()
    db.refresh(db_notif)
    return db_notif


@router.put("/read-all/clear", status_code=status.HTTP_200_OK)
def mark_all_notifications_read(
    pov: str = Query(default="admin"),
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    stmt = select(models.Notification).where(
        models.Notification.organization_id == organization_id,
        or_(models.Notification.pov == pov.lower(), models.Notification.pov == "all")
    )
    notifs = list(db.scalars(stmt).all())
    for n in notifs:
        n.status = "read"
        n.is_read = True
    db.commit()
    return {"message": "All notifications marked as read."}


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notification_id: uuid.UUID,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    stmt = select(models.Notification).where(
        models.Notification.id == notification_id,
        models.Notification.organization_id == organization_id
    )
    db_notif = db.scalar(stmt)
    if not db_notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")

    db.delete(db_notif)
    db.commit()
    return None