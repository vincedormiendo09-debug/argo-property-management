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


def ensure_sandbox_unit_and_tenant(db: Session, org_id: uuid.UUID):
    """Ensures a Property, Unit, and Tenant exist to link default leases."""
    ensure_sandbox_organization(db, org_id)

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

    return unit, tenant


# 1. GET /api/leases/ - Read leases scoped by organization_id
@router.get("/", response_model=List[schemas.LeaseSchema])
def read_leases(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    unit_id: Optional[uuid.UUID] = Query(default=None),
    tenant_id: Optional[uuid.UUID] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    stmt = select(models.Lease).where(models.Lease.organization_id == organization_id)
    if unit_id:
        stmt = stmt.where(models.Lease.unit_id == unit_id)
    if tenant_id:
        stmt = stmt.where(models.Lease.tenant_id == tenant_id)

    leases = list(db.scalars(stmt).all())

    # Seed default sandbox lease if DB is empty for this org
    if not leases and not unit_id and not tenant_id:
        unit, tenant = ensure_sandbox_unit_and_tenant(db, organization_id)
        default_leases = [
            models.Lease(
                id=uuid.uuid4(),
                organization_id=organization_id,
                unit_id=unit.id,
                tenant_id=tenant.id,
                start_date="2026-01-01",
                end_date="2026-12-31",
                monthly_rent=15000.0,
                status="Active"
            )
        ]
        db.add_all(default_leases)
        db.commit()
        leases = list(db.scalars(stmt).all())

    return leases


# 2. POST /api/leases/ - Create a new lease with FK validation
@router.post("/", response_model=schemas.LeaseSchema, status_code=status.HTTP_201_CREATED)
def create_lease(lease_in: schemas.LeaseCreate, db: Session = Depends(get_db)):
    ensure_sandbox_organization(db, lease_in.organization_id)

    # 1. Validate Unit exists under this org
    unit_stmt = select(models.Unit).where(
        models.Unit.id == lease_in.unit_id,
        models.Unit.organization_id == lease_in.organization_id
    )
    if not db.scalar(unit_stmt):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit with ID '{lease_in.unit_id}' not found in this organization."
        )

    # 2. Validate Tenant exists under this org
    tenant_stmt = select(models.Tenant).where(
        models.Tenant.id == lease_in.tenant_id,
        models.Tenant.organization_id == lease_in.organization_id
    )
    if not db.scalar(tenant_stmt):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID '{lease_in.tenant_id}' not found in this organization."
        )

    db_lease = models.Lease(
        id=uuid.uuid4(),
        organization_id=lease_in.organization_id,
        unit_id=lease_in.unit_id,
        tenant_id=lease_in.tenant_id,
        start_date=lease_in.start_date,
        end_date=lease_in.end_date,
        monthly_rent=lease_in.monthly_rent,
        status=lease_in.status,
        created_by=lease_in.created_by
    )

    db.add(db_lease)
    db.commit()
    db.refresh(db_lease)
    return db_lease


# 3. GET /api/leases/{lease_id} - Fetch single lease by UUID
@router.get("/{lease_id}", response_model=schemas.LeaseSchema)
def get_lease(
    lease_id: uuid.UUID,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    stmt = select(models.Lease).where(
        models.Lease.id == lease_id,
        models.Lease.organization_id == organization_id
    )
    lease = db.scalar(stmt)

    if not lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found."
        )

    return lease