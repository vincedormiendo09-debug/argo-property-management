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


# 1. GET /api/leases/ - Read leases scoped by organization_id with filter options
@router.get("/", response_model=List[schemas.LeaseSchema])
def read_leases(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    unit_id: Optional[uuid.UUID] = Query(default=None),
    tenant_id: Optional[uuid.UUID] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    stmt = select(models.Lease).where(models.Lease.organization_id == organization_id)
    if unit_id:
        stmt = stmt.where(models.Lease.unit_id == unit_id)
    if tenant_id:
        stmt = stmt.where(models.Lease.tenant_id == tenant_id)
    if status_filter:
        stmt = stmt.where(models.Lease.status.ilike(f"%{status_filter}%"))
    if search:
        search_terms = []
        if hasattr(models.Lease, "lease_id"):
            search_terms.append(models.Lease.lease_id.ilike(f"%{search}%"))
        if hasattr(models.Lease, "status"):
            search_terms.append(models.Lease.status.ilike(f"%{search}%"))
        if search_terms:
            stmt = stmt.where(or_(*search_terms))

    leases = list(db.scalars(stmt).all())

    # Seed default sandbox lease if DB is empty for this org
    if not leases and not unit_id and not tenant_id and not search:
        unit, tenant = ensure_sandbox_unit_and_tenant(db, organization_id)
        default_leases = [
            models.Lease(
                id=uuid.uuid4(),
                organization_id=organization_id,
                lease_id="LSE-2026-001" if hasattr(models.Lease, "lease_id") else None,
                unit_id=unit.id,
                tenant_id=tenant.id,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                rent=15000.0 if hasattr(models.Lease, "rent") else None,
                deposit=30000.0 if hasattr(models.Lease, "deposit") else None,
                status="ACTIVE"
            )
        ]
        db.add_all(default_leases)
        db.commit()
        leases = list(db.scalars(stmt).all())

    return leases


# 2. POST /api/leases/ - Create a new lease with FK validation & unit occupancy update
@router.post("/", response_model=schemas.LeaseSchema, status_code=status.HTTP_201_CREATED)
def create_lease(lease_in: schemas.LeaseCreate, db: Session = Depends(get_db)):
    org_id = getattr(lease_in, "organization_id", DEFAULT_ORG_ID)
    ensure_sandbox_organization(db, org_id)

    # 1. Validate Unit exists under this org
    unit_stmt = select(models.Unit).where(
        models.Unit.id == lease_in.unit_id,
        models.Unit.organization_id == org_id
    )
    unit = db.scalar(unit_stmt)
    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit with ID '{lease_in.unit_id}' not found in this organization."
        )

    # 2. Validate Tenant exists under this org
    tenant_stmt = select(models.Tenant).where(
        models.Tenant.id == lease_in.tenant_id,
        models.Tenant.organization_id == org_id
    )
    tenant = db.scalar(tenant_stmt)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID '{lease_in.tenant_id}' not found in this organization."
        )

    lease_data = lease_in.dict(exclude_unset=True)
    if "id" not in lease_data or not lease_data["id"]:
        lease_data["id"] = uuid.uuid4()
    if "organization_id" not in lease_data:
        lease_data["organization_id"] = org_id
    if "lease_id" not in lease_data and hasattr(models.Lease, "lease_id"):
        lease_data["lease_id"] = f"LSE-{datetime.now().year}-{str(uuid.uuid4())[:6].upper()}"

    db_lease = models.Lease(**lease_data)
    db.add(db_lease)

    # Update unit status if lease is created as ACTIVE
    if str(lease_data.get("status", "")).upper() == "ACTIVE":
        unit.status = "OCCUPIED"

    db.commit()
    db.refresh(db_lease)
    return db_lease


# 3. GET /api/leases/{lease_id} - Fetch single lease by UUID or string code
@router.get("/{lease_id}", response_model=schemas.LeaseSchema)
def get_lease(
    lease_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(lease_id)
        stmt = select(models.Lease).where(
            models.Lease.id == parsed_uuid,
            models.Lease.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Lease, "lease_id"):
            stmt = select(models.Lease).where(
                models.Lease.lease_id == lease_id,
                models.Lease.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid lease identifier."
            )

    lease = db.scalar(stmt)

    if not lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found."
        )

    return lease


# 4. PUT /api/leases/{lease_id} - Update lease status (e.g., Activation / Move-Out)
@router.put("/{lease_id}", response_model=schemas.LeaseSchema)
def update_lease(
    lease_id: str,
    lease_update: schemas.LeaseUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(lease_id)
        stmt = select(models.Lease).where(
            models.Lease.id == parsed_uuid,
            models.Lease.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Lease, "lease_id"):
            stmt = select(models.Lease).where(
                models.Lease.lease_id == lease_id,
                models.Lease.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid lease identifier."
            )

    db_lease = db.scalar(stmt)
    if not db_lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found."
        )

    update_data = lease_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(db_lease, field):
            setattr(db_lease, field, value)

    # Sync unit status on Move-In (ACTIVE) or Move-Out (ENDED)
    new_status = str(update_data.get("status", "")).upper()
    if new_status and db_lease.unit_id:
        unit = db.scalar(select(models.Unit).where(models.Unit.id == db_lease.unit_id))
        if unit:
            if new_status == "ACTIVE":
                unit.status = "OCCUPIED"
            elif new_status == "ENDED":
                unit.status = "VACANT"

    db.commit()
    db.refresh(db_lease)
    return db_lease


# 5. DELETE /api/leases/{lease_id} - Terminate or delete lease record
@router.delete("/{lease_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lease(
    lease_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(lease_id)
        stmt = select(models.Lease).where(
            models.Lease.id == parsed_uuid,
            models.Lease.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Lease, "lease_id"):
            stmt = select(models.Lease).where(
                models.Lease.lease_id == lease_id,
                models.Lease.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid lease identifier."
            )

    db_lease = db.scalar(stmt)
    if not db_lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found."
        )

    # Free up unit status upon deleting lease
    if db_lease.unit_id:
        unit = db.scalar(select(models.Unit).where(models.Unit.id == db_lease.unit_id))
        if unit:
            unit.status = "VACANT"

    db.delete(db_lease)
    db.commit()
    return None