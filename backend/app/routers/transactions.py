import uuid
from datetime import datetime
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
        sandbox_org = models.Organization(id=org_id, name="Sunrise Property Group")
        db.add(sandbox_org)
        db.commit()


@router.get("/", response_model=List[schemas.TransactionSchema])
def read_transactions(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    direction: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    category: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)
    stmt = select(models.Transaction).where(models.Transaction.organization_id == organization_id)

    if direction:
        stmt = stmt.where(models.Transaction.direction.ilike(f"%{direction}%"))
    if status_filter:
        stmt = stmt.where(models.Transaction.status.ilike(f"%{status_filter}%"))
    if category:
        stmt = stmt.where(models.Transaction.category.ilike(f"%{category}%"))

    if search:
        search_terms = [
            models.Transaction.txn_id.ilike(f"%{search}%"),
            models.Transaction.ref_code.ilike(f"%{search}%"),
            models.Transaction.payer.ilike(f"%{search}%"),
            models.Transaction.category.ilike(f"%{search}%"),
            models.Transaction.property_location.ilike(f"%{search}%")
        ]
        stmt = stmt.where(or_(*search_terms))

    transactions = list(db.scalars(stmt).all())

    # Fallback seed if DB is empty
    if not transactions and not search and not direction and not status_filter:
        default_txn = models.Transaction(
            id=uuid.uuid4(),
            organization_id=organization_id,
            txn_id="TXN-2026-08-001",
            ref_code="#BDO-TRF8812",
            payer="Sunrise Property Management",
            property_location="Sunrise Residences",
            category="Owner Yield Disbursement",
            direction="OUTFLOW",
            gross_amount=-112500.00,
            channel="Bank Transfer (BDO)",
            status="Disbursed"
        )
        db.add(default_txn)
        db.commit()
        transactions = list(db.scalars(stmt).all())

    return transactions


@router.post("/", response_model=schemas.TransactionSchema, status_code=status.HTTP_201_CREATED)
def create_transaction(
    txn_in: schemas.TransactionCreate,
    db: Session = Depends(get_db)
):
    org_id = getattr(txn_in, "organization_id", DEFAULT_ORG_ID)
    ensure_sandbox_organization(db, org_id)

    txn_id = txn_in.txn_id or f"TXN-{datetime.now().year}-{datetime.now().strftime('%m')}-{str(uuid.uuid4())[:4].upper()}"

    txn_data = txn_in.dict(exclude_unset=True)
    if "id" not in txn_data or not txn_data["id"]:
        txn_data["id"] = uuid.uuid4()
    txn_data["organization_id"] = org_id
    txn_data["txn_id"] = txn_id

    db_txn = models.Transaction(**txn_data)
    db.add(db_txn)
    db.commit()
    db.refresh(db_txn)
    return db_txn


@router.get("/{txn_id}", response_model=schemas.TransactionSchema)
def get_transaction(
    txn_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(txn_id)
        stmt = select(models.Transaction).where(
            models.Transaction.id == parsed_uuid,
            models.Transaction.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Transaction).where(
            models.Transaction.txn_id == txn_id,
            models.Transaction.organization_id == organization_id
        )

    txn = db.scalar(stmt)
    if not txn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction record not found.")
    return txn


@router.put("/{txn_id}", response_model=schemas.TransactionSchema)
@router.patch("/{txn_id}", response_model=schemas.TransactionSchema)
def update_transaction(
    txn_id: str,
    txn_update: schemas.TransactionUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(txn_id)
        stmt = select(models.Transaction).where(
            models.Transaction.id == parsed_uuid,
            models.Transaction.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Transaction).where(
            models.Transaction.txn_id == txn_id,
            models.Transaction.organization_id == organization_id
        )

    db_txn = db.scalar(stmt)
    if not db_txn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction record not found.")

    update_data = txn_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(db_txn, field):
            setattr(db_txn, field, value)

    db.commit()
    db.refresh(db_txn)
    return db_txn


@router.delete("/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    txn_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(txn_id)
        stmt = select(models.Transaction).where(
            models.Transaction.id == parsed_uuid,
            models.Transaction.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Transaction).where(
            models.Transaction.txn_id == txn_id,
            models.Transaction.organization_id == organization_id
        )

    db_txn = db.scalar(stmt)
    if not db_txn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction record not found.")

    db.delete(db_txn)
    db.commit()
    return None