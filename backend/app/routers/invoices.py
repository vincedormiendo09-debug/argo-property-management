import uuid
import logging
from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from .. import models, schemas

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

# Default Organization UUID matching schema.sql and seed.py
DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


def find_invoice_by_identifier(db: Session, invoice_id: str, organization_id: uuid.UUID):
    """Robustly resolves an invoice by UUID or string invoice_id (e.g. 'INV-2026-0001')."""
    try:
        parsed_uuid = uuid.UUID(invoice_id)
        invoice = db.scalar(
            select(models.Invoice).where(
                models.Invoice.id == parsed_uuid,
                models.Invoice.organization_id == organization_id
            )
        )
        if invoice:
            return invoice
    except ValueError:
        pass

    if hasattr(models.Invoice, "invoice_id"):
        invoice = db.scalar(
            select(models.Invoice).where(
                models.Invoice.invoice_id.ilike(invoice_id.strip()),
                models.Invoice.organization_id == organization_id
            )
        )
        if invoice:
            return invoice

    return None


# 1. GET /api/invoices/ - Read real invoices and collection records scoped by organization_id
@router.get("/", response_model=List[schemas.InvoiceSchema])
def read_invoices(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    lease_id: Optional[uuid.UUID] = Query(default=None),
    tenant_id: Optional[uuid.UUID] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    stmt = select(models.Invoice).where(models.Invoice.organization_id == organization_id)
    
    if lease_id and hasattr(models.Invoice, "lease_id"):
        stmt = stmt.where(models.Invoice.lease_id == lease_id)
        
    if tenant_id and hasattr(models.Invoice, "tenant_id"):
        stmt = stmt.where(models.Invoice.tenant_id == tenant_id)

    if status_filter:
        s_clean = status_filter.strip().upper()
        if s_clean == "PAID":
            stmt = stmt.where(models.Invoice.status.ilike("paid"))
        elif s_clean in ("UNPAID", "OVERDUE"):
            stmt = stmt.where(or_(
                models.Invoice.status.ilike("unpaid"),
                models.Invoice.status.ilike("overdue")
            ))
        elif s_clean == "PENDING":
            stmt = stmt.where(models.Invoice.status.ilike("%pending%"))
        else:
            stmt = stmt.where(models.Invoice.status.ilike(f"%{status_filter.strip()}%"))

    if search:
        search_term = search.strip()
        search_terms = []
        if hasattr(models.Invoice, "invoice_id"):
            search_terms.append(models.Invoice.invoice_id.ilike(f"%{search_term}%"))
        if hasattr(models.Invoice, "type"):
            search_terms.append(models.Invoice.type.ilike(f"%{search_term}%"))
        if hasattr(models.Invoice, "ref_no"):
            search_terms.append(models.Invoice.ref_no.ilike(f"%{search_term}%"))
        if hasattr(models.Invoice, "sub"):
            search_terms.append(models.Invoice.sub.ilike(f"%{search_term}%"))
        if search_terms:
            stmt = stmt.where(or_(*search_terms))

    return list(db.scalars(stmt).all())


# 2. POST /api/invoices/ - Create a new billing invoice linked to Lease and Tenant
@router.post("/", response_model=schemas.InvoiceSchema, status_code=status.HTTP_201_CREATED)
def create_invoice(invoice_in: schemas.InvoiceCreate, db: Session = Depends(get_db)):
    org_id = getattr(invoice_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    invoice_data = invoice_in.model_dump(exclude_unset=True) if hasattr(invoice_in, "model_dump") else invoice_in.dict(exclude_unset=True)
    
    if "id" not in invoice_data or not invoice_data["id"]:
        invoice_data["id"] = uuid.uuid4()
    if "organization_id" not in invoice_data or not invoice_data["organization_id"]:
        invoice_data["organization_id"] = org_id
    if "invoice_id" not in invoice_data or not invoice_data["invoice_id"]:
        invoice_data["invoice_id"] = f"INV-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"
    if "status" not in invoice_data or not invoice_data["status"]:
        invoice_data["status"] = "Unpaid"

    # Validate lease if lease_id is provided
    lease_id = invoice_data.get("lease_id")
    if lease_id:
        lease = db.scalar(
            select(models.Lease).where(
                models.Lease.id == lease_id,
                models.Lease.organization_id == org_id
            )
        )
        if lease:
            # Auto-fill tenant_id if missing and supported
            if "tenant_id" not in invoice_data and hasattr(models.Invoice, "tenant_id"):
                invoice_data["tenant_id"] = lease.tenant_id

    db_invoice = models.Invoice(**invoice_data)
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)
    return db_invoice


# 3. GET /api/invoices/{invoice_id} - Fetch single invoice record
@router.get("/{invoice_id}", response_model=schemas.InvoiceSchema)
def get_invoice(
    invoice_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    invoice = find_invoice_by_identifier(db, invoice_id, organization_id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found."
        )
    return invoice


# 4. PUT / PATCH /api/invoices/{invoice_id} - Update invoice status (UNPAID -> PENDING -> PAID)
@router.put("/{invoice_id}", response_model=schemas.InvoiceSchema)
@router.patch("/{invoice_id}", response_model=schemas.InvoiceSchema)
def update_invoice(
    invoice_id: str,
    invoice_update: schemas.InvoiceUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    db_invoice = find_invoice_by_identifier(db, invoice_id, organization_id)
    if not db_invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found."
        )

    update_data = invoice_update.model_dump(exclude_unset=True) if hasattr(invoice_update, "model_dump") else invoice_update.dict(exclude_unset=True)

    # Normalize payment status casing
    if "status" in update_data and update_data["status"]:
        s = str(update_data["status"]).strip().upper()
        if s == "PAID":
            update_data["status"] = "Paid"
            if hasattr(db_invoice, "paid_at") and not getattr(db_invoice, "paid_at", None):
                setattr(db_invoice, "paid_at", datetime.now())
        elif s in ("PENDING", "PENDING VERIFICATION", "PENDING_VERIFICATION"):
            update_data["status"] = "Pending"
        elif s in ("UNPAID", "OVERDUE"):
            update_data["status"] = "Unpaid"

    for field, value in update_data.items():
        if hasattr(db_invoice, field):
            setattr(db_invoice, field, value)

    db.commit()
    db.refresh(db_invoice)
    return db_invoice


# 5. DELETE /api/invoices/{invoice_id} - Delete invoice record
@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(
    invoice_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    db_invoice = find_invoice_by_identifier(db, invoice_id, organization_id)
    if not db_invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found."
        )

    try:
        db.delete(db_invoice)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete invoice because it is tied to active ledger transactions."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting invoice: {str(e)}"
        )

    return None