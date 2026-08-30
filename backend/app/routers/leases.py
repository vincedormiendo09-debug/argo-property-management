import uuid
import logging
from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

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


# 1. GET /api/leases/ - Read real leases scoped by organization_id with filter options
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
        stmt = stmt.where(models.Lease.status.ilike(f"%{status_filter.strip()}%"))
        
    if search:
        search_term = search.strip()
        search_terms = []
        if hasattr(models.Lease, "lease_id"):
            search_terms.append(models.Lease.lease_id.ilike(f"%{search_term}%"))
        if hasattr(models.Lease, "status"):
            search_terms.append(models.Lease.status.ilike(f"%{search_term}%"))
        if search_terms:
            stmt = stmt.where(or_(*search_terms))

    return list(db.scalars(stmt).all())


# 2. POST /api/leases/ - Create a new lease with FK validation & unit occupancy update
@router.post("/", response_model=schemas.LeaseSchema, status_code=status.HTTP_201_CREATED)
def create_lease(lease_in: schemas.LeaseCreate, db: Session = Depends(get_db)):
    org_id = getattr(lease_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    # 1. Validate Unit exists under this organization
    unit_stmt = select(models.Unit).where(
        models.Unit.id == lease_in.unit_id,
        models.Unit.organization_id == org_id
    )
    unit = db.scalar(unit_stmt)
    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit with ID '{lease_in.unit_id}' was not found in this organization."
        )

    # 2. Validate Tenant exists under this organization
    tenant_stmt = select(models.Tenant).where(
        models.Tenant.id == lease_in.tenant_id,
        models.Tenant.organization_id == org_id
    )
    tenant = db.scalar(tenant_stmt)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID '{lease_in.tenant_id}' was not found in this organization."
        )

    lease_data = lease_in.model_dump(exclude_unset=True) if hasattr(lease_in, "model_dump") else lease_in.dict(exclude_unset=True)
    
    if "id" not in lease_data or not lease_data["id"]:
        lease_data["id"] = uuid.uuid4()
    if "organization_id" not in lease_data or not lease_data["organization_id"]:
        lease_data["organization_id"] = org_id
    if "lease_id" not in lease_data and hasattr(models.Lease, "lease_id"):
        lease_data["lease_id"] = f"LSE-{datetime.now().year}-{str(uuid.uuid4())[:6].upper()}"
    if "status" not in lease_data or not lease_data["status"]:
        lease_data["status"] = "ACTIVE"

    db_lease = models.Lease(**lease_data)
    db.add(db_lease)

    # Automatically set unit occupancy to OCCUPIED on active lease
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
                models.Lease.lease_id == lease_id.strip(),
                models.Lease.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid lease identifier format."
            )

    lease = db.scalar(stmt)
    if not lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found."
        )

    return lease


# 4. PUT / PATCH /api/leases/{lease_id} - Update lease status and sync unit occupancy
@router.put("/{lease_id}", response_model=schemas.LeaseSchema)
@router.patch("/{lease_id}", response_model=schemas.LeaseSchema)
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
                models.Lease.lease_id == lease_id.strip(),
                models.Lease.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid lease identifier format."
            )

    db_lease = db.scalar(stmt)
    if not db_lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found."
        )

    update_data = lease_update.model_dump(exclude_unset=True) if hasattr(lease_update, "model_dump") else lease_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        if hasattr(db_lease, field):
            setattr(db_lease, field, value)

    # Sync unit status on Move-In (ACTIVE) or Move-Out / Termination (ENDED, TERMINATED, EXPIRED)
    new_status = str(update_data.get("status", "")).upper()
    if new_status and db_lease.unit_id:
        unit = db.scalar(select(models.Unit).where(models.Unit.id == db_lease.unit_id))
        if unit:
            if new_status == "ACTIVE":
                unit.status = "OCCUPIED"
            elif new_status in ["ENDED", "TERMINATED", "EXPIRED", "CANCELLED"]:
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
                models.Lease.lease_id == lease_id.strip(),
                models.Lease.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid lease identifier format."
            )

    db_lease = db.scalar(stmt)
    if not db_lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found."
        )

    # Revert unit status to VACANT upon deleting lease
    if db_lease.unit_id:
        unit = db.scalar(select(models.Unit).where(models.Unit.id == db_lease.unit_id))
        if unit:
            unit.status = "VACANT"

    db.delete(db_lease)
    db.commit()
    return None