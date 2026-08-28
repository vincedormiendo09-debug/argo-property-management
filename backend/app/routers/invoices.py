import uuid
from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()

# Default Organization UUID matching schema.sql and seed.py
DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in local DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="Sunrise Property Group")
        db.add(sandbox_org)
        db.commit()


def ensure_sandbox_unit_and_tenant(db: Session, org_id: uuid.UUID):
    """Ensures Property, Building, Unit, and Tenant exist to link default leases."""
    ensure_sandbox_organization(db, org_id)

    # 1. Parent Property
    prop = db.scalar(select(models.Property).where(models.Property.organization_id == org_id))
    if not prop:
        prop = models.Property(
            id=uuid.uuid4(),
            organization_id=org_id,
            code="PROP-001",
            name="Sunrise Residences",
            type="Residential",
            location="Parañaque, Metro Manila",
            units_count=2,
            status="Active"
        )
        db.add(prop)
        db.commit()
        db.refresh(prop)

    # 2. Parent Building
    bldg = db.scalar(select(models.Building).where(models.Building.organization_id == org_id))
    if not bldg:
        bldg = models.Building(
            id=uuid.uuid4(),
            organization_id=org_id,
            property_id=prop.id,
            code="BLDG-A",
            name="Tower A",
            floors=10,
            total_units=50,
            status="ACTIVE"
        )
        db.add(bldg)
        db.commit()
        db.refresh(bldg)

    # 3. Parent Unit
    unit = db.scalar(select(models.Unit).where(models.Unit.organization_id == org_id))
    if not unit:
        unit = models.Unit(
            id=uuid.uuid4(),
            organization_id=org_id,
            property_id=prop.id,
            building_id=bldg.id,
            unit_no="Unit 101",
            type="1BR",
            floor="1st Floor",
            rent=15000.0,
            status="OCCUPIED",
            subtitle="Sunrise Residences • Tower A • Unit 101"
        )
        db.add(unit)
        db.commit()
        db.refresh(unit)

    # 4. Parent Tenant
    tenant = db.scalar(select(models.Tenant).where(models.Tenant.organization_id == org_id))
    if not tenant:
        tenant = models.Tenant(
            id=uuid.uuid4(),
            organization_id=org_id,
            tnt_id="TNT-1001",
            name="Maria Santos",
            email="maria.santos@tenant.ph",
            phone="09171234567",
            type="Individual",
            status="Active"
        )
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

    return unit, tenant


# 1. GET /api/invoices/ - Read invoices and collection records scoped by organization_id with filter options
@router.get("/", response_model=List[schemas.InvoiceSchema])
def read_invoices(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    lease_id: Optional[uuid.UUID] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    stmt = select(models.Invoice).where(models.Invoice.organization_id == organization_id)
    if lease_id:
        stmt = stmt.where(models.Invoice.lease_id == lease_id)
    if status_filter:
        # Support precise collection filters (Paid vs Unpaid/Overdue/Pending)
        if status_filter.upper() == "PAID":
            stmt = stmt.where(models.Invoice.status.ilike("paid"))
        elif status_filter.upper() in ("UNPAID", "OVERDUE", "PENDING"):
            stmt = stmt.where(or_(
                models.Invoice.status.ilike("unpaid"),
                models.Invoice.status.ilike("overdue"),
                models.Invoice.status.ilike("%pending%")
            ))
        else:
            stmt = stmt.where(models.Invoice.status.ilike(f"%{status_filter}%"))

    if search:
        search_terms = []
        if hasattr(models.Invoice, "invoice_id"):
            search_terms.append(models.Invoice.invoice_id.ilike(f"%{search}%"))
        if hasattr(models.Invoice, "type"):
            search_terms.append(models.Invoice.type.ilike(f"%{search}%"))
        if hasattr(models.Invoice, "ref_no"):
            search_terms.append(models.Invoice.ref_no.ilike(f"%{search}%"))
        if search_terms:
            stmt = stmt.where(or_(*search_terms))

    invoices = list(db.scalars(stmt).all())

    # Seed default sandbox invoice if DB is empty for this org
    if not invoices and not lease_id and not search and not status_filter:
        unit, tenant = ensure_sandbox_unit_and_tenant(db, organization_id)
        default_invoices = [
            models.Invoice(
                id=uuid.uuid4(),
                organization_id=organization_id,
                invoice_id="INV-2026-0801",
                type="Monthly Base Rent (Unit 101)",
                sub="Sunrise Residences • Tower A • Unit 101",
                category_type="Rent",
                due_date=date(2026, 8, 30),
                amount=15000.0,
                status="Paid",
                channel="GCash Verification (#GC-2026-0819)",
                ref_no="#GC-2026-0819"
            ),
            models.Invoice(
                id=uuid.uuid4(),
                organization_id=organization_id,
                invoice_id="INV-2026-0901",
                type="Monthly Base Rent (Unit 101)",
                sub="Sunrise Residences • Tower A • Unit 101",
                category_type="Rent",
                due_date=date(2026, 9, 30),
                amount=15000.0,
                status="Unpaid",
                channel="Pending Payment",
                ref_no=None
            )
        ]
        db.add_all(default_invoices)
        db.commit()
        invoices = list(db.scalars(stmt).all())

    return invoices


# 2. POST /api/invoices/ - Create a new billing invoice
@router.post("/", response_model=schemas.InvoiceSchema, status_code=status.HTTP_201_CREATED)
def create_invoice(invoice_in: schemas.InvoiceCreate, db: Session = Depends(get_db)):
    org_id = getattr(invoice_in, "organization_id", DEFAULT_ORG_ID)
    ensure_sandbox_organization(db, org_id)

    invoice_data = invoice_in.dict(exclude_unset=True)
    if "id" not in invoice_data or not invoice_data["id"]:
        invoice_data["id"] = uuid.uuid4()
    if "organization_id" not in invoice_data:
        invoice_data["organization_id"] = org_id
    if "invoice_id" not in invoice_data or not invoice_data["invoice_id"]:
        invoice_data["invoice_id"] = f"INV-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"

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
    try:
        parsed_uuid = uuid.UUID(invoice_id)
        stmt = select(models.Invoice).where(
            models.Invoice.id == parsed_uuid,
            models.Invoice.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Invoice).where(
            models.Invoice.invoice_id == invoice_id,
            models.Invoice.organization_id == organization_id
        )

    invoice = db.scalar(stmt)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found."
        )
    return invoice


# 4. PUT / PATCH /api/invoices/{invoice_id} - Update invoice payment status (Verified / Paid vs Overdue)
@router.put("/{invoice_id}", response_model=schemas.InvoiceSchema)
@router.patch("/{invoice_id}", response_model=schemas.InvoiceSchema)
def update_invoice(
    invoice_id: str,
    invoice_update: schemas.InvoiceUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(invoice_id)
        stmt = select(models.Invoice).where(
            models.Invoice.id == parsed_uuid,
            models.Invoice.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Invoice).where(
            models.Invoice.invoice_id == invoice_id,
            models.Invoice.organization_id == organization_id
        )

    db_invoice = db.scalar(stmt)
    if not db_invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found."
        )

    update_data = invoice_update.dict(exclude_unset=True)
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
    try:
        parsed_uuid = uuid.UUID(invoice_id)
        stmt = select(models.Invoice).where(
            models.Invoice.id == parsed_uuid,
            models.Invoice.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Invoice).where(
            models.Invoice.invoice_id == invoice_id,
            models.Invoice.organization_id == organization_id
        )

    db_invoice = db.scalar(stmt)
    if not db_invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found."
        )

    db.delete(db_invoice)
    db.commit()
    return None