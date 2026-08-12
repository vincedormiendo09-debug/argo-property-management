import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()

# Default Organization UUID for local sandbox testing
DEFAULT_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in local DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="Default Sandbox Org")
        db.add(sandbox_org)
        db.commit()


def ensure_sandbox_lease(db: Session, org_id: uuid.UUID) -> models.Lease:
    """Ensures a full chain (Property -> Unit + Tenant -> Lease) exists for default seeding."""
    ensure_sandbox_organization(db, org_id)
    lease = db.scalar(select(models.Lease).where(models.Lease.organization_id == org_id))
    if not lease:
        # 1. Parent Property
        prop = db.scalar(select(models.Property).where(models.Property.organization_id == org_id))
        if not prop:
            prop = models.Property(
                id=uuid.uuid4(),
                organization_id=org_id,
                code="PROP-001",
                name="Sunrise Property",
                type="Residential",
                location="Parañaque, Metro Manila",
                status="Active"
            )
            db.add(prop)
            db.commit()
            db.refresh(prop)

        # 2. Parent Unit
        unit = db.scalar(select(models.Unit).where(models.Unit.organization_id == org_id))
        if not unit:
            unit = models.Unit(
                id=uuid.uuid4(),
                organization_id=org_id,
                property_id=prop.id,
                unit_no="Unit 101",
                type="1BR",
                rent=15000.0,
                status="OCCUPIED"
            )
            db.add(unit)
            db.commit()
            db.refresh(unit)

        # 3. Parent Tenant
        tenant = db.scalar(select(models.Tenant).where(models.Tenant.organization_id == org_id))
        if not tenant:
            tenant = models.Tenant(
                id=uuid.uuid4(),
                organization_id=org_id,
                name="Maria Santos",
                email="maria@example.com",
                phone="09171234567",
                status="Active"
            )
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

        # 4. Lease
        lease = models.Lease(
            id=uuid.uuid4(),
            organization_id=org_id,
            unit_id=unit.id,
            tenant_id=tenant.id,
            start_date="2026-01-01",
            end_date="2026-12-31",
            monthly_rent=15000.0,
            status="Active"
        )
        db.add(lease)
        db.commit()
        db.refresh(lease)

    return lease


# 1. GET /api/invoices/ - Read invoices scoped by organization_id
@router.get("/", response_model=List[schemas.InvoiceSchema])
def read_invoices(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    lease_id: Optional[uuid.UUID] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    stmt = select(models.Invoice).where(models.Invoice.organization_id == organization_id)
    if lease_id:
        stmt = stmt.where(models.Invoice.lease_id == lease_id)

    invoices = list(db.scalars(stmt).all())

    # Seed default sandbox invoice if database is empty for this org
    if not invoices and not lease_id:
        parent_lease = ensure_sandbox_lease(db, organization_id)
        default_invoices = [
            models.Invoice(
                id=uuid.uuid4(),
                organization_id=organization_id,
                lease_id=parent_lease.id,
                amount=15000.0,
                due_date="2026-09-05",
                status="Unpaid"
            )
        ]
        db.add_all(default_invoices)
        db.commit()
        invoices = list(db.scalars(stmt).all())

    return invoices


# 2. POST /api/invoices/ - Create a new invoice with lease validation
@router.post("/", response_model=schemas.InvoiceSchema, status_code=status.HTTP_201_CREATED)
def create_invoice(invoice_in: schemas.InvoiceCreate, db: Session = Depends(get_db)):
    ensure_sandbox_organization(db, invoice_in.organization_id)

    # Verify parent lease exists under this organization
    lease_stmt = select(models.Lease).where(
        models.Lease.id == invoice_in.lease_id,
        models.Lease.organization_id == invoice_in.organization_id
    )
    parent_lease = db.scalar(lease_stmt)
    if not parent_lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lease with ID '{invoice_in.lease_id}' not found in this organization."
        )

    db_invoice = models.Invoice(
        id=uuid.uuid4(),
        organization_id=invoice_in.organization_id,
        lease_id=invoice_in.lease_id,
        amount=invoice_in.amount,
        due_date=invoice_in.due_date,
        status=invoice_in.status,
        created_by=invoice_in.created_by
    )

    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)
    return db_invoice


# 3. GET /api/invoices/{invoice_id} - Fetch single invoice by UUID
@router.get("/{invoice_id}", response_model=schemas.InvoiceSchema)
def get_invoice(
    invoice_id: uuid.UUID,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    stmt = select(models.Invoice).where(
        models.Invoice.id == invoice_id,
        models.Invoice.organization_id == organization_id
    )
    invoice = db.scalar(stmt)

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found."
        )

    return invoice